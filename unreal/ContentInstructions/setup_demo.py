"""Run once with UE 5.6 -run=pythonscript -script=... -unattended.

Creates only /Game/GlassImpact assets and the independent GlassImpactDemo map.
Re-running replaces the generated material graphs/map; keep authored changes elsewhere.
"""
from pathlib import Path
import json
import unreal as ue

ROOT = Path(__file__).resolve().parents[1]
PKG = "/Game/GlassImpact"
ME = ue.MaterialEditingLibrary
AS = ue.EditorAssetLibrary
AT = ue.AssetToolsHelpers.get_asset_tools()
WHITE = ue.load_asset("/Engine/EngineResources/WhiteSquareTexture.WhiteSquareTexture")
REBUILD_MATERIALS = "-RebuildGlassMaterials" in ue.SystemLibrary.get_command_line()

def material(name, wire=False):
    path = PKG + "/" + name
    mat = ue.load_asset(path) if AS.does_asset_exist(path) else None
    if mat is None:
        mat = AT.create_asset(name, PKG, ue.Material, ue.MaterialFactoryNew())
    ME.delete_all_material_expressions(mat)
    mat.set_editor_property("two_sided", True)
    mat.set_editor_property("wireframe", wire)
    mat.set_editor_property("blend_mode", ue.BlendMode.BLEND_OPAQUE if wire else ue.BlendMode.BLEND_TRANSLUCENT)
    mat.set_editor_property("shading_model", ue.MaterialShadingModel.MSM_UNLIT if wire else ue.MaterialShadingModel.MSM_DEFAULT_LIT)
    if not wire:
        mat.set_editor_property("translucency_lighting_mode", ue.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
        mat.set_editor_property("refraction_method", ue.RefractionMode.RM_INDEX_OF_REFRACTION)
    return mat

def node(mat, cls, **props):
    n = ME.create_material_expression(mat, cls)
    for key, value in props.items():
        n.set_editor_property(key, value)
    return n

def scalar(mat, name, value):
    return node(mat, ue.MaterialExpressionScalarParameter, parameter_name=name, default_value=value)

def vector(mat, name, xyz):
    return node(mat, ue.MaterialExpressionVectorParameter, parameter_name=name, default_value=ue.LinearColor(*xyz))

def connect(a, b, pin, output=""):
    assert ME.connect_material_expressions(a, output, b, pin), "Cannot connect " + pin

def custom(mat, code, inputs, components):
    n = node(mat, ue.MaterialExpressionCustom, code=code,
             output_type=getattr(ue.CustomMaterialOutputType, "CMOT_FLOAT" + str(components)))
    arr = []
    for name in inputs:
        item = ue.CustomInput()
        item.set_editor_property("input_name", name)
        arr.append(item)
    n.set_editor_property("inputs", arr)
    for name, expr in inputs.items():
        connect(expr, n, name)
    return n

def prop(n, mat, name):
    assert ME.connect_material_property(n, "", getattr(ue.MaterialProperty, name)), name

def create_field_material(name, wire=False):
    existing=ue.load_asset(PKG+"/"+name) if AS.does_asset_exist(PKG+"/"+name) else None
    if existing is not None and not REBUILD_MATERIALS:
        return existing
    mat=material(name, wire)
    uv=node(mat, ue.MaterialExpressionTextureCoordinate, coordinate_index=0)
    alpha=scalar(mat,"FrameAlpha",0)
    textures={key:node(mat, ue.MaterialExpressionTextureObjectParameter, parameter_name=key, texture=WHITE)
              for key in ("StateA","StateB","DispA","DispB")}
    blend=(ROOT/"Shaders/FieldBlend.hlsl").read_text(encoding="utf-8")
    state=custom(mat,blend,{"A":textures["StateA"],"B":textures["StateB"],"UV":uv,"Alpha":alpha},4)
    disp=custom(mat,blend,{"A":textures["DispA"],"B":textures["DispB"],"UV":uv,"Alpha":alpha},4)
    minimum=vector(mat,"DisplacementMin",(0,0,0,0))
    span=vector(mat,"DisplacementSpan",(0,0,0,0))
    scale=scalar(mat,"DisplacementScale",1)
    local=custom(mat,(ROOT/"Shaders/Displacement.hlsl").read_text(encoding="utf-8"),
                 {"D":disp,"Minimum":minimum,"Span":span,"UV":uv,"Scale":scale},3)
    transform=node(mat, ue.MaterialExpressionTransform,
                   transform_source_type=ue.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_LOCAL,
                   transform_type=ue.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    connect(local, transform,"")
    prop(transform,mat,"MP_WORLD_POSITION_OFFSET")
    threshold=scalar(mat,"DamageThreshold",.35)
    intensity=scalar(mat,"CrackIntensity",1)
    crack=custom(mat,"float c = Threshold >= 0.999999 ? step(1.0,saturate(S.r)) : smoothstep(Threshold,min(1.0,Threshold+0.10),saturate(S.r)); return c * saturate(D.a) * max(0.0,Intensity);",
                 {"S":state,"D":disp,"Threshold":threshold,"Intensity":intensity},1)
    if wire:
        color=custom(mat,"return lerp(float3(0.04,0.6,0.8),float3(1,0.35,0.12),saturate(C))*1.6;",{"C":crack},3)
        prop(color,mat,"MP_EMISSIVE_COLOR")
    else:
        whitening=scalar(mat,"CrackWhiteningStrength",.9)
        refraction=scalar(mat,"RefractionStrength",.25)
        color=custom(mat,"return lerp(float3(0.065,0.13,0.15),float3(0.87,0.94,0.97),saturate(C*W));",{"C":crack,"W":whitening},3)
        opacity=custom(mat,"return lerp(0.07,0.78,saturate(C));",{"C":crack},1)
        rough=custom(mat,"return lerp(0.035,0.64,saturate(C));",{"C":crack},1)
        refr=custom(mat,"return 1.0 + max(0.0,R)*lerp(0.008,0.10,saturate(C));",{"C":crack,"R":refraction},1)
        glow=custom(mat,"return float3(0.50,0.64,0.69)*C*0.28;",{"C":crack},3)
        texel=vector(mat,"TexelSize",(1/512,1/512,0,0))
        coverage=custom(mat,"return saturate(D.a);",{"D":disp},1)
        normal=custom(mat,(ROOT/"Shaders/CrackNormal.hlsl").read_text(encoding="utf-8"),
                      {"A":textures["StateA"],"B":textures["StateB"],"Alpha":alpha,"UV":uv,"Texel":texel,
                       "Threshold":threshold,"Intensity":intensity,"Coverage":coverage},3)
        for expr,p in ((color,"MP_BASE_COLOR"),(opacity,"MP_OPACITY"),(rough,"MP_ROUGHNESS"),
                       (refr,"MP_REFRACTION"),(normal,"MP_NORMAL"),(glow,"MP_EMISSIVE_COLOR")):
            prop(expr,mat,p)
    ME.layout_material_expressions(mat)
    ME.recompile_material(mat)
    AS.save_loaded_asset(mat)
    return mat

def solid_material(name, color, emission=0):
    existing=ue.load_asset(PKG+"/"+name) if AS.does_asset_exist(PKG+"/"+name) else None
    if existing is not None and not REBUILD_MATERIALS:
        return existing
    m=material(name,True)
    m.set_editor_property("wireframe",False)
    c=node(m,ue.MaterialExpressionConstant3Vector,constant=ue.LinearColor(*color))
    prop(c,m,"MP_EMISSIVE_COLOR")
    ME.recompile_material(m)
    AS.save_loaded_asset(m)
    return m

def surface_master():
    path=PKG+"/M_StudioSurface"
    if AS.does_asset_exist(path) and not REBUILD_MATERIALS:
        return ue.load_asset(path)
    m=material("M_StudioSurface",False)
    m.set_editor_property("blend_mode",ue.BlendMode.BLEND_OPAQUE)
    base=vector(m,"Tint",(.075,.095,.12,1))
    prop(base,m,"MP_BASE_COLOR")
    prop(scalar(m,"Metallic",.35),m,"MP_METALLIC")
    prop(scalar(m,"Roughness",.36),m,"MP_ROUGHNESS")
    emit=custom(m,"return Color.rgb*Fill;",{"Color":base,"Fill":scalar(m,"Fill",.05)},3)
    prop(emit,m,"MP_EMISSIVE_COLOR")
    ME.layout_material_expressions(m); ME.recompile_material(m); AS.save_loaded_asset(m)
    return m


def surface_instance(name,parent,tint,metallic,roughness,fill=.05):
    path=PKG+"/"+name
    m=ue.load_asset(path) if AS.does_asset_exist(path) else AT.create_asset(name,PKG,ue.MaterialInstanceConstant,ue.MaterialInstanceConstantFactoryNew())
    ME.set_material_instance_parent(m,parent)
    ME.set_material_instance_vector_parameter_value(m,"Tint",ue.LinearColor(*tint))
    for key,value in (("Metallic",metallic),("Roughness",roughness),("Fill",fill)):
        ME.set_material_instance_scalar_parameter_value(m,key,value)
    ME.update_material_instance(m); AS.save_loaded_asset(m)
    return m


def studio_background():
    path=PKG+"/M_StudioBackdrop"
    if AS.does_asset_exist(path) and not REBUILD_MATERIALS:
        return ue.load_asset(path)
    m=material("M_StudioBackdrop",True)
    m.set_editor_property("wireframe",False)
    world=node(m,ue.MaterialExpressionWorldPosition)
    color=custom(m,"float h=saturate((P.z+10)/260.0); return lerp(float3(0.030,0.045,0.062),float3(0.009,0.016,0.028),h);",{"P":world},3)
    prop(color,m,"MP_EMISSIVE_COLOR")
    ME.recompile_material(m); AS.save_loaded_asset(m)
    return m


glass=create_field_material("M_GlassImpactStudio")
wire=create_field_material("M_GlassWire",True)
surface=surface_master()
frame=surface_instance("MI_FrameAnodized",surface,(.075,.105,.14,1),.45,.32,.12)
seal=surface_instance("MI_GasketRubber",surface,(.003,.005,.007,1),0,.85,.10)
trim=surface_instance("MI_BevelEdge",surface,(.20,.26,.31,1),.65,.26,.08)
base=surface_instance("MI_StandBase",surface,(.018,.027,.037,1),.20,.42,.12)
floor=surface_instance("MI_StudioFloor",surface,(.034,.047,.062,1),.0,.8,.30)
backdrop=studio_background()

levels=ue.get_editor_subsystem(ue.LevelEditorSubsystem)
actors=ue.get_editor_subsystem(ue.EditorActorSubsystem)
AS.make_directory(PKG+"/Maps")
world=ue.EditorLoadingAndSavingUtils.new_blank_map(False)
assert world is not None, "Could not create blank demo world"
cube=ue.load_asset("/Engine/BasicShapes/Cube.Cube")
cylinder=ue.load_asset("/Engine/BasicShapes/Cylinder.Cylinder")

def shape(name, loc, scale, mat, mesh=cube):
    a=actors.spawn_actor_from_class(ue.StaticMeshActor,ue.Vector(*loc))
    a.set_actor_label(name)
    comp=a.static_mesh_component
    comp.set_static_mesh(mesh); comp.set_material(0,mat)
    # Desired sizes are scale * 100 cm; do not assume every engine primitive
    # has the same source bounds (in particular Cylinder height).
    extent=mesh.get_bounds().box_extent
    a.set_actor_scale3d(ue.Vector(scale[0]*100/(2*extent.x),scale[1]*100/(2*extent.y),scale[2]*100/(2*extent.z)))
    comp.set_editor_property("cast_shadow",True)
    return a

# Unreal Roll=-90 makes +local Y -> world +Z and local normal -> -world Y.
# Always use named Rotator arguments: Python positional order differs from FRotator C++.
demo=actors.spawn_actor_from_class(ue.GlassImpactDemoActor,ue.Vector(0,0,75),ue.Rotator(pitch=0,yaw=0,roll=-90))
assert abs(demo.get_actor_rotation().roll+90)<0.001, "Glass must stand upright"
normal=ue.MathLibrary.transform_direction(demo.get_actor_transform(),ue.Vector(0,0,1))
up=ue.MathLibrary.transform_direction(demo.get_actor_transform(),ue.Vector(0,1,0))
assert normal.y < -.999 and up.z > .999, "Glass local basis does not match the front camera"
demo.set_actor_label("Glass specimen - SYNTHETIC field demo")
demo.set_editor_property("glass_material",glass)
demo.set_editor_property("wire_material",wire)
demo.set_editor_property("frame_material",frame)
demo.set_editor_property("gasket_material",seal)
demo.set_editor_property("trim_material",trim)
demo.glass_mesh.set_material(0,glass)
demo.frame_mesh.set_material(0,frame)
demo.gasket_mesh.set_material(0,seal)
demo.trim_mesh.set_material(0,trim)
demo.playback.set_editor_property("refraction_strength",.08)
# A short rounded base supports the frame. Post tops overlap the lower rail by
# 1 mm. The glass/frame/seal alignment itself is built inside ONE C++ actor.
shape("Elliptical instrument base",(0,1,2.25),(1.06,.40,.045),base,cylinder)
for x in (-38,38):
    shape("Support foot",(x,1,4.2),(.060,.060,.018),seal,cylinder)
    shape("Support column",(x,1,12.4),(.028,.028,.174),trim,cylinder)
# Unbounded-looking studio wall replaces the separate tilted-looking checker.
shape("Studio floor",(0,0,-1.5),(20,20,.03),floor)
shape("Continuous studio wall",(0,180,220),(20,.04,8),backdrop)

for name,rot,intensity,color in (
    ("Key soft direction",ue.Rotator(pitch=-32,yaw=55,roll=0),3.0,(.87,.94,1)),
    ("Fill soft direction",ue.Rotator(pitch=-18,yaw=-135,roll=0),1.5,(.65,.81,1)),
    ("Rim soft direction",ue.Rotator(pitch=-45,yaw=150,roll=0),2.5,(1,.86,.68))):
    light=actors.spawn_actor_from_class(ue.DirectionalLight,ue.Vector(0,0,250),rot)
    light.set_actor_label(name)
    light.light_component.set_editor_property("intensity",intensity)
    light.light_component.set_light_color(ue.LinearColor(*color,1))
    light.light_component.set_editor_property("light_source_angle",4.0)
    light.light_component.set_editor_property("cast_shadows",name.startswith("Key"))
camera=actors.spawn_actor_from_class(ue.CameraActor,ue.Vector(140,-425,112))
camera.set_actor_label("Editor camera - aimed at glass")
target=ue.Vector(0,0,67)
camera.set_actor_rotation(ue.MathLibrary.find_look_at_rotation(camera.get_actor_location(),target),False)
camera.camera_component.set_editor_property("field_of_view",38.0)
camera.camera_component.set_editor_property("constrain_aspect_ratio",False)
ue.get_editor_subsystem(ue.UnrealEditorSubsystem).set_level_viewport_camera_info(camera.get_actor_location(),camera.get_actor_rotation())
assert ue.EditorLoadingAndSavingUtils.save_map(world,PKG+"/Maps/GlassImpactDemo"), "Failed to save GlassImpactDemo"
saved_actors=actors.get_all_level_actors()
assert sum(isinstance(a,ue.GlassImpactDemoActor) for a in saved_actors)==1, "Demo actor missing or duplicated"
assert len(saved_actors)>=12, "Incomplete studio scene"
assert demo.frame_mesh.get_attach_parent()==demo.glass_mesh, "Frame is not attached to glass"
assert demo.gasket_mesh.get_attach_parent()==demo.glass_mesh, "Gasket is not attached to glass"
audit={"glass_size_cm":[100,100],"frame_aperture_cm":[98,98],"glass_overlap_per_edge_cm":1,
       "seal_aperture_cm":[97.6,97.6],"seal_local_z_cm":[-.03,.42],
       "shared_actor_transform":True,"world_front_normal":[normal.x,normal.y,normal.z],
       "world_local_y":[up.x,up.y,up.z],"camera_fov_degrees":38,
       "glass_center_world_cm":[0,0,75],"source_kind":"synthetic",
       "note":"Fixture geometry checks, not a new physics simulation."}
audit_path=ROOT.parent/"docs/fixture_geometry_audit.json"
audit_path.write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
AS.save_directory(PKG,only_if_is_dirty=False,recursive=True)
ue.log("GLASS_DEMO_ASSETS_CREATED")

using UnrealBuildTool;
public class GlassImpactEditorTarget : TargetRules
{
    public GlassImpactEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V5;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_6;
        ExtraModuleNames.Add("GlassImpactRuntime");
    }
}

using UnrealBuildTool;
public class GlassImpactRuntime : ModuleRules
{
    public GlassImpactRuntime(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] {"Core", "CoreUObject", "Engine", "InputCore", "Json", "ProceduralMeshComponent", "Niagara", "RenderCore", "RHI"});
    }
}

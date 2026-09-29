using UnrealBuildTool;

public class AtelierFX : ModuleRules
{
    public AtelierFX(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "DeveloperSettings", "ProceduralMeshComponent" });
    }
}

using UnrealBuildTool;

public class AtelierSkate : ModuleRules
{
    public AtelierSkate(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "DeveloperSettings" });
        PrivateDependencyModuleNames.AddRange(new string[] { "Json", "AtelierCore", "AtelierFX" });
    }
}

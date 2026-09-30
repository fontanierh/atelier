using UnrealBuildTool;

public class AtelierSkate : ModuleRules
{
    public AtelierSkate(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        // Native solver files retain private arithmetic helpers and translation-unit FP settings.
        bUseUnity = false;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "DeveloperSettings" });
        PrivateDependencyModuleNames.AddRange(new string[] { "Json", "AtelierCore", "AtelierFX", "RenderCore", "RHI", "AnimationCore", "PhysicsCore" });
    }
}

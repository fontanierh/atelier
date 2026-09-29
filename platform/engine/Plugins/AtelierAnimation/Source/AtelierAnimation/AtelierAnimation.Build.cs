using UnrealBuildTool;

public class AtelierAnimation : ModuleRules
{
    public AtelierAnimation(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "AnimGraphRuntime", "AnimationCore" });
    }
}

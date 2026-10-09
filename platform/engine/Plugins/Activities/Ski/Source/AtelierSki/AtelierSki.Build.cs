using UnrealBuildTool;

public class AtelierSki : ModuleRules
{
    public AtelierSki(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        // The native simulation's translation units each keep private helpers of the same names.
        bUseUnity = false;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "DeveloperSettings", "ProceduralMeshComponent" });
        PrivateDependencyModuleNames.AddRange(new string[] { "AnimationCore", "AnimGraphRuntime", "PhysicsCore", "PhysicsControl" });
    }
}

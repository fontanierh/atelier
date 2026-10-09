using UnrealBuildTool;

public class AtelierSkate : ModuleRules
{
    public AtelierSkate(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        // Simulation solver files retain private arithmetic helpers and translation-unit FP settings.
        bUseUnity = false;
        // Keep the same IEEE arithmetic used by the independent simulation proofs.
        // Explicit std::fma calls supply only the original fused operations.
        FPSemantics = FPSemanticsMode.Precise;
        // The routines keep scoped variable names that shadow. Keep shadow
        // diagnostics visible without rejecting the simulation code.
        CppCompileWarningSettings.ShadowVariableWarningLevel = WarningLevel.Warning;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "DeveloperSettings" });
        PrivateDependencyModuleNames.AddRange(new string[] { "Json", "AtelierCore", "AtelierFX", "RenderCore", "RHI", "AnimationCore", "AnimGraphRuntime", "PhysicsCore", "PhysicsControl", "Chaos" });
        if (Target.bBuildEditor) PrivateDependencyModuleNames.Add("AssetRegistry");
        // The 120 Hz flick reading polls the controller off the game thread (SkatePadReader.cpp).
        if (Target.Platform == UnrealTargetPlatform.Mac) PublicFrameworks.Add("GameController");
    }
}

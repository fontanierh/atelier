using UnrealBuildTool;

public class AtelierSkate : ModuleRules
{
    public AtelierSkate(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        // Native solver files retain private arithmetic helpers and translation-unit FP settings.
        bUseUnity = false;
        // Keep the same IEEE arithmetic used by the independent native proofs.
        // Explicit std::fma calls supply only the original fused operations.
        FPSemantics = FPSemanticsMode.Precise;
        // The translated routines retain scoped source variable names. Keep
        // shadow diagnostics visible without rejecting the recovered code.
        CppCompileWarningSettings.ShadowVariableWarningLevel = WarningLevel.Warning;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "DeveloperSettings" });
        PrivateDependencyModuleNames.AddRange(new string[] { "Json", "AtelierCore", "AtelierFX", "RenderCore", "RHI", "AnimationCore", "PhysicsCore" });
    }
}

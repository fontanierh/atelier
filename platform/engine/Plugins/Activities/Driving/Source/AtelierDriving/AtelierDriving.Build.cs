using UnrealBuildTool;

public class AtelierDriving : ModuleRules
{
    public AtelierDriving(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        // The simulation solver keeps private arithmetic helpers and translation-unit FP settings.
        bUseUnity = false;
        // Keep the same IEEE arithmetic as the independent simulation proofs.
        FPSemantics = FPSemanticsMode.Precise;
        CppCompileWarningSettings.ShadowVariableWarningLevel = WarningLevel.Warning;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
        PrivateDependencyModuleNames.AddRange(new string[] { "InputCore" });
    }
}

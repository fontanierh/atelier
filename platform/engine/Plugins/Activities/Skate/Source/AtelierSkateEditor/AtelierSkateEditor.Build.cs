using UnrealBuildTool;

public class AtelierSkateEditor : ModuleRules
{
    public AtelierSkateEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        bUseUnity = false;
        FPSemantics = FPSemanticsMode.Precise;
        PublicDependencyModuleNames.AddRange(new string[] {
            "Core", "CoreUObject", "Engine", "AtelierSkate", "AnimGraph", "BlueprintGraph"
        });
        PrivateDependencyModuleNames.AddRange(new string[] {
            "UnrealEd", "Json", "AssetRegistry", "AssetTools", "AnimGraphRuntime",
            "RenderCore", "RHI", "PhysicsCore"
        });
        PrivateIncludePaths.Add(System.IO.Path.Combine(ModuleDirectory, "../AtelierSkate/Private"));
    }
}

using UnrealBuildTool;

// Preparation owns derived foliage geometry; raw import certification cannot depend on it.
public class YorimichiFoliagePreparation : ModuleRules
{
    public YorimichiFoliagePreparation(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PrivateIncludePaths.Add(ModuleDirectory);
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
        PrivateDependencyModuleNames.AddRange(new string[] { "UnrealEd", "AssetRegistry", "RenderCore", "RHI",
            "MeshDescription", "StaticMeshDescription", "ImageCore", "Json" });
    }
}

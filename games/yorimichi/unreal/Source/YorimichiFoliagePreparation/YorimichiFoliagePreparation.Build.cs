using UnrealBuildTool;

// Saved foliage geometry is prepared independently of gameplay and raw import certification.
public class YorimichiFoliagePreparation : ModuleRules
{
    public YorimichiFoliagePreparation(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PrivateIncludePaths.Add(ModuleDirectory);
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
        PrivateDependencyModuleNames.AddRange(new string[] { "UnrealEd", "AssetRegistry", "RenderCore", "RHI",
            "MeshDescription", "StaticMeshDescription", "ImageCore", "Json", "Chaos",
            "MeshReductionInterface", "MeshUtilitiesCommon" });
    }
}

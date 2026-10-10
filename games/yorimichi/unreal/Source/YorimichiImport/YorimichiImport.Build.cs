using UnrealBuildTool;

// The editor code that content imports run (Scripts/import_modori.py, import_megapark.py, import_communitypark.py).
// Apart from the game module so their build steps depend on exactly this code (games/yorimichi/build.py, IMPORT_CODE).
public class YorimichiImport : ModuleRules
{
    public YorimichiImport(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PrivateIncludePaths.Add(ModuleDirectory);
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
        PrivateDependencyModuleNames.AddRange(new string[] { "UnrealEd", "AssetRegistry", "RenderCore", "RHI", "ChaosCloth",
            "ClothingSystemEditorInterface", "ClothingSystemRuntimeCommon", "ClothingSystemRuntimeInterface", "SkeletalMeshEditor" });
    }
}

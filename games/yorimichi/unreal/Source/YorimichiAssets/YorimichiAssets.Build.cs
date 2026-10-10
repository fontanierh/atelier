using UnrealBuildTool;

// The types that content imports save in assets (Scripts/import_modori.py, import_megapark.py): data with no gameplay,
// apart from the game module so their imports depend on exactly this code (games/yorimichi/build.py, SAVED_TYPES).
public class YorimichiAssets : ModuleRules
{
    public YorimichiAssets(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
    }
}

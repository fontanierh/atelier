using UnrealBuildTool;
using System.IO;

public class AtelierBuildWorker : ModuleRules
{
    public AtelierBuildWorker(ReadOnlyTargetRules Target) : base(Target)
    {
        PrivateIncludePaths.Add(Path.Combine(EngineDirectory, "Source/Developer/IoStoreUtilities/Internal"));
        PrivateIncludePaths.Add(Path.Combine(EngineDirectory, "Source/Developer/Zen/Internal"));
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
        PrivateDependencyModuleNames.AddRange(new string[] { "AssetRegistry", "DerivedDataCache", "InterchangeEngine", "Json", "IoStoreUtilities", "Zen", "Projects", "RHI", "UnrealEd" });
    }
}

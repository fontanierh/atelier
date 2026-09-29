using UnrealBuildTool;

public class AtelierStream : ModuleRules
{
    public AtelierStream(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "DeveloperSettings", "Json", "PixelStreaming2Input" });
        PrivateDependencyModuleNames.AddRange(new string[] { "PixelStreaming2", "PixelStreaming2Core" });
    }
}

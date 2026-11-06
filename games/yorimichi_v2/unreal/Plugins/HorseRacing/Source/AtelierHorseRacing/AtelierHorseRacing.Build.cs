using UnrealBuildTool;

public class AtelierHorseRacing : ModuleRules
{
    public AtelierHorseRacing(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        // The sources share file-local helper names (Noise, StableName, ...): unity files would merge them.
        bUseUnity = false;
        // Pure rules: plain data and functions, no engine world, actor or UI.
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject" });
        PrivateDependencyModuleNames.AddRange(new string[] { "Json", "JsonUtilities", "Projects" });
    }
}

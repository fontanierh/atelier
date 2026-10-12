using UnrealBuildTool;

public class AtelierCore : ModuleRules
{
    public AtelierCore(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "Json" });
        // SkinMorphOffsets reads skeletal render data (vertex and skin weight buffers).
        PrivateDependencyModuleNames.Add("RenderCore");
    }
}

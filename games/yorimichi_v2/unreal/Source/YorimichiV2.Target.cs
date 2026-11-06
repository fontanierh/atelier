using UnrealBuildTool;
using System.Collections.Generic;

public class YorimichiV2Target : TargetRules
{
    public YorimichiV2Target(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("Yorimichi");
    }
}

using UnrealBuildTool;
using System.Collections.Generic;

public class YorimichiTarget : TargetRules
{
    public YorimichiTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("Yorimichi");
    }
}

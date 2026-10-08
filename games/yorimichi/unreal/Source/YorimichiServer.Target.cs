using UnrealBuildTool;
using System.Collections.Generic;

public class YorimichiServerTarget : TargetRules
{
    public YorimichiServerTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Server;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("Yorimichi");
    }
}

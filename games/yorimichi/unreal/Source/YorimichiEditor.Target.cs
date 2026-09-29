using UnrealBuildTool;
using System.Collections.Generic;

public class YorimichiEditorTarget : TargetRules
{
    public YorimichiEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("Yorimichi");
    }
}

using UnrealBuildTool;
using System.Collections.Generic;

public class YorimichiV2EditorTarget : TargetRules
{
    public YorimichiV2EditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("Yorimichi");
        ExtraModuleNames.Add("YorimichiImport");
    }
}

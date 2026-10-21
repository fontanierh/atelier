using UnrealBuildTool;
using System.Collections.Generic;
using System.IO;

public class YorimichiTarget : TargetRules
{
    public YorimichiTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("Yorimichi");
        if (Target.Platform.ToString() == "HTML5")
        {
            // Retain the skating arithmetic boundaries until the required FTZ
            // pass. Link options require an independent build environment.
            BuildEnvironment = TargetBuildEnvironment.Unique;
            DebugInfo = DebugInfoMode.None;
            bAllowLTCG = false;
            AdditionalLinkerArguments = "-O0 --profiling-funcs -Wl,--export=fma -Wl,--export=fmaf " +
                "-sBINARYEN_EXTRA_PASSES=--always-inline-max-function-size=0," +
                "--flexible-inline-max-function-size=0,--one-caller-inline-max-function-size=0";
            string Project = ProjectFile!.Directory.FullName;
            string Root = Path.GetFullPath(Path.Combine(Project, "../../.."));
            string Tools = Path.Combine(Root, "platform/engine/Plugins/Activities/Skate/Tools");
            string Binary = Target.Configuration == UnrealTargetConfiguration.Development
                ? "Yorimichi" : "Yorimichi-HTML5-" + Target.Configuration;
            string Python = BuildHostPlatform.Current.Platform == UnrealTargetPlatform.Win64 ? "python" : "python3";
            PostBuildSteps.Add(Python + " \"" + Path.Combine(Tools, "prepare_wasm.py") + "\" \"" +
                Path.Combine(Project, "Binaries/HTML5", Binary + ".wasm") + "\" --work \"" +
                Path.Combine(Root, "build/yorimichi/browser-float", Binary) + "\" --link-manifest \"" +
                Path.Combine(Project, "Binaries/HTML5", Binary + ".html5link.json") + "\"");
        }
    }
}

using UnrealBuildTool;

public class AtelierLive : ModuleRules
{
    public AtelierLive(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "DeveloperSettings" });
        PrivateDependencyModuleNames.AddRange(new string[] { "AtelierCore", "InputCore", "Json", "ImageCore", "RHI", "Projects", "ClothingSystemRuntimeInterface" });
        bool NativeLive = Target.Platform.ToString() != "HTML5";
        PrivateDefinitions.Add("ATELIER_WITH_NATIVE_LIVE=" + (NativeLive ? "1" : "0"));
        if (NativeLive) PrivateDependencyModuleNames.AddRange(new string[] { "HTTPServer", "GLTFCore", "MeshDescription", "StaticMeshDescription" });
        // Agent Python runs in uncooked (editor-binary) sessions only.
        if (Target.bBuildEditor) PrivateDependencyModuleNames.Add("PythonScriptPlugin");
    }
}

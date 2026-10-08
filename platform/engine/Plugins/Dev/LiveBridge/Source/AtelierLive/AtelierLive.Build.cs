using UnrealBuildTool;

public class AtelierLive : ModuleRules
{
    public AtelierLive(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "DeveloperSettings" });
        PrivateDependencyModuleNames.AddRange(new string[] { "InputCore", "Json", "HTTPServer", "GLTFCore", "MeshDescription", "StaticMeshDescription", "ImageCore", "RHI", "Projects", "ClothingSystemRuntimeInterface" });
        // Agent Python runs in uncooked (editor-binary) sessions only.
        if (Target.bBuildEditor) PrivateDependencyModuleNames.Add("PythonScriptPlugin");
    }
}

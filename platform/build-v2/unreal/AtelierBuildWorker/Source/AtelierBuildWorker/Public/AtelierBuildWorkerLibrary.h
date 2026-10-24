#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "AtelierBuildWorkerLibrary.generated.h"

/**
 * What the build-v2 Unreal job loop (platform/studio/atelier/build_v2/unreal_worker.py) asks of the editor, seen from
 * Python as unreal.AtelierBuildWorkerLibrary.<snake_case>. Results that are structures are JSON text.
 */
UCLASS()
class ATELIERBUILDWORKER_API UAtelierBuildWorkerLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** {build_id, modules: [project module], plugins: {name: base dir}, libraries: [loaded module file], rhi}. */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static FString NativeContext();
    /** {graph, nodes: [{kind, path, local, status}]}: every cache store of the effective DDC graph, from its stats tree (full paths). */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static FString DdcGraph();
    /** False means recording is unavailable; the job must refuse. */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static bool BeginReadRecording();
    /** {version:1, best_effort:true, files:[absolute path]}; IO bypassing IPlatformFile is not observable. */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static FString EndReadRecording();
    /** Start recording every package save (UPackage::PackageSavedWithContextEvent). */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static void BeginSaveRecording();
    /** Stop recording; [{package, filename, files: {path: sha1}}] saved since BeginSaveRecording, in order, hashed after each save's writes were flushed. */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static FString EndSaveRecording();
    /** Finish asset and shader compilation and pending async loads. */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static void FinishBackgroundWork();
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static TArray<FString> DirtyPackageNames();
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static TArray<FString> LoadedPackageNames(const FString& Prefix);
    /** [[import path, class]] from a saved package file's own import table, in table order; empty text if unreadable. */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static FString PackageImports(const FString& Filename);
    /** {found, value}: the effective value of an ini key (File is a base name such as Engine). */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static FString ConfigValue(const FString& File, const FString& Section, const FString& Key);
    /** {name: [value, set by]} for every console variable; "Constructor" means still at its default. */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static FString SettingsSnapshot();
    /** An immediate, synchronous garbage collection (the Kismet one only schedules it for the next tick). */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static void CollectGarbageNow();
    /** {object path: shortest root path} for every object of a package still in memory. Diagnostic only. */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static FString ReferenceChains(const FString& PackageName);
    /** Drop editor state that can hold job objects: "transactions", "selection" or "interchange". */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static bool ReleaseEditorState(const FString& Which);
    /** Start counting failed ensures (FCoreDelegates::OnEnsureFailed) from zero. */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static void BeginEnsureCount();
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static int32 EnsureCount();
    /** Ask the asset registry to rescan files that were moved or deleted. */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Build") static void ForgetFiles(const TArray<FString>& Files);
};

#pragma once
#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "FoliageSystem.generated.h"

class UStaticMeshComponent;
class UHierarchicalInstancedStaticMeshComponent;
class UStaticMesh;
class UMaterialInterface;
class FJsonObject;

USTRUCT()
struct FYorimichiFoliageSource
{
    GENERATED_BODY()
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Original;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Visual;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Shadow;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> NearVisual;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Patches;
    TWeakObjectPtr<UStaticMesh> SourceMesh;
    FString SourcePath;
    bool HasRigid=false;
    bool Visible = false, Hidden = false, CastShadow = false, DistanceField = false;
    bool ShadowOnly = false, EvaluateWPO = true;
    FString Kind;
    int32 InstanceCount=0;
};

/** Every region's vegetation shares one representation and settings owner.
 * The active mesh set owns collision; inactive legacy assets are paths, never resident meshes.
 */
UCLASS()
class YORIMICHI_API UYorimichiFoliageSubsystem : public UTickableWorldSubsystem
{
    GENERATED_BODY()
public:
    /** All instanced scenery uses this factory so new regional plants cannot escape registration/audit. */
    static UHierarchicalInstancedStaticMeshComponent* NewInstances(UObject* Outer, FName Name = NAME_None);
    /** Resolve before loading: optimized play never opens the legacy source package. */
    static UStaticMesh* LoadMesh(UWorld* World,const FString& SourcePath);
    static FString SourcePath(const UStaticMesh* Mesh);
    static FString SourceName(const UStaticMesh* Mesh);
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    bool Refresh();
    /** Call after editing an already registered instance layout/material binding, before rendering it again. */
    bool RefreshSource(UStaticMeshComponent* Component);
    /** Change authored visibility on the source and its managed renderers together. */
    void SetSourceVisibility(UStaticMeshComponent* Component, bool Visible);
    bool SetEnabled(bool Enabled);
    UFUNCTION(BlueprintPure, Category="Foliage")
    bool IsEnabled() const { return bEnabled; }
    bool IsReloading() const { return RequestedEnabled.IsSet(); }
    /** Unique loaded mesh objects for managed scenery: legacy and prepared respectively. */
    FIntPoint LoadedModeCounts() const;
    void SetDistances(bool Performance, float Detail, float SwayMetres, float ShadowMetres);
    const FString& GetError() const { return Error; }
    virtual void Tick(float Dt) override;
    virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UYorimichiFoliageSubsystem,STATGROUP_Tickables); }
    virtual bool DoesSupportWorldType(EWorldType::Type Type) const override;
    virtual void Deinitialize() override;
private:
    struct FAsset { FString Optimized, Shadow, Patch, Rigid, Kind; int32 Triangles=0,ShadowTriangles=0,RigidTriangles=0;
        TArray<FString> SourceMaterials;TArray<int32> LODTriangles;TArray<TArray<FVector>> Coverage;bool Aggregate=false;FBox Canopy; };
    TMap<FString,FAsset> Assets;
    TMap<FString,FString> ResidentSources;
    TSet<FString> LeafMaterials;
    TArray<FString> Words;
    struct FClassification
    {
        TWeakObjectPtr<UStaticMesh> Mesh;
        TArray<TWeakObjectPtr<UMaterialInterface>> Materials;
        TArray<FName> Slots;
        bool Required=false;
    };
    // Weak keys/values do not keep scenery alive. Reclassify only a new or
    // changed mesh/material/role binding, including previously rigid sources.
    TMap<TWeakObjectPtr<UStaticMeshComponent>,FClassification> ClassificationCache;
    UPROPERTY() TArray<FYorimichiFoliageSource> Sources;
    FString Error;
    bool bRegistryLoaded=false, bEnabled=true, bPerformance=true, bReportedSetting=false;
    TOptional<bool> RequestedEnabled;
    bool bStartupCompleted=false;
    bool bModeLoadFailed=false;
    TSet<TWeakObjectPtr<UStaticMesh>> StartupMeasuredMeshes;
    TSet<TWeakObjectPtr<UStaticMesh>> StartupVertexCopies;
    float Detail=.4f, Sway=60.f, ShadowDistance=80.f, AuditElapsed=0.f;
    bool LoadRegistry();
    bool ReadRegistry(const TSharedPtr<FJsonObject>& Registry);
    friend class FYorimichiFoliageToggleTest;
    friend class FYorimichiFoliageRegistryTest;
    friend class FYorimichiFoliageClassificationTest;
    bool RequiresRegistration(UStaticMeshComponent* Component) const;
    bool CachedRequiresRegistration(UStaticMeshComponent* Component);
    bool Register(UStaticMeshComponent* Component);
    void DestroyRenderers(FYorimichiFoliageSource& Source);
    bool ReloadMode(bool Enabled);
    void ReleaseStartupVertexCopies();
    void Apply(FYorimichiFoliageSource& Source);
    void Restore(FYorimichiFoliageSource& Source);
};

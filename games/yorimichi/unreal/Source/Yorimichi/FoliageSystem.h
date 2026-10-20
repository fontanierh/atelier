#pragma once
#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "FoliageSystem.generated.h"

class UStaticMeshComponent;
class UHierarchicalInstancedStaticMeshComponent;
class UStaticMesh;
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
    UPROPERTY() TObjectPtr<UStaticMesh> SourceMesh;
    bool Visible = false, Hidden = false, CastShadow = false, DistanceField = false;
    bool ShadowOnly = false, EvaluateWPO = true;
    FString Kind;
    int32 InstanceCount=0;
};

/** Every region's vegetation, including mixed meshes, shares one representation and settings owner.
 * Original components retain all collision and placements. Optimized children render only.
 */
UCLASS()
class YORIMICHI_API UYorimichiFoliageSubsystem : public UTickableWorldSubsystem
{
    GENERATED_BODY()
public:
    /** All instanced scenery uses this factory so new regional plants cannot escape registration/audit. */
    static UHierarchicalInstancedStaticMeshComponent* NewInstances(UObject* Outer, FName Name = NAME_None);
    bool Refresh();
    /** Call after editing an already registered instance layout/material binding, before rendering it again. */
    bool RefreshSource(UStaticMeshComponent* Component);
    bool SetEnabled(bool Enabled);
    UFUNCTION(BlueprintPure, Category="Foliage")
    bool IsEnabled() const { return bEnabled; }
    void SetDistances(bool Performance, float Detail, float SwayMetres, float ShadowMetres);
    const FString& GetError() const { return Error; }
    virtual void Tick(float Dt) override;
    virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UYorimichiFoliageSubsystem,STATGROUP_Tickables); }
    virtual bool DoesSupportWorldType(EWorldType::Type Type) const override;
    virtual void Deinitialize() override;
private:
    struct FAsset { FString Optimized, Shadow, Patch, Kind; int32 Triangles=0,ShadowTriangles=0;
        TArray<int32> LODTriangles;bool Aggregate=false;FBox Canopy; };
    TMap<FString,FAsset> Assets;
    TSet<FString> LeafMaterials;
    TArray<FString> Words;
    UPROPERTY() TArray<FYorimichiFoliageSource> Sources;
    FString Error;
    bool bRegistryLoaded=false, bEnabled=true, bPerformance=true, bReportedSetting=false;
    float Detail=.4f, Sway=60.f, ShadowDistance=80.f, AuditElapsed=0.f;
    bool LoadRegistry();
    bool ReadRegistry(const TSharedPtr<FJsonObject>& Registry);
    friend class FYorimichiFoliageToggleTest;
    friend class FYorimichiFoliageRegistryTest;
    bool RequiresRegistration(UStaticMeshComponent* Component) const;
    bool Register(UStaticMeshComponent* Component);
    void Apply(FYorimichiFoliageSource& Source);
    void Restore(FYorimichiFoliageSource& Source);
};

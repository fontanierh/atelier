#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "JapanWorld.generated.h"

class UHierarchicalInstancedStaticMeshComponent;
class UStaticMeshComponent;

/** A tree house room for the camera see-through's hole mode (docs/CAMERA.md): Unreal centre (cm), half size (cm; a
 *  round room has its radius on every axis), yaw (radians). */
struct FSeeThroughRoom
{
    FVector Center = FVector::ZeroVector;
    FVector Extent = FVector::ZeroVector;
    float Yaw = 0.f;
    bool bRound = false;
};

USTRUCT()
struct FWorldShot
{
    GENERATED_BODY()
    FVector Location = FVector::ZeroVector;
    FRotator Rotation = FRotator::ZeroRotator;
};

/** Spawns the generated world (Content/Data/world.json): instanced props, sky dome, sea. Positions in the json are
 *  Blender metres (X east, Y north, Z up); Unreal is centimetres with Y flipped, yaw negated. */
UCLASS()
class YORIMICHI_API AJapanWorld : public AActor
{
    GENERATED_BODY()
public:
    AJapanWorld();
    virtual void BeginPlay() override;

    static FVector ToUE(double X, double Y, double Z) { return FVector(X * 100.0, -Y * 100.0, Z * 100.0); }

    UPROPERTY() TObjectPtr<class AZeppelinService> Zeppelin;
    FTransform PlayerStart;
    TArray<FWorldShot> Shots;
    bool bLoaded = false;
    bool bHidamariLoaded = false;
    int32 TotalInstances = 0;
    bool bForestLakeLoaded = false;
    FVector ForestLakeCenter = FVector::ZeroVector;
    FVector2D ForestLakeRadii = FVector2D::ZeroVector;
    FVector ForestLakeSafeShore = FVector::ZeroVector;

    UPROPERTY() TArray<UHierarchicalInstancedStaticMeshComponent*> Groups;
    // The far-hill backdrop subset, kept separately so its cull distance can be set on its own.
    UPROPERTY() TArray<UHierarchicalInstancedStaticMeshComponent*> BackdropGroups;
    UPROPERTY() UStaticMeshComponent* SkyDome = nullptr;
    UPROPERTY() UStaticMeshComponent* Sea = nullptr;
    UPROPERTY() class UMaterialParameterCollection* WindMPC = nullptr;

    // wind (Unreal frame, cm/s): a steady direction with slow gusts
    FVector WindDir = FVector(0.3, -0.95, 0); float WindSpeed = 350.f;
    float WindStrength(const FVector& P, float T) const;
    FVector WindAt(const FVector& P, float T) const { return WindDir * WindSpeed * WindStrength(P, T); }
    virtual void Tick(float Dt) override;
    // Cosmetic particles sample the generated ground directly; gameplay still uses collision.
    bool SampleGroundHeight(const FVector& Position, float& Height) const;
    void ApplyPerformanceSettings(bool bPerformance);
    // Diagnosis only: honours japan.HideGroups so one foliage family can be priced at a time.
    void ApplyGroupDiagnostics();

    // Camera see-through (SeeThrough.h, docs/CAMERA.md): the tree house's instance groups (tagged
    // JapanSeeThrough::Tag) and its rooms from treehouse/runtime.json.
    UPROPERTY() TArray<UHierarchicalInstancedStaticMeshComponent*> SeeThroughGroups;
    TArray<FSeeThroughRoom> SeeThroughRooms;
    /** Whether P (Unreal cm) is inside room Index grown by Margin cm (negative: shrunk). False for no room. */
    bool IsInSeeThroughRoom(int32 Index, const FVector& P, float Margin) const;
    /** The first room P is inside (grown by Margin cm), or INDEX_NONE. */
    int32 FindSeeThroughRoom(const FVector& P, float Margin) const;
    /** true (hole mode, japan.SeeThroughHole 1): the chase camera's probe passes the tree house, which the hole cuts
     *  instead; false (the default): it stops there like any solid thing (UJapanCameraArm reads this). */
    void SetSeeThroughProbe(bool bIgnore);
    bool IsSeeThroughProbeIgnored() const { return bSeeThroughProbeIgnored; }

private:
    TArray<float> GroundHeights;
    int32 GroundResolution = 0;
    float GroundSize = 0.f;
    FString AppliedHideGroups;
    float AppliedBackdropCull = 0.f;
    int32 AppliedPerformanceMode = -1;
    bool bSeeThroughProbeIgnored = false;
    void Load();
};

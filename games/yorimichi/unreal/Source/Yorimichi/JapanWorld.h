#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "JapanWorld.generated.h"

class UHierarchicalInstancedStaticMeshComponent;
class UStaticMeshComponent;

/** The volumetric fog's look, from the settings menu (UJapanPreferences, docs/VOLUMETRIC_FOG.md). */
struct FVolumetricFogLook
{
    float Density = .07f;       // the height fog's density at sea level, in the countryside
    float Reach = 3000.f;       // the froxel grid's view distance (cm)
    float Falloff = .12f;       // the height fog's falloff: the density halves every 1000 / Falloff cm up
    float Scattering = .5f;     // the phase function's anisotropy: 0 even, toward 0.9 a glow toward the sun
    float Shafts = 1.f;         // the sun's volumetric scattering intensity
    float Town = 0.f;           // the share of the density left when the view holds Hidamari
    bool bPerformance = false;  // the Graphics setting (only the grid's resolution, set by console variables)
    bool operator==(const FVolumetricFogLook&) const = default;
};

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
    /** Volumetric fog (the settings menu's "fog" and its sliders, docs/VOLUMETRIC_FOG.md): ground mist lit and shadowed
     *  by the sun and the sky, inside the froxel grid around the camera. Off restores the level's fog and sun as built. */
    void ApplyVolumetricFog(bool bOn, const FVolumetricFogLook& Look);
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
    // The level's height fog and sun before the volumetric look (setup_project.py builds the fog with no density), and
    // the look applied (unset: off).
    struct FFogBase { float Density = 0.f, Falloff = 0.f, Cutoff = 0.f, Distance = 0.f, Shafts = 1.f; bool bVolumetric = false; };
    TOptional<FFogBase> FogBase;
    TOptional<FVolumetricFogLook> AppliedFog;
    bool bFogApplied = false;
    // The mist's density as applied, Hidamari's bounds (Unreal cm) and how much of the town the view holds, eased
    // (UpdateFogDensity: Dt 0 snaps).
    float AppliedFogDensity = -1.f, TownView = 0.f;
    FBox2D TownBounds = FBox2D(ForceInit);
    void UpdateFogDensity(float Dt);
    bool bSeeThroughProbeIgnored = false;
    void Load();
};

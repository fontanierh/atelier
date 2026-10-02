#pragma once
#include "CoreMinimal.h"
#include "Native/GameplayWorld.h"
#include <cfloat>

class UWorld;
class ACharacter;
class UStaticMesh;
class UStaticMeshComponent;
class USkateCollisionAsset;
class USkateCollisionMeshData;
class USkateRailSubsystem;
struct FKConvexElem;

struct FSkateCollisionTriangleMaterial
{
    bool bOverride=false;
    float StaticFriction=0,DynamicFriction=0,Restitution=0;
    uint16 Surface=0;
};
/** Plain snapshot: all UObject reads occur on the game thread, before worker handoff. */
struct ATELIERSKATE_API FSkateCollisionSnapshot
{
    FBox Region=FBox(ForceInit);
    int32 Budget=500000;
    TArray<FVector3f> Points;
    TArray<TArray<FVector3f>> Rails;
    TArray<FSkateCollisionTriangleMaterial> Materials;
    FVector3f Spawn=FVector3f::ZeroVector;
    float Heading=0;
    FSkateCollisionTriangleMaterial CurrentMaterial;
    int32 Num() const {return Points.Num()/3;}
    bool Full() const {return Num()>Budget;}
    void Add(const FVector& A,FVector B,FVector C);
    void AddFacing(const FVector& Centre,const FVector& A,const FVector& B,const FVector& C);
    void AddBox(const FTransform& T,const FVector& Half);
    void AddCapsule(const FTransform& T,double Radius,double Half);
    void AddHull(const FKConvexElem& Hull,const FTransform& T,const TArray<int32>& Indices);
    void AddSurface(const USkateCollisionMeshData& Data,const FTransform& T,
        const UStaticMeshComponent* Component,TConstArrayView<USkateCollisionAsset*> Catalogs);
};
struct ATELIERSKATE_API FSkateCollisionDiagnostics
{
    int32 TriangleCount=0,MaterialOverrideCount=0,NonzeroSurfaceCount=0;
    int32 MissingCatalogCount=0,UnsupportedComponentCount=0;
    uint64 SceneGeneration=0;
    TArray<FString> Errors,Warnings;
    bool Okay() const {return Errors.IsEmpty();}
    FString Summary() const;
};
ATELIERSKATE_API FVector SkateCollisionSnapshotCentre(UWorld* World,const FVector& Position);
// Catalogs must pass Validate once on load; refreshes never rescan baked vertex arrays.
ATELIERSKATE_API bool SkateGatherCollisionWorld(UWorld* World,ACharacter* Rider,FVector Centre,
    FVector Spawn,float Yaw,USkateRailSubsystem* Rails,TConstArrayView<USkateCollisionAsset*> Catalogs,
    FSkateCollisionSnapshot& Snapshot,double& Reach,FSkateCollisionDiagnostics& Diagnostics,uint64 SceneGeneration=0);
inline bool SkateGatherCollisionWorld(UWorld* World,ACharacter* Rider,FVector Centre,FVector Spawn,float Yaw,
    USkateRailSubsystem* Rails,USkateCollisionAsset* Catalog,FSkateCollisionSnapshot& Snapshot,
    double& Reach,FSkateCollisionDiagnostics& Diagnostics,uint64 SceneGeneration=0)
{
    return SkateGatherCollisionWorld(World,Rider,Centre,Spawn,Yaw,Rails,
        MakeArrayView(&Catalog,1),Snapshot,Reach,Diagnostics,SceneGeneration);
}
ATELIERSKATE_API atelier::skate::GameplayWorldSnapshot SkateNativeCollisionSnapshot(const FSkateCollisionSnapshot& Snapshot);
// Exported wrappers run plain native validation on a 32 MiB thread under the
// saved/default/restored floating environment; no UObject reads occur there.
ATELIERSKATE_API bool SkateValidateNativeCollisionSnapshot(const FSkateCollisionSnapshot& Snapshot,FString& Error);
ATELIERSKATE_API bool SkateValidateCollisionMaterialTransport(FString& Error);
ATELIERSKATE_API bool SkateCollisionSnapshotsEqual(const FSkateCollisionSnapshot& A,
    const FSkateCollisionSnapshot& B,FString& Difference);

/** Exact state bytes, not a lossy hash. Object/instance/rail enumeration order is retained.
 * Validated baked mesh records are immutable until the catalog Revision changes. */
struct FSkateCollisionSceneState
{
    TArray<uint8> Bytes;
    bool operator==(const FSkateCollisionSceneState& Other) const {return Bytes==Other.Bytes;}
};
ATELIERSKATE_API FSkateCollisionSceneState SkateCaptureCollisionSceneState(UWorld* World,ACharacter* Rider,
    const FBox& Region,USkateRailSubsystem* Rails,TConstArrayView<USkateCollisionAsset*> Catalogs);
/** Kinematic geometry is refreshed at bounded scan latency; no rigid-body coupling or platform velocity. */
class ATELIERSKATE_API FSkateCollisionSceneTracker
{
public:
    double ScanPeriodSeconds=.25;
    bool Poll(UWorld* World,ACharacter* Rider,const FBox& Region,USkateRailSubsystem* Rails,
        TConstArrayView<USkateCollisionAsset*> Catalogs,double NowSeconds);
    void AcceptSnapshot(UWorld* World,ACharacter* Rider,const FBox& Region,USkateRailSubsystem* Rails,
        TConstArrayView<USkateCollisionAsset*> Catalogs,double NowSeconds);
    void Reset();
    uint64 Generation() const {return Generation_;}
private:
    TOptional<FSkateCollisionSceneState> State_;
    double LastScanSeconds_=-DBL_MAX;
    uint64 Generation_=0;
};

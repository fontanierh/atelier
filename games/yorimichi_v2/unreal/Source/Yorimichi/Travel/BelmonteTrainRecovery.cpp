#include "BelmonteTrainRecovery.h"
#include "Engine/World.h"
#include "Engine/HitResult.h"
#include "Components/PrimitiveComponent.h"
#include "CollisionQueryParams.h"
#include "WorldCollision.h"

namespace BelmonteTrainRecovery
{
// The step the standing capsule is tested above the ground: room for a walkable slope under its rounded foot.
static constexpr double Step = 45.;

BelmonteTrainRules::FStandProbe Probe(const UWorld* World, const FVector& Point, double Near, double MaxOff,
    const FStander& Stander, TFunctionRef<bool(const UPrimitiveComponent*)> IsTrain, FVector& Feet)
{
    BelmonteTrainRules::FStandProbe Result;
    Feet = Point;
    if (!World || !FMath::IsFinite(Near) || Point.ContainsNaN() || MaxOff <= 0.) return Result;
    // Simple collision: what the character itself stands on and collides with (complex-as-simple meshes included).
    FCollisionQueryParams Params(SCENE_QUERY_STAT(TrainRecovery), false);
    if (Stander.Ignore) Params.AddIgnoredActor(Stander.Ignore);
    // Everything that can be stood on or be in the way, the train included (it must be seen to be refused).
    FCollisionObjectQueryParams Solid;
    for (const ECollisionChannel Channel : {ECC_WorldStatic, ECC_WorldDynamic, ECC_Vehicle, ECC_PhysicsBody, ECC_Destructible})
        Solid.AddObjectTypesToQuery(Channel);
    FHitResult Ground;
    if (!World->LineTraceSingleByObjectType(Ground, FVector(Point.X, Point.Y, Near + MaxOff), FVector(Point.X, Point.Y, Near - MaxOff - 1.), Solid, Params))
        return Result;
    Result.bGround = true;
    Result.bGroundIsTrain = IsTrain(Ground.GetComponent());
    Result.GroundNormalZ = Ground.ImpactNormal.Z;
    Result.GroundOff = Ground.ImpactPoint.Z - Near;
    // Standing room, other people included: the whole capsule a step above that ground overlaps nothing.
    FCollisionObjectQueryParams Room = Solid;
    Room.AddObjectTypesToQuery(ECC_Pawn);
    const FCollisionShape Capsule = FCollisionShape::MakeCapsule(Stander.Radius, Stander.HalfHeight);
    const FVector Start(Point.X, Point.Y, Ground.ImpactPoint.Z + Stander.HalfHeight + Step);
    Result.bClear = !World->OverlapAnyTestByObjectType(Start, FQuat::Identity, Room, Capsule, Params);
    if (!Result.bClear) return Result;
    // Then down onto its floor, as the character's own floor check would find it.
    FHitResult Floor;
    const FVector End(Point.X, Point.Y, Ground.ImpactPoint.Z + Stander.HalfHeight - 20.);
    if (World->SweepSingleByObjectType(Floor, Start, End, FQuat::Identity, Room, Capsule, Params) && !Floor.bStartPenetrating)
    {
        const UPrimitiveComponent* Component = Floor.GetComponent();
        // Never on someone's head.
        Result.bFloor = !Component || Component->GetCollisionObjectType() != ECC_Pawn;
        Result.bFloorIsTrain = IsTrain(Component);
        Result.FloorNormalZ = Floor.ImpactNormal.Z;
        Feet = Floor.Location - FVector(0, 0, Stander.HalfHeight);
    }
    return Result;
}

bool SafeStand(const UWorld* World, const FVector& Point, double Near, double MaxOff, const FStander& Stander,
    TFunctionRef<bool(const UPrimitiveComponent*)> IsTrain, FVector& Feet)
{
    return BelmonteTrainRules::AcceptStand(Probe(World, Point, Near, MaxOff, Stander, IsTrain, Feet), Stander.WalkableZ, MaxOff);
}
}

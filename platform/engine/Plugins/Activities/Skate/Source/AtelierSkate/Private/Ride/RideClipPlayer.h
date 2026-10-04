#pragma once
#include "CoreMinimal.h"
#include "RideAnimator.h"
#include "Engine/EngineTypes.h"
#include "CollisionQueryParams.h"

class UWorld;
struct FHitResult;

/**
 * The transitions' clips (RIDE.md, "Transitions"): the mount, dismount, carry, run-out, kick-out and get-up clips play
 * through FRideAnimator on the hidden native rig, and Step publishes their pose like a riding frame (a root,
 * root-space bones on the native rig's names), which RetargetRetailPose puts on the character. Riding, the pose is
 * Native's session's.
 */
class FRideClipPlayer
{
public:
    /** Load the rig and the clips (blocking on first use). */
    void Preload() { Animator.Preload(); }
    bool HasRig() const { return Animator.HasRig(); }
    FRideAnimator& GetAnimator() { return Animator; }
    const FRideAnimator& GetAnimator() const { return Animator; }
    /** The animator's override layers alone, their TRAJECTORY at TrajectoryWorld (the clips' root space): Root, Names,
     *  Reference and Bones (the board bones are the clip's). */
    void Step(float Dt, const FTransform& TrajectoryWorld);

    FTransform Root = FTransform::Identity;
    TArray<FName> Names;
    TArray<FTransform> Reference, Bones;

    /** A box swept from one pose to another, its rotation in steps that move no corner more than 4 cm (a nose turning
     *  into a wall is caught where the centre barely moves). Hit.Time is the fraction of the whole move; Reached (if
     *  given) the box's pose at the hit: touching the face, or the pose found inside something when the hit starts
     *  there (bStartPenetrating; the pose at Hit.Time before it is the last one found free). The loose board's
     *  (RideTransition.cpp, RidePhysicalRider.cpp). */
    static bool SweepBox(const UWorld& World, const FTransform& From, const FTransform& To, const FVector& Extent, ECollisionChannel Channel,
        const FCollisionQueryParams& Params, const FCollisionResponseParams& Response, FHitResult& Hit, FTransform* Reached = nullptr);

private:
    FRideAnimator Animator;
};

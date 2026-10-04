#include "RideClipPlayer.h"
#include "Engine/World.h"
#include "Engine/HitResult.h"
#include "CollisionShape.h"

namespace
{
    // SweepBox turns the box in steps that move no corner more than CornerStep (cm), at most RotationSteps a sweep.
    constexpr float CornerStep = 4.f;
    constexpr int32 RotationSteps = 8;
}

void FRideClipPlayer::Step(float Dt, const FTransform& TrajectoryWorld)
{
    Root = TrajectoryWorld;
    if (Names.Num() != Animator.GetNames().Num()) { Names = Animator.GetNames(); Reference = Animator.GetReference(); }
    Animator.EvaluateFree(Dt, Bones);
}

bool FRideClipPlayer::SweepBox(const UWorld& World, const FTransform& From, const FTransform& To, const FVector& Extent, ECollisionChannel Channel,
    const FCollisionQueryParams& Params, const FCollisionResponseParams& Response, FHitResult& Hit, FTransform* Reached)
{
    const FCollisionShape Box = FCollisionShape::MakeBox(Extent);
    const FQuat R0 = From.GetRotation().GetNormalized(), R1 = To.GetRotation().GetNormalized();
    const float Turn = float(R0.AngularDistance(R1)) * float(Extent.Size());
    const int32 Steps = FMath::Clamp(FMath::CeilToInt(Turn / CornerStep), 1, RotationSteps);
    FVector A = From.GetLocation();
    for (int32 I = 1; I <= Steps; ++I)
    {
        const float T = float(I) / float(Steps);
        const FQuat R = Steps == 1 ? R1 : FQuat::Slerp(R0, R1, T).GetNormalized();
        const FVector B = FMath::Lerp(From.GetLocation(), To.GetLocation(), double(T));
        // A box standing still sweeps a hair, so one that starts (or turns) inside something still reports it.
        const FVector End = FVector::DistSquared(A, B) > 1e-4 ? B : A + FVector(0, 0, .01f);
        if (World.SweepSingleByChannel(Hit, A, End, R, Channel, Box, Params, Response))
        {
            Hit.Time = (float(I - 1) + (Hit.bStartPenetrating ? 0.f : Hit.Time)) / float(Steps);
            if (Reached) *Reached = FTransform(R, Hit.bStartPenetrating ? A : FVector(Hit.Location));
            return true;
        }
        A = B;
    }
    return false;
}

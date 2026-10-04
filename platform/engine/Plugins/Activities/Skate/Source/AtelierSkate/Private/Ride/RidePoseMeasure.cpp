#include "RidePoseMeasure.h"

void FRidePoseMeasure::Measure(const TArray<FName>& Names, const TArray<FTransform>& Reference, const TArray<FTransform>& Bones, float Dt,
    float Travel, bool bReversed)
{
    if (MeasuredNames != Names)
    {
        MeasuredNames = Names;
        BodyBone.SetNum(Names.Num());
        for (int32 I = 0; I < Names.Num(); ++I)
        {
            const FString Name = Names[I].ToString();
            // TRAJECTORY is Native's motion bone, not the body: it slides under the root as the session moves.
            BodyBone[I] = !Name.Contains(TEXT("SKATEBOARD")) && !Name.Contains(TEXT("TRUCK")) && !Name.Contains(TEXT("WHEEL")) && !Name.Contains(TEXT("REPARENTED"))
                && Name != TEXT("TRAJECTORY");
        }
        DeckBone = Names.IndexOfByKey(FName(TEXT("SKATEBOARD_ROOT")));
        ToeBone[0] = Names.IndexOfByKey(FName(TEXT("LEFTTOEBASE")));
        ToeBone[1] = Names.IndexOfByKey(FName(TEXT("RIGHTTOEBASE")));
        LastBones.Reset();
        HipsBone = Names.IndexOfByKey(FName(TEXT("HIPS")));
        HeadBone = Names.IndexOfByKey(FName(TEXT("HEAD")));
        ChestBone = Names.IndexOfByKey(FName(TEXT("SPINE3")));
        const int32 Arm[2] = {Names.IndexOfByKey(FName(TEXT("LEFTARM"))), Names.IndexOfByKey(FName(TEXT("RIGHTARM")))};
        HeadAxis = ChestAxis = FVector::ForwardVector;
        if (Reference.IsValidIndex(Arm[0]) && Reference.IsValidIndex(Arm[1]) && Reference.IsValidIndex(HeadBone) && Reference.IsValidIndex(ChestBone))
        {
            // Facing away from the back: up crossed with the line from the right shoulder to the left one.
            const FVector Facing = FVector::CrossProduct(FVector::UpVector, Reference[Arm[0]].GetLocation() - Reference[Arm[1]].GetLocation()).GetSafeNormal();
            HeadAxis = Reference[HeadBone].GetRotation().UnrotateVector(Facing);
            ChestAxis = Reference[ChestBone].GetRotation().UnrotateVector(Facing);
        }
    }
    PoseNaN = 0;
    for (const FTransform& Bone : Bones) if (Bone.ContainsNaN()) ++PoseNaN;
    // The fastest body bone. The bones are in the root's space, so the ride's own travel and turning do not count.
    PoseStep = 0; PoseStepBone = INDEX_NONE; PoseDt = Dt;
    const bool bStep = LastBones.Num() == Bones.Num() && Dt > 1e-4f;
    LastBones.SetNum(Bones.Num(), EAllowShrinking::No);
    for (int32 I = 0; I < Bones.Num(); ++I)
    {
        const FVector Local = Bones[I].GetLocation();
        const float Step = bStep && BodyBone.IsValidIndex(I) && BodyBone[I] ? float(FVector::Dist(Local, LastBones[I])) / Dt : 0.f;
        if (Step > PoseStep) { PoseStep = Step; PoseStepBone = I; }
        LastBones[I] = Local;
    }
    FeetOff = 0;
    if (Bones.IsValidIndex(DeckBone))
        for (int32 F = 0; F < 2; ++F)
        {
            if (!Bones.IsValidIndex(ToeBone[F])) continue;
            const FVector Local = Bones[DeckBone].InverseTransformPosition(Bones[ToeBone[F]].GetLocation());
            // Along the travel: the deck's own length runs against it on a board left end for end.
            FootHeight[F] = float(Local.Z); FootAlong[F] = float(Local.X) * Travel * (bReversed ? -1.f : 1.f);
            // Off the deck: beyond its outline or clear of its grip.
            if (FMath::Abs(Local.X) > 42.f || FMath::Abs(Local.Y) > 14.f || Local.Z > 16.f || Local.Z < -4.f) ++FeetOff;
        }
    HipBoard = Bones.IsValidIndex(HipsBone) && Bones.IsValidIndex(DeckBone) ? float(Bones[HipsBone].GetLocation().Z - Bones[DeckBone].GetLocation().Z) : 0.f;
    auto FromTravel = [&Bones, Travel](int32 Bone, const FVector& Axis)
    {
        if (!Bones.IsValidIndex(Bone)) return 0.f;
        const FVector Facing = Bones[Bone].GetRotation().RotateVector(Axis);
        return FMath::RadiansToDegrees(FMath::Atan2(FMath::Abs(float(Facing.Y)), float(Facing.X) * Travel));
    };
    HeadYaw = FromTravel(HeadBone, HeadAxis); ChestYaw = FromTravel(ChestBone, ChestAxis);
}

FString FRidePoseMeasure::Describe() const
{
    return FString::Printf(TEXT("step=%.0f stepbone=%s dt=%.1f feet=%.1f,%.1f feetoff=%d nan=%d hipboard=%.1f headyaw=%.1f chestyaw=%.1f feetalong=%.1f,%.1f"),
        PoseStep, *StepBoneName().ToString(), PoseDt * 1000.f, FootHeight[0], FootHeight[1], FeetOff, PoseNaN, HipBoard, HeadYaw, ChestYaw,
        FootAlong[0], FootAlong[1]);
}

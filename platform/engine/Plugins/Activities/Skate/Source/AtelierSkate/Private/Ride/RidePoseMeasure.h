#pragma once
// The shown rider pose's health for QA, from its bones in the root's space (Native's skeleton: SKATEBOARD_ROOT, HIPS,
// HEAD, SPINE3, the toes). The Ride backend measures its animator's pose with it, and the hybrid (Native's session under
// Ride's body) the pose Native publishes, so both state lines carry the same fields.
#include "CoreMinimal.h"

struct FRidePoseMeasure
{
    /** Measure this frame's pose (Dt since the last); Travel is -1 rolling backward, Reversed a board left end for end. */
    void Measure(const TArray<FName>& Names, const TArray<FTransform>& Reference, const TArray<FTransform>& Bones, float Dt,
        float Travel, bool bReversed);
    /** The fields as the Ride backend's state line names them: step, stepbone, dt, feet, feetoff, nan, hipboard,
     *  headyaw, chestyaw, feetalong and nosefirst. */
    FString Describe() const;
    FName StepBoneName() const { return MeasuredNames.IsValidIndex(PoseStepBone) ? MeasuredNames[PoseStepBone] : FName(TEXT("none")); }

    int32 DeckBone = INDEX_NONE;
    float PoseStep = 0, FootHeight[2] = {0, 0};
    int32 PoseStepBone = INDEX_NONE;   // the bone of PoseStep
    float PoseDt = 0;                  // the frame PoseStep was measured over (s)
    int32 PoseNaN = 0, FeetOff = 0;
    // The hips above the board (HIPS over SKATEBOARD_ROOT along the root's up, cm), and the head's and the chest's
    // (SPINE3) facing from the travel (degrees on the root's plane, 0 looking along it); each bone's facing axis is the
    // one that points where the shoulders face in the rig's reference pose.
    float HipBoard = 0, HeadYaw = 0, ChestYaw = 0;
    float FootAlong[2] = {0, 0};       // each toe along the travel from the deck's pivot (cm; left, right)
    // The deck's nose leads the travel the yaws are measured from (the end that leads, not the stance's fakie flag,
    // which Native turns some frames after the travel reverses).
    bool NoseFirst = true;

private:
    TArray<FName> MeasuredNames;
    TArray<FVector> LastBones;       // root space
    TArray<bool> BodyBone;
    int32 ToeBone[2] = {INDEX_NONE, INDEX_NONE}, HipsBone = INDEX_NONE, HeadBone = INDEX_NONE, ChestBone = INDEX_NONE;
    FVector HeadAxis = FVector::ForwardVector, ChestAxis = FVector::ForwardVector;
};

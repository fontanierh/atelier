#pragma once
#include "CoreMinimal.h"
#include "RideTypes.h"

/**
 * The rider's pose for the Ride backend. It publishes bones on the native rig's names in root space (the same contract
 * as FSkateRuntime's native output): the board's seven bones always, and the rider's body once the clip rig is
 * loaded. Until then the body is absent and the character keeps its own locomotion pose.
 */
class FRideAnimator
{
public:
    FRideAnimator();
    /** Load the rig and clips if they are in the build (blocking; called before the first ride). */
    void Preload();
    bool HasRig() const { return bRig; }
    const TArray<FName>& GetNames() const { return Names; }
    const TArray<FTransform>& GetReference() const { return Reference; }
    /** Root-space bones for this frame. */
    void Evaluate(const FRideBodyPose& Body, const FRideBoardPose& Board, TArray<FTransform>& Bones);

private:
    bool bRig = false, bTried = false;
    TArray<FName> Names;
    TArray<FTransform> Reference;
    // Board bones: their indices in Names and their bind relative to the deck.
    int32 DeckIndex = 0;
    int32 TruckIndex[2] = {1, 2};
    int32 WheelIndex[4] = {3, 4, 5, 6};
    FTransform TruckFromDeck[2], WheelFromTruck[4];
    void SetBoardOnly();
    void PlaceBoard(const FRideBoardPose& Board, TArray<FTransform>& Bones) const;
};

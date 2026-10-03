#include "RideAnimator.h"

namespace
{
    // The native rig's board bones in its reference pose (root space, cm): the deck, the trucks at the axles and
    // the wheel centres (RIDE.md, "Rig").
    const TCHAR* BoardNames[] = {TEXT("SKATEBOARD_ROOT"), TEXT("TRUCK_FRONT"), TEXT("TRUCK_BACK"),
        TEXT("RIGHT_WHEELFRONT"), TEXT("LEFT_WHEELFRONT"), TEXT("RIGHT_WHEELBACK"), TEXT("LEFT_WHEELBACK")};
    const FVector BoardBind[] = {{0, 0, 8.9f}, {25.92f, 0, 6.12f}, {-25.92f, 0, 6.12f},
        {24.29f, 9.75f, 3.25f}, {24.29f, -9.75f, 3.25f}, {-24.35f, 9.75f, 3.27f}, {-24.35f, -9.75f, 3.27f}};
}

FRideAnimator::FRideAnimator() { SetBoardOnly(); }

void FRideAnimator::SetBoardOnly()
{
    Names.Reset(); Reference.Reset();
    for (int32 I = 0; I < 7; ++I) { Names.Add(BoardNames[I]); Reference.Add(FTransform(BoardBind[I])); }
    DeckIndex = 0; TruckIndex[0] = 1; TruckIndex[1] = 2; for (int32 I = 0; I < 4; ++I) WheelIndex[I] = 3 + I;
    for (int32 I = 0; I < 2; ++I) TruckFromDeck[I] = Reference[TruckIndex[I]].GetRelativeTransform(Reference[DeckIndex]);
    for (int32 I = 0; I < 4; ++I) WheelFromTruck[I] = Reference[WheelIndex[I]].GetRelativeTransform(Reference[TruckIndex[I / 2]]);
    bRig = false;
}

void FRideAnimator::Preload()
{
    if (bTried) return;
    bTried = true;
}

void FRideAnimator::PlaceBoard(const FRideBoardPose& Board, TArray<FTransform>& Bones) const
{
    Bones[DeckIndex] = Board.Deck;
    for (int32 I = 0; I < 2; ++I)
    {
        // Trucks lean about their own length (the kingpin's roll) as the rider turns.
        const FTransform Lean(FQuat(FVector::ForwardVector, FMath::DegreesToRadians(Board.TruckLean)));
        Bones[TruckIndex[I]] = Lean * TruckFromDeck[I] * Board.Deck;
    }
    for (int32 I = 0; I < 4; ++I)
    {
        const FTransform Spin(FQuat(FVector::RightVector, FMath::DegreesToRadians(Board.WheelSpin)));
        Bones[WheelIndex[I]] = Spin * WheelFromTruck[I] * Bones[TruckIndex[I / 2]];
    }
}

void FRideAnimator::Evaluate(const FRideBodyPose& Body, const FRideBoardPose& Board, TArray<FTransform>& Bones)
{
    Bones.SetNum(Names.Num(), EAllowShrinking::No);
    for (int32 I = 0; I < Names.Num(); ++I) Bones[I] = Reference[I];
    PlaceBoard(Board, Bones);
}

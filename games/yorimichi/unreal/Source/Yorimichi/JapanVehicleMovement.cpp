#include "JapanCharacterMovement.h"
#include "WandererCharacter.h"
#include "BikeComponent.h"
#include "SailboatComponent.h"
#include "BotwMoveSet.h"
#include "Serialization/MemoryWriter.h"
#include "Serialization/MemoryReader.h"

FJapanMoveCheckpoint UJapanCharacterMovement::CaptureMovementState() const
{
    const auto* Rider = Cast<AWandererCharacter>(CharacterOwner);
    if (!Rider) return {};
    if (Rider->GetNetworkActivity() == EJapanActivity::OnFoot) return Rider->GetMoves()->CaptureNetworkState();
    FJapanMoveCheckpoint Result;
    if (Rider->GetNetworkActivity() == EJapanActivity::Bike && Rider->GetBike())
    {
        auto State = Rider->GetBike()->CaptureNetworkState();
        Result.Action = State.Clip;
        FMemoryWriter Writer(Result.Bytes, true);
        if (!State.SerializeCheckpoint(Writer)) Result.Bytes.Reset();
    }
    if (Rider->GetNetworkActivity() == EJapanActivity::Sailboat && Rider->GetSailboat())
    {
        auto State=Rider->GetSailboat()->CaptureNetworkState();Result.Action=TEXT("Sailboat");
        FMemoryWriter Writer(Result.Bytes,true);if(!State.SerializeCheckpoint(Writer))Result.Bytes.Reset();
    }
    return Result;
}

bool UJapanCharacterMovement::ApplyMovementState(const FJapanMoveCheckpoint& State)
{
    auto* Rider = Cast<AWandererCharacter>(CharacterOwner);
    if (!Rider) return false;
    if (Rider->GetNetworkActivity() == EJapanActivity::OnFoot) return Rider->GetMoves()->ApplyNetworkState(State);
    if (Rider->GetNetworkActivity() == EJapanActivity::Sailboat)
    {
        if(State.Bytes.Num()!=FJapanSailState::CheckpointBytes||State.Action!=TEXT("Sailboat"))return false;
        FMemoryReader Reader(State.Bytes,true);FJapanSailState Sail;
        return Sail.SerializeCheckpoint(Reader)&&Reader.AtEnd()&&Rider->GetSailboat()->ApplyNetworkState(Sail);
    }
    if (Rider->GetNetworkActivity() != EJapanActivity::Bike || State.Bytes.Num() != FJapanBikeState::CheckpointBytes) return false;
    FMemoryReader Reader(State.Bytes, true);
    FJapanBikeState Bike;
    return Bike.SerializeCheckpoint(Reader) && Reader.AtEnd() && Bike.Clip == State.Action &&
        Rider->GetBike()->ApplyNetworkState(Bike);
}

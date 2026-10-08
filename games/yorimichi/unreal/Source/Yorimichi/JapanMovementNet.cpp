#include "JapanMovementNet.h"
#include "JapanCharacterMovement.h"
#include "JapanJumpReplayQA.h"
#include "WandererCharacter.h"
#include "BotwMoveSet.h"
#include "Engine/PackageMapClient.h"
#include "Misc/CommandLine.h"

namespace
{
const FName Buttons[] = { TEXT("jump"), TEXT("jump_release"), TEXT("dodge"), TEXT("attack"),
    TEXT("attack_release"), TEXT("guard"), TEXT("guard_release"), TEXT("weapon"), TEXT("crouch"),
    TEXT("dash"), TEXT("drop_holds"), TEXT("wave"), TEXT("bike_sprint") };
UJapanCharacterMovement* MovementOf(ACharacter* Character)
{
    return Character ? Cast<UJapanCharacterMovement>(Character->GetCharacterMovement()) : nullptr;
}
}

int32 FJapanMoveInput::ButtonIndex(FName Name)
{
    for (int32 I = 0; I < UE_ARRAY_COUNT(Buttons); ++I) if (Buttons[I] == Name) return I;
    return INDEX_NONE;
}

FName FJapanMoveInput::ButtonName(uint8 Index) { return Index < UE_ARRAY_COUNT(Buttons) ? Buttons[Index] : NAME_None; }

void FJapanMoveInput::ApplyNewEdges(uint16& LastApplied, TFunctionRef<void(uint8)> Apply) const
{
    for (int32 I = 0; I < Edges.Num(); ++I)
        if (uint16(FirstEdge + I) == uint16(LastApplied + 1))
        {
            ++LastApplied;
            Apply(Edges[I]);
        }
}

bool FJapanMoveInput::Serialize(FArchive& Ar)
{
    Ar << X << Y;
    Ar.SerializeBits(&Flags, 7);
    Ar << FirstEdge << ActivityEpoch;
    uint8 Count = uint8(Edges.Num());
    Ar.SerializeBits(&Count, 5);
    if (Count > MaximumEdges || X == -128 || Y == -128) { Ar.SetError(); return false; }
    if (Ar.IsLoading()) { Edges.SetNum(Count); EdgeAgeMilliseconds.SetNum(Count); }
    else if (EdgeAgeMilliseconds.IsEmpty()) EdgeAgeMilliseconds.SetNumZeroed(Count);
    if (EdgeAgeMilliseconds.Num() != Count) { Ar.SetError(); return false; }
    for (int32 I = 0; I < Count; ++I)
    {
        Ar.SerializeBits(&Edges[I], 4);
        Ar.SerializeBits(&EdgeAgeMilliseconds[I], 9);
        if (Edges[I] >= UE_ARRAY_COUNT(Buttons) || (EdgeAgeMilliseconds[I] > 500 && EdgeAgeMilliseconds[I] != 511)) { Ar.SetError(); return false; }
    }
    return !Ar.IsError();
}

bool FJapanMoveCheckpoint::Serialize(FArchive& Ar, UPackageMap* Map)
{
    uint32 Count = Bytes.Num();
    Ar.SerializeIntPacked(Count);
    if (Count == 0 || Count > MaximumBytes || !Map) { Ar.SetError(); return false; }
    if (Ar.IsLoading()) Bytes.SetNumUninitialized(Count);
    Ar.Serialize(Bytes.GetData(), Count);
    Map->SerializeName(Ar, Action);
    UObject* Focus = Target.Get();
    UObject* Lunge = LungeTarget.Get();
    Map->SerializeObject(Ar, AActor::StaticClass(), Focus);
    Map->SerializeObject(Ar, AActor::StaticClass(), Lunge);
    if (Ar.IsLoading()) { Target = Cast<AActor>(Focus); LungeTarget = Cast<AActor>(Lunge); }
    return !Ar.IsError();
}

void FSavedMove_Japan::Clear()
{
    Super::Clear(); Input = FJapanMoveInput(); PostState = FJapanMoveCheckpoint(); PostEdge = 0; PostCrouch = false;
}

#if !UE_BUILD_SHIPPING
void FSavedMove_Japan::PrepareStaleClockProbe(ACharacter* Character,
    FNetworkPredictionData_Client_Character& ClientData, uint32 OldEpoch)
{
    Clear();
    // UE's packet builder dereferences CharacterOwner; Clear alone does not initialize it.
    // Use the base initializer so this diagnostic does not consume the real input journal.
    Super::SetMoveFor(Character, .125f, FVector(1000., 0., 0.), ClientData);
    TimeStamp = 123.25f;
    Input.ActivityEpoch = OldEpoch;
    Input.FirstEdge = 60000; Input.Y = 127; Input.Flags = FJapanMoveInput::Sprint;
    // Deliberately absolute and far away: stale rejection must leave the host root unchanged.
    // Clear has removed any pooled end base and relative-location state.
    SavedLocation = Character->GetActorLocation() + FVector(1000., 0., 0.);
    SavedControlRotation = Character->GetControlRotation().Clamp();
    EndPackedMovementMode = Character->GetCharacterMovement()->PackNetworkMovementMode();
}
#endif

void FSavedMove_Japan::PostUpdate(ACharacter* Character, EPostUpdateMode Mode)
{
    const FVector OriginalLocation = Mode == PostUpdate_Replay ? SavedLocation : FVector::ZeroVector;
    const FVector OriginalVelocity = Mode == PostUpdate_Replay ? SavedVelocity : FVector::ZeroVector;
    Super::PostUpdate(Character, Mode);
    if (auto* Movement = MovementOf(Character); Movement && Movement->PredictsMoves())
    {
        PostState = Movement->CaptureMovementState();
        PostEdge = Movement->GetProcessedEdge();
        PostCrouch = Movement->bWantsToCrouch;
        JapanJumpReplayQA::Move(Movement, *this, Mode == PostUpdate_Replay, OriginalLocation, OriginalVelocity);
#if !UE_BUILD_SHIPPING
        static const bool Trace = FParse::Param(FCommandLine::Get(), TEXT("networkgameplay")) ||
            FParse::Param(FCommandLine::Get(), TEXT("networkvehicles"));
        if (Trace && Movement->TraceClientStep(TimeStamp))
            UE_LOG(LogJapanMovementQA, Display, TEXT("NETWORK move client epoch=%u timestamp=%.6f dt=%.6f stick=%d,%d flags=%u mode=%u accel=%s maxspeed=%.3f position=%s velocity=%s replay=%d first_edge=%u edges=%d applied_edge=%u action=%s action_time=%.6f pending_launch=%s"),
                Input.ActivityEpoch, TimeStamp, DeltaTime, Input.X, Input.Y, Input.Flags, Movement->PackNetworkMovementMode(), *Movement->GetCurrentAcceleration().ToString(),
                Movement->GetMaxSpeed(), *SavedLocation.ToString(), *SavedVelocity.ToString(), Mode == PostUpdate_Replay,
                Input.FirstEdge, Input.Edges.Num(), PostEdge, *PostState.Action.ToString(),
                CastChecked<AWandererCharacter>(Character)->GetActionTime(), *Movement->GetPendingLaunch().ToString());
#endif
    }
}

void FSavedMove_Japan::SetMoveFor(ACharacter* Character, float Dt, const FVector& Accel,
    FNetworkPredictionData_Client_Character& ClientData)
{
    Super::SetMoveFor(Character, Dt, Accel, ClientData);
    if (UJapanCharacterMovement* Movement = MovementOf(Character))
    {
        Input = Movement->ConsumeMoveInput(Dt);
        Movement->SetMoveInput(Input);
    }
}

void FSavedMove_Japan::PrepMoveFor(ACharacter* Character)
{
    Super::PrepMoveFor(Character);
    // Replay inputs against the corrected state. Restoring a predicted state here would undo the server's correction.
    if (UJapanCharacterMovement* Movement = MovementOf(Character)) Movement->SetMoveInput(Input);
}

bool FSavedMove_Japan::CanCombineWith(const FSavedMovePtr& NewMove, ACharacter* Character, float MaxDelta) const
{
    const auto& Next = static_cast<const FSavedMove_Japan&>(*NewMove);
    if (!Input.Edges.IsEmpty() || !Next.Input.Edges.IsEmpty() || Input.Flags != Next.Input.Flags ||
        Input.X != Next.Input.X || Input.Y != Next.Input.Y || Input.ActivityEpoch != Next.Input.ActivityEpoch) return false;
    if (const UJapanCharacterMovement* Movement = MovementOf(Character); Movement && Movement->PredictsMoves()) return false;
    return Super::CanCombineWith(NewMove, Character, MaxDelta);
}

bool FSavedMove_Japan::IsImportantMove(const FSavedMovePtr& LastAcked) const
{
    if (!Input.Edges.IsEmpty()) return true;
    if (LastAcked.IsValid())
    {
        const FJapanMoveInput& Previous = static_cast<const FSavedMove_Japan&>(*LastAcked).Input;
        if (Input.Flags != Previous.Flags || Input.X != Previous.X || Input.Y != Previous.Y) return true;
    }
    return Super::IsImportantMove(LastAcked);
}

void FJapanNetworkMoveData::ClientFillNetworkMoveData(const FSavedMove_Character& Move, ENetworkMoveType Type)
{
    FCharacterNetworkMoveData::ClientFillNetworkMoveData(Move, Type);
    Input = static_cast<const FSavedMove_Japan&>(Move).Input;
}

bool FJapanNetworkMoveData::Serialize(UCharacterMovementComponent& Movement, FArchive& Ar,
    UPackageMap* Map, ENetworkMoveType Type)
{
    return FCharacterNetworkMoveData::Serialize(Movement, Ar, Map, Type) && Input.Serialize(Ar);
}

void FJapanMoveResponse::ServerFillResponseData(const UCharacterMovementComponent& Movement,
    const FClientAdjustment& Adjustment)
{
    FCharacterMoveResponseDataContainer::ServerFillResponseData(Movement, Adjustment);
    ActivityEpoch = static_cast<const UJapanCharacterMovement&>(Movement).GetActivityEpoch();
    bHasRotation = IsCorrection();
    AcknowledgedEdge = static_cast<const UJapanCharacterMovement&>(Movement).PendingAcknowledgedEdge;
    Checkpoint = static_cast<const UJapanCharacterMovement&>(Movement).PendingCheckpoint;
    bHasCheckpoint = IsCorrection() && !Checkpoint.Bytes.IsEmpty() &&
        static_cast<const UJapanCharacterMovement&>(Movement).PendingCheckpointTime == Adjustment.TimeStamp;
    JapanJumpReplayQA::Sent(*this);
}

bool FJapanMoveResponse::Serialize(UCharacterMovementComponent& Movement, FArchive& Ar, UPackageMap* Map)
{
    if (!FCharacterMoveResponseDataContainer::Serialize(Movement, Ar, Map)) return false;
    Ar << AcknowledgedEdge << ActivityEpoch;
    if (!IsCorrection()) return !Ar.IsError();
    Ar.SerializeBits(&bHasCheckpoint, 1);
    return !bHasCheckpoint || Checkpoint.Serialize(Ar, Map);
}

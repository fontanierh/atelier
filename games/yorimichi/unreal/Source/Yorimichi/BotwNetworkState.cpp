#include "BotwNetworkState.h"
#include "WandererCharacter.h"
#include "WandererDefinition.h"
#include "JapanCharacterMovement.h"
#include "Components/SkeletalMeshComponent.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/MemoryWriter.h"

namespace
{
void Field(FArchive& Ar, float& Value)
{
    Ar << Value;
    if (!FMath::IsFinite(Value) || FMath::Abs(Value) > 1.e9f) Ar.SetError();
}
void Field(FArchive& Ar, int32& Value) { Ar << Value; }
void Field(FArchive& Ar, uint32& Value) { Ar << Value; }
void Field(FArchive& Ar, bool& Value) { Ar.SerializeBits(&Value, 1); }
void Field(FArchive& Ar, EBotwMoveMode& Value)
{
    uint8 Byte = uint8(Value); Ar << Byte;
    if (Byte > uint8(EBotwMoveMode::Swim)) Ar.SetError();
    else Value = EBotwMoveMode(Byte);
}
void Field(FArchive& Ar, FVector& Value)
{
    float X = Value.X, Y = Value.Y, Z = Value.Z;
    Field(Ar, X); Field(Ar, Y); Field(Ar, Z);
    if (Ar.IsLoading()) Value = FVector(X, Y, Z);
}
void Field(FArchive& Ar, FQuat& Value)
{
    float X = Value.X, Y = Value.Y, Z = Value.Z, W = Value.W;
    Field(Ar, X); Field(Ar, Y); Field(Ar, Z); Field(Ar, W);
    if (Ar.IsLoading())
    {
        Value = FQuat(X, Y, Z, W);
        if (FMath::Abs(Value.SizeSquared() - 1.) > .01) Ar.SetError();
        else Value.Normalize();
    }
}
}

void UBotwMoveSet::ApplyInputHolds(uint8 Flags)
{
    bAttackHeld = (Flags & FJapanMoveInput::AttackHeld) != 0;
    bGuardHeld = (Flags & FJapanMoveInput::GuardHeld) != 0;
    bJumpHeld = (Flags & FJapanMoveInput::JumpHeld) != 0;
}

void UBotwMoveSet::DropHolds()
{
    if (Character)
        if (auto* Movement = Cast<UJapanCharacterMovement>(Character->GetCharacterMovement());
            Movement && Movement->QueueMoveButton(TEXT("drop_holds"))) return;
    bAttackHeld = bGuardHeld = bJumpHeld = false;
}

void FBotwNetworkState::Capture(const UBotwMoveSet& Moves)
{
#define BOTW_FIELD(Type, Name) Name = Moves.Name;
#include "BotwNetworkFields.inl"
#undef BOTW_FIELD
    const AWandererCharacter& Rider = *Moves.Character;
    if (Rider.HasAuthority() && Moves.Target.IsValid()) { LockPoint = Moves.Target->GetActorLocation(); bLockPoint = true; }
    ActionSerial = Rider.ActionSerial;
    ActionBlendTime = Rider.ActionBlendTime; ActionTime = Rider.ActionTime; ActionDuration = Rider.ActionDuration;
    ActionSourceStartTime = Rider.ActionSourceStartTime; ActionPlayRate = Rider.ActionPlayRate;
    bActionLoops = Rider.bActionLoops; Stamina = Rider.Stamina;
    bImpactClimbable = Moves.Climbable(Moves.LastImpact);
    ImpactPoint = Moves.LastImpact.ImpactPoint; ImpactNormal = Moves.LastImpact.ImpactNormal;
    const auto* Movement = CastChecked<UJapanCharacterMovement>(Rider.GetCharacterMovement());
    bWantsToCrouch = Movement->bWantsToCrouch; PendingLaunch = Movement->GetPendingLaunch();
}

void FBotwNetworkState::Apply(UBotwMoveSet& Moves, const FJapanMoveCheckpoint& Checkpoint) const
{
    const bool HadGlider = Moves.bGliderShown;
#define BOTW_FIELD(Type, Name) Moves.Name = Name;
#include "BotwNetworkFields.inl"
#undef BOTW_FIELD
    AWandererCharacter& Rider = *Moves.Character;
    Rider.AnimationAction = Checkpoint.Action;
    Rider.ActionSerial = ActionSerial;
    Rider.ActionBlendTime = ActionBlendTime; Rider.ActionTime = ActionTime; Rider.ActionDuration = ActionDuration;
    Rider.ActionSourceStartTime = ActionSourceStartTime; Rider.ActionPlayRate = ActionPlayRate;
    Rider.bActionLoops = bActionLoops; Rider.Stamina = Stamina;
    // Rebuild authored offsets from replay state; never transplant the listen host mesh smoothing offset.
    Moves.bMeshTurned = Moves.bMeshOffset = true;
    Moves.AdvanceMeshOffset(0.f);
    Moves.Target = Checkpoint.Target; Moves.LungeTarget = Checkpoint.LungeTarget;
    // Only climbable static contacts can influence the next move. No per-process actor name crosses the wire.
    Moves.LastImpact = FHitResult();
    Moves.LastImpact.bBlockingHit = bImpactClimbable;
    Moves.LastImpact.ImpactPoint = ImpactPoint; Moves.LastImpact.ImpactNormal = ImpactNormal;
    auto* Movement = CastChecked<UJapanCharacterMovement>(Rider.GetCharacterMovement());
    Movement->bWantsToCrouch = bWantsToCrouch; Movement->SetPendingLaunch(PendingLaunch);
    // Reconcile physical attachments explicitly; restoring a visibility flag alone leaves yesterday's component state.
    for (auto& Pair : Moves.Slots)
    {
        const bool InHand = bArmed && !Pair.Value.Hand.IsNone();
        if (Pair.Value.bInHand != InHand) { Pair.Value.bInHand = InHand; Moves.Attach(Pair.Key); }
    }
    Moves.bGliderShown = HadGlider;
    Moves.ShowGlider(bGliderShown);
    Moves.AdvanceGliderGrip(0.f);
}

bool FBotwNetworkState::Serialize(FArchive& Ar)
{
    uint16 Schema = 1;
    Ar << Schema;
    if (Schema != 1) { Ar.SetError(); return false; }
#define BOTW_FIELD(Type, Name) Field(Ar, Name);
#include "BotwNetworkFields.inl"
#undef BOTW_FIELD
    Field(Ar, ActionSerial); Field(Ar, ActionBlendTime); Field(Ar, ActionTime); Field(Ar, ActionDuration);
    Field(Ar, ActionSourceStartTime); Field(Ar, ActionPlayRate); Field(Ar, bActionLoops);
    Field(Ar, Stamina.Units); Field(Ar, Stamina.Capacity); Field(Ar, Stamina.RecoveryDelay);
    Field(Ar, Stamina.SprintSeconds); Field(Ar, Stamina.RefillSeconds); Field(Ar, Stamina.Delay);
    Field(Ar, Stamina.Exhausted); Field(Ar, Stamina.Sprinting);
    Field(Ar, bWantsToCrouch); Field(Ar, PendingLaunch);
    Field(Ar, bImpactClimbable); Field(Ar, ImpactPoint); Field(Ar, ImpactNormal);
    if (Stamina.Capacity != FSprintStamina().Capacity || Stamina.Units < 0.f || Stamina.Units > Stamina.Capacity ||
        Stamina.SprintSeconds <= 0.f || Stamina.RefillSeconds <= 0.f || ActionPlayRate < 0.f) Ar.SetError();
    return !Ar.IsError();
}

FJapanMoveCheckpoint UBotwMoveSet::CaptureNetworkState() const
{
    FJapanMoveCheckpoint Checkpoint;
    if (!Character) return Checkpoint;
    FBotwNetworkState State; State.Capture(*this);
    FMemoryWriter Writer(Checkpoint.Bytes, true);
    if (!State.Serialize(Writer) || Checkpoint.Bytes.Num() > FJapanMoveCheckpoint::MaximumBytes)
    {
        UE_LOG(LogTemp, Error, TEXT("Network movement checkpoint invalid or exceeds %u bytes"), FJapanMoveCheckpoint::MaximumBytes);
        Checkpoint.Bytes.Reset(); return Checkpoint;
    }
    Checkpoint.Action = Character->AnimationAction;
    Checkpoint.Target = Target; Checkpoint.LungeTarget = LungeTarget;
    return Checkpoint;
}

void UBotwMoveSet::ClearNetworkReactionTargets()
{
    // A mounted strike starts a fresh, untargeted foot reaction. Its handoff
    // must never depend on the network mapping of an attacker or old cut target.
    Target = nullptr; LungeTarget = nullptr;
    bLockPoint = bLungePoint = false; LungeTime = 0.f;
}

bool UBotwMoveSet::ApplyNetworkState(const FJapanMoveCheckpoint& Checkpoint)
{
    if (!Character || Checkpoint.Bytes.IsEmpty() || Checkpoint.Bytes.Num() > FJapanMoveCheckpoint::MaximumBytes) return false;
    if (!Checkpoint.Action.IsNone() && (!Character->Definition || !Character->Definition->FindAction(Checkpoint.Action))) return false;
    FMemoryReader Reader(Checkpoint.Bytes, true);
    FBotwNetworkState State;
    if (!State.Serialize(Reader) || Reader.Tell() != Reader.TotalSize()) return false;
    State.Apply(*this, Checkpoint);
    return true;
}

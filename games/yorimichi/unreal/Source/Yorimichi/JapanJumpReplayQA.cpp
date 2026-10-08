#include "JapanJumpReplayQA.h"
#include "JapanCharacterMovement.h"
#include "JapanMovementNet.h"
#include "WandererCharacter.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "TimerManager.h"

#if !UE_BUILD_SHIPPING
namespace
{
int32 Case()
{
    static const int32 Value = [] { int32 N = -1; FParse::Value(FCommandLine::Get(), TEXT("networkjumpreplay="), N); return N; }();
    return Value;
}
struct FProbe
{
    TWeakObjectPtr<UJapanCharacterMovement> Movement;
    uint32 Epoch = 0;
    float PreviousStamp = -1.f, Takeoff = -1.f, FirstAir = -1.f, Target = -1.f, Latest = -1.f;
    double Began = 0.;
    bool Armed = false, Scheduled = false, Injecting = false, Done = false, Replayed = false;
    bool AckApplied = false, PendingBeforeAck = false;
    int32 Applications = 0, SavedBeforeAck = 0;
    float FirstSavedBeforeAck = -1.f;
    FString Error;
    FString Folder;
    TArray<FJapanMoveResponse> Responses;
    TArray<TSharedPtr<FJsonValue>> Comparisons;
    FJapanMoveResponse Selected, Ack;
};
FProbe Probe;
TArray<TSharedPtr<FJsonValue>> HostResponses;
TWeakObjectPtr<UJapanCharacterMovement> HostMovement;
uint32 HostEpoch = 0;
double HostBegan = 0., HostFirstForce = 0., HostLastForce = 0.;
int32 HostForced = 0, HostAirMoves = 0;
bool HostStopped = false;

TSharedPtr<FJsonObject> ResponseRow(const FJapanMoveResponse& Response)
{
    auto O = MakeShared<FJsonObject>();
    O->SetNumberField(TEXT("epoch"), Response.ActivityEpoch);
    O->SetNumberField(TEXT("timestamp"), Response.ClientAdjustment.TimeStamp);
    O->SetNumberField(TEXT("edge"), Response.AcknowledgedEdge);
    O->SetBoolField(TEXT("correction"), Response.IsCorrection());
    // Good ACKs carry no position/checkpoint fields on the wire.
    if (!Response.IsCorrection()) return O;
    O->SetNumberField(TEXT("mode"), Response.ClientAdjustment.MovementMode);
    O->SetNumberField(TEXT("z"), Response.ClientAdjustment.NewLoc.Z);
    O->SetNumberField(TEXT("vz"), Response.ClientAdjustment.NewVel.Z);
    O->SetBoolField(TEXT("checkpoint"), Response.bHasCheckpoint);
    O->SetNumberField(TEXT("checkpoint_bytes"), Response.Checkpoint.Bytes.Num());
    return O;
}
void Schedule(UJapanCharacterMovement* Movement)
{
    if (!Probe.Armed || Probe.Scheduled || Probe.Target < 0.f || Probe.Takeoff < 0.f || Probe.Latest < Probe.Takeoff + .12f) return;
    const auto* Packet = Probe.Responses.FindByPredicate([](const FJapanMoveResponse& R)
    { return R.ActivityEpoch == Probe.Epoch && R.ClientAdjustment.TimeStamp == Probe.Target && R.IsCorrection() && R.bHasCheckpoint; });
    if (!Packet) return;
    if (Case() >= 3)
    {
        const auto* Ack = Probe.Responses.FindByPredicate([](const FJapanMoveResponse& R)
        { return R.ActivityEpoch == Probe.Epoch && R.IsGoodMove() && R.ClientAdjustment.TimeStamp > Probe.Target &&
            R.ClientAdjustment.TimeStamp <= Probe.Latest; });
        if (!Ack) return;
        Probe.Ack = *Ack;
    }
    Probe.Selected = *Packet; Probe.Scheduled = true;
    Movement->GetWorld()->GetTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(Movement, [Movement]
    {
        if (Movement->GetActivityEpoch() != Probe.Epoch) { Probe.Error = TEXT("Jump replay epoch changed before injection"); return; }
        Probe.Injecting = true;
        Movement->ClientHandleMoveResponse(Probe.Selected);
        const auto* Client = Movement->GetPredictionData_Client_Character();
        if (!Client->LastAckedMove.IsValid() || Client->LastAckedMove->TimeStamp != Probe.Target)
            Probe.Error = TEXT("Jump replay correction was not acknowledged");
        else
        {
            ++Probe.Applications;
            if (Case() >= 3)
            {
                Probe.PendingBeforeAck = Client->bUpdatePosition;
                Probe.SavedBeforeAck = Client->SavedMoves.Num();
                if (!Client->SavedMoves.IsEmpty()) Probe.FirstSavedBeforeAck = Client->SavedMoves[0]->TimeStamp;
                Movement->ClientHandleMoveResponse(Probe.Ack);
                Probe.AckApplied = Client->LastAckedMove.IsValid() && Client->LastAckedMove->TimeStamp == Probe.Ack.ClientAdjustment.TimeStamp;
            }
            const bool ExplicitReplay = Movement->ClientUpdatePositionAfterServerUpdate();
            // A production ordering fix may replay inside the next-response handler.
            // PostUpdate receipts still prove which moves actually ran.
            Probe.Replayed = ExplicitReplay || !Probe.Comparisons.IsEmpty();
        }
        Probe.Injecting = false; Probe.Armed = false; Probe.Done = true; Probe.Responses.Reset();
        if (!FFileHelper::SaveStringToFile(FString::FromInt(Probe.Epoch), *(Probe.Folder / TEXT("jump-replay-done.txt"))))
            Probe.Error = TEXT("Could not close jump replay host window");
    }));
}
}

bool JapanJumpReplayQA::Enabled() { return Case() >= 0 && Case() <= 5 && FParse::Param(FCommandLine::Get(), TEXT("networkgameplay")); }
void JapanJumpReplayQA::Arm(UJapanCharacterMovement* Movement, const FString& Folder)
{
    if (!Enabled() || !Movement || Movement->GetNetMode() != NM_Client || Probe.Armed || Probe.Done) return;
    Probe.Movement = Movement; Probe.Epoch = Movement->GetActivityEpoch(); Probe.Armed = true; Probe.Began = FPlatformTime::Seconds();
    Probe.Folder = Folder;
    // Same-machine diagnostic scheduling only. Acceptance still requires the
    // real server response, its serialized checkpoint and actual CMC replay.
    if (!FFileHelper::SaveStringToFile(FString::FromInt(Probe.Epoch), *(Folder / TEXT("jump-replay-arm.txt"))))
        Probe.Error = TEXT("Could not arm jump replay host window");
}
void JapanJumpReplayQA::ObserveHost(UJapanCharacterMovement* Movement, const FString& Folder)
{
    if (!Enabled() || !Movement || HostStopped) return;
    FString EpochText;
    if (!HostEpoch)
    {
        if (!FFileHelper::LoadFileToString(EpochText, *(Folder / TEXT("jump-replay-arm.txt"))) ||
            EpochText != FString::FromInt(Movement->GetActivityEpoch())) return;
        HostMovement = Movement; HostEpoch = Movement->GetActivityEpoch(); HostBegan = FPlatformTime::Seconds();
    }
    HostStopped = Movement->GetActivityEpoch() != HostEpoch || FPlatformTime::Seconds() - HostBegan >= 3. ||
        (FFileHelper::LoadFileToString(EpochText, *(Folder / TEXT("jump-replay-done.txt"))) && EpochText == FString::FromInt(HostEpoch));
}
bool JapanJumpReplayQA::Tick(FString& Error)
{
    if (!Enabled()) return true;
    if (Probe.Armed && FPlatformTime::Seconds() - Probe.Began > 3.) Probe.Error = TEXT("Jump replay correction/replay deadline expired");
    if (!Probe.Error.IsEmpty()) { Error = Probe.Error; return false; }
    return true;
}
bool JapanJumpReplayQA::ForceResponse(UJapanCharacterMovement* Movement)
{
    if (!Enabled() || HostStopped || !HostEpoch || Movement != HostMovement.Get() || Movement->GetActivityEpoch() != HostEpoch) return false;
    const double Age = FPlatformTime::Seconds() - HostBegan;
    if (Age >= 3.) { HostStopped = true; return false; }
    // Paired cases stop forcing just after the chosen boundary, so a later
    // response is a real ordinary good ACK, not a fabricated packet.
    if (Case() >= 3 && Movement->IsFalling() && Movement->Velocity.Z > 0. && ++HostAirMoves > Case() - 3)
    { HostStopped = true; return false; }
    if (!HostForced++) HostFirstForce = Age;
    HostLastForce = Age;
    Movement->GetPredictionData_Server_Character()->bForceClientUpdate = true;
    return true;
}
void JapanJumpReplayQA::Sent(const FJapanMoveResponse& Response)
{
    if (!Enabled() || HostResponses.Num() >= 512) return;
    HostResponses.Add(MakeShared<FJsonValueObject>(ResponseRow(Response)));
}
bool JapanJumpReplayQA::Defer(UJapanCharacterMovement* Movement, const FJapanMoveResponse& Response)
{
    if (!Enabled() || !Probe.Armed || Probe.Injecting || Movement != Probe.Movement.Get()) return false;
    if (Probe.Responses.Num() >= 128) Probe.Error = TEXT("Jump replay response queue overflow");
    else Probe.Responses.Add(Response);
    Schedule(Movement);
    return true;
}
void JapanJumpReplayQA::Move(UJapanCharacterMovement* Movement, const FSavedMove_Japan& Saved, bool Replay,
    const FVector& OriginalLocation, const FVector& OriginalVelocity)
{
    if (!Enabled() || Movement->GetNetMode() != NM_Client) return;
    if (Replay)
    {
        if (!Probe.Injecting) return;
        if (Probe.Comparisons.Num() >= 128) { Probe.Error = TEXT("Jump replay move receipt overflow"); return; }
        auto O = MakeShared<FJsonObject>();
        O->SetNumberField(TEXT("timestamp"), Saved.TimeStamp);
        O->SetNumberField(TEXT("dt"), Saved.DeltaTime);
        O->SetNumberField(TEXT("epoch"), Saved.Input.ActivityEpoch);
        O->SetNumberField(TEXT("mode"), Saved.EndPackedMovementMode);
        O->SetNumberField(TEXT("original_z"), OriginalLocation.Z); O->SetNumberField(TEXT("replayed_z"), Saved.SavedLocation.Z);
        O->SetNumberField(TEXT("original_vz"), OriginalVelocity.Z); O->SetNumberField(TEXT("replayed_vz"), Saved.SavedVelocity.Z);
        Probe.Comparisons.Add(MakeShared<FJsonValueObject>(O));
        return;
    }
    if (Probe.Armed && Saved.Input.ActivityEpoch == Probe.Epoch)
    {
        Probe.Latest = Saved.TimeStamp;
        if (Probe.Takeoff < 0.f && Saved.Input.Edges.Contains(uint8(FJapanMoveInput::ButtonIndex(TEXT("jump")))))
        {
            if (Saved.EndPackedMovementMode != MOVE_Falling || Saved.SavedVelocity.Z <= 0. || Saved.PostState.Action != TEXT("Jump"))
                Probe.Error = TEXT("Jump replay did not capture an actual upward takeoff");
            Probe.Takeoff = Saved.TimeStamp;
            if (Case() % 3 == 0) Probe.Target = Probe.PreviousStamp;
            if (Case() % 3 == 1) Probe.Target = Saved.TimeStamp;
        }
        else if (Probe.Takeoff > 0.f && Probe.FirstAir < 0.f)
        {
            Probe.FirstAir = Saved.TimeStamp;
            if (Case() % 3 == 2) Probe.Target = Saved.TimeStamp;
        }
        Schedule(Movement);
    }
    Probe.PreviousStamp = Saved.TimeStamp;
}
TSharedPtr<FJsonObject> JapanJumpReplayQA::Receipt(bool Server)
{
    auto O = MakeShared<FJsonObject>();
    O->SetBoolField(TEXT("enabled"), Enabled()); O->SetNumberField(TEXT("case"), Case());
    if (Server)
    {
        O->SetArrayField(TEXT("responses"), HostResponses);
        O->SetNumberField(TEXT("forced_epoch"), HostEpoch); O->SetNumberField(TEXT("forced_count"), HostForced);
        O->SetNumberField(TEXT("first_force_seconds"), HostFirstForce); O->SetNumberField(TEXT("last_force_seconds"), HostLastForce);
        O->SetBoolField(TEXT("window_closed"), HostStopped);
    }
    else
    {
        O->SetBoolField(TEXT("complete"), Probe.Done); O->SetBoolField(TEXT("replayed"), Probe.Replayed);
        O->SetStringField(TEXT("error"), Probe.Error); O->SetNumberField(TEXT("applications"), Probe.Applications);
        O->SetNumberField(TEXT("epoch"), Probe.Epoch); O->SetNumberField(TEXT("takeoff"), Probe.Takeoff);
        O->SetNumberField(TEXT("first_air"), Probe.FirstAir); O->SetNumberField(TEXT("target"), Probe.Target);
        O->SetObjectField(TEXT("selected"), ResponseRow(Probe.Selected));
        if (Case() >= 3)
        {
            O->SetObjectField(TEXT("ack"), ResponseRow(Probe.Ack));
            O->SetBoolField(TEXT("ack_applied"), Probe.AckApplied); O->SetBoolField(TEXT("pending_before_ack"), Probe.PendingBeforeAck);
            O->SetNumberField(TEXT("saved_before_ack"), Probe.SavedBeforeAck);
            O->SetNumberField(TEXT("first_saved_before_ack"), Probe.FirstSavedBeforeAck);
        }
        O->SetArrayField(TEXT("moves"), Probe.Comparisons);
    }
    return O;
}
#else
bool JapanJumpReplayQA::Enabled() { return false; }
void JapanJumpReplayQA::Arm(UJapanCharacterMovement*, const FString&) {}
void JapanJumpReplayQA::ObserveHost(UJapanCharacterMovement*, const FString&) {}
bool JapanJumpReplayQA::Tick(FString&) { return true; }
bool JapanJumpReplayQA::ForceResponse(UJapanCharacterMovement*) { return false; }
void JapanJumpReplayQA::Sent(const FJapanMoveResponse&) {}
bool JapanJumpReplayQA::Defer(UJapanCharacterMovement*, const FJapanMoveResponse&) { return false; }
void JapanJumpReplayQA::Move(UJapanCharacterMovement*, const FSavedMove_Japan&, bool, const FVector&, const FVector&) {}
TSharedPtr<FJsonObject> JapanJumpReplayQA::Receipt(bool) { return MakeShared<FJsonObject>(); }
#endif

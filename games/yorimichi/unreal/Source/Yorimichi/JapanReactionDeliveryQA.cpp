#include "JapanReactionDeliveryQA.h"
#if !UE_BUILD_SHIPPING
#include "JapanCharacterMovement.h"
#include "JapanSession.h"
#include "WandererCharacter.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "Misc/CommandLine.h"
#include "Misc/SecureHash.h"

namespace JapanReactionDeliveryQA
{
namespace
{
struct FDeliveryRecord
{
    TArray<TSharedPtr<FJsonValue>> Rows;
    uint32 Overflow = 0;
};
TMap<TWeakObjectPtr<const UJapanCharacterMovement>, FDeliveryRecord> DeliveryRecords;
bool Enabled()
{
    static const bool Value = FParse::Param(FCommandLine::Get(), TEXT("networkreactiondelivery"));
    return Value;
}
TSharedPtr<FJsonObject> DeliveryRow(const UJapanCharacterMovement* Movement, const TCHAR* Event)
{
    if (!Enabled() || !Movement || !Movement->GetWorld()) return {};
    const auto* Rider = Cast<AWandererCharacter>(Movement->GetOwner());
    if (!Rider || Rider->IsNpc()) return {};
    auto& Record = DeliveryRecords.FindOrAdd(Movement);
    if (Record.Rows.Num() >= 4096) { ++Record.Overflow; return {}; }
    auto Data = MakeShared<FJsonObject>();
    Data->SetStringField(TEXT("event"), Event);
    Data->SetNumberField(TEXT("at"), FPlatformTime::Seconds());
    Data->SetNumberField(TEXT("world_time"), Movement->GetWorld()->GetTimeSeconds());
    Data->SetNumberField(TEXT("epoch"), Movement->GetActivityEpoch());
    Data->SetBoolField(TEXT("authority"), Rider->HasAuthority());
    Data->SetBoolField(TEXT("local"), Rider->IsLocallyControlled());
    Data->SetNumberField(TEXT("remote_role"), int32(Rider->GetRemoteRole()));
    Record.Rows.Add(MakeShared<FJsonValueObject>(Data));
    return Data;
}
}
void State(const UJapanCharacterMovement* Movement, const TCHAR* Event, bool Pending, bool Captured, float Stamp)
{
    if (auto Data = DeliveryRow(Movement, Event))
    {
        Data->SetBoolField(TEXT("pending"), Pending);
        Data->SetBoolField(TEXT("captured"), Captured);
        Data->SetNumberField(TEXT("stamp"), Stamp);
        Data->SetNumberField(TEXT("checkpoint_stamp"), Movement->PendingCheckpointTime);
        Data->SetStringField(TEXT("action"), Movement->PendingCheckpoint.Action.ToString());
        if(const auto* Rider=Cast<AWandererCharacter>(Movement->GetOwner()))
            Data->SetStringField(TEXT("live_action"),Rider->GetAnimationAction().ToString());
    }
}
void Response(const UJapanCharacterMovement* Movement, const TCHAR* Event, const FJapanMoveResponse& ResponseData,
    float CorrectionCm)
{
    if (auto Data = DeliveryRow(Movement, Event))
    {
        Data->SetNumberField(TEXT("response_epoch"), ResponseData.ActivityEpoch);
        Data->SetNumberField(TEXT("stamp"), ResponseData.ClientAdjustment.TimeStamp);
        Data->SetNumberField(TEXT("edge"), ResponseData.AcknowledgedEdge);
        Data->SetBoolField(TEXT("correction"), ResponseData.IsCorrection());
        Data->SetBoolField(TEXT("checkpoint"), ResponseData.bHasCheckpoint);
        if (CorrectionCm >= 0.f) Data->SetNumberField(TEXT("correction_cm"), CorrectionCm);
        Data->SetNumberField(TEXT("reaction_through"), ResponseData.bHasCheckpoint ? ResponseData.Checkpoint.ReactionThrough : 0);
        Data->SetStringField(TEXT("action"), ResponseData.bHasCheckpoint ? ResponseData.Checkpoint.Action.ToString() : FString());
        FString Digest;
        if (ResponseData.bHasCheckpoint)
        {
            uint8 Hash[20];
            FSHA1::HashBuffer(ResponseData.Checkpoint.Bytes.GetData(), ResponseData.Checkpoint.Bytes.Num(), Hash);
            Digest = BytesToHex(Hash, 20).ToLower();
        }
        Data->SetStringField(TEXT("digest"), Digest);
    }
}
void Scheduled(const UJapanCharacterMovement* Movement, const TCHAR* Event,
    const FJapanScheduledReaction& Reaction, const FJapanReactionMarker* Marker)
{
    if (auto Data = DeliveryRow(Movement, Event))
    {
        Data->SetNumberField(TEXT("reaction_epoch"), Reaction.Epoch);
        Data->SetNumberField(TEXT("sequence"), Reaction.Sequence);
        Data->SetNumberField(TEXT("resolved_generation"), Reaction.Resolved.Generation);
        Data->SetNumberField(TEXT("resolved_stamp"), Reaction.Resolved.Time);
        Data->SetStringField(TEXT("reaction_action"), Reaction.Value.Action.ToString());
        uint8 Hash[20]; FSHA1::HashBuffer(Reaction.Value.Bytes.GetData(), Reaction.Value.Bytes.Num(), Hash);
        Data->SetStringField(TEXT("payload_digest"), BytesToHex(Hash, 20).ToLower());
        Data->SetNumberField(TEXT("payload_bytes"), Reaction.Value.Bytes.Num());
        Data->SetNumberField(TEXT("applied_through"), Movement->GetScheduledReactionThrough());
        Data->SetBoolField(TEXT("replay"), Movement->IsReplaying());
        const auto Clock = Movement->GetReactionMoveStamp();
        Data->SetNumberField(TEXT("host_move_generation"), Clock.Generation);
        Data->SetNumberField(TEXT("host_move_stamp"), Clock.Time);
        if (Marker)
        {
            Data->SetNumberField(TEXT("previous_generation"), Marker->Origin.Previous.Generation);
            Data->SetNumberField(TEXT("previous_stamp"), Marker->Origin.Previous.Time);
            Data->SetNumberField(TEXT("end_generation"), Marker->Origin.End.Generation);
            Data->SetNumberField(TEXT("end_stamp"), Marker->Origin.End.Time);
            Data->SetNumberField(TEXT("saved_dt"), Marker->Origin.DeltaTime);
            Data->SetNumberField(TEXT("edge_before"), Marker->EdgeBefore);
            Data->SetNumberField(TEXT("edge_after"), Marker->EdgeAfter);
        }
    }
}
TSharedPtr<FJsonObject> LargestCorrection(const FJapanMovementStats& Stats)
{
    if (Stats.LargestCorrectionCm <= 0.f) return {};
    const auto& Sample = Stats.LargestCorrection;
    auto Data = MakeShared<FJsonObject>();
    Data->SetNumberField(TEXT("epoch"), Sample.Epoch);
    Data->SetNumberField(TEXT("stamp"), Sample.Timestamp);
    Data->SetNumberField(TEXT("dt"), Sample.DeltaTime);
    Data->SetNumberField(TEXT("world_time"), Sample.WorldTime);
    Data->SetNumberField(TEXT("through_edge"), Sample.ThroughEdge);
    Data->SetNumberField(TEXT("predicted_edge"), Sample.PredictedEdge);
    Data->SetNumberField(TEXT("predicted_mode"), Sample.PredictedMode);
    Data->SetNumberField(TEXT("authoritative_mode"), Sample.AuthoritativeMode);
    Data->SetNumberField(TEXT("checkpoint_bytes"), Sample.CheckpointBytes);
    auto Vector = [&](const TCHAR* Name, const FVector& Value)
    {
        Data->SetArrayField(Name, {MakeShared<FJsonValueNumber>(Value.X),
            MakeShared<FJsonValueNumber>(Value.Y), MakeShared<FJsonValueNumber>(Value.Z)});
    };
    // Numeric XYZ retains the saved sample's precision; ToString rounds small
    // errors at large world coordinates and cannot establish their direction.
    Vector(TEXT("predicted_position"), Sample.PredictedLocation);
    Vector(TEXT("authoritative_position"), Sample.AuthoritativeLocation);
    Vector(TEXT("predicted_velocity"), Sample.PredictedVelocity);
    Vector(TEXT("authoritative_velocity"), Sample.AuthoritativeVelocity);
    Vector(TEXT("delta_cm"), Sample.AuthoritativeLocation - Sample.PredictedLocation);
    Data->SetNumberField(TEXT("position_error_cm"), FVector::Dist(Sample.PredictedLocation, Sample.AuthoritativeLocation));
    Data->SetNumberField(TEXT("velocity_error_cm_s"), FVector::Dist(Sample.PredictedVelocity, Sample.AuthoritativeVelocity));
    Data->SetStringField(TEXT("predicted_action"), Sample.PredictedAction.ToString());
    Data->SetStringField(TEXT("authoritative_action"), Sample.AuthoritativeAction.ToString());
    return Data;
}
TSharedPtr<FJsonObject> Snapshot(const UJapanCharacterMovement* Movement)
{
    auto Data = MakeShared<FJsonObject>();
    Data->SetStringField(TEXT("scope"), TEXT("Development-only, same-machine platform clock; serialized is not received"));
    Data->SetBoolField(TEXT("enabled"), Enabled());
    if (!Enabled() || !Movement) return Data;
    Data->SetBoolField(TEXT("packed_responses"), Movement->ShouldUsePackedMovementRPCs());
    Data->SetBoolField(TEXT("scheduled_reactions"), true);
    auto ScheduledStats = MakeShared<FJsonObject>();
    const auto& Stats = Movement->GetScheduledReactionStats();
    ScheduledStats->SetNumberField(TEXT("issued"), Stats.Issued);
    ScheduledStats->SetNumberField(TEXT("received"), Stats.Received);
    ScheduledStats->SetNumberField(TEXT("applied"), Stats.Applied);
    ScheduledStats->SetNumberField(TEXT("replayed"), Stats.Replayed);
    ScheduledStats->SetNumberField(TEXT("forced"), Stats.Forced);
    ScheduledStats->SetNumberField(TEXT("invalid_payloads"), Stats.InvalidPayloads);
    ScheduledStats->SetNumberField(TEXT("invalid_origins"), Stats.InvalidOrigins);
    ScheduledStats->SetNumberField(TEXT("failed_apply"), Stats.FailedApply);
    ScheduledStats->SetNumberField(TEXT("failed_restore"), Stats.FailedRestore);
    ScheduledStats->SetNumberField(TEXT("recoveries"), Stats.Recoveries);
    ScheduledStats->SetNumberField(TEXT("rejected_resets"), Stats.RejectedResets);
    ScheduledStats->SetNumberField(TEXT("rejected_recoveries"), Stats.RejectedRecoveries);
    ScheduledStats->SetNumberField(TEXT("lethal_superseded"), Stats.LethalSuperseded);
    ScheduledStats->SetNumberField(TEXT("folded_slices"), Stats.FoldedSlices);
    ScheduledStats->SetNumberField(TEXT("suppressed_attacks"), Stats.SuppressedAttacks);
    ScheduledStats->SetNumberField(TEXT("suppressed_defence_inputs"), Stats.SuppressedDefenceInputs);
    ScheduledStats->SetNumberField(TEXT("known"), Movement->GetScheduledReactionKnown());
    ScheduledStats->SetNumberField(TEXT("through"), Movement->GetScheduledReactionThrough());
    Data->SetObjectField(TEXT("scheduled_stats"), ScheduledStats);
    Data->SetNumberField(TEXT("minimum_adjustment_interval"),FMath::Min(Movement->NetworkMinTimeBetweenClientAdjustments,Movement->NetworkMinTimeBetweenClientAdjustmentsLargeCorrection));
    const auto* Rider = Cast<AWandererCharacter>(Movement->GetOwner());
    const auto* Person = Rider ? Rider->GetPlayerState<AJapanPlayerState>() : nullptr;
    Data->SetStringField(TEXT("player_id"), Person ? Person->SessionPlayerId : FString());
    Data->SetArrayField(TEXT("rows"),TArray<TSharedPtr<FJsonValue>>());
    Data->SetNumberField(TEXT("overflow"),0);
    if (const auto* Record = DeliveryRecords.Find(Movement))
    {
        Data->SetArrayField(TEXT("rows"), Record->Rows);
        Data->SetNumberField(TEXT("overflow"), Record->Overflow);
    }
    return Data;
}
}
#else
void JapanReactionDeliveryQA::State(const UJapanCharacterMovement*, const TCHAR*, bool, bool, float) {}
void JapanReactionDeliveryQA::Response(const UJapanCharacterMovement*, const TCHAR*, const FJapanMoveResponse&, float) {}
void JapanReactionDeliveryQA::Scheduled(const UJapanCharacterMovement*, const TCHAR*, const FJapanScheduledReaction&, const FJapanReactionMarker*) {}
TSharedPtr<FJsonObject> JapanReactionDeliveryQA::Snapshot(const UJapanCharacterMovement*) { return {}; }
TSharedPtr<FJsonObject> JapanReactionDeliveryQA::LargestCorrection(const FJapanMovementStats&) { return {}; }
#endif

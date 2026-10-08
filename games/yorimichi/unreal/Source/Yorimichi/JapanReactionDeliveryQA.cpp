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
void Response(const UJapanCharacterMovement* Movement, const TCHAR* Event, const FJapanMoveResponse& ResponseData)
{
    if (auto Data = DeliveryRow(Movement, Event))
    {
        Data->SetNumberField(TEXT("response_epoch"), ResponseData.ActivityEpoch);
        Data->SetNumberField(TEXT("stamp"), ResponseData.ClientAdjustment.TimeStamp);
        Data->SetNumberField(TEXT("edge"), ResponseData.AcknowledgedEdge);
        Data->SetBoolField(TEXT("correction"), ResponseData.IsCorrection());
        Data->SetBoolField(TEXT("checkpoint"), ResponseData.bHasCheckpoint);
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
TSharedPtr<FJsonObject> Snapshot(const UJapanCharacterMovement* Movement)
{
    auto Data = MakeShared<FJsonObject>();
    Data->SetStringField(TEXT("scope"), TEXT("Development-only, same-machine platform clock; serialized is not received"));
    Data->SetBoolField(TEXT("enabled"), Enabled());
    if (!Enabled() || !Movement) return Data;
    Data->SetBoolField(TEXT("packed_responses"), Movement->ShouldUsePackedMovementRPCs());
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
void JapanReactionDeliveryQA::Response(const UJapanCharacterMovement*, const TCHAR*, const FJapanMoveResponse&) {}
TSharedPtr<FJsonObject> JapanReactionDeliveryQA::Snapshot(const UJapanCharacterMovement*) { return {}; }
#endif

#include "JapanVehicleTelemetry.h"
#if !UE_BUILD_SHIPPING
#include "WandererCharacter.h"
#include "JapanSession.h"
#include "JapanMovementNet.h"
#include "BikeComponent.h"
#include "SailboatComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Misc/CommandLine.h"

namespace
{
bool Enabled()
{
    static const bool Value=FParse::Param(FCommandLine::Get(),TEXT("networkvehicles"));
    return Value;
}
struct FRecord
{
    TArray<TSharedPtr<FJsonValue>> Moves, Actions, Requests, Crashes, RejectedMoves, OldAcceptedMoves;
    uint32 Rejected=0, OldAccepted=0, Checkpoints=0, InvalidCheckpoints=0, Presentations=0, Overflow=0;
    double LastPresentation=-1.;
};
TWeakObjectPtr<UWorld> ObservedWorld;
TMap<TWeakObjectPtr<const AWandererCharacter>,FRecord> Records;
FRecord* Get(const AWandererCharacter* Rider)
{
    if(!Enabled()||!Rider)return nullptr;
    if(ObservedWorld.Get()!=Rider->GetWorld())
    {ObservedWorld=Rider->GetWorld();Records.Reset();}
    return &Records.FindOrAdd(Rider);
}
void Append(FRecord& Record,TArray<TSharedPtr<FJsonValue>>& Rows,const TSharedPtr<FJsonObject>& Row)
{
    if(Rows.Num()>=4096){++Record.Overflow;return;}
    Rows.Add(MakeShared<FJsonValueObject>(Row));
}
TSharedPtr<FJsonObject> Row(const AWandererCharacter* Rider)
{
    auto Result=MakeShared<FJsonObject>();
    Result->SetNumberField(TEXT("at"),Rider->GetWorld()->GetTimeSeconds());
    Result->SetNumberField(TEXT("platform_at"),FPlatformTime::Seconds());
    Result->SetNumberField(TEXT("epoch"),Rider->GetActivityEpoch());
    Result->SetNumberField(TEXT("activity"),uint8(Rider->GetNetworkActivity()));
    return Result;
}
}
void JapanVehicleTelemetry::Reset(UWorld* World)
{if(Enabled()){ObservedWorld=World;Records.Reset();}}
void JapanVehicleTelemetry::Move(AWandererCharacter* Rider,const FJapanMoveInput& Input,float Dt,bool Replay,
    const FVector& Before,float BeforeYaw)
{
    auto* Record=Get(Rider);if(!Record)return;
    const auto Activity=Rider->GetNetworkActivity();
    if(Activity!=EJapanActivity::Bike&&Activity!=EJapanActivity::Sailboat)return;
    auto Data=Row(Rider);
    Data->SetNumberField(TEXT("input_epoch"),Input.ActivityEpoch);
    Data->SetNumberField(TEXT("dt"),Dt);Data->SetBoolField(TEXT("replay"),Replay);
    Data->SetNumberField(TEXT("flags"),Input.Flags);
    Data->SetNumberField(TEXT("x"),Input.X);Data->SetNumberField(TEXT("y"),Input.Y);
    Data->SetNumberField(TEXT("distance_cm"),FVector::Dist2D(Before,Rider->GetActorLocation()));
    Data->SetNumberField(TEXT("turn_degrees"),FMath::FindDeltaAngleDegrees(BeforeYaw,Rider->GetActorRotation().Yaw));
    Data->SetNumberField(TEXT("before_yaw"),BeforeYaw);Data->SetNumberField(TEXT("after_yaw"),Rider->GetActorRotation().Yaw);
    Data->SetNumberField(TEXT("speed"),Activity==EJapanActivity::Bike?Rider->GetBike()->GetSpeed():Rider->GetSailboat()->GetSpeed());
    Data->SetNumberField(TEXT("serial"),Activity==EJapanActivity::Bike?Rider->GetBike()->GetSerial():Rider->GetSailboat()->GetSerial());
    Append(*Record,Record->Moves,Data);
}
void JapanVehicleTelemetry::Crash(AWandererCharacter* Rider,const FHitResult& Hit,float Speed)
{
    auto* R=Get(Rider);if(!R)return;
    auto Data=Row(Rider);Data->SetNumberField(TEXT("speed"),Speed);
    Data->SetStringField(TEXT("owner_class"),Hit.GetActor()?Hit.GetActor()->GetClass()->GetName():FString());
    const auto* Mesh=Cast<UStaticMeshComponent>(Hit.GetComponent());
    Data->SetStringField(TEXT("mesh"),Mesh&&Mesh->GetStaticMesh()?Mesh->GetStaticMesh()->GetPathName():FString());
    Data->SetNumberField(TEXT("item"),Hit.Item);Append(*R,R->Crashes,Data);
}
void JapanVehicleTelemetry::AcceptedMove(AWandererCharacter* Rider,uint32 Epoch)
{
    // Called at MoveAutonomous, including foot moves after the vehicle handoff.
    if(auto* R=Get(Rider);R&&Rider->HasAuthority()&&Epoch!=Rider->GetActivityEpoch())
    {++R->OldAccepted;auto Data=Row(Rider);Data->SetNumberField(TEXT("input_epoch"),Epoch);Append(*R,R->OldAcceptedMoves,Data);}
}
void JapanVehicleTelemetry::RejectedMove(AWandererCharacter* Rider,uint32 Epoch)
{
    if(auto* R=Get(Rider);R&&Epoch!=Rider->GetActivityEpoch())
    {++R->Rejected;auto Data=Row(Rider);Data->SetNumberField(TEXT("input_epoch"),Epoch);Append(*R,R->RejectedMoves,Data);}
}
void JapanVehicleTelemetry::Checkpoint(AWandererCharacter* Rider,bool Applied,int32 Bytes)
{
    if(Rider->GetNetworkActivity()!=EJapanActivity::Bike&&Rider->GetNetworkActivity()!=EJapanActivity::Sailboat)return;
    if(auto* R=Get(Rider)){if(Applied&&Bytes>0)++R->Checkpoints;else ++R->InvalidCheckpoints;}
}
void JapanVehicleTelemetry::Presentation(AWandererCharacter* Rider,double Stamp)
{
    if(auto* R=Get(Rider);R&&Stamp!=R->LastPresentation&&!Rider->HasAuthority()&&!Rider->IsLocallyControlled())
    {++R->Presentations;R->LastPresentation=Stamp;}
}
void JapanVehicleTelemetry::Action(AWandererCharacter* Rider,FName Button,uint16 Edge,bool Accepted,bool Replay)
{
    auto* R=Get(Rider);if(!R)return;
    auto Data=Row(Rider);Data->SetStringField(TEXT("button"),Button.ToString());
    Data->SetNumberField(TEXT("edge"),Edge);Data->SetBoolField(TEXT("accepted"),Accepted);Data->SetBoolField(TEXT("replay"),Replay);
    Append(*R,R->Actions,Data);
}
void JapanVehicleTelemetry::Request(AWandererCharacter* Rider,bool Bike,uint32 Epoch,bool Pending,bool Locked,bool Encounter)
{
    auto* R=Get(Rider);if(!R)return;
    auto Data=Row(Rider);Data->SetStringField(TEXT("kind"),Bike?TEXT("bike"):TEXT("sail"));
    const auto* Rules=Rider->GetWorld()->GetGameState<AJapanGameState>();
    Data->SetBoolField(TEXT("enabled"),Rules&&Rules->bPredictedVehicles);
    Data->SetNumberField(TEXT("request_epoch"),Epoch);Data->SetBoolField(TEXT("pending"),Pending);
    Data->SetBoolField(TEXT("locked"),Locked);Data->SetBoolField(TEXT("encounter"),Encounter);
    Append(*R,R->Requests,Data);
}
TSharedPtr<FJsonObject> JapanVehicleTelemetry::Snapshot(const AWandererCharacter* Rider)
{
    auto Data=MakeShared<FJsonObject>();auto* R=Get(Rider);if(!R)return Data;
    const auto* State=Rider->GetPlayerState<AJapanPlayerState>();
    Data->SetStringField(TEXT("player"),State?State->SessionPlayerId:FString());
    Data->SetBoolField(TEXT("authority"),Rider->HasAuthority());Data->SetBoolField(TEXT("local"),Rider->IsLocallyControlled());
    Data->SetArrayField(TEXT("crashes"),R->Crashes);Data->SetArrayField(TEXT("moves"),R->Moves);Data->SetArrayField(TEXT("actions"),R->Actions);Data->SetArrayField(TEXT("requests"),R->Requests);
    Data->SetArrayField(TEXT("rejected_moves"),R->RejectedMoves);Data->SetArrayField(TEXT("old_accepted_moves"),R->OldAcceptedMoves);
    Data->SetNumberField(TEXT("stale_moves_rejected"),R->Rejected);Data->SetNumberField(TEXT("stale_moves_accepted"),R->OldAccepted);
    Data->SetNumberField(TEXT("checkpoints"),R->Checkpoints);Data->SetNumberField(TEXT("invalid_checkpoints"),R->InvalidCheckpoints);
    Data->SetNumberField(TEXT("applied_presentations"),R->Presentations);Data->SetNumberField(TEXT("overflow"),R->Overflow);
    return Data;
}
#else
void JapanVehicleTelemetry::Reset(UWorld*){}
void JapanVehicleTelemetry::Move(AWandererCharacter*,const FJapanMoveInput&,float,bool,const FVector&,float){}
void JapanVehicleTelemetry::Crash(AWandererCharacter*,const FHitResult&,float){}
void JapanVehicleTelemetry::AcceptedMove(AWandererCharacter*,uint32){}
void JapanVehicleTelemetry::RejectedMove(AWandererCharacter*,uint32){}
void JapanVehicleTelemetry::Checkpoint(AWandererCharacter*,bool,int32){}
void JapanVehicleTelemetry::Presentation(AWandererCharacter*,double){}
void JapanVehicleTelemetry::Action(AWandererCharacter*,FName,uint16,bool,bool){}
void JapanVehicleTelemetry::Request(AWandererCharacter*,bool,uint32,bool,bool,bool){}
TSharedPtr<FJsonObject> JapanVehicleTelemetry::Snapshot(const AWandererCharacter*){return {};}
#endif

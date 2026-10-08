#include "JapanReactionDeliveryProbe.h"
#if !UE_BUILD_SHIPPING
#include "JapanReactionDeliveryQA.h"
#include "JapanCharacterMovement.h"
#include "JapanSession.h"
#include "WandererCharacter.h"
#include "BotwMoveSet.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "HAL/FileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace JapanReactionDeliveryQA
{
// Only the historical defence decision is selected by the fixture. IncomingStrike
// still executes the ordinary guard reaction, health/FX and checkpoint request.
struct FStimulus
{
    static int32 Guard(UBotwMoveSet& Moves, AActor* Source, const FVector& From)
    {
        TGuardValue<TOptional<EJapanDefence>> Override(Moves.DefenceOverride, TOptional<EJapanDefence>(EJapanDefence::Guard));
        return Moves.IncomingStrike(Source, 1.f, From);
    }
};
namespace
{
int32 DeliveryCase()
{
    static const int32 Value=[]
    {
        int32 Result=-1;
        if(FParse::Param(FCommandLine::Get(),TEXT("networkreactiondelivery")))
            FParse::Value(FCommandLine::Get(),TEXT("networkreactioncase="),Result);
        return Result;
    }();
    return Value;
}
bool MovingDelivery()
{
    static const bool Value=FParse::Param(FCommandLine::Get(),TEXT("networkreactionmoving"));
    return Value;
}
bool SaveDelivery(const FString& File,const TSharedPtr<FJsonObject>& Data)
{
    FString Text;
    FJsonSerializer::Serialize(Data.ToSharedRef(),TJsonWriterFactory<>::Create(&Text));
    return FFileHelper::SaveStringToFile(Text,*(File+TEXT(".tmp")))&&
        IFileManager::Get().Move(*File,*(File+TEXT(".tmp")),true,true);
}
TSharedPtr<FJsonObject> ReadDelivery(const FString& File)
{
    FString Text;TSharedPtr<FJsonObject> Data;
    if(FFileHelper::LoadFileToString(Text,*File))FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Data);
    return Data;
}
struct FDeliveryStimulusState
{
    TWeakObjectPtr<AWandererCharacter> Host, Guest;
    double Began=0., TriggerAt=0., MovingSeconds=0.;
    bool Active=false, Triggered=false, SecondTriggered=false, Complete=false, Saved=false;
    int32 Captures=0, Holds=0, Serialized=0;
    uint32 InitialEpoch=0;
    TArray<TSharedPtr<FJsonValue>> Events;
    TArray<double> FrameTimes;
    FString Failure;
    bool Owns(const UJapanCharacterMovement* Movement) const
    {return Active&&Movement&&Guest.IsValid()&&Movement->GetOwner()==Guest.Get()&&Guest->HasAuthority();}
    void Event(const TCHAR* Name,const UJapanCharacterMovement* Movement)
    {
        auto Row=MakeShared<FJsonObject>();Row->SetStringField(TEXT("event"),Name);
        Row->SetNumberField(TEXT("at"),FPlatformTime::Seconds());
        Row->SetNumberField(TEXT("epoch"),Movement->GetActivityEpoch());
        Row->SetNumberField(TEXT("checkpoint_stamp"),Movement->PendingCheckpointTime);
        Events.Add(MakeShared<FJsonValueObject>(Row));
    }
    void Hit(bool Guard=false,bool OwnPawn=false)
    {
        auto* Rider=OwnPawn?Host.Get():Guest.Get();
        auto* Movement=Rider?Cast<UJapanCharacterMovement>(Rider->GetCharacterMovement()):nullptr;
        if(!Rider||!Movement||!Rider->GetMoves()){Failure=TEXT("Reaction stimulus lost its pawn/move set");return;}
        Triggered=true;if(!TriggerAt)TriggerAt=FPlatformTime::Seconds();
        const FVector From=Rider->GetActorLocation()+(Guard?FVector::ZeroVector:Rider->GetActorForwardVector()*100.);
        const double BeforeSpeed=Movement->Velocity.Size2D();
        const int32 BeforeY=Movement->ReadMoveInput().Y;
        const int32 Outcome=Guard?FStimulus::Guard(*Rider->GetMoves(),OwnPawn?Guest.Get():Host.Get(),From):
            Rider->GetMoves()->ResolveUnprotectedStrike(OwnPawn?Guest.Get():Host.Get(),1.f,From);
        Event(OwnPawn?TEXT("host_own_hit"):Guard?TEXT("zero_impulse_guard"):TEXT("hit"),Movement);
        auto Row=Events.Last()->AsObject();Row->SetNumberField(TEXT("outcome"),Outcome);
        Row->SetNumberField(TEXT("pre_hit_speed"),BeforeSpeed);Row->SetNumberField(TEXT("pre_hit_input_y"),BeforeY);
        Row->SetNumberField(TEXT("moving_seconds_before_hit"),MovingSeconds);
        Row->SetStringField(TEXT("action"),Rider->GetAnimationAction().ToString());
        Row->SetNumberField(TEXT("speed"),Movement->Velocity.Size());
        Row->SetBoolField(TEXT("guard"),Guard);
        if(Guard&&Movement->Velocity.Size()>.01)Failure=TEXT("Guard fixture did not produce zero impulse");
    }
    TSharedPtr<FJsonObject> Frames() const
    {
        auto Data=MakeShared<FJsonObject>();TArray<double> Sorted=FrameTimes;Sorted.Sort();
        Data->SetNumberField(TEXT("count"),Sorted.Num());
        Data->SetNumberField(TEXT("median"),Sorted.IsEmpty()?0.:Sorted[Sorted.Num()/2]);
        Data->SetNumberField(TEXT("p95"),Sorted.IsEmpty()?0.:Sorted[FMath::Clamp(FMath::CeilToInt(Sorted.Num()*.95)-1,0,Sorted.Num()-1)]);
        return Data;
    }
    TSharedPtr<FJsonObject> Receipt(const UJapanCharacterMovement* Movement) const
    {
        auto Data=Snapshot(Movement);Data->SetNumberField(TEXT("case"),DeliveryCase());
        Data->SetNumberField(TEXT("initial_epoch"),InitialEpoch);
        Data->SetBoolField(TEXT("moving"),MovingDelivery());
        Data->SetBoolField(TEXT("complete"),Complete);Data->SetStringField(TEXT("error"),Failure);
        Data->SetBoolField(TEXT("artificial_send_hold"),DeliveryCase()==2);
        Data->SetNumberField(TEXT("response_window_end"),TriggerAt+2.);
        Data->SetNumberField(TEXT("observed_until"),FPlatformTime::Seconds());
        Data->SetNumberField(TEXT("held_sends"),Holds);Data->SetNumberField(TEXT("post_hit_captures"),Captures);
        Data->SetArrayField(TEXT("stimuli"),Events);
        Data->SetObjectField(TEXT("frame_statistics"),Frames());
        if(Host.IsValid())Data->SetObjectField(TEXT("host_own"),Snapshot(Cast<UJapanCharacterMovement>(Host->GetCharacterMovement())));
        return Data;
    }
} DeliveryStimulus;
}

void AfterCapture(UJapanCharacterMovement* Movement,bool Pending,bool Captured,bool GoodAckEligible)
{
    auto& S=DeliveryStimulus;if(!S.Owns(Movement)||S.Complete)return;
    const auto* Server=Movement->GetPredictionData_Server_Character();
    if(S.Triggered&&Pending&&Captured)++S.Captures;
    if(DeliveryCase()==3&&!S.Triggered&&Server&&Server->PendingAdjustment.bAckGoodMove&&GoodAckEligible)
    {
        // The hit lands after this accepted move was captured, between moves.
        S.Event(TEXT("prepared_good_ack"),Movement);S.Hit();Movement->SendClientAdjustment();
    }
    if(DeliveryCase()==4&&S.Triggered&&!S.SecondTriggered&&Captured)
    {S.SecondTriggered=true;S.Event(TEXT("second_after_capture"),Movement);S.Hit(true);}
}
bool HoldSend(UJapanCharacterMovement* Movement)
{
    auto& S=DeliveryStimulus;if(!S.Owns(Movement)||S.Complete)return false;
    if(DeliveryCase()==5&&!S.Triggered)
    {
        const auto* Server=Movement->GetPredictionData_Server_Character();
        if(Server&&Server->PendingAdjustment.TimeStamp>0.f&&!Server->PendingAdjustment.bAckGoodMove&&
            Movement->PendingCheckpointTime==Server->PendingAdjustment.TimeStamp&&!Movement->PendingCheckpoint.Bytes.IsEmpty())
        {S.Event(TEXT("prepared_correction_before_hit"),Movement);S.Hit();}
    }
    if(DeliveryCase()==2&&S.Triggered&&S.Captures<3)
    {++S.Holds;return true;}
    return false;
}
void AfterSend(UJapanCharacterMovement* Movement,bool Serialized)
{
    auto& S=DeliveryStimulus;if(!S.Owns(Movement)||S.Complete||!Serialized)return;
    ++S.Serialized;
    if(DeliveryCase()==0&&!S.Triggered)
    {S.Event(TEXT("correction_before_hit"),Movement);S.Hit();}
}

bool Tick(UWorld* World,bool Server,const FString& Folder,FString& Error)
{
    const int32 Case=DeliveryCase();if(Case<0||Case>7){Error=TEXT("Invalid reaction delivery case");return false;}
    if(MovingDelivery()&&Case!=0&&Case!=5){Error=TEXT("Moving delivery only supports cases 0 and 5");return false;}
    if(DeliveryStimulus.Saved)return true;
    const auto* Session=World->GetGameState<AJapanGameState>();
    if(!Session||!Session->bWorldReady||Session->PlayerArray.Num()!=2)return false;
    for(const APlayerState* Person:Session->PlayerArray)
        if(const auto* Player=Cast<AJapanPlayerState>(Person);!Player||!Player->bWorldReady||Player->SessionPlayerId.IsEmpty())return false;
    AWandererCharacter* Guest=nullptr;AWandererCharacter* Host=nullptr;
    for(TActorIterator<AWandererCharacter> It(World);It;++It)
        if(!It->IsNpc())
        {
            if(Server?!It->IsLocallyControlled():It->IsLocallyControlled())Guest=*It;else Host=*It;
        }
    if(!Guest||!Host||!Guest->IsReady()||!Host->IsReady()||!Guest->GetMoves()||!Host->GetMoves())return false;
    auto* Movement=Cast<UJapanCharacterMovement>(Guest->GetCharacterMovement());
    if(!Movement){Error=TEXT("Missing reaction delivery movement");return false;}
    if(DeliveryStimulus.FrameTimes.Num()>=1024){Error=TEXT("Reaction delivery frame history overflow");return false;}
    DeliveryStimulus.FrameTimes.Add(World->GetDeltaSeconds());
    if(!Server)
    {
        Guest->Live_Drive(MovingDelivery()?FVector2D(0,1):FVector2D::ZeroVector,0.f);
        auto Control=ReadDelivery(Folder/TEXT("reaction-control.json"));
        if(!Control||!Control->GetBoolField(TEXT("complete")))return false;
        auto Data=Snapshot(Movement);Data->SetNumberField(TEXT("case"),Case);
        Data->SetBoolField(TEXT("moving"),MovingDelivery());
        Data->SetNumberField(TEXT("drive_y"),Movement->ReadMoveInput().Y);
        Data->SetObjectField(TEXT("frame_statistics"),DeliveryStimulus.Frames());
        Data->SetBoolField(TEXT("complete"),true);
        Data->SetStringField(TEXT("error"),TEXT(""));
        const auto& Stats=Movement->GetNetworkStats();
        Data->SetNumberField(TEXT("position_corrections"),Stats.PositionCorrections);
        Data->SetNumberField(TEXT("largest_correction_cm"),Stats.LargestCorrectionCm);
        if (auto Detail = LargestCorrection(Stats)) Data->SetObjectField(TEXT("largest_correction"), Detail);
        Data->SetNumberField(TEXT("rejected_checkpoints"),Stats.Rejected);
        Data->SetNumberField(TEXT("response_window_end"),Control->GetNumberField(TEXT("response_window_end")));
        Data->SetNumberField(TEXT("observed_until"),FPlatformTime::Seconds());
        if(!SaveDelivery(Folder/TEXT("reaction-client.json"),Data))Error=TEXT("Cannot save reaction guest receipt");
        DeliveryStimulus.Saved=Error.IsEmpty();
        return Error.IsEmpty();
    }
    auto& S=DeliveryStimulus;const double Now=FPlatformTime::Seconds();
    if(!S.Began){S.Began=Now;S.Host=Host;S.Guest=Guest;S.InitialEpoch=Guest->GetActivityEpoch();}
    if(Now-S.Began>12.&&!S.Complete){Error=TEXT("Reaction delivery stimulus deadline expired");return false;}
    if(!S.Failure.IsEmpty()){Error=S.Failure;return false;}
    if(Now-S.Began<1.)return false;
    if(MovingDelivery()&&!S.Triggered)
    {
        const bool Driving=Movement->ReadMoveInput().Y==127&&Movement->Velocity.Size2D()>40.;
        S.MovingSeconds=Driving?S.MovingSeconds+World->GetDeltaSeconds():0.;
        S.Active=Driving&&S.MovingSeconds>=.15;
        if(!S.Active)return false;
    }
    else S.Active=true;
    if(!S.Triggered)
    {
        if(Case==1)S.Hit(true);
        if(Case==2||Case==4)S.Hit();
        if(Case==6)
        {
            S.Hit();S.Event(TEXT("cancel_before_epoch"),Movement);
            Guest->BeginNetworkActivity(EJapanActivity::OnFoot,false);
            S.Event(TEXT("cancel_after_epoch"),Movement);
        }
        if(Case==7)S.Hit(false,true);
    }
    if(S.Triggered&&Now-S.TriggerAt>3.)S.Complete=true;
    if(!S.Complete)return false;
    if(!SaveDelivery(Folder/TEXT("reaction-server.json"),S.Receipt(Movement)))
    {Error=TEXT("Cannot save reaction host receipt");return false;}
    auto Control=MakeShared<FJsonObject>();Control->SetBoolField(TEXT("complete"),true);
    Control->SetNumberField(TEXT("response_window_end"),S.TriggerAt+2.);
    if(!SaveDelivery(Folder/TEXT("reaction-control.json"),Control))Error=TEXT("Cannot save reaction completion marker");
    S.Saved=Error.IsEmpty();
    return Error.IsEmpty();
}
}
#else
bool JapanReactionDeliveryQA::Tick(UWorld*,bool,const FString&,FString& Error){Error=TEXT("Reaction probe is unavailable in shipping");return false;}
void JapanReactionDeliveryQA::AfterCapture(UJapanCharacterMovement*,bool,bool,bool){}
bool JapanReactionDeliveryQA::HoldSend(UJapanCharacterMovement*){return false;}
void JapanReactionDeliveryQA::AfterSend(UJapanCharacterMovement*,bool){}
#endif

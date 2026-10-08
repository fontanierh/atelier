#include "JapanVehicleQA.h"
#if !UE_BUILD_SHIPPING
#include "JapanVehicleTelemetry.h"
#include "JapanVehicleQASite.h"
#include "JapanCombatResolver.h"
#include "JapanSession.h"
#include "JapanGameplayCollision.h"
#include "JapanCharacterMovement.h"
#include "JapanWorld.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "BikeComponent.h"
#include "SailboatComponent.h"
#include "BotwMoveSet.h"
#include "EngineUtils.h"
#include "Engine/TargetPoint.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Components/CapsuleComponent.h"
#include "Dom/JsonObject.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformProcess.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

// QA uses the ordinary request and RPC entry points, including their host gates.
// Keep this access local to the nonshipping probe rather than exposing the RPCs.
struct FJapanVehicleQAAccess
{
    static bool Request(AWandererCharacter* Player,bool Sail)
    {return Sail?Player->RequestNetworkSail():Player->RequestNetworkBike();}
    static void SendRequest(AWandererCharacter* Player,bool Sail)
    {
        if(Sail)Player->ServerRequestSail(Player->GetActivityEpoch());
        else Player->ServerRequestBike(Player->GetActivityEpoch());
    }
};

namespace
{
bool Enabled(){static const bool Value=FParse::Param(FCommandLine::Get(),TEXT("networkvehicles"));return Value;}
FString Identity(const AWandererCharacter* Player)
{
    const auto* State=Player?Player->GetPlayerState<AJapanPlayerState>():nullptr;
    return State?State->SessionPlayerId:FString();
}
bool Write(const FString& File,const TSharedPtr<FJsonObject>& Data)
{
    FString Text;FJsonSerializer::Serialize(Data.ToSharedRef(),TJsonWriterFactory<>::Create(&Text));
    return FFileHelper::SaveStringToFile(Text,*(File+TEXT(".tmp")))&&IFileManager::Get().Move(*File,*(File+TEXT(".tmp")),true,true);
}
TSharedPtr<FJsonObject> Read(const FString& File)
{
    FString Text;TSharedPtr<FJsonObject> Data;
    if(FFileHelper::LoadFileToString(Text,*File))FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Data);
    return Data;
}
struct FVehicleProbe
{
    TWeakObjectPtr<UWorld> World;
    TWeakObjectPtr<AWandererCharacter> Host,Guest;
    TWeakObjectPtr<AActor> Source;
    FString Case,Error;
    int32 Phase=0,Seen=-1,ActionIndex=0,Callbacks=0,Contacts=0,Outcome=-1,HealthChanges=0;
    bool DefaultDisabled=false,DefaultAttempt=false,LocalSent=false,Complete=false,MenuSent=false;
    bool HitTerminal=false,HitHop=false;
    bool LandedOnce=false;
    bool PendingRefused=false,LaterMount=false;
    double ClockDriveAt=-1.,HitchSeconds=0.,HitchEnded=-1.;
    float HitchSpeed=0.;int32 HitchInputY=0;uint32 HitchEpoch=0,ControlEpoch=0;
    double PendingRequestAt=-1.;uint32 ContactEpoch=0,LaterRequestEpoch=0;
    double GroundBelowWater=0.,ContactAt=-1.,Due=-1.;
    uint32 StartEpoch=0,EndEpoch=0,PendingBikeBefore=0,PendingSailBefore=0;
    float HealthBefore=0,LastHealth=-1,HopLift=0;
    uint32 LastGuestEpoch=0;uint8 LastGuestActivity=0;bool LastParked=false;
    FName HitClip,ParkedClip;
    double Began=-1,PhaseBegan=0,LastWrite=-1,NextAction=0,ResolvedAt=-1,StableSince=-1;
    FVector StartPosition=FVector::ZeroVector,CrashStart=FVector::ZeroVector;
    float CrashYaw=0;bool CrashSiteReady=false;TSharedPtr<FJsonObject> CrashSite=MakeShared<FJsonObject>();
    bool CircuitReady=false;
    FVector CircuitStart[2];
    TSharedPtr<FJsonObject> CircuitSite[2];
    double CircuitMaxRadius[2]={0.,0.},CircuitMaxSpeed[2]={0.,0.};
    double CircuitMinPeerDistance=UE_BIG_NUMBER;int32 CircuitObservations=0;
    bool CircuitCase()const{return Case==TEXT("bike")||Case==TEXT("park");}
    float StartYaw=0;
    int32 MeasuredPhase=-1;
    TArray<double> FrameTimes;
    FVector PhaseStart=FVector::ZeroVector,PhaseForward=FVector::ForwardVector;
    float PhaseYaw=0,PhaseTurn=0,SailStart=0,SailMin=0,SailMax=0;
    void Observe()
    {
        auto* P=Guest.Get();
        if(MeasuredPhase!=Phase)
        {
            MeasuredPhase=Phase;FrameTimes.Reset();PhaseStart=P->GetActorLocation();PhaseForward=P->GetActorForwardVector();
            PhaseYaw=P->GetActorRotation().Yaw;PhaseTurn=0;SailStart=SailMin=SailMax=P->GetSailboat()->GetSailAmount();
        }
        if(FrameTimes.Num()>=8192){Fail(TEXT("Vehicle phase frame history overflow"));return;}
        FrameTimes.Add(World->GetDeltaSeconds());
        PhaseTurn+=FMath::FindDeltaAngleDegrees(PhaseYaw,P->GetActorRotation().Yaw);PhaseYaw=P->GetActorRotation().Yaw;
        SailMin=FMath::Min(SailMin,P->GetSailboat()->GetSailAmount());SailMax=FMath::Max(SailMax,P->GetSailboat()->GetSailAmount());
    }
    TSharedPtr<FJsonObject> FrameStats()const
    {
        auto Data=MakeShared<FJsonObject>();TArray<double> Sorted=FrameTimes;Sorted.Sort();
        Data->SetNumberField(TEXT("count"),Sorted.Num());
        Data->SetNumberField(TEXT("min"),Sorted.IsEmpty()?0.:Sorted[0]);
        Data->SetNumberField(TEXT("max"),Sorted.IsEmpty()?0.:Sorted.Last());
        Data->SetNumberField(TEXT("median"),Sorted.IsEmpty()?0.:Sorted[Sorted.Num()/2]);
        Data->SetNumberField(TEXT("p95"),Sorted.IsEmpty()?0.:Sorted[FMath::Clamp(FMath::CeilToInt(Sorted.Num()*.95)-1,0,Sorted.Num()-1)]);
        return Data;
    }
    TArray<TSharedPtr<FJsonValue>> Phases;
    TSharedPtr<FJsonObject> LastPeer,ContactFrames;
    double NextPeerRead=0.;float ContactDt=0;
    TSharedPtr<FJsonObject> ReadPeer(const FString& Folder)
    {
        const double Now=FPlatformTime::Seconds();
        if(Now>=NextPeerRead){LastPeer=Read(Folder/TEXT("vehicle-observed.json"));NextPeerRead=Now+.1;}
        return LastPeer;
    }
    bool Sail()const{return Case.EndsWith(TEXT("sail"));}
    bool ClockCase()const{return Case==TEXT("clock-bike");}
    bool PendingCase()const{return Case.StartsWith(TEXT("mount-"));}
    void Fail(const FString& Why){if(Error.IsEmpty())Error=Why;}
    EJapanActivity Activity()const{return Sail()?EJapanActivity::Sailboat:EJapanActivity::Bike;}
    bool Riding(const AWandererCharacter* P)const
    {return P&&P->GetNetworkActivity()==Activity()&&(Sail()?P->GetSailboat()->IsEquipped():P->GetBike()->IsRiding());}
    bool Request(AWandererCharacter* P)const{return FJapanVehicleQAAccess::Request(P,Sail());}
    void Step(int32 Next){Phase=Next;PhaseBegan=FPlatformTime::Seconds();StableSince=-1;}
    double PhaseLimit()const
    {
        // Bound each stimulus even when replication or the other rider prevents
        // advancement. Never keep steering until the global session deadline.
        switch(Phase)
        {
        case 0:return 5.; case 1:return 10.; case 2:case 8:return 15.;
        case 3:return 6.; case 4:return 5.; case 5:return Sail()?7.:16.;
        case 6:return 5.; case 7:return 8.; case 9:return 12.; case 10:return 12.;
        case 30:return 3.; case 31:return 15.; case 32:return 8.;
        case 40:return 5.; case 41:return 9.; default:return 5.;
        }
    }
    TSharedPtr<FJsonObject> RiderGate(AWandererCharacter* P)const
    {
        auto Row=MakeShared<FJsonObject>();auto* Movement=CastChecked<UJapanCharacterMovement>(P->GetCharacterMovement());
        const auto& Stats=Movement->GetNetworkStats();const FVector Position=P->GetActorLocation();
        Row->SetStringField(TEXT("player"),Identity(P));Row->SetNumberField(TEXT("epoch"),P->GetActivityEpoch());
        Row->SetNumberField(TEXT("activity"),uint8(P->GetNetworkActivity()));Row->SetBoolField(TEXT("riding"),Riding(P));
        Row->SetBoolField(TEXT("pending"),P->IsNetworkActivityPending());Row->SetNumberField(TEXT("movement_mode"),uint8(Movement->MovementMode));
        Row->SetNumberField(TEXT("speed"),Movement->Velocity.Size2D());Row->SetStringField(TEXT("bike_clip"),P->GetBike()->GetClip().ToString());
        Row->SetBoolField(TEXT("parked"),P->GetBike()->IsParked());Row->SetNumberField(TEXT("timeouts"),Stats.TimeoutCorrections);
        Row->SetNumberField(TEXT("budget_resets"),Stats.TimeBudgetCorrections);
        Row->SetNumberField(TEXT("x"),Position.X);Row->SetNumberField(TEXT("y"),Position.Y);Row->SetNumberField(TEXT("z"),Position.Z);
        return Row;
    }
    TSharedPtr<FJsonObject> Snapshot(AWandererCharacter* P,bool Detailed=true)
    {
        auto Data=MakeShared<FJsonObject>();
        const auto* Rules=World->GetGameState<AJapanGameState>();
        if(CircuitReady)
        {
            auto Sites=MakeShared<FJsonObject>();
            Sites->SetNumberField(TEXT("observations"),CircuitObservations);
            Sites->SetNumberField(TEXT("min_peer_distance_cm"),CircuitMinPeerDistance);
            for(int32 I=0;I<2;++I)
            {
                auto Site=MakeShared<FJsonObject>(*CircuitSite[I]);
                Site->SetNumberField(TEXT("max_radius_cm"),CircuitMaxRadius[I]);
                Site->SetNumberField(TEXT("max_speed_cm_s"),CircuitMaxSpeed[I]);
                Sites->SetObjectField(I==0?TEXT("host"):TEXT("guest"),Site);
            }
            Data->SetObjectField(TEXT("circuit_site"),Sites);
        }
        Data->SetStringField(TEXT("case"),Case);Data->SetStringField(TEXT("player"),Identity(P));
        Data->SetNumberField(TEXT("phase"),Phase);Data->SetNumberField(TEXT("epoch"),P->GetActivityEpoch());
        Data->SetNumberField(TEXT("activity"),uint8(P->GetNetworkActivity()));
        Data->SetBoolField(TEXT("authority"),P->HasAuthority());Data->SetBoolField(TEXT("local"),P->IsLocallyControlled());
        Data->SetBoolField(TEXT("default_disabled"),DefaultDisabled);Data->SetBoolField(TEXT("default_attempt"),DefaultAttempt);
        Data->SetBoolField(TEXT("rule_enabled"),Rules&&Rules->bPredictedVehicles);
        Data->SetNumberField(TEXT("health"),P->GetSword()->GetHealth());Data->SetNumberField(TEXT("health_changes"),HealthChanges);
        Data->SetBoolField(TEXT("bike_equipped"),P->GetBike()->IsEquipped());Data->SetBoolField(TEXT("sail_equipped"),P->GetSailboat()->IsEquipped());
        Data->SetBoolField(TEXT("terminal_at_contact"),HitTerminal);Data->SetBoolField(TEXT("hop_at_contact"),HitHop);
        Data->SetNumberField(TEXT("phase_lift_cm"),P->GetBike()->GetAuthoredLift());
        Data->SetObjectField(TEXT("frame_statistics"),FrameStats());
        if(ContactFrames)Data->SetObjectField(TEXT("contact_frame_statistics"),ContactFrames);
        Data->SetNumberField(TEXT("contact_frame_dt"),ContactDt);
        Data->SetNumberField(TEXT("phase_forward_cm"),FVector::DotProduct(P->GetActorLocation()-PhaseStart,PhaseForward));
        Data->SetNumberField(TEXT("phase_turn_degrees"),PhaseTurn);
        Data->SetNumberField(TEXT("phase_began"),PhaseBegan);
        Data->SetNumberField(TEXT("sail_start"),SailStart);Data->SetNumberField(TEXT("sail_min"),SailMin);Data->SetNumberField(TEXT("sail_max"),SailMax);
        Data->SetStringField(TEXT("parked_clip"),ParkedClip.ToString());
        const FVector2D Gaps=P->GetBike()->GetWheelGaps();
        Data->SetNumberField(TEXT("wheel_front_gap_cm"),Gaps.X);Data->SetNumberField(TEXT("wheel_rear_gap_cm"),Gaps.Y);
        Data->SetBoolField(TEXT("parked"),P->GetBike()->IsParked());Data->SetBoolField(TEXT("riding"),Riding(P));
        if(ClockCase())
        {
            const FTransform Parked=P->GetBike()->GetBikeTransform();
            const FVector Location=Parked.GetLocation();const FQuat Rotation=Parked.GetRotation();
            Data->SetNumberField(TEXT("parked_x"),Location.X);Data->SetNumberField(TEXT("parked_y"),Location.Y);Data->SetNumberField(TEXT("parked_z"),Location.Z);
            Data->SetNumberField(TEXT("parked_qx"),Rotation.X);Data->SetNumberField(TEXT("parked_qy"),Rotation.Y);
            Data->SetNumberField(TEXT("parked_qz"),Rotation.Z);Data->SetNumberField(TEXT("parked_qw"),Rotation.W);
            Data->SetNumberField(TEXT("hitch_seconds"),HitchSeconds);Data->SetNumberField(TEXT("hitch_ended"),HitchEnded);
            Data->SetNumberField(TEXT("hitch_speed"),HitchSpeed);Data->SetNumberField(TEXT("hitch_input_y"),HitchInputY);
            Data->SetNumberField(TEXT("hitch_epoch"),HitchEpoch);
            Data->SetNumberField(TEXT("drive_seconds"),HitchEnded<0.?0.:HitchEnded-HitchSeconds-ClockDriveAt);
            Data->SetNumberField(TEXT("control_start_epoch"),ControlEpoch);
            Data->SetNumberField(TEXT("control_epoch"),Host->GetActivityEpoch());
            Data->SetBoolField(TEXT("control_riding"),Riding(Host.Get()));
            Data->SetNumberField(TEXT("control_timeouts"),CastChecked<UJapanCharacterMovement>(Host->GetCharacterMovement())->GetNetworkStats().TimeoutCorrections);
        }
        Data->SetNumberField(TEXT("speed"),Sail()?P->GetSailboat()->GetSpeed():P->GetBike()->GetSpeed());
        Data->SetNumberField(TEXT("sail"),P->GetSailboat()->GetSailAmount());
        Data->SetStringField(TEXT("clip"),P->GetBike()->GetClip().ToString());
        Data->SetNumberField(TEXT("x"),P->GetActorLocation().X);Data->SetNumberField(TEXT("y"),P->GetActorLocation().Y);Data->SetNumberField(TEXT("z"),P->GetActorLocation().Z);
        Data->SetNumberField(TEXT("yaw"),P->GetActorRotation().Yaw);
        Data->SetBoolField(TEXT("walking"),P->GetCharacterMovement()->IsMovingOnGround());
        Data->SetBoolField(TEXT("swimming"),P->GetMoves()->GetMode()==EBotwMoveMode::Swim);
        Data->SetBoolField(TEXT("menu_sent"),MenuSent);
        Data->SetNumberField(TEXT("action_count"),ActionIndex);
        Data->SetNumberField(TEXT("callbacks"),Callbacks);Data->SetNumberField(TEXT("contacts"),Contacts);
        Data->SetNumberField(TEXT("outcome"),Outcome);Data->SetNumberField(TEXT("health_before"),HealthBefore);
        Data->SetNumberField(TEXT("start_epoch"),StartEpoch);Data->SetNumberField(TEXT("end_epoch"),EndEpoch);
        Data->SetNumberField(TEXT("hop_lift_cm"),HopLift);Data->SetStringField(TEXT("hit_clip"),HitClip.ToString());
        Data->SetNumberField(TEXT("ground_below_water_cm"),GroundBelowWater);
        Data->SetNumberField(TEXT("resolved_at"),ResolvedAt);
        Data->SetNumberField(TEXT("since_resolve"),ResolvedAt<0.?-1.:FPlatformTime::Seconds()-ResolvedAt);
        auto* Combat=World->GetSubsystem<UJapanCombatResolver>();
        Data->SetNumberField(TEXT("pending_bike_refusals"),Combat->PendingBikeRefusals-PendingBikeBefore);
        Data->SetNumberField(TEXT("pending_sail_refusals"),Combat->PendingSailRefusals-PendingSailBefore);
        Data->SetBoolField(TEXT("simulated_proxy"),P->GetLocalRole()==ROLE_SimulatedProxy);
        Data->SetBoolField(TEXT("pending_refused"),PendingRefused);Data->SetBoolField(TEXT("later_mount"),LaterMount);
        Data->SetNumberField(TEXT("contact_at"),ContactAt);Data->SetNumberField(TEXT("due"),Due);
        Data->SetNumberField(TEXT("pending_request_at"),PendingRequestAt);Data->SetNumberField(TEXT("contact_epoch"),ContactEpoch);
        Data->SetNumberField(TEXT("later_request_epoch"),LaterRequestEpoch);
        Data->SetNumberField(TEXT("movement_mode"),uint8(P->GetCharacterMovement()->MovementMode));
        if(auto* Movement=Cast<UJapanCharacterMovement>(P->GetCharacterMovement()))
        {const auto& Stats=Movement->GetNetworkStats();Data->SetNumberField(TEXT("replayed_moves"),Stats.ReplayedMoves);
         Data->SetNumberField(TEXT("largest_correction_cm"),Stats.LargestCorrectionCm);
         if(ClockCase())
         {
             Data->SetNumberField(TEXT("position_corrections_over_1cm"),Stats.PositionCorrections);
             Data->SetNumberField(TEXT("timeout_corrections"),Stats.TimeoutCorrections);
             Data->SetNumberField(TEXT("time_budget_corrections"),Stats.TimeBudgetCorrections);
             Data->SetNumberField(TEXT("time_budget_rejected"),Stats.TimeBudgetRejected);
             Data->SetNumberField(TEXT("stale_epoch_moves"),Stats.StaleEpochMoves);
             Data->SetNumberField(TEXT("stale_probe_sent"),Stats.StaleProbeSent);
             Data->SetNumberField(TEXT("stale_probe_rejected"),Stats.StaleProbeRejected);
             Data->SetNumberField(TEXT("stale_probe_root_cm"),Stats.StaleProbeRootCm);
             Data->SetNumberField(TEXT("stale_probe_clock_delta"),Stats.StaleProbeClockDelta);
             Data->SetNumberField(TEXT("clock_arrivals"),Stats.ClockArrivals);
             Data->SetNumberField(TEXT("neutral_path_cm"),Stats.NeutralPathCm);
             Data->SetNumberField(TEXT("clock_arrival_drift_cm"),FVector::Dist(Stats.ClockArrivalRoot,Stats.ClockHandoffRoot));
             Data->SetNumberField(TEXT("neutral_max_acceleration"),Stats.NeutralMaxAcceleration);
             Data->SetNumberField(TEXT("neutral_late_ground_frames"),Stats.NeutralLateGroundFrames);
             Data->SetNumberField(TEXT("neutral_late_max_speed"),Stats.NeutralLateMaxSpeed);
             const auto Input=Movement->ReadMoveInput();
             Data->SetNumberField(TEXT("input_x"),Input.X);Data->SetNumberField(TEXT("input_y"),Input.Y);Data->SetNumberField(TEXT("input_flags"),Input.Flags);
         }}
        Data->SetArrayField(TEXT("phases"),Phases);Data->SetObjectField(TEXT("crash_site"),CrashSite);
        Data->SetBoolField(TEXT("complete"),Complete);Data->SetStringField(TEXT("error"),Error);
        Data->SetNumberField(TEXT("at"),FPlatformTime::Seconds());
        // Live coordination needs current state, not the cumulative replay log.
        // Keep full traces in phase/result/failure evidence and the final owner
        // receipt; serializing/parsing them at 10 Hz would skew the fps proof.
        if(Detailed)
        {
            Data->SetObjectField(TEXT("telemetry"),JapanVehicleTelemetry::Snapshot(P));
            AWandererCharacter* Other=P==Host.Get()?Guest.Get():Host.Get();
            if(Other)Data->SetObjectField(TEXT("peer_telemetry"),JapanVehicleTelemetry::Snapshot(Other));
        }
        return Data;
    }
    void Drive(AWandererCharacter* P)
    {
        const bool Enter=Seen!=Phase;
        if(Enter){Seen=Phase;LocalSent=false;NextAction=0;ActionIndex=0;}
        if(ClockCase()&&Phase>=40)
        {
            if(Phase==40&&Enter)
            {
                ControlEpoch=Host->GetActivityEpoch();
                if(P==Guest.Get()){P->Live_Drive(FVector2D(0,1),2);ClockDriveAt=FPlatformTime::Seconds();}
            }
            if(Phase==41&&P==Guest.Get()&&Enter)
            {
                auto* Movement=CastChecked<UJapanCharacterMovement>(P->GetCharacterMovement());
                HitchEpoch=P->GetActivityEpoch();HitchSpeed=Movement->Velocity.Size2D();HitchInputY=Movement->ReadMoveInput().Y;
                const double Started=FPlatformTime::Seconds();
                FPlatformProcess::Sleep(1.05f);
                HitchEnded=FPlatformTime::Seconds();HitchSeconds=HitchEnded-Started;
            }
            // No neutralization or repeated drive call: the ordinary epoch reset must clear the latched input.
            if(P==Guest.Get())CastChecked<UJapanCharacterMovement>(P->GetCharacterMovement())->SendStaleClockProbe();
            return;
        }
        P->Live_Drive(FVector2D::ZeroVector,1);
        if(Phase!=6)P->SetMenuOpen(false);
        if(Phase==0&&Enter)
        {
            const auto* Rules=World->GetGameState<AJapanGameState>();
            DefaultDisabled=Rules&&!Rules->bPredictedVehicles;
            DefaultAttempt=DefaultDisabled&&!Request(P);
            // Also exercise the host gate through the ordinary owner RPC.
            FJapanVehicleQAAccess::SendRequest(P,Sail());
        }
        if(Phase==1&&Enter&&CircuitCase())
            P->TravelTo(CircuitStart[P==Guest.Get()?1:0],0.f,TEXT("network bike infield"));
        if(Phase==1&&Enter&&Sail())
            P->TravelTo(AJapanWorld::ToUE(P==Host.Get()?-226.f:-216.f,-169.f,1.6f),80.f,TEXT("network vehicle shore"));
        if(Phase==1&&Enter&&Case==TEXT("crash")&&P==Guest.Get())P->TravelTo(CrashStart,CrashYaw,TEXT("network authored wall approach"));
        if(!PendingCase()&&(Phase==2||Phase==8)&&!Riding(P)&&!P->IsNetworkActivityPending()&&P->GetCharacterMovement()->IsMovingOnGround()&&FPlatformTime::Seconds()>=NextAction)
        {LocalSent=Request(P);NextAction=FPlatformTime::Seconds()+.75;}
        if(Phase==3)P->Live_Drive(FVector2D(0,1),1);
        if(Phase==4)P->Live_Drive(FVector2D(.6f,1),1);
        if(Phase==5)
        {
            if(Sail()){P->Live_Drive(FVector2D(0,FPlatformTime::Seconds()-PhaseBegan<2.?-1.:1.),1);return;}
            // Keep the action sequence inside the certified infield disk.
            // Steering still runs through the ordinary predicted move input.
            P->Live_Drive(FVector2D(.6f,1),1);
            if(!Sail()&&P->GetBike()->GetClip()==TEXT("BikeRide")&&FPlatformTime::Seconds()>=NextAction)
            {
                static const FName Buttons[]={TEXT("attack"),TEXT("wave"),TEXT("sprint"),TEXT("dodge")};
                if(ActionIndex<UE_ARRAY_COUNT(Buttons))
                {
                    if(P->Live_Press(Buttons[ActionIndex]))++ActionIndex;
                    NextAction=FPlatformTime::Seconds()+2.;
                }
            }
        }
        if(Phase==6){P->SetMenuOpen(true);MenuSent=true;}
        if(Phase==7&&P->GetNetworkActivity()!=EJapanActivity::OnFoot&&!P->IsNetworkActivityPending()&&FPlatformTime::Seconds()>=NextAction)
        {LocalSent=Request(P);NextAction=FPlatformTime::Seconds()+.75;}
        if(Phase==9&&Case==TEXT("crash"))
        {
            if(P==Guest.Get())P->Live_Drive(FVector2D(0,1),1);
            return;
        }
        if(Phase==9&&Case==TEXT("park"))
        {
            if(P==Guest.Get()&&!P->IsNetworkActivityPending()&&FPlatformTime::Seconds()>=NextAction&&Riding(P))
            {LocalSent=Request(P);NextAction=FPlatformTime::Seconds()+.75;}
            return;
        }
        if(Phase==9)
        {
            P->Live_Drive(FVector2D(CircuitCase()?.6f:0.f,1),1);
            if(!Sail()&&P==Guest.Get()&&!LocalSent&&P->GetBike()->IsRiding()&&FPlatformTime::Seconds()-PhaseBegan>=1.1)LocalSent=P->Live_Press(TEXT("jump"));
        }
        if(Phase>=10){P->Live_Drive(FVector2D::ZeroVector,1);P->Live_Press(TEXT("attack_release"));P->Live_Press(TEXT("jump_release"));}
        if(PendingCase()&&P==Guest.Get())
        {
            if(Phase==30&&!LocalSent&&!P->IsNetworkActivityPending())LocalSent=Request(P);
            if(Phase==31&&!Riding(P)&&!P->MovementLocked()&&!P->IsNetworkActivityPending()&&FPlatformTime::Seconds()>=NextAction)
            {LocalSent=Request(P);NextAction=FPlatformTime::Seconds()+.75;}
            if(Phase==32&&P->GetNetworkActivity()!=EJapanActivity::OnFoot&&!P->IsNetworkActivityPending()&&FPlatformTime::Seconds()>=NextAction)
            {LocalSent=Request(P);NextAction=FPlatformTime::Seconds()+.75;}
        }
    }
    void Strike(AWandererCharacter* P)
    {
        if(Contacts||!P||!P->HasAuthority())return;
        Source=World->SpawnActor<ATargetPoint>();if(!Source.IsValid()){Fail(TEXT("Vehicle strike source spawn failed"));return;}
        ContactFrames=FrameStats();ContactDt=World->GetDeltaSeconds();
        HealthBefore=P->GetSword()->GetHealth();StartEpoch=P->GetActivityEpoch();
        ContactAt=World->GetTimeSeconds();Due=ContactAt+P->GetMoves()->DefenceWait();ContactEpoch=StartEpoch;
        HitClip=P->GetBike()->GetClip();HopLift=P->GetBike()->GetAuthoredLift();HitHop=HitClip==TEXT("BikeHop")&&HopLift>5.f;
        HitTerminal=P->GetBike()->NeedsNetworkPark();++Contacts;
        World->GetSubsystem<UJapanCombatResolver>()->Strike(Source.Get(),P,8.f,P->GetActorLocation()+P->GetActorForwardVector()*80.f,
            [this](int32 Result)
            {
                ++Callbacks;Outcome=Result;ResolvedAt=FPlatformTime::Seconds();
                if(Guest.IsValid()){EndEpoch=Guest->GetActivityEpoch();ParkedClip=Guest->GetBike()->GetClip();}
            });
    }
    bool Tick(bool Server,const FString& Folder);
    bool PeerMatches(const TSharedPtr<FJsonObject>& Peer) const
    {
        if(!Peer||!Guest.IsValid())return false;
        return Peer->GetStringField(TEXT("error")).IsEmpty()&&Peer->GetStringField(TEXT("player"))==Identity(Guest.Get())&&
            Peer->GetNumberField(TEXT("phase"))==Phase&&Peer->GetNumberField(TEXT("epoch"))==Guest->GetActivityEpoch()&&
            Peer->GetNumberField(TEXT("activity"))==uint8(Guest->GetNetworkActivity())&&
            Peer->GetBoolField(TEXT("local"))&&!Peer->GetBoolField(TEXT("authority"))&&
            FPlatformTime::Seconds()-Peer->GetNumberField(TEXT("at"))<1.;
    }
    void SavePhase(const TSharedPtr<FJsonObject>& Peer)
    {
        auto Row=Snapshot(Guest.Get());Row->RemoveField(TEXT("phases"));
        Row->SetObjectField(TEXT("owner_observation"),Peer);
        Row->SetObjectField(TEXT("host_telemetry"),JapanVehicleTelemetry::Snapshot(Host.Get()));
        Phases.Add(MakeShared<FJsonValueObject>(Row));
    }
};
FVehicleProbe Probe;
}

bool FVehicleProbe::Tick(bool Server,const FString& Folder)
{
    const double Now=FPlatformTime::Seconds();
    if(Began>=0.&&!Complete&&Now-Began>120.)Fail(FString::Printf(TEXT("Vehicle deadline: %s phase %d"),*Case,Phase));
    // Unsupported routes fail explicitly until their real stimulus is implemented.
    if(Case!=TEXT("bike")&&Case!=TEXT("sail")&&Case!=TEXT("mount-bike")&&Case!=TEXT("mount-sail")&&Case!=TEXT("park")&&Case!=TEXT("crash")&&!ClockCase())Fail(TEXT("Vehicle case has no native stimulus yet"));
    int32 Count=0;
    for(TActorIterator<AWandererCharacter> It(World.Get());It;++It)
    {
        if(It->IsNpc())continue;
        const auto* State=It->GetPlayerState<AJapanPlayerState>();
        if(!State||!State->bWorldReady||!It->IsReady()||!It->GetLandscape()||!It->GetLandscape()->bGameplayReady)return false;
        ++Count;
        if(Server?It->IsLocallyControlled():!It->IsLocallyControlled())Host=*It;else Guest=*It;
    }
    if(Count!=2||!Host.IsValid()||!Guest.IsValid())return false;
    if(CircuitCase()&&!CircuitReady)
    {
        CircuitReady=JapanVehicleQASite::Circuit(Host.Get(),false,CircuitStart[0],CircuitSite[0])&&
            JapanVehicleQASite::Circuit(Guest.Get(),true,CircuitStart[1],CircuitSite[1]);
        if(!CircuitReady)
        {
            auto Failed=MakeShared<FJsonObject>();
            for(int32 I=0;I<2;++I)if(CircuitSite[I])Failed->SetObjectField(I==0?TEXT("host"):TEXT("guest"),CircuitSite[I]);
            Write(Folder/(Server?TEXT("circuit-host-failed.json"):TEXT("circuit-guest-failed.json")),Failed);
            Fail(TEXT("Bike fixture has no clear supported infield circuit"));return false;
        }
    }
    if(Began<0.)Began=PhaseBegan=Now;
    if(Server&&Case==TEXT("crash")&&!CrashSiteReady)
    {
        CrashSiteReady=JapanVehicleQASite::Crash(Guest.Get(),CrashStart,CrashYaw,CrashSite);
        if(!CrashSiteReady){Fail(TEXT("No flat approach to an existing fixed wall was found"));return false;}
    }
    if(!Server)
    {
        auto Control=Read(Folder/TEXT("vehicle-control.json"));if(!Control)return false;
        if(Case==TEXT("crash"))
        {
            CrashSite=Control->GetObjectField(TEXT("crash_site"));
            CrashStart=FVector(CrashSite->GetNumberField(TEXT("x")),CrashSite->GetNumberField(TEXT("y")),CrashSite->GetNumberField(TEXT("z")));
            CrashYaw=CrashSite->GetNumberField(TEXT("yaw"));CrashSiteReady=true;
        }
        const int32 Next=int32(Control->GetNumberField(TEXT("phase")));
        if(Next!=Phase){Phase=Next;PhaseBegan=Now;}
        Complete=Control->GetBoolField(TEXT("complete"));
    }
    const float Health=Guest->GetSword()->GetHealth();
    if(LastHealth>=0.f&&!FMath::IsNearlyEqual(Health,LastHealth,.01f))++HealthChanges;
    LastHealth=Health;LastGuestEpoch=Guest->GetActivityEpoch();LastGuestActivity=uint8(Guest->GetNetworkActivity());LastParked=Guest->GetBike()->IsParked();
    if(CircuitReady&&Phase>=2)
    {
        ++CircuitObservations;
        CircuitMinPeerDistance=FMath::Min(CircuitMinPeerDistance,FVector::Dist2D(Host->GetActorLocation(),Guest->GetActorLocation()));
        if(CircuitMinPeerDistance<400.)Fail(TEXT("Bike fixture riders approached within four metres"));
        for(int32 I=0;I<2;++I)
        {
            const auto* Player=I==0?Host.Get():Guest.Get();
            const FVector Centre(CircuitSite[I]->GetNumberField(TEXT("x")),CircuitSite[I]->GetNumberField(TEXT("y")),0);
            CircuitMaxSpeed[I]=FMath::Max(CircuitMaxSpeed[I],double(FMath::Abs(Player->GetBike()->GetSpeed())));
            CircuitMaxRadius[I]=FMath::Max(CircuitMaxRadius[I],FVector::Dist2D(Player->GetActorLocation(),Centre));
            if(CircuitMaxRadius[I]>2200.)Fail(TEXT("Bike fixture left its certified infield circuit"));
        }
    }
    Observe();
    if(!Server&&Seen!=Phase)
    {
        // Preserve the cumulative owner trace at each boundary without putting
        // it in the live file the host reads for phase coordination.
        auto Evidence=Snapshot(Guest.Get());Evidence->RemoveField(TEXT("phases"));
        if(!Write(Folder/FString::Printf(TEXT("vehicle-owner-phase-%d.json"),Phase),Evidence))
            Fail(TEXT("Could not save vehicle owner phase evidence"));
    }
    Drive(Server?Host.Get():Guest.Get());
    // Sample authored hop lift at the world tick cadence, not the 10 Hz receipt
    // cadence. The peer must have observed this phase before the host stimulus.
    if(Server&&Phase==9&&Now-PhaseBegan>=1.1&&Case!=TEXT("park")&&Case!=TEXT("crash")&&Riding(Host.Get())&&Riding(Guest.Get()))
    {
        auto HopPeer=ReadPeer(Folder);
        const bool InPhase=PeerMatches(HopPeer)&&HopPeer->GetBoolField(TEXT("riding"));
        GroundBelowWater=Guest->GetSailboat()->GetWaterDepth();
        const bool Ready=Sail()?GroundBelowWater>=80.:
            Guest->GetBike()->GetClip()==TEXT("BikeHop")&&Guest->GetBike()->GetAuthoredLift()>5.f&&
            Guest->GetCharacterMovement()->IsMovingOnGround()&&InPhase&&HopPeer->GetBoolField(TEXT("walking"));
        if(InPhase&&Ready){SavePhase(HopPeer);Strike(Guest.Get());Step(10);}
    }
    if(!Error.IsEmpty())
    {Write(Folder/(Server?TEXT("vehicle-failed.json"):TEXT("vehicle-client-failed.json")),Snapshot(Guest.Get()));return false;}
    if(Now-LastWrite<.1&&!Complete)return false;
    LastWrite=Now;
    if(!Server)
    {
        auto Row=Snapshot(Guest.Get(),Complete);Row->RemoveField(TEXT("phases"));
        if(!Write(Folder/TEXT("vehicle-observed.json"),Row))Fail(TEXT("Could not save vehicle owner observation"));
        return Complete;
    }
    const auto Peer=ReadPeer(Folder);
    const bool Matches=PeerMatches(Peer);
    const bool BothRiding=Riding(Host.Get())&&Riding(Guest.Get())&&Peer&&Peer->GetBoolField(TEXT("riding"));
    const double Elapsed=Now-PhaseBegan;
    auto Control=MakeShared<FJsonObject>();Control->SetNumberField(TEXT("phase"),Phase);Control->SetBoolField(TEXT("complete"),Complete);Control->SetObjectField(TEXT("crash_site"),CrashSite);
    Control->SetNumberField(TEXT("phase_elapsed"),Elapsed);Control->SetNumberField(TEXT("phase_limit"),PhaseLimit());
    Control->SetBoolField(TEXT("peer_matches"),Matches);Control->SetBoolField(TEXT("both_riding"),BothRiding);
    Control->SetObjectField(TEXT("host_rider"),RiderGate(Host.Get()));Control->SetObjectField(TEXT("guest_rider"),RiderGate(Guest.Get()));
    if(Peer)
    {
        Control->SetNumberField(TEXT("peer_age"),Now-Peer->GetNumberField(TEXT("at")));
        for(const TCHAR* Key:{TEXT("phase"),TEXT("epoch"),TEXT("activity")})Control->SetNumberField(FString(TEXT("peer_"))+Key,Peer->GetNumberField(Key));
    }
    if(!Write(Folder/TEXT("vehicle-control.json"),Control)){Fail(TEXT("Could not save vehicle control"));return false;}
    if(Peer&&!Peer->GetStringField(TEXT("error")).IsEmpty()){Fail(Peer->GetStringField(TEXT("error")));return false;}
    if(!Complete&&Elapsed>PhaseLimit())
    {
        Fail(FString::Printf(TEXT("Vehicle phase %d deadline %.1fs: peer_matches=%d both_riding=%d host_activity=%u guest_activity=%u"),
            Phase,PhaseLimit(),Matches,BothRiding,uint32(Host->GetNetworkActivity()),uint32(Guest->GetNetworkActivity())));
        auto Failed=Snapshot(Guest.Get());Failed->SetObjectField(TEXT("phase_gate"),Control);
        Write(Folder/TEXT("vehicle-failed.json"),Failed);return false;
    }
    if(Complete)
    {
        if(Callbacks!=(ClockCase()?0:1)||Guest->GetActivityEpoch()!=EndEpoch||!FMath::IsNearlyEqual(HealthBefore-Health,ClockCase()?0.f:8.f,.01f))Fail(TEXT("Vehicle outcome changed after completion"));
        return Error.IsEmpty();
    }
    if(!Matches)return false;
    bool DisabledRequestObserved=false;
    if(Phase==0)
    {
        const auto Trace=JapanVehicleTelemetry::Snapshot(Guest.Get());
        for(const auto& Value:Trace->GetArrayField(TEXT("requests")))
        {
            const auto R=Value->AsObject();
            DisabledRequestObserved|=!R->GetBoolField(TEXT("enabled"))&&R->GetStringField(TEXT("kind"))==(Sail()?TEXT("sail"):TEXT("bike"))&&
                R->GetNumberField(TEXT("request_epoch"))==Guest->GetActivityEpoch();
        }
    }
    if(Phase==0&&Elapsed>.5&&DefaultAttempt&&Peer->GetBoolField(TEXT("default_attempt"))&&DisabledRequestObserved)
    {
        SavePhase(Peer);
        auto* Rules=World->GetGameState<AJapanGameState>();Rules->bPredictedVehicles=true;Rules->ForceNetUpdate();Step(1);
    }
    else if(Phase==1&&Elapsed>1.&&Peer->GetBoolField(TEXT("rule_enabled"))&&
        Host->GetCharacterMovement()->IsMovingOnGround()&&Guest->GetCharacterMovement()->IsMovingOnGround()&&
        !Guest->IsNetworkActivityPending()&&(!CircuitCase()||
            (FVector::Dist2D(Host->GetActorLocation(),CircuitStart[0])<30.&&FVector::Dist2D(Guest->GetActorLocation(),CircuitStart[1])<30.&&
            FMath::Abs(FRotator::NormalizeAxis(Host->GetActorRotation().Yaw))<1.&&FMath::Abs(FRotator::NormalizeAxis(Guest->GetActorRotation().Yaw))<1.))&&(Case!=TEXT("crash")||FVector::Dist2D(Guest->GetActorLocation(),CrashStart)<30.))Step(2);
    else if(ClockCase())
    {
        if(Phase==2&&BothRiding)
        {StartEpoch=Guest->GetActivityEpoch();HealthBefore=Health;SavePhase(Peer);Step(40);}
        else if(Phase==40&&BothRiding&&Elapsed>=1.2&&Guest->GetCharacterMovement()->Velocity.Size2D()>200.f&&Peer->GetNumberField(TEXT("speed"))>200.)
        {SavePhase(Peer);Step(41);}
        else if(Phase==41)
        {
            const double End=Peer->GetNumberField(TEXT("hitch_ended"));
            if(End>0.&&Now-End>=.85&&Guest->GetNetworkActivity()==EJapanActivity::OnFoot&&Guest->GetCharacterMovement()->IsMovingOnGround())
            {
                EndEpoch=Guest->GetActivityEpoch();SavePhase(Peer);Complete=true;
                auto Result=Snapshot(Guest.Get());Result->SetBoolField(TEXT("passed"),true);
                if(!Write(Folder/TEXT("vehicle-result.json"),Result))Fail(TEXT("Could not save clock vehicle result"));
                Control->SetBoolField(TEXT("complete"),true);Write(Folder/TEXT("vehicle-control.json"),Control);
            }
            else if(Elapsed>8.)Fail(TEXT("Bike timeout did not reach a replicated foot state within eight seconds"));
        }
    }
    else if(PendingCase())
    {
        if(Phase==2&&Elapsed>=3.&&Guest->GetNetworkActivity()==EJapanActivity::OnFoot&&!Guest->MovementLocked())
        {
            SavePhase(Peer);Strike(Guest.Get());Step(30);
            // Write immediately: adding the periodic file interval here can push
            // the real RPC past Due. No RPC is delayed or reordered by the probe.
            Control->SetNumberField(TEXT("phase"),Phase);Write(Folder/TEXT("vehicle-control.json"),Control);
        }
        else if(Phase==30&&Callbacks==1)
        {
            auto* Combat=World->GetSubsystem<UJapanCombatResolver>();
            const uint32 Refusals=Sail()?Combat->PendingSailRefusals-PendingSailBefore:Combat->PendingBikeRefusals-PendingBikeBefore;
            const auto Trace=JapanVehicleTelemetry::Snapshot(Guest.Get());
            int32 Received=0;
            for(const auto& Value:Trace->GetArrayField(TEXT("requests")))
            {
                const auto RequestRow=Value->AsObject();const double At=RequestRow->GetNumberField(TEXT("at"));
                if(At<ContactAt||RequestRow->GetStringField(TEXT("kind"))!=(Sail()?TEXT("sail"):TEXT("bike")))continue;
                ++Received;
                if(At<Due&&RequestRow->GetBoolField(TEXT("pending"))&&!RequestRow->GetBoolField(TEXT("locked"))&&
                    !RequestRow->GetBoolField(TEXT("encounter"))&&RequestRow->GetNumberField(TEXT("request_epoch"))==ContactEpoch)
                    PendingRequestAt=At;
            }
            if(Received>0)
            {
                if(Received!=1||Refusals!=1||PendingRequestAt<0.||Outcome!=0||Guest->GetNetworkActivity()!=EJapanActivity::OnFoot)
                    Fail(TEXT("RETRY: mount request did not arrive exclusively inside the pending-contact window"));
                else{PendingRefused=true;LaterRequestEpoch=Guest->GetActivityEpoch();SavePhase(Peer);Step(31);}
            }
            else if(Now-ResolvedAt>1.)Fail(TEXT("RETRY: no mount RPC observed by the pending-contact deadline"));
        }
        else if(Phase==31&&Riding(Guest.Get())&&Peer->GetBoolField(TEXT("riding")))
        {LaterMount=true;SavePhase(Peer);Step(32);}
        else if(Phase==32&&Guest->GetNetworkActivity()==EJapanActivity::OnFoot&&Guest->GetCharacterMovement()->IsMovingOnGround()&&
            Peer->GetBoolField(TEXT("walking"))&&HealthChanges==1&&Peer->GetNumberField(TEXT("health_changes"))==1)
        {
            EndEpoch=Guest->GetActivityEpoch();LandedOnce=true;SavePhase(Peer);Complete=true;
            auto Result=Snapshot(Guest.Get());Result->SetBoolField(TEXT("passed"),Error.IsEmpty());
            Result->SetBoolField(TEXT("normal_park_and_remount"),true);Write(Folder/TEXT("vehicle-result.json"),Result);
            Control->SetBoolField(TEXT("complete"),true);Write(Folder/TEXT("vehicle-control.json"),Control);
        }
    }
    else if(Phase==2&&BothRiding){SavePhase(Peer);Step(Case==TEXT("crash")?9:Sail()?7:3);}
    else if(Phase==3&&BothRiding&&Elapsed>3.){SavePhase(Peer);Step(4);}
    else if(Phase==4&&BothRiding&&Elapsed>2.){SavePhase(Peer);Step(5);}
    else if(Phase==5&&BothRiding&&((Sail()&&Elapsed>4.)||(!Sail()&&ActionIndex==4&&Peer->GetNumberField(TEXT("action_count"))==4&&Elapsed>9.)))
    {SavePhase(Peer);Step(6);}
    else if(Phase==6&&BothRiding&&Elapsed>2.&&Peer->GetBoolField(TEXT("menu_sent"))&&
        FMath::Abs(Sail()?Guest->GetSailboat()->GetSpeed():Guest->GetBike()->GetSpeed())<.1f)
    {SavePhase(Peer);Step(Sail()?9:7);}
    else if(Phase==7&&Host->GetNetworkActivity()==EJapanActivity::OnFoot&&Guest->GetNetworkActivity()==EJapanActivity::OnFoot&&
        Host->GetCharacterMovement()->IsMovingOnGround()&&Guest->GetCharacterMovement()->IsMovingOnGround()&&Peer->GetBoolField(TEXT("walking")))
    {LandedOnce=true;SavePhase(Peer);Step(8);}
    else if(Phase==8&&BothRiding){SavePhase(Peer);Step(Sail()?3:9);}
    else if(Phase==10&&Callbacks==1&&Outcome==0&&Now-ResolvedAt>=2.&&Guest->GetActivityEpoch()==EndEpoch&&
        Guest->GetNetworkActivity()==EJapanActivity::OnFoot&&Peer->GetNumberField(TEXT("health"))==Health&&HealthChanges==1&&
        Peer->GetNumberField(TEXT("health_changes"))==1&&
        (Sail()?(Guest->GetMoves()->GetMode()==EBotwMoveMode::Swim||Guest->GetCharacterMovement()->IsMovingOnGround()):Guest->GetCharacterMovement()->IsMovingOnGround()))
    {
        SavePhase(Peer);Complete=true;
        auto Result=Snapshot(Guest.Get());Result->SetBoolField(TEXT("passed"),true);
        Result->SetBoolField(TEXT("normal_park_and_remount"),LandedOnce);
        if(!Write(Folder/TEXT("vehicle-result.json"),Result))Fail(TEXT("Could not save vehicle result"));
        Control->SetBoolField(TEXT("complete"),true);Write(Folder/TEXT("vehicle-control.json"),Control);
    }
    if(Phase==10&&ResolvedAt>0.&&Now-ResolvedAt>12.&&!Complete)Fail(TEXT("Vehicle strike did not reach a safe replicated foot state"));
    if(Complete&&(Callbacks!=(ClockCase()?0:1)||Guest->GetActivityEpoch()!=EndEpoch||!FMath::IsNearlyEqual(HealthBefore-Health,ClockCase()?0.f:8.f,.01f)))
        Fail(TEXT("Vehicle outcome changed after completion"));
    return Complete;
}
bool JapanVehicleQA::Tick(UWorld* World,bool Server,const FString& Folder,FString& Error)
{
    if(!Enabled())return false;
    if(Probe.World.Get()!=World)
    {
        Probe=FVehicleProbe();Probe.World=World;
        FParse::Value(FCommandLine::Get(),TEXT("networkvehiclecase="),Probe.Case);
        JapanVehicleTelemetry::Reset(World);
        const auto* Combat=World->GetSubsystem<UJapanCombatResolver>();
        Probe.PendingBikeBefore=Combat->PendingBikeRefusals;Probe.PendingSailBefore=Combat->PendingSailRefusals;
    }
    const bool Done=Probe.Tick(Server,Folder);Error=Probe.Error;return Done;
}
bool JapanVehicleQA::Finalize(const FString& Folder,FString& Error)
{
    // The session invokes Finalize after the remote pawn is destroyed. Tick kept
    // its last live state; callback counts remain live through this audit.
    if(!Probe.Complete||Probe.Callbacks!=(Probe.ClockCase()?0:1)||Probe.Contacts!=(Probe.ClockCase()?0:1)||Probe.LastGuestEpoch!=Probe.EndEpoch||
        Probe.LastGuestActivity!=uint8(EJapanActivity::OnFoot)||!FMath::IsNearlyEqual(Probe.HealthBefore-Probe.LastHealth,Probe.ClockCase()?0.f:8.f,.01f))Probe.Fail(TEXT("Vehicle teardown changed the exactly-once outcome"));
    Error=Probe.Error;
    auto Data=MakeShared<FJsonObject>();
    Data->SetStringField(TEXT("case"),Probe.Case);Data->SetBoolField(TEXT("passed"),Error.IsEmpty());
    Data->SetStringField(TEXT("error"),Error);Data->SetNumberField(TEXT("callbacks"),Probe.Callbacks);
    Data->SetNumberField(TEXT("contacts"),Probe.Contacts);Data->SetNumberField(TEXT("end_epoch"),Probe.EndEpoch);
    Data->SetNumberField(TEXT("health"),Probe.LastHealth);Data->SetBoolField(TEXT("parked"),Probe.LastParked);
    if(Probe.Source.IsValid())Probe.Source->Destroy();
    return Write(Folder/TEXT("vehicle-final.json"),Data)&&Error.IsEmpty();
}
void JapanVehicleQA::BeforeBikePark(AWandererCharacter* Rider)
{
    if(!Enabled()||Probe.World.Get()!=Rider->GetWorld()||(Probe.Case!=TEXT("park")&&Probe.Case!=TEXT("crash"))||Probe.Phase!=9||
        Probe.Guest.Get()!=Rider||!Rider->HasAuthority()||!Rider->GetBike()->NeedsNetworkPark())return;
    const FName Expected=Probe.Case==TEXT("park")?TEXT("BikeKickstand"):TEXT("BikeCrash");
    if(Rider->GetBike()->GetClip()!=Expected){Probe.Fail(TEXT("Expected the requested authored terminal clip"));return;}
    // Called above the production NeedsNetworkPark predicate, so the foot handoff
    // caused by Strike cannot fall through into a second CommitNetworkPark.
    Probe.Strike(Rider);Probe.Step(10);
}
#else
bool JapanVehicleQA::Tick(UWorld*,bool,const FString&,FString&){return false;}
bool JapanVehicleQA::Finalize(const FString&,FString&){return true;}
void JapanVehicleQA::BeforeBikePark(AWandererCharacter*){}
#endif

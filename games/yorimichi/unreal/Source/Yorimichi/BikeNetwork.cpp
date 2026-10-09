#include "BikeComponent.h"
#include "WandererCharacter.h"
#include "JapanNetwork.h"
#include "JapanVehicleTelemetry.h"
#include "JapanCharacterMovement.h"
#include "Components/SceneComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Engine/World.h"

void UBikeComponent::SimulateNetwork(float Dt,FVector2D Stick,float RiderLean,bool Menu)
{
    if(!JapanNetwork::IsOnline(GetWorld())||!Rider||State==EState::Off||!FMath::IsFinite(Dt)||Dt<=0.f)return;
    SetInput(Stick,RiderLean,Menu);
    if(bTerminal){Rider->GetCharacterMovement()->Velocity=FVector(0,0,Rider->GetCharacterMovement()->Velocity.Z);return;}
    bool Pedal=false;float Cadence=0.f;
    AdvanceSimulation(Dt,Pedal,Cadence);bNetworkPedalling=Pedal;
}

FJapanBikeState UBikeComponent::CaptureNetworkState() const
{
    FJapanBikeState S;
    S.Yaw=Rider?FRotator::NormalizeAxis(Rider->GetActorRotation().Yaw):0.f;
    S.State=uint8(State);S.Clip=Clip;S.Resume=Resume;S.Serial=Serial;S.ClipTime=ClipTime;
    S.Speed=Speed;S.Steering=Steering;S.StillTime=StillTime;S.AppliedYaw=AppliedYaw;S.Crank=SimCrank;
    S.Coast=Coast;S.Recoil=Recoil;S.Sprint=bSprint;S.Terminal=bTerminal;S.Pedalling=bNetworkPedalling;
    S.Drift=Drift;S.Wheelie=Wheelie;S.WheelieRate=WheelieRate;S.Rise=Rise;S.Air=Air;S.AirFall=AirFall;
    return S;
}

bool UBikeComponent::ApplyNetworkState(const FJapanBikeState& S,bool RestoreFacing)
{
    if(!S.IsValid()||!Rider||!bAssetsReady)return false;
    const FClip* C=Clips.Find(S.Clip);
    if(S.State!=0&&(!C||S.ClipTime>C->Duration+.001f))return false;
    // A correction restores only simulation fields. Activity handoffs separately own
    // attachment, friction, visibility, collision and the retained parked-bike entity.
    if(RestoreFacing)Rider->SetActorRotation(FRotator(0.f,S.Yaw,0.f));
    State=EState(S.State);Clip=S.Clip;Resume=S.Resume;Serial=S.Serial;ClipTime=S.ClipTime;
    Speed=S.Speed;Steering=S.Steering;StillTime=S.StillTime;AppliedYaw=S.AppliedYaw;SimCrank=S.Crank;
    Coast=S.Coast;Recoil=S.Recoil;bSprint=S.Sprint;bTerminal=S.Terminal;bNetworkPedalling=S.Pedalling;
    Drift=S.Drift;Wheelie=S.Wheelie;WheelieRate=S.WheelieRate;Rise=S.Rise;Air=S.Air;AirFall=S.AirFall;
    return true;
}

bool UBikeComponent::CommitNetworkPark()
{
    if(!Rider||!Rider->HasAuthority()||!JapanNetwork::IsOnline(GetWorld())||!bTerminal)return false;
    // Author the terminal bike pose from the simulation, not an interpolated display.
    TArray<float> C;if(!Channels(C))return false;
    Rider->GetMesh()->SetRelativeLocationAndRotation(MeshLocation,MeshRotation);
    Pose(C);
    Park();bTerminal=false;
    return true;
}

bool UBikeComponent::ForceNetworkPark(FJapanBikeState& ParkedPose)
{
    if(!Rider||!Rider->HasAuthority()||!IsEquipped()||!JapanNetwork::IsOnline(GetWorld()))return false;
    // An interrupted hop has no supported parking pose; hide the bike instead.
    if(Rider->GetCharacterMovement()->IsFalling()||Clip==TEXT("BikeHop"))return false;
    const FClip* End=Clips.Find(TEXT("BikeDismount"));
    if(!End)return false;
    State=EState::Parking;Clip=TEXT("BikeDismount");ClipTime=End->Duration;Resume=NAME_None;
    ++Serial;bTerminal=true;bNetworkPedalling=false;Speed=Steering=Drift=Wheelie=WheelieRate=Rise=Air=AirFall=0.f;
    ParkedPose=CaptureNetworkState();
    return CommitNetworkPark();
}

bool UBikeComponent::QueueNetworkAction(FName Button,bool& Accepted)
{
    if(!Rider||!JapanNetwork::IsOnline(GetWorld()))return false;
    auto* Movement=CastChecked<UJapanCharacterMovement>(Rider->GetCharacterMovement());
    if(Movement->IsExecutingMove())return false;
    Accepted=Movement->QueueMoveButton(Button);
    return true;
}

void UBikeComponent::RefreshTickOrder()
{
    if(!Rider)return;
    const bool Online=JapanNetwork::IsOnline(GetWorld());
    if(bTickModeSet&&bNetworkTickOrder==Online)return;
    auto* Movement=Rider->GetCharacterMovement();
    Movement->RemoveTickPrerequisiteComponent(this);
    RemoveTickPrerequisiteComponent(Movement);
    if(Online)AddTickPrerequisiteComponent(Movement);
    else Movement->AddTickPrerequisiteComponent(this);
    bTickModeSet=true;bNetworkTickOrder=Online;
}

bool UBikeComponent::ApplyNetworkActivity(const FJapanBikeState& Snapshot)
{
    if(!Rider||!bAssetsReady||!Snapshot.IsValid()||Snapshot.State==0)return false;
    auto* Movement=Rider->GetCharacterMovement();
    if(State==EState::Off)
    {SavedFriction=Movement->GroundFriction;SavedBraking=Movement->BrakingDecelerationWalking;}
    if(!ApplyNetworkState(Snapshot))return false;
    RefreshTickOrder();
    Movement->GroundFriction=0.f;Movement->BrakingDecelerationWalking=0.f;
    bParked=false;bSnapGround=true;
    BikeRoot->AttachToComponent(Rider->GetMesh(),FAttachmentTransformRules::SnapToTargetNotIncludingScale);
    BikeRoot->SetVisibility(true,true);
    return true;
}

bool UBikeComponent::ShowNetworkParked(const FJapanBikeState& Snapshot,const FTransform& Transform)
{
    if(!Rider||!bAssetsReady||State!=EState::Off||!Snapshot.IsValid()||Transform.ContainsNaN())return false;
    if(!Clips.Contains(Snapshot.Clip))return false;
    // Sample the authored terminal parts without applying the rider's checkpoint
    // or its yaw. This record belongs to the parked object, outside the epoch.
    const FName PreviousClip=Clip;const float PreviousTime=ClipTime,PreviousSteering=Steering;
    Clip=Snapshot.Clip;ClipTime=Snapshot.ClipTime;Steering=Snapshot.Steering;
    TArray<float> C;const bool Ready=Channels(C)!=nullptr;
    if(Ready)
    {
        Pose(C);
        BikeRoot->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
        BikeRoot->SetWorldTransform(Transform);
        BikeRoot->SetVisibility(true,true);bParked=true;
    }
    Clip=PreviousClip;ClipTime=PreviousTime;Steering=PreviousSteering;
    return Ready;
}

void UBikeComponent::HideNetworkParked()
{
    if(State==EState::Off&&BikeRoot){BikeRoot->SetVisibility(false,true);bParked=false;}
}

void UBikeComponent::ReceiveNetworkPresentation(uint32 Epoch,double Stamp,const FJapanBikeState& Snapshot)
{
    if(!Rider||Rider->HasAuthority()||Rider->IsLocallyControlled()||!Snapshot.IsValid()||!FMath::IsFinite(Stamp))return;
    if(Epoch!=Rider->GetActivityEpoch())return;
    if(PresentationBufferEpoch!=Epoch)
    {PresentationBufferEpoch=Epoch;NetworkPoses.Reset();NetworkPlayout=FJapanSkatePlayout();LastPresentationStamp=-1.;}
    if(Stamp<=LastPresentationStamp)return;
    LastPresentationStamp=Stamp;
    const double Now=GetWorld()->GetTimeSeconds();
    const double At=NetworkPlayout.Map(Stamp,Now);
    if(!NetworkPoses.IsEmpty()&&At<=NetworkPoses.Last().At)return;
    NetworkPlayout.ReceivePose(At,Now,.05);
    NetworkPoses.Add({At,Snapshot});
    if(NetworkPoses.Num()>48)NetworkPoses.RemoveAt(0,NetworkPoses.Num()-48);
}

void UBikeComponent::SampleNetworkPresentation()
{
    if(!Rider||Rider->HasAuthority()||Rider->IsLocallyControlled()||NetworkPoses.IsEmpty()||
        PresentationBufferEpoch!=Rider->GetActivityEpoch())return;
    const auto Sample=FJapanSkatePlayout::Sample(NetworkPoses,NetworkPlayout.Advance(GetWorld()->GetTimeSeconds()),
        [](const FNetworkPose& P){return P.At;});
    const auto& A=NetworkPoses[Sample.A].State;const auto& B=NetworkPoses[Sample.B].State;
    FJapanBikeState StateToShow=Sample.Alpha>=1.f?B:A;
    if(A.Serial==B.Serial&&A.State==B.State&&A.Clip==B.Clip)
    {
        float EndTime=B.ClipTime;
        const FClip* C=Clips.Find(A.Clip);
        if(C&&C->bLoop&&EndTime<A.ClipTime)EndTime+=C->Duration;
        StateToShow.ClipTime=FMath::Lerp(A.ClipTime,EndTime,Sample.Alpha);
        if(C&&C->bLoop)StateToShow.ClipTime=FMath::Fmod(StateToShow.ClipTime,C->Duration);
        StateToShow.Speed=FMath::Lerp(A.Speed,B.Speed,Sample.Alpha);
        StateToShow.Steering=FMath::Lerp(A.Steering,B.Steering,Sample.Alpha);
    }
    if(ApplyNetworkState(StateToShow,false))JapanVehicleTelemetry::Presentation(Rider,NetworkPoses[Sample.Alpha>=1.f?Sample.B:Sample.A].At); // CMC owns/smooths the proxy root; visual state never rotates it.
}

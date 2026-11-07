#include "SailboatComponent.h"
#include "WandererCharacter.h"
#include "JapanNetwork.h"
#include "JapanVehicleTelemetry.h"
#include "Components/SceneComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Engine/World.h"

void USailboatComponent::SimulateNetwork(float Dt,FVector2D Stick,bool Menu)
{
    if(!Rider||!bEquipped||!JapanNetwork::IsOnline(GetWorld())||!FMath::IsFinite(Dt)||Dt<=0.f)return;
    SetInput(Stick,Menu);
    AdvanceSimulation(Dt);
}
FJapanSailState USailboatComponent::CaptureNetworkState() const
{
    FJapanSailState S;
    S.Equipped=bEquipped;S.Serial=Serial;
    S.Yaw=Rider?FRotator::NormalizeAxis(Rider->GetActorRotation().Yaw):0.f;
    S.Speed=Speed;S.Steering=Steering;S.SailAmount=SailAmount;S.SailTarget=SailTarget;
    return S;
}
bool USailboatComponent::ApplyNetworkState(const FJapanSailState& S,bool RestoreFacing)
{
    if(!Rider||!bAssetsReady||!S.IsValid())return false;
    if(RestoreFacing)Rider->SetActorRotation(FRotator(0,S.Yaw,0));
    bEquipped=S.Equipped;Serial=S.Serial;Speed=S.Speed;Steering=S.Steering;
    SailAmount=S.SailAmount;SailTarget=S.SailTarget;
    RideVelocity=FRotator(0,S.Yaw,0).Vector()*Speed;
    return true;
}
bool USailboatComponent::ApplyNetworkActivity(const FJapanSailState& S)
{
    if(!S.Equipped||!S.IsValid()||!Rider||!bAssetsReady)return false;
    if(!bEquipped&&Rider->IsLocallyControlled())
        if(auto* Arm=Rider->FindComponentByClass<USpringArmComponent>())
        {
            OriginalSocketOffset=Arm->SocketOffset;OriginalArmLength=Arm->TargetArmLength;
            Arm->SocketOffset=FVector(0,85,125);Arm->TargetArmLength=FMath::Max(850.f,OriginalArmLength);
        }
    if(!ApplyNetworkState(S))return false;
    HullRoot->SetVisibility(true,true);
    Rider->GetCharacterMovement()->SetMovementMode(MOVE_Flying);
    return true;
}

void USailboatComponent::ReceiveNetworkPresentation(uint32 Epoch,double Stamp,const FJapanSailState& Snapshot)
{
    if(!Rider||Rider->HasAuthority()||Rider->IsLocallyControlled()||!Snapshot.IsValid()||!FMath::IsFinite(Stamp)||Epoch!=Rider->GetActivityEpoch())return;
    if(PresentationEpoch!=Epoch){PresentationEpoch=Epoch;NetworkPoses.Reset();NetworkPlayout=FJapanSkatePlayout();LastPresentationStamp=-1.;}
    if(Stamp<=LastPresentationStamp)return;
    LastPresentationStamp=Stamp;
    const double Now=GetWorld()->GetTimeSeconds(),At=NetworkPlayout.Map(Stamp,Now);
    if(!NetworkPoses.IsEmpty()&&At<=NetworkPoses.Last().At)return;
    NetworkPlayout.ReceivePose(At,Now,.05);NetworkPoses.Add({At,Snapshot});
    if(NetworkPoses.Num()>48)NetworkPoses.RemoveAt(0,NetworkPoses.Num()-48);
}
void USailboatComponent::SampleNetworkPresentation()
{
    if(!Rider||Rider->HasAuthority()||Rider->IsLocallyControlled()||NetworkPoses.IsEmpty()||PresentationEpoch!=Rider->GetActivityEpoch())return;
    const auto S=FJapanSkatePlayout::Sample(NetworkPoses,NetworkPlayout.Advance(GetWorld()->GetTimeSeconds()),[](const FNetworkPose& P){return P.At;});
    const auto& A=NetworkPoses[S.A].State;const auto& B=NetworkPoses[S.B].State;
    FJapanSailState Show=S.Alpha>=1.f?B:A;
    if(A.Serial==B.Serial)
    {
        Show.Speed=FMath::Lerp(A.Speed,B.Speed,S.Alpha);Show.Steering=FMath::Lerp(A.Steering,B.Steering,S.Alpha);
        Show.SailAmount=FMath::Lerp(A.SailAmount,B.SailAmount,S.Alpha);
    }
    if(ApplyNetworkState(Show,false))JapanVehicleTelemetry::Presentation(Rider,NetworkPoses[S.Alpha>=1.f?S.B:S.A].At);
}

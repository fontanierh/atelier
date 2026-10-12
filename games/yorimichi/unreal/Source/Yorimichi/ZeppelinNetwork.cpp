#include "ZeppelinService.h"
#include "JapanNetwork.h"
#include "JapanWorld.h"
#include "JapanSession.h"
#include "WandererCharacter.h"
#include "AdventureMoveSet.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Engine/World.h"
#include "Engine/DirectionalLight.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Net/UnrealNetwork.h"

namespace
{
float FlightEase(float T) { T=FMath::Clamp(T,0.f,1.f);return T*T*(3.f-2.f*T); }
double ServerNow(const UWorld* World)
{
 const auto* State=World->GetGameState();
 return State?State->GetServerWorldTimeSeconds():World->GetTimeSeconds();
}
}

void AZeppelinService::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& Out) const
{
 Super::GetLifetimeReplicatedProps(Out);
 DOREPLIFETIME(AZeppelinService,NetworkState);
}

void AZeppelinService::PublishNetworkState()
{
 if(!HasAuthority())return;
 ++NetworkState.Serial;
 NetworkState.Phase=Phase;NetworkState.Dock=Dock;NetworkState.Destination=Destination;NetworkState.Came=Came;
 NetworkState.PhaseTime=PhaseTime;NetworkState.Stamp=GetWorld()->GetTimeSeconds();NetworkState.FlightSpeed=FlightSpeed;
 LastNetworkPublication=NetworkState.Stamp;
 ForceNetUpdate();
}

void AZeppelinService::OnRep_NetworkState()
{
 if(!Ready||!NetworkState.Serial||!Stations.IsValidIndex(NetworkState.Dock)||
    !Stations.IsValidIndex(NetworkState.Destination)||NetworkState.Phase<0||NetworkState.Phase>6)return;
 const bool Changed=!bNetworkStateReceived||Phase!=NetworkState.Phase||Dock!=NetworkState.Dock||Destination!=NetworkState.Destination;
 Phase=NetworkState.Phase;Dock=NetworkState.Dock;Destination=NetworkState.Destination;Came=NetworkState.Came;
 FlightSpeed=NetworkState.FlightSpeed;
 if(Changed)PhaseTime=NetworkState.PhaseTime;
 bNetworkStateReceived=true;
}

FVector AZeppelinService::PassengerSeat(int32 Index) const
{
 // Keep the first two riders side by side inside the deck. Larger sessions use rows.
 return FVector(-70.f+70.f*(Index/2),Index%2?55.f:-55.f,0.f);
}

FVector AZeppelinService::WalkPath(const TArray<FVector>& Points,float Distance,bool& Complete) const
{
 Complete=false;
 if(Points.IsEmpty()){Complete=true;return FVector::ZeroVector;}
 for(int32 I=1;I<Points.Num();++I)
 {
  const float Length=FVector::Dist(Points[I-1],Points[I]);
  if(Distance<Length)return FMath::Lerp(Points[I-1],Points[I],Distance/FMath::Max(Length,.001f));
  Distance-=Length;
 }
 Complete=true;return Points.Last();
}

bool AZeppelinService::InteractNetwork(AWandererCharacter* C)
{
 if(!HasAuthority()||!C||!C->HasAuthority()||!C->IsReady())return false;
 if(IsPassenger(C))
 {
  if(IsFlying()){SetPhase(5);PhaseTime=LandSeconds();PublishNetworkState();}
  return true;
 }
 const int32 At=Nearby(C,260.f);
 if(At==INDEX_NONE)return false;
 if(Phase!=0&&Phase!=2)return false;
 if(At!=Dock)
 {
  if(Phase!=0)return false;
  Came=Dock;Dock=At;Destination=NextStop(At);SetPhase(1);PublishNetworkState();return true;
 }
 if(!C->GetCharacterMovement()->IsMovingOnGround()||C->GetNetworkActivity()!=EJapanActivity::OnFoot)return false;
 // Bound the current deck to eight seats rather than overlapping passengers outside its railings.
 if(NetworkState.Passengers.Num()>=8)return false;
 FZeppelinPassenger P;
 P.Rider=C;P.Start=C->GetActorLocation()-FVector(0,0,C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
 P.BoardedAt=GetWorld()->GetTimeSeconds();
 while(NetworkState.Passengers.ContainsByPredicate([&](const auto& Other){return Other.Seat==P.Seat;}))++P.Seat;
 NetworkState.Passengers.Add(P);
 AddTickPrerequisiteActor(C);C->GetMesh()->AddTickPrerequisiteActor(this);
 C->BeginNetworkActivity(EJapanActivity::Zeppelin);
 if(Phase==0)SetPhase(2);
 PublishNetworkState();return true;
}

bool AZeppelinService::ReplacePassenger(AWandererCharacter* From,AWandererCharacter* To)
{
 if(!HasAuthority()||!To)return false;
 for(auto& P:NetworkState.Passengers)if(P.Rider==From)
 {
  if (const auto* Camera = PassengerCameras.Find(From)) PassengerCameras.Add(To, *Camera);
  RemoveTickPrerequisiteActor(From);From->GetMesh()->RemoveTickPrerequisiteActor(this);
  P.Rider=To;AddTickPrerequisiteActor(To);To->GetMesh()->AddTickPrerequisiteActor(this);
  PublishNetworkState();return true;
 }
 return false;
}

void AZeppelinService::RestoreNetworkCamera(AWandererCharacter* C)
{
 if(!C)return;
 if(const auto* Saved=PassengerCameras.Find(C))
 {
  C->CameraArm->TargetArmLength=Saved->Arm;C->CameraArm->TargetOffset=Saved->Offset;
  C->CameraArm->bDoCollisionTest=Saved->Collision;C->CameraArm->RemoveTickPrerequisiteActor(this);
  PassengerCameras.Remove(C);
 }
 PassengerWalkSpeeds.Remove(C);
}

void AZeppelinService::CancelNetwork(AWandererCharacter* C)
{
 if(!C)return;
 RestoreNetworkCamera(C);
 if(!HasAuthority())return;
 if(!NetworkState.Passengers.RemoveAll([C](const auto& P){return P.Rider==C;}))return;
 RemoveTickPrerequisiteActor(C);C->GetMesh()->RemoveTickPrerequisiteActor(this);
 if(C->GetNetworkActivity()==EJapanActivity::Zeppelin)C->BeginNetworkActivity(EJapanActivity::OnFoot,true);
 if(NetworkState.Passengers.IsEmpty()&&Phase==2)DockAt(Dock);
 PublishNetworkState();
}

void AZeppelinService::SetPassengerCameraDistance(float Distance)
{
 if(!JapanNetwork::IsOnline(GetWorld())){if(Passenger)StoredArm=Distance;return;}
 for(auto& Pair:PassengerCameras)if(Pair.Key.IsValid()&&Pair.Key->IsLocallyControlled())Pair.Value.Arm=Distance;
}

float AZeppelinService::GetWalkSpeed(const AWandererCharacter* C) const
{
 if(!JapanNetwork::IsOnline(GetWorld()))return WalkSpeed;
 if(const float* Value=PassengerWalkSpeeds.Find(const_cast<AWandererCharacter*>(C)))return *Value;
 return 0.f;
}

void AZeppelinService::AdvanceShip(float Dt)
{
 FVector Position=Stations[Dock].Ship;FRotator Rotation=FRotator::ZeroRotator;
 if(Phase==1)Position.Z+=3500.f*(1.f-FlightEase(PhaseTime/5.f));
 else if(Phase==3)
 {
  const float T=FlightEase(FMath::Max(0.f,PhaseTime-.8f)/ClimbSeconds());
  Position.Z=FMath::Lerp<double>(Position.Z,Leg().X,T);Rotation.Yaw=Heading()*T;
 }
 else if(Phase==4)
 {
  const float T=FlightEase(PhaseTime/Leg().Y);
  Position=FMath::Lerp(Stations[Dock].Ship,Stations[Destination].Ship,T);Position.Z=Leg().X+200.f*FMath::Sin(PI*T);
  Rotation=FRotator(0,Heading(),1.3f*FMath::Sin(PI*T));
 }
 else if(Phase==5)
 {
  const float T=FlightEase(PhaseTime/LandSeconds());
  Position=Stations[Destination].Ship;Position.Z=FMath::Lerp<double>(Leg().X,Position.Z,T);Rotation.Yaw=Heading()*(1.f-T);
 }
 ShipRoot->SetWorldLocationAndRotation(Position,Rotation);
}

bool AZeppelinService::PlaceNetworkPassengers(float Dt)
{
 bool AllComplete=true;
 const double Now=ServerNow(GetWorld());
 for(const auto& P:NetworkState.Passengers)
 {
  auto* C=P.Rider.Get();if(!C)continue;
  if(C->GetNetworkActivity()!=EJapanActivity::Zeppelin)continue; // Its activity channel may still be arriving.
  C->GetMesh()->AddTickPrerequisiteActor(this);
  const FVector Seat=ShipRoot->GetComponentTransform().TransformPosition(PassengerSeat(P.Seat));
  FVector Feet=Seat;bool Complete=true;
  if(Phase==2)
  {
   const TArray<FVector> Path={P.Start,Stations[Dock].Origin+AJapanWorld::ToUE(6,.55,1.65),
                              Stations[Dock].Ship+AJapanWorld::ToUE(0,-1.1,0),Seat};
   Feet=WalkPath(Path,float(FMath::Max(0.,Now-P.BoardedAt))*145.f,Complete);
  }
  else if(Phase==6)
  {
   const TArray<FVector> Path={Seat,Stations[Dock].Ship+AJapanWorld::ToUE(0,-1.1,0),
                              Stations[Dock].Origin+AJapanWorld::ToUE(6,.55,1.65),Stations[Dock].Entry};
   Feet=WalkPath(Path,PhaseTime*145.f,Complete);
  }
  AllComplete&=Complete;
  const FVector PreviousFeet=C->GetActorLocation()-FVector(0,0,C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+2.f);
  const FVector Walking=Feet-PreviousFeet;
  const bool Walk=Phase==2||Phase==6;
  PassengerWalkSpeeds.FindOrAdd(C)=Walk&&!Complete?145.f:0.f;
  C->SetActorLocation(Feet+FVector(0,0,C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+2.f),false,nullptr,ETeleportType::TeleportPhysics);
  if(Walk&&Walking.Size2D()>1.f)
   C->SetActorRotation(FMath::RInterpTo(C->GetActorRotation(),FRotator(0,Walking.Rotation().Yaw,0),Dt,7.f));
  else if(!Walk)C->SetActorRotation(FRotator(0,ShipRoot->GetComponentRotation().Yaw,0));
  C->GetCharacterMovement()->Velocity=FVector::ZeroVector;
  if(C->IsLocallyControlled())
  {
   if(!PassengerCameras.Contains(C))
   {
    PassengerCameras.Add(C,{C->CameraArm->TargetArmLength,C->CameraArm->TargetOffset,C->CameraArm->bDoCollisionTest});
    C->CameraArm->bDoCollisionTest=false;C->CameraArm->AddTickPrerequisiteActor(this);
   }
   const auto& Saved=PassengerCameras.FindChecked(C);
   const float Arm=IsFlying()?FMath::Clamp(Saved.Arm*11.f,4200.f,7000.f):Saved.Arm;
   C->CameraArm->TargetArmLength=FMath::FInterpTo(C->CameraArm->TargetArmLength,Arm,Dt,1.2f);
   C->CameraArm->TargetOffset=FMath::VInterpTo(C->CameraArm->TargetOffset,IsFlying()?FVector(0,0,Arm*.24f):Saved.Offset,Dt,1.2f);
  }
 }
 TArray<TWeakObjectPtr<AWandererCharacter>> Cameras;PassengerCameras.GetKeys(Cameras);
 for(const auto& C:Cameras)if(!C.IsValid())PassengerCameras.Remove(C);
 else if(!IsPassenger(C.Get()))RestoreNetworkCamera(C.Get());
 return AllComplete;
}

void AZeppelinService::TickNetwork(float Dt)
{
 auto* World=JapanNetwork::FindWorld(GetWorld());
 if(!World||!World->bGameplayReady)return;
 if(!Ready&&GetNetMode()==NM_Client&&World->ZeppelinRecord.IsValid())Initialize(World->ZeppelinRecord);
 if(!Ready)return;
 World->Zeppelin=this;
 if(!HasAuthority()&&!bNetworkStateReceived)return;
 if(Fabric&&Sun.IsValid())
 {
  const FVector Direction=-Sun->GetActorForwardVector();
  if(!Direction.Equals(LastSunDirection,.0001f)){Fabric->SetVectorParameterValue(TEXT("SunDirection"),FLinearColor(Direction.X,Direction.Y,Direction.Z,0));LastSunDirection=Direction;}
 }
 const float TargetRPM=IsFlying()?(Phase==5?90.f:480.f)*FMath::Sqrt(FlightSpeed):55.f;
 RPM=FMath::FInterpTo(RPM,TargetRPM,Dt,1.2f);PropAngle=FMath::Fmod(PropAngle+RPM*6.f*Dt,360.f);
 for(int32 I=0;I<Propellers.Num();++I)Propellers[I]->SetRelativeRotation(FRotator(0,0,PropAngle*(I?-1:1)));
 if(HasAuthority())
 {
  for(int32 I=NetworkState.Passengers.Num()-1;I>=0;--I)
   if(!IsValid(NetworkState.Passengers[I].Rider)||!NetworkState.Passengers[I].Rider->GetController())NetworkState.Passengers.RemoveAt(I);
  PhaseTime+=Dt*(IsFlying()?FlightSpeed:1.f);
 }
 else
 {
  const float Age=float(FMath::Clamp(ServerNow(GetWorld())-NetworkState.Stamp,0.,.25));
  const float Target=NetworkState.PhaseTime+Age*(IsFlying()?FlightSpeed:1.f);
  PhaseTime+=Dt*(IsFlying()?FlightSpeed:1.f);
  PhaseTime=FMath::FInterpTo(PhaseTime,Target,Dt,12.f);
 }
 AdvanceShip(Dt);
 const bool WalkComplete=PlaceNetworkPassengers(Dt);
 if(HasAuthority())
 {
  if(Phase==1&&PhaseTime>=5.f)DockAt(Dock);
  else if(Phase==2&&WalkComplete&&PhaseTime>=4.f)SetPhase(3);
  else if(Phase==3&&PhaseTime>=ClimbSeconds()+.8f)SetPhase(4);
  else if(Phase==4&&PhaseTime>=Leg().Y)SetPhase(5);
  else if(Phase==5&&PhaseTime>=LandSeconds()+.7f){Came=Dock;Dock=Destination;SetPhase(6);}
  else if(Phase==6&&WalkComplete)
  {
   const auto Leaving=NetworkState.Passengers;NetworkState.Passengers.Reset();
   for(const auto& P:Leaving)if(auto* C=P.Rider.Get())
   {
    RemoveTickPrerequisiteActor(C);C->GetMesh()->RemoveTickPrerequisiteActor(this);RestoreNetworkCamera(C);
    C->BeginNetworkActivity(EJapanActivity::OnFoot);
   }
   DockAt(Dock);
  }
  if(GetWorld()->GetTimeSeconds()-LastNetworkPublication>=.05)PublishNetworkState();
 }
 AdvanceParts(Dt);
}

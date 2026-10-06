#include "SailboatComponent.h"
#include "WandererCharacter.h"
#include "WandererDefinition.h"
#include "JapanWorld.h"
#include "Components/StaticMeshComponent.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Animation/AnimSequence.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"

// Before physics, like the movement component it follows: the mesh waits on it (Initialize), so a later group would carry
// the mesh, and the skate rider's physics control after it, past the physics step.
USailboatComponent::USailboatComponent(){PrimaryComponentTick.bCanEverTick=true;PrimaryComponentTick.TickGroup=TG_PrePhysics;}
void USailboatComponent::Initialize(AWandererCharacter* C,AJapanWorld* W)
{
 Rider=C;Landscape=W;
 OriginalMeshLocation=C->GetMesh()->GetRelativeLocation();OriginalMeshRotation=C->GetMesh()->GetRelativeRotation().Quaternion();
 AddTickPrerequisiteComponent(C->GetCharacterMovement());C->GetMesh()->AddTickPrerequisiteComponent(this);
 HullRoot=NewObject<USceneComponent>(C,TEXT("SailboatRoot"));HullRoot->SetupAttachment(C->GetRootComponent());HullRoot->RegisterComponent();
 auto Part=[&](const TCHAR* Name,const TCHAR* Asset){auto* P=NewObject<UStaticMeshComponent>(C,Name);P->SetupAttachment(HullRoot);P->SetCollisionEnabled(ECollisionEnabled::NoCollision);P->SetGenerateOverlapEvents(false);P->SetCanEverAffectNavigation(false);P->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,Asset));P->RegisterComponent();return P;};
 Hull=Part(TEXT("SailboatHull"),TEXT("/Game/Japan/Assets/SB_Hull.SB_Hull"));
 Sail=Part(TEXT("SailboatSail"),TEXT("/Game/Japan/Assets/SB_Sail.SB_Sail"));
 Boom=Part(TEXT("SailboatBoom"),TEXT("/Game/Japan/Assets/SB_Boom.SB_Boom"));
 ClothMaterial=Sail->CreateDynamicMaterialInstance(0);
 Rudder=Part(TEXT("SailboatRudder"),TEXT("/Game/Japan/Assets/SB_Rudder.SB_Rudder"));
 Wake=Part(TEXT("SailboatWake"),TEXT("/Game/Japan/Assets/SB_Wake.SB_Wake"));Wake->SetCastShadow(false);FoamMaterial=Wake->CreateDynamicMaterialInstance(0);
 HullRoot->SetVisibility(false,true);bAssetsReady=Hull->GetStaticMesh()&&Sail->GetStaticMesh()&&Rudder->GetStaticMesh();
}
void USailboatComponent::QueryParams(FCollisionQueryParams& P) const
{
 P.AddIgnoredActor(Rider);
 if(!Landscape)return;
 P.AddIgnoredComponent(Landscape->Sea);
 for(auto* G:Landscape->Groups)if(G&&G->GetStaticMesh())
 {const FString N=G->GetStaticMesh()->GetName();if(N==TEXT("Sea")||N==TEXT("HD_Sea")||N==TEXT("HD_InlandWater")||N==TEXT("HD_PlazaWater"))P.AddIgnoredComponent(G);}
}
bool USailboatComponent::GroundAt(FVector P,FHitResult& Hit) const
{
 FCollisionQueryParams Q(SCENE_QUERY_STAT(SailboatGround),true);QueryParams(Q);
 return GetWorld()->LineTraceSingleByChannel(Hit,FVector(P.X,P.Y,4000),FVector(P.X,P.Y,-10000),ECC_Visibility,Q);
}
bool USailboatComponent::ClearWater(FVector Center,float Yaw) const
{
 // Confine sailing to the coastal ocean, including the mainland/island crossing.
 if(FMath::Abs(Center.X)>220000 || Center.Y<4000 || Center.Y>150000)return false;
 FRotator R(0,Yaw,0);
 for(FVector Offset:{FVector(170,0,0),FVector(-180,0,0),FVector(0,70,0),FVector(0,-70,0),FVector(0,0,0)})
 {FHitResult H;if(GroundAt(Center+R.RotateVector(Offset),H)&&H.ImpactPoint.Z>-42.f)return false;}
 FCollisionQueryParams Q(SCENE_QUERY_STAT(SailboatHull),false);QueryParams(Q);
 return !GetWorld()->OverlapBlockingTestByChannel(Center+FVector(0,0,52),R.Quaternion(),ECC_WorldStatic,FCollisionShape::MakeBox(FVector(190,78,67)),Q);
}
bool USailboatComponent::FindLanding(FVector& Point) const
{
 const FVector C=HullRoot->GetComponentLocation();const float Half=Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
 for(float Distance:{180.f,260.f,360.f,480.f,600.f})for(int32 I=0;I<16;++I)
 {
  const FVector P=C+FRotator(0,Rider->GetActorRotation().Yaw+I*22.5f,0).Vector()*Distance;FHitResult H;
  if(!GroundAt(P,H)||H.ImpactPoint.Z<0 || H.ImpactPoint.Z>340 || H.ImpactNormal.Z<.72)continue;
  FCollisionQueryParams Q(SCENE_QUERY_STAT(SailboatLanding),false);QueryParams(Q);
  const FVector At=H.ImpactPoint+FVector(0,0,Half+3);
  FHitResult Barrier;
  if(GetWorld()->LineTraceSingleByChannel(Barrier,C+FVector(0,0,Half+60),At,ECC_Visibility,Q))continue;
  if(!GetWorld()->OverlapBlockingTestByChannel(At,FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(Rider->GetCapsuleComponent()->GetScaledCapsuleRadius(),Half),Q)){Point=At;return true;}
 }
 return false;
}
bool USailboatComponent::Toggle()
{
 if(!bAssetsReady||!Rider){Hint=TEXT("Sailboat assets are unavailable");return false;}
 if(bEquipped)
 {
  FVector Landing;if(!FindLanding(Landing)){Hint=TEXT("Sail closer to shore to step off");return false;}
  StowImmediately();Rider->SetActorLocation(Landing,false,nullptr,ETeleportType::TeleportPhysics);Rider->GetCharacterMovement()->bForceNextFloorCheck=true;return true;
 }
 if(!Rider->GetCharacterMovement()->IsMovingOnGround()||Rider->bIsCrouched)return false;
 FHitResult H;const FVector Start=Rider->GetActorLocation();
 if(Start.Z>500){Hint=TEXT("Launch near a beach or low dock");return false;}
 FVector Center;float Yaw=Rider->GetActorRotation().Yaw;bool Found=false;
 for(float Distance:{220.f,350.f,500.f,700.f,950.f})
 {for(float Angle:{0.f,30.f,-30.f,60.f,-60.f,90.f,-90.f,135.f,-135.f,180.f})
  {const float A=Rider->GetActorRotation().Yaw+Angle;const FVector P=Start+FRotator(0,A,0).Vector()*Distance;if(ClearWater(FVector(P.X,P.Y,0),A)){Center=FVector(P.X,P.Y,0);Yaw=A;Found=true;break;}}
  if(Found)break;
 }
 if(!Found){Hint=TEXT("Find an open stretch of shoreline");return false;}
 bEquipped=true;++Serial;Speed=0;SailTarget=0;SailAmount=0;Steering=0;Phase=0;RideVelocity=FVector::ZeroVector;
 auto* M=Rider->GetCharacterMovement();M->StopMovementImmediately();M->SetMovementMode(MOVE_Flying);
 Rider->SetActorLocationAndRotation(Center-FRotator(0,Yaw,0).Vector()*115+FVector(0,0,Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),FRotator(0,Yaw,0),false,nullptr,ETeleportType::TeleportPhysics);
 if(auto* Arm=Rider->FindComponentByClass<USpringArmComponent>()){OriginalSocketOffset=Arm->SocketOffset;OriginalArmLength=Arm->TargetArmLength;Arm->SocketOffset=FVector(0,85,125);Arm->TargetArmLength=FMath::Max(850.f,OriginalArmLength);}
 HullRoot->SetVisibility(true,true);Hint=TEXT("Raise sail to get underway");UpdateVisuals(0);return true;
}
void USailboatComponent::EmergencyStop(){Speed=0;SailTarget=0;Input=FVector2D::ZeroVector;RideVelocity=FVector::ZeroVector;if(Rider)Rider->GetCharacterMovement()->StopMovementImmediately();}
void USailboatComponent::StowImmediately()
{
 if(!bEquipped)return;
 bEquipped=false;++Serial;EmergencyStop();HullRoot->SetVisibility(false,true);
 Rider->GetMesh()->SetRelativeLocationAndRotation(OriginalMeshLocation,OriginalMeshRotation);
 Rider->GetCharacterMovement()->SetMovementMode(MOVE_Falling);
 if(auto* Arm=Rider->FindComponentByClass<USpringArmComponent>()){Arm->SocketOffset=OriginalSocketOffset;Arm->TargetArmLength=OriginalArmLength;}
 Hint=TEXT("Launch near a shore or low dock");
}
void USailboatComponent::SetCameraDistance(float Distance)
{
 if(bEquipped)OriginalArmLength=Distance;
 if(auto* Arm=Rider->FindComponentByClass<USpringArmComponent>())Arm->TargetArmLength=bEquipped?FMath::Max(850.f,Distance):Distance;
}
void USailboatComponent::SetInput(FVector2D V,bool Menu){Input=V;bMenu=Menu;if(Menu&&bEquipped)EmergencyStop();}
UAnimSequence* USailboatComponent::GetSequence() const{return Rider&&Rider->GetDefinition()?Rider->GetDefinition()->FindAction(TEXT("Idle")):nullptr;}
FVector USailboatComponent::PosePoint(FVector Local) const{return HullRoot->GetComponentTransform().TransformPosition(Local);}
FVector USailboatComponent::HandPoint(int32 Side) const{return Side?Rudder->GetComponentTransform().TransformPosition(FVector(100,22,4)):PosePoint(FVector(-84,-25,67));}
FVector USailboatComponent::TillerDirection() const{return Rudder->GetComponentTransform().TransformVectorNoScale(FVector(1,.22,0)).GetSafeNormal();}
FVector USailboatComponent::TillerUp() const{return Rudder->GetUpVector();}
void USailboatComponent::TickComponent(float Dt,ELevelTick Type,FActorComponentTickFunction* Tick)
{
 Super::TickComponent(Dt,Type,Tick);if(!bEquipped||!Rider)return;
 if(bMenu){EmergencyStop();UpdateVisuals(Dt);return;}
 if(Input.Y>.15f)SailTarget=1;else if(Input.Y<-.15f)SailTarget=0;
 SailAmount=FMath::FInterpConstantTo(SailAmount,SailTarget,Dt,1.4f);
 Speed=FMath::FInterpConstantTo(Speed,SailTarget*650,Dt,SailTarget>0?110:340);
 Steering=FMath::FInterpTo(Steering,Input.X,Dt,4.f);
 const float Turn=Steering*42.f*(.3f+.7f*FMath::Clamp(Speed/160.f,0.f,1.f))*Dt;
 const float OldYaw=Rider->GetActorRotation().Yaw,Yaw=OldYaw+Turn;
 const FVector OldCenter=Rider->GetActorLocation()+Rider->GetActorForwardVector()*115-FVector(0,0,Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
 const FVector Forward=FRotator(0,Yaw,0).Vector(),Delta=Forward*Speed*Dt;
 FCollisionQueryParams Q(SCENE_QUERY_STAT(SailboatSweep),false);QueryParams(Q);FHitResult Hit;
 const bool Blocked=GetWorld()->SweepSingleByChannel(Hit,OldCenter+FVector(0,0,52),OldCenter+Delta+FVector(0,0,52),FRotator(0,Yaw,0).Quaternion(),ECC_WorldStatic,FCollisionShape::MakeBox(FVector(190,78,67)),Q);
 if(Blocked||!ClearWater(OldCenter+Delta,Yaw)){Speed=0;SailTarget=0;RideVelocity=FVector::ZeroVector;Hint=TEXT("Shallows ahead - turn away or step ashore");}
 else
 {
  // Component owns surface translation; CharacterMovement receives zero propulsion.
  Rider->SetActorLocationAndRotation(OldCenter+Delta-Forward*115+FVector(0,0,Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),FRotator(0,Yaw,0),false,nullptr,ETeleportType::TeleportPhysics);
  RideVelocity=Forward*Speed;Hint=SailTarget>0?TEXT("Sailing"):TEXT("Sail lowered");
 }
 Rider->GetCharacterMovement()->Velocity=FVector::ZeroVector;UpdateVisuals(Dt);
}
void USailboatComponent::UpdateVisuals(float Dt)
{
 Phase+=Dt;const float Half=Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
 const float Heel=Steering*FMath::Clamp(Speed/650.f,0.f,1.f)*3.f+FMath::Sin(Phase*.9f)*1.0f;
 HullRoot->SetRelativeLocationAndRotation(FVector(115,0,-Half+FMath::Sin(Phase*1.3f)*2),FRotator(FMath::Sin(Phase)*.5f,0,Heel));
 const float Side=Landscape&&FVector::DotProduct(Landscape->WindDir,Rider->GetActorRightVector())<0?-1.f:1.f;
 BoomAngle=FMath::FInterpTo(BoomAngle,Side*(12+20*SailAmount),Dt,2.f);
 Sail->SetRelativeLocationAndRotation(FVector(48,0,160),FRotator(0,BoomAngle,0));Sail->SetRelativeScale3D(FVector(1,1,.035+.965*SailAmount));
 Boom->SetRelativeLocationAndRotation(FVector(48,0,160),FRotator(0,BoomAngle,0));
 if(ClothMaterial){ClothMaterial->SetScalarParameterValue(TEXT("SailFill"),SailAmount);ClothMaterial->SetVectorParameterValue(TEXT("FlutterDirection"),FLinearColor(Sail->GetRightVector()));}
 Rudder->SetRelativeLocationAndRotation(FVector(-190,0,64),FRotator(0,-Steering*22.f,0));
 WakeAmount=FMath::FInterpTo(WakeAmount,FMath::Clamp(Speed/650.f,0.f,1.f),Dt,1.5f);
 const FVector Center=HullRoot->GetComponentLocation();
 Wake->SetWorldLocationAndRotation(FVector(Center.X,Center.Y,3),FRotator(0,Rider->GetActorRotation().Yaw,0));
 Wake->SetVisibility(WakeAmount>.01f);if(FoamMaterial)FoamMaterial->SetScalarParameterValue(TEXT("WakeAmount"),WakeAmount);
}

#include "JapanCharacterMovement.h"
#include "MegaRamp.h"
#include "WandererCharacter.h"
#include "WandererDefinition.h"
#include "SkateboardComponent.h"
#include "SkateComponent.h"
#include "Components/CapsuleComponent.h"
#include "EngineUtils.h"

namespace
{
bool OnMegaDeck(const FVector& Feet,const AMegaRamp* Ramp)
{
 const FVector P=Feet-Ramp->GetActorLocation();
 return P.X>=-320&&P.X<=80&&FMath::Abs(P.Y)<Ramp->HalfWidth-35&&FMath::Abs(P.Z-1070)<65;
}
}
FString UJapanCharacterMovement::MegaEntryHint() const
{
 if(IsMega())return MegaStatus();
 if(!CharacterOwner)return FString();
 const auto* Rider=Cast<AWandererCharacter>(CharacterOwner);
 if(!Rider || !Rider->GetDefinition() || !Rider->GetDefinition()->SupportsSkateboarding)return FString();
 const FVector Feet=UpdatedComponent->GetComponentLocation()-FVector(0,0,CharacterOwner->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
 for(TActorIterator<AMegaRamp> It(GetWorld());It;++It)
 {
  if(OnMegaDeck(Feet,*It))return TEXT("Use to drop in — the ramp carries you through the gap");
  if(FVector::Dist(Feet,It->LadderBottom())<230)return TEXT("Use to climb the mini-mega ladder");
 }
 return FString();
}
bool UJapanCharacterMovement::EnterMegaDeck(AMegaRamp* Candidate,bool Drop)
{
 auto* Rider=Cast<AWandererCharacter>(CharacterOwner);
 if(!Rider||!Candidate||!IsMovingOnGround())return false;
 const FVector Feet=UpdatedComponent->GetComponentLocation()-FVector(0,0,Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
 if(!OnMegaDeck(Feet,Candidate))return false;
 if(Rider->bIsCrouched){UnCrouch();if(Rider->bIsCrouched)return false;}
 if(!Rider->GetSkateboard()->BeginMega())return false;
 Ramp=Candidate;bReturnedVert=false;Section=0;PhaseTime=0;LandingTime=1;LateralSpeed=0;
 SurfaceS=FMath::Clamp(float(Feet.X-Ramp->GetActorLocation().X+300),0.f,300.f);
 Lateral=Feet.Y-Ramp->GetActorLocation().Y;
 SurfaceSpeed=FMath::Max(180.f,float(Velocity.X));
 FVector T,N;BoardPoint=Ramp->Sample(0,SurfaceS,Lateral,T,N);
 MegaPhase=Drop?2:1;
 Rider->GetCapsuleComponent()->IgnoreActorWhenMoving(Ramp,true);
 SetMovementMode(MOVE_Custom,1);
 return true;
}
void UJapanCharacterMovement::UpdateCharacterStateBeforeMovement(float Dt)
{
 Super::UpdateCharacterStateBeforeMovement(Dt);
 auto* Rider=Cast<AWandererCharacter>(CharacterOwner);
 if(!Rider||IsMega()||!IsMovingOnGround())return;
 auto* Skate=Rider->GetSkateboard();
 if(!Skate||!Skate->IsEquipped()||!Skate->CanRoll()||Skate->IsStopping()||Skate->IsMenuOpen())return;
 // Capture ordinary riders on the level deck before walking physics can
 // detach the capsule at the convex drop-in. Keep their earned entry speed.
 if(Velocity.X>30||Skate->GetInput().Y>.15f)
 for(TActorIterator<AMegaRamp> It(GetWorld());It;++It)if(EnterMegaDeck(*It,true))break;
}
bool UJapanCharacterMovement::TryMegaInteract()
{
 auto* Rider=Cast<AWandererCharacter>(CharacterOwner);if(!Rider || !Rider->GetDefinition() || !Rider->GetDefinition()->SupportsSkateboarding)return false;
 if(IsMega()){if(MegaPhase==1){MegaPhase=2;PhaseTime=0;SurfaceSpeed=180;}return true;}
 for(TActorIterator<AMegaRamp> It(GetWorld());It;++It)if(EnterMegaDeck(*It,true))return true;
 if(!IsMovingOnGround())return false;
 if(Rider->bIsCrouched){UnCrouch();if(Rider->bIsCrouched)return false;}
 for(TActorIterator<AMegaRamp> It(GetWorld());It;++It)
 {
  const FVector Feet=UpdatedComponent->GetComponentLocation()-FVector(0,0,Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
  if(FVector::Dist(Feet,It->LadderBottom())>180)continue;
  if(!Rider->GetSkateboard()->BeginMega())return false;
  Ramp=*It;bReturnedVert=false;
  SetMovementMode(MOVE_Custom,1);MegaPhase=0;PhaseTime=0;LandingTime=1;Section=0;SurfaceSpeed=0;LateralSpeed=0;
  // Ramp collision is resolved against its shared surface profile while riding.
  // The capsule still sweeps every displacement against the rest of the world.
  Rider->GetCapsuleComponent()->IgnoreActorWhenMoving(Ramp,true);
  BoardPoint=Feet;Velocity=FVector::ZeroVector;
  return true;
 }
 return false;
}
void UJapanCharacterMovement::ExitMega()
{
 auto* Rider=Cast<AWandererCharacter>(CharacterOwner);if(!Rider)return;
 Rider->GetCapsuleComponent()->IgnoreActorWhenMoving(Ramp,false);
 FHitResult Hit;const FVector P=BoardPoint+FVector(0,0,Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+5);
 SafeMoveUpdatedComponent(P-UpdatedComponent->GetComponentLocation(),FRotator(0,UpdatedComponent->GetComponentRotation().Yaw,0).Quaternion(),true,Hit);
 SetMovementMode(MOVE_Falling);Ramp=nullptr;
}
void UJapanCharacterMovement::StartMegaAir(const FVector& V,bool Vert)
{
 MegaPhase=3;AirTime=0;AirVelocity=V;bVertAir=Vert;VertFlightTime=FMath::Max(.2f,2.f*FMath::Max(0.f,float(V.Z))/-GetGravityZ());
}
void UJapanCharacterMovement::MegaJump()
{
 if(!IsMega()||MegaPhase!=2)return;
 FVector T,N;Ramp->Sample(Section,SurfaceS,Lateral,T,N);
 StartMegaAir(T*SurfaceSpeed+FVector(0,LateralSpeed,0)+N*260,false);
}
FName UJapanCharacterMovement::MegaClip() const
{
 if(MegaPhase==0)return TEXT("MegaClimb");
 if(MegaPhase==1)return TEXT("SkateMount");
 if(MegaPhase==3)return TEXT("MegaAir");
 if(LandingTime<.5f)return TEXT("MegaLand");
 return TEXT("MegaRide");
}
float UJapanCharacterMovement::MegaPoseTime() const
{
 if(MegaPhase==0)return FMath::Fmod(PhaseTime,1.f);
 if(MegaPhase==1)return FMath::Min(PhaseTime,1.2f);
 if(MegaPhase==3)
 {
  // Play approach / hold / release over the actual flight, including short airs.
  float Duration=VertFlightTime;
  if(!bVertAir&&FMath::Abs(AirVelocity.X)>1)
  {
   const float Lip=Ramp->GetActorLocation().X+Ramp->Sections[1].Points[0].X;
   Duration=AirTime+FMath::Max(0.f,(Lip-BoardPoint.X)/AirVelocity.X);
  }
  return .6f*FMath::Clamp(AirTime/FMath::Max(.2f,Duration),0.f,1.f);
 }
 if(LandingTime<.5f)return LandingTime;
 return FMath::Fmod(PhaseTime,2.f);
}
FString UJapanCharacterMovement::MegaStatus() const
{
 if(MegaPhase==0)return TEXT("Climbing to the roll-in");
 if(MegaPhase==1)return TEXT("Push or Use to drop in — no jump needed");
 if(MegaPhase==4)return TEXT("Rollout — returning to the clearing");
 if(MegaPhase==3)return bVertAir?TEXT("Vert air"):TEXT("Gap air");
 return TEXT("Ramp riding — steer / brake");
}
void UJapanCharacterMovement::PhysCustom(float Dt,int32 Iterations)
{
 if(CustomMovementMode==USkateComponent::MovementMode){if(auto* Rider=Cast<AWandererCharacter>(CharacterOwner);Rider&&Rider->GetSkate())Rider->GetSkate()->PhysSkate(Dt);return;}
 if(!IsMega()||!Ramp){Super::PhysCustom(Dt,Iterations);return;}
 auto* Rider=Cast<AWandererCharacter>(CharacterOwner);auto* Skate=Rider->GetSkateboard();
 if(Skate->IsMenuOpen()){Velocity=FVector::ZeroVector;return;}
 const FVector2D Input=Skate->GetInput();const float Half=Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
 float Remaining=FMath::Min(Dt,.25f);
 while(Remaining>SMALL_NUMBER)
 {
  const float H=FMath::Min(Remaining,1.f/120.f);Remaining-=H;PhaseTime+=H;LandingTime+=H;
  FVector T=FVector::ForwardVector,N=FVector::UpVector;
  FQuat Rotation=UpdatedComponent->GetComponentQuat();FVector Target;
  if(MegaPhase==0)
  {
   const FVector Bottom=Ramp->LadderBottom();
   // First align at ground level, then climb rung by rung and step over the deck.
   if(PhaseTime<.6f)BoardPoint=FMath::VInterpTo(BoardPoint,Bottom+FVector(0,24,2),H,10);
   else if(PhaseTime<18.45f)
   {
    float Z=FMath::Min((PhaseTime-.6f)*60.f,1070.f);
    BoardPoint=Bottom+FVector(0,24-Z/1175.f*155.f,Z+2);
   }
   else
   {
    float U=FMath::SmoothStep(0.f,1.f,(PhaseTime-18.45f)/1.0f);
    BoardPoint=FMath::Lerp(Bottom+FVector(0,24-1070.f/1175.f*155.f,1072),Ramp->DeckStart(),U);
    if(U>=1){MegaPhase=1;PhaseTime=0;SurfaceS=120;Lateral=0;}
   }
   Rotation=FRotator(0,-90,0).Quaternion();Target=BoardPoint+FVector(0,0,Half);
  }
  else if(MegaPhase==1)
  {
   Rotation=FQuat::Slerp(Rotation,FQuat::Identity,1-FMath::Exp(-5*H));Target=BoardPoint+FVector(0,0,Half);
   if(PhaseTime>1.2&&Input.Y>.15){MegaPhase=2;PhaseTime=0;SurfaceSpeed=180;Section=0;}
  }
  else if(MegaPhase==2)
  {
   Ramp->Sample(Section,SurfaceS,Lateral,T,N);
   const float Sign=SurfaceSpeed>=0?1.f:-1.f;
   float Accel=GetGravityZ()*T.Z-7.f*Sign;
   if(Input.Y<-.15f||Skate->IsStopping())Accel-=Sign*(240.f+FMath::Abs(SurfaceSpeed)*.24f);
   if(FMath::Abs(SurfaceSpeed)<200&&Input.Y>.15f)Accel+=160.f*Sign;
   const float OldSpeed=SurfaceSpeed;SurfaceSpeed=FMath::Clamp(SurfaceSpeed+Accel*H,-2500.f,2500.f);
   if((Input.Y<-.15f||Skate->IsStopping())&&OldSpeed*SurfaceSpeed<0)SurfaceSpeed=0;
   LateralSpeed=FMath::FInterpTo(LateralSpeed,Input.X*FMath::Abs(SurfaceSpeed)*.28f,H,4);
   SurfaceS+=SurfaceSpeed*H;Lateral+=LateralSpeed*H;
   BoardPoint=Ramp->Sample(Section,SurfaceS,Lateral,T,N);
   FVector Forward=T*(SurfaceSpeed>=0?1.f:-1.f);Rotation=FRotationMatrix::MakeFromXZ(Forward,N).ToQuat();
   Target=BoardPoint+N*(Half+2.f);Velocity=T*SurfaceSpeed+FVector(0,LateralSpeed,0);
   if(FMath::Abs(Lateral)>Ramp->HalfWidth-15){StartMegaAir(Velocity,false);}
   else if(SurfaceS>Ramp->Sections[Section].Lengths.Last())
   {
    if(Section==1)StartMegaAir(Velocity,true);else StartMegaAir(Velocity,false);
   }
   else if(SurfaceS<0){StartMegaAir(Velocity,false);}
   if(Section==1&&bReturnedVert&&SurfaceSpeed<0&&BoardPoint.X<=Ramp->GetActorLocation().X+5200)
   {MegaPhase=4;SurfaceS=0;SurfaceSpeed=FMath::Abs(SurfaceSpeed);RolloutOffset=Lateral;}
   if(Skate->IsStopping()&&FMath::Abs(SurfaceSpeed)<5&&N.Z>.8f){ExitMega();return;}
  }
  else if(MegaPhase==4)
  {
   BoardPoint=Ramp->SampleRollout(SurfaceS,T);
   SurfaceSpeed=FMath::Max(0.f,SurfaceSpeed+(GetGravityZ()*T.Z-15.f-FMath::Max(0.f,SurfaceSpeed-850.f)*1.3f-(Input.Y<-.15f?350.f:0.f))*H);
   SurfaceS+=SurfaceSpeed*H;
   BoardPoint=Ramp->SampleRollout(SurfaceS,T);
   const float Blend=1-FMath::SmoothStep(0.f,600.f,SurfaceS);
   BoardPoint.Y+=RolloutOffset*Blend;
   Rotation=FRotationMatrix::MakeFromXZ(T,FVector::UpVector).ToQuat();N=Rotation.GetUpVector();
   Target=BoardPoint+N*(Half+2);Velocity=T*SurfaceSpeed;
   if(SurfaceS>=Ramp->RolloutLengths.Last()){++RolloutExits;ExitMega();return;}
   if(Skate->IsStopping()&&SurfaceSpeed<5){ExitMega();return;}
  }
  else
  {
   AirTime+=H;FVector Old=BoardPoint;
   AirVelocity.Z+=GetGravityZ()*H;
   // Air steering adjusts lateral travel gently; no airborne forward boost.
   AirVelocity.Y+=Input.X*100.f*H;
   BoardPoint+=AirVelocity*H;
   int32 HitSection=0;float HitS=0,Alpha=0;
   bool Contact=Ramp->CrossSurface(Old+FVector(0,0,.05f),BoardPoint,HitSection,HitS,Alpha);
   // A true vertical launch returns along the same wall. The offset covers
   // numerical drift at its endpoint, without adding speed or raising the rider.
   if(bVertAir&&AirVelocity.Z<0&&BoardPoint.Z<=Ramp->GetActorLocation().Z+610&&AirTime>.1f&&FMath::Abs(BoardPoint.Y-Ramp->GetActorLocation().Y)<Ramp->HalfWidth-15)
   {Contact=true;HitSection=1;HitS=Ramp->Sections[1].Lengths.Last()-.1f;}
   if(Contact)
   {
    Section=HitSection;SurfaceS=HitS;Lateral=BoardPoint.Y-Ramp->GetActorLocation().Y;
    BoardPoint=Ramp->Sample(Section,SurfaceS,Lateral,T,N);
    SurfaceSpeed=FVector::DotProduct(AirVelocity,T);LateralSpeed=AirVelocity.Y;
    if(bVertAir){++VertLandings;bReturnedVert=true;}else if(Section==1)++GapLandings;
    MegaPhase=2;LandingTime=0;PhaseTime=0;
    Rotation=FRotationMatrix::MakeFromXZ(T*(SurfaceSpeed>=0?1.f:-1.f),N).ToQuat();
   }
   else
   {
    if(bVertAir)
    {
     const float U=FMath::Clamp(AirTime/VertFlightTime,0.f,1.f);
     // Rider and deck turn together about the ramp normal, not a somersault.
     Rotation=FRotator(90.f*FMath::Cos(PI*U),180.f*FMath::SmoothStep(.25f,.75f,U),0).Quaternion();
    }
    else
    {
     const FVector Forward=FVector(AirVelocity.X,AirVelocity.Y,AirVelocity.Z*.65f).GetSafeNormal();
     const FQuat Desired=FRotationMatrix::MakeFromXZ(Forward,FVector::UpVector).ToQuat();
     Rotation=FQuat::Slerp(Rotation,Desired,1-FMath::Exp(-5*H));
    }
    N=Rotation.GetUpVector();
   }
   Velocity=AirVelocity;Target=BoardPoint+N*(Half+2);
   if(BoardPoint.Z<Ramp->GetActorLocation().Z+12&&MegaPhase==3){ExitMega();return;}
  }
  FHitResult Hit;SafeMoveUpdatedComponent(Target-UpdatedComponent->GetComponentLocation(),Rotation,true,Hit);
  if(Hit.IsValidBlockingHit())
  {
   // Ordinary obstacles and terrain remain solid even during a failed air.
   BoardPoint=UpdatedComponent->GetComponentLocation()-Rotation.GetUpVector()*Half;
   Velocity=FVector::VectorPlaneProject(Velocity,Hit.Normal);ExitMega();return;
  }
 }
}

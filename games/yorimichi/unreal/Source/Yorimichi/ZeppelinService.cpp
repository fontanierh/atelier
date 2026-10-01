#include "ZeppelinService.h"
#include "JapanWorld.h"
#include "WandererCharacter.h"
#include "SkateComponent.h"
#include "SailboatComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Dom/JsonObject.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Engine/DirectionalLight.h"
#include "EngineUtils.h"
#include "Materials/MaterialInstanceDynamic.h"

static float Ease(float X) { X=FMath::Clamp(X,0.f,1.f);return X*X*(3.f-2.f*X); }
// Ride speeds the passenger can step through in flight. 1x is the authored cruise (Woodland to Hidamari in 28 s).
static const TArray<float> FlightSpeeds={.5f,.75f,1.f,1.5f,2.f,3.f};
static FString SpeedLabel(float Speed)
{
 FString Text=FString::SanitizeFloat(Speed,2);
 while(Text.EndsWith(TEXT("0")))Text.LeftChopInline(1);
 if(Text.EndsWith(TEXT(".")))Text.LeftChopInline(1);
 return Text+TEXT("x");
}
static FVector Local(double X,double Y,double Z) { return AJapanWorld::ToUE(X,Y,Z); }
AZeppelinService::AZeppelinService()
{
 PrimaryActorTick.bCanEverTick=true;
 RootComponent=CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
 ShipRoot=CreateDefaultSubobject<USceneComponent>(TEXT("Ship"));ShipRoot->SetupAttachment(RootComponent);
}
UStaticMeshComponent* AZeppelinService::Mesh(const TCHAR* Name,const TCHAR* Asset,USceneComponent* Parent)
{
 auto* C=NewObject<UStaticMeshComponent>(this,Name);C->SetupAttachment(Parent);C->SetMobility(EComponentMobility::Movable);
 C->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,*FString::Printf(TEXT("/Game/Japan/Assets/%s.%s"),Asset,Asset)));
 C->SetCollisionEnabled(ECollisionEnabled::NoCollision);C->SetGenerateOverlapEvents(false);C->RegisterComponent();return C;
}
void AZeppelinService::Initialize(const TSharedPtr<FJsonObject>& Data)
{
 const TArray<TSharedPtr<FJsonValue>>* Rows=nullptr;const TArray<TSharedPtr<FJsonValue>>* LegRows=nullptr;
 if(!Data.IsValid()||!Data->TryGetArrayField(TEXT("stations"),Rows)||Rows->Num()<2||!Data->TryGetArrayField(TEXT("legs"),LegRows))return;
 for(const auto& V:*Rows)
 {
  auto J=V->AsObject();FZeppelinStation S;S.Name=J->GetStringField(TEXT("name"));
  auto P=[&](const TCHAR* Key){const auto& A=J->GetArrayField(Key);return Local(A[0]->AsNumber(),A[1]->AsNumber(),A[2]->AsNumber());};
  S.Origin=P(TEXT("origin"));S.Ship=P(TEXT("ship"));S.Entry=P(TEXT("entry"));S.Safe=P(TEXT("safe"));Stations.Add(S);
 }
 const int32 N=Stations.Num();Legs.Init(FVector2f::ZeroVector,N*N);
 for(const auto& V:*LegRows)
 {
  auto J=V->AsObject();const auto& Stops=J->GetArrayField(TEXT("stops"));
  if(Stops.Num()!=2)continue;const int32 A=(int32)Stops[0]->AsNumber(),B=(int32)Stops[1]->AsNumber();if(A<0||B<0||A>=N||B>=N||A==B)continue;
  Legs[A*N+B]=Legs[B*N+A]=FVector2f(float(J->GetNumberField(TEXT("height"))*100),float(J->GetNumberField(TEXT("seconds"))));
 }
 for(int32 A=0;A<N;++A)for(int32 B=0;B<N;++B)
  if(A!=B&&Legs[A*N+B].Y<=0){UE_LOG(LogTemp,Error,TEXT("ZEPPELIN has no leg from %s to %s"),*Stations[A].Name,*Stations[B].Name);Stations.Reset();return;}
 Motors=Mesh(TEXT("Motors"),TEXT("ZP_Motors"),ShipRoot);Motors->SetCastShadow(false);Motors->SetAffectDistanceFieldLighting(false);
 Hull=Mesh(TEXT("Hull"),TEXT("ZP_Airship"),ShipRoot);
 // Fabric uses soft continuous shading; fittings retain the world material.
 // Follow the actual sun, including changes made in the lighting settings.
 for(int32 I=0;I<Hull->GetNumMaterials();++I)
  if(Hull->GetMaterial(I)&&Hull->GetMaterial(I)->GetName().Contains(TEXT("ZeppelinFabric")))Fabric=Hull->CreateDynamicMaterialInstance(I);
 TActorIterator<ADirectionalLight> SunActor(GetWorld());if(SunActor)Sun=*SunActor;
 Gate=Mesh(TEXT("DeckGate"),TEXT("ZP_Gate"),ShipRoot);Gate->SetRelativeLocation(Local(-.85,-1.70,0));
 const auto& PropellerPositions=Data->GetArrayField(TEXT("propeller_centers"));
 if(PropellerPositions.Num()!=2)return;
 for(int32 Side=0;Side<2;++Side)
 {
  const auto& Position=PropellerPositions[Side]->AsArray();
  auto* P=Mesh(Side?TEXT("StarboardPropeller"):TEXT("PortPropeller"),TEXT("ZP_Propeller"),ShipRoot);P->SetRelativeLocation(Local(Position[0]->AsNumber(),Position[1]->AsNumber(),Position[2]->AsNumber()));P->SetCastShadow(false);P->SetAffectDistanceFieldLighting(false);Propellers.Add(P);
 }
 for(int32 I=0;I<N;++I)
 {
  auto* G=Mesh(*FString::Printf(TEXT("DockGate%d"),I),TEXT("ZP_Gate"),RootComponent);G->SetRelativeLocation(Stations[I].Origin+Local(5.15,1.04,1.65));DockGates.Add(G);
  auto* W=Mesh(*FString::Printf(TEXT("Gangway%d"),I),TEXT("ZP_Gangway"),RootComponent);W->SetRelativeLocation(Stations[I].Origin+Local(6,1.04,1.65));Gangways.Add(W);
 }
 Ready=Hull->GetStaticMesh()&&Motors->GetStaticMesh()&&Gate->GetStaticMesh()&&Gangways[0]->GetStaticMesh()&&Propellers[0]->GetStaticMesh();
 int32 InitialDock=0;FParse::Value(FCommandLine::Get(),TEXT("zeppelindock="),InitialDock);
 DockAt(FMath::Clamp(InitialDock,0,N-1));UE_LOG(LogTemp,Display,TEXT("ZEPPELIN ready=%d, %d stations"),Ready,N);
}
bool AZeppelinService::IsPassenger(const AWandererCharacter* C) const { return Passenger && Passenger==C; }
FVector AZeppelinService::ShipPosition() const { return ShipRoot->GetComponentLocation(); }
int32 AZeppelinService::Nearby(const AWandererCharacter* C,float Radius) const
{
 if(!C||!Ready)return INDEX_NONE;
 FVector Feet=C->GetActorLocation()-FVector(0,0,C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
 for(int32 I=0;I<Stations.Num();++I)
 {
  const FVector Deck=Feet-Stations[I].Ship;
  const bool OnDeck=I==Dock&&Phase==0&&FMath::Abs(Deck.X)<300&&FMath::Abs(Deck.Y)<160&&FMath::Abs(Deck.Z)<20;
  if(OnDeck||(FVector::Dist2D(Feet,Stations[I].Entry)<Radius&&FMath::Abs(Feet.Z-Stations[I].Entry.Z)<95))return I;
 }
 return INDEX_NONE;
}
FString AZeppelinService::Hint(const AWandererCharacter* C) const
{
 if(IsPassenger(C))
 {
  if(Phase==2)return TEXT("Boarding the zeppelin");
  if(Phase==6)return TEXT("Welcome — stepping onto the platform");
  return FString::Printf(TEXT("Flying to %s at %s — look around · Use to skip"),*Stations[Destination].Name,*SpeedLabel(FlightSpeed));
 }
 int32 I=Nearby(C,420);if(I==INDEX_NONE)return FString();
 if(Phase!=0)return Phase==1?TEXT("Zeppelin arriving — wait on the platform"):TEXT("Zeppelin is travelling — please wait");
 return I==Dock?FString::Printf(TEXT("Use to board · %s"),*Stations[Destination].Name):TEXT("Use to call the zeppelin");
}
bool AZeppelinService::CanChooseStop(const AWandererCharacter* C) const
{
 return Stations.Num()>2&&Phase==0&&!IsPassenger(C)&&Nearby(C,420)==Dock;
}
bool AZeppelinService::ChooseDestination(const AWandererCharacter* C,int32 Direction)
{
 if(Direction==0||!CanChooseStop(C))return false;
 const int32 N=Stations.Num();int32 Next=Destination;
 do Next=(Next+(Direction<0?N-1:1))%N; while(Next==Dock);
 Destination=Next;UE_LOG(LogTemp,Display,TEXT("ZEPPELIN destination=%d"),Destination);return true;
}
int32 AZeppelinService::NextStop(int32 At) const
{
 // Carry on along the line the way the ship came, turning back at either end.
 int32 Step=Came!=INDEX_NONE&&Came>At?-1:1;
 if(!Stations.IsValidIndex(At+Step))Step=-Step;
 return Stations.IsValidIndex(At+Step)?At+Step:At;
}
float AZeppelinService::Heading() const { return float((Stations[Destination].Ship-Stations[Dock].Ship).Rotation().Yaw); }
// Long climbs and descents (the Mega Park legs cruise high over the volcano's flank) take longer than the 5 and 4 seconds of the first leg.
float AZeppelinService::ClimbSeconds() const { return FMath::Max(5.f,float(FMath::Abs(Leg().X-Stations[Dock].Ship.Z))/2400.f); }
float AZeppelinService::LandSeconds() const { return FMath::Max(4.f,float(FMath::Abs(Leg().X-Stations[Destination].Ship.Z))/3000.f); }
void AZeppelinService::AdjustFlightSpeed(int32 Direction)
{
 if(Direction==0)return;
 int32 Index=0;float Best=BIG_NUMBER;
 for(int32 I=0;I<FlightSpeeds.Num();++I){const float D=FMath::Abs(FlightSpeeds[I]-FlightSpeed);if(D<Best){Best=D;Index=I;}}
 const int32 Next=FMath::Clamp(Index+FMath::Clamp(Direction,-1,1),0,FlightSpeeds.Num()-1);
 if(Next==Index)return;
 FlightSpeed=FlightSpeeds[Next];
 UE_LOG(LogTemp,Display,TEXT("ZEPPELIN flight speed %s"),*SpeedLabel(FlightSpeed));
}
void AZeppelinService::SetPhase(int32 P)
{
 Phase=P;PhaseTime=0;UE_LOG(LogTemp,Display,TEXT("ZEPPELIN phase=%d dock=%d destination=%d"),Phase,Dock,Destination);
 // Frame departure exactly once, on the state transition. The flight clock is
 // speed-scaled, so comparing it with a frame delta can skip (or repeat) this.
 if(Phase==3&&Passenger&&Passenger->Controller)
  Passenger->Controller->SetControlRotation(FRotator(-12,ShipRoot->GetComponentRotation().Yaw+45,0));
}
void AZeppelinService::DockAt(int32 I)
{
 Dock=I;Destination=NextStop(I);ShipRoot->SetWorldLocationAndRotation(Stations[I].Ship,FRotator::ZeroRotator);GateOpen=0;SetPhase(0);
}
bool AZeppelinService::TryInteract(AWandererCharacter* C)
{
 if(!Ready)return false;
 if(IsPassenger(C))
 {
  // Skipping still performs docking and disembarkation; never drops the rider in mid-air.
  if(Phase>=3&&Phase<=5){ShipRoot->SetWorldLocationAndRotation(Stations[Destination].Ship,FRotator::ZeroRotator);SetPhase(5);PhaseTime=LandSeconds();}
  return true;
 }
 int32 I=Nearby(C,260);if(I==INDEX_NONE)return false;
 if(Phase!=0)return true;
 if(I!=Dock)
 {
  Came=Dock;Dock=I;Destination=NextStop(I);ShipRoot->SetWorldLocationAndRotation(Stations[I].Ship+FVector(0,0,3500),FRotator::ZeroRotator);SetPhase(1);return true;
 }
 if(!C->GetCharacterMovement()->IsMovingOnGround())return true;
 BeginBoarding(C);return true;
}
void AZeppelinService::BeginBoarding(AWandererCharacter* C)
{
 Passenger=C;AddTickPrerequisiteActor(C);C->CameraArm->AddTickPrerequisiteActor(this);
 auto* M=C->GetCharacterMovement();C->GetSkate()->StowImmediately();C->Sailboat->StowImmediately();C->UnCrouch();
 C->SetAction(NAME_None);C->MoveIntent=FVector2D::ZeroVector;C->bSprintHeld=false;C->JumpBuffer=0;C->bPendingTakeoff=false;C->StopJumping();
 M->StopMovementImmediately();M->ClearAccumulatedForces();M->CurrentRootMotion.Clear();M->SetMovementMode(MOVE_None);C->SetActorEnableCollision(false);
 StoredArm=C->CameraArm->TargetArmLength;StoredOffset=C->CameraArm->TargetOffset;StoredCameraCollision=C->CameraArm->bDoCollisionTest;
 C->CameraArm->bDoCollisionTest=false;
 const FVector Deck=C->GetActorLocation()-FVector(0,0,C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight())-Stations[Dock].Ship;
 const bool AlreadyAboard=FMath::Abs(Deck.X)<300&&FMath::Abs(Deck.Y)<160&&FMath::Abs(Deck.Z)<20;
 WalkPoints=AlreadyAboard?TArray<FVector>{Stations[Dock].Ship}:TArray<FVector>{Stations[Dock].Origin+Local(6,.55,1.65),Stations[Dock].Ship+Local(0,-1.1,0),Stations[Dock].Ship};WalkIndex=0;
 SetPhase(2);
}
void AZeppelinService::RestorePassenger()
{
 if(!Passenger)return;auto* C=Passenger.Get();RemoveTickPrerequisiteActor(C);C->CameraArm->RemoveTickPrerequisiteActor(this);Passenger=nullptr;
 C->SetActorEnableCollision(true);auto* M=C->GetCharacterMovement();M->StopMovementImmediately();M->ClearAccumulatedForces();M->SetMovementMode(MOVE_Walking);M->bForceNextFloorCheck=true;
 C->MoveIntent=FVector2D::ZeroVector;C->bJog=C->bWalk=C->bSprintHeld=false;C->SetAction(NAME_None);
 C->CameraArm->TargetArmLength=StoredArm;C->CameraArm->TargetOffset=StoredOffset;C->CameraArm->bDoCollisionTest=StoredCameraCollision;WalkSpeed=0;
}
void AZeppelinService::Cancel(AWandererCharacter* C)
{
 if(!IsPassenger(C))return;RestorePassenger();DockAt(Dock);
}
void AZeppelinService::EndPlay(const EEndPlayReason::Type Reason)
{RestorePassenger();Super::EndPlay(Reason);}
void AZeppelinService::WalkPassenger(float Dt)
{
 if(!Passenger||!WalkPoints.IsValidIndex(WalkIndex))return;
 auto* C=Passenger.Get();const FVector Offset(0,0,C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+2.f);
 const FVector Before=C->GetActorLocation();FVector Target=WalkPoints[WalkIndex]+Offset;
 const FVector Next=FMath::VInterpConstantTo(Before,Target,Dt,145.f);const FVector V=(Next-Before)/FMath::Max(Dt,.001f);WalkSpeed=V.Size2D();
 C->SetActorLocation(Next,false,nullptr,ETeleportType::TeleportPhysics);
 if(V.Size2D()>2)C->SetActorRotation(FMath::RInterpTo(C->GetActorRotation(),FRotator(0,V.Rotation().Yaw,0),Dt,7.f));
 if(FVector::Dist(Next,Target)<2.f)++WalkIndex;
}
void AZeppelinService::PlacePassenger(bool Walking,float Dt)
{
 if(!Passenger)return;auto* C=Passenger.Get();
 if(Walking)WalkPassenger(Dt);
 else
 {
  WalkSpeed=0;C->GetCharacterMovement()->Velocity=FVector::ZeroVector;
  C->SetActorLocation(ShipPosition()+FVector(0,0,C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+2.f),false,nullptr,ETeleportType::TeleportPhysics);
  C->SetActorRotation(FRotator(0,ShipRoot->GetComponentRotation().Yaw,0));
 }
 const bool Flight=IsFlying();
 // Pull well back in flight so the landscape reads, scaled by whatever camera distance the player prefers.
 const float FlightArm=FMath::Clamp(StoredArm*11.f,4200.f,7000.f);
 C->CameraArm->TargetArmLength=FMath::FInterpTo(C->CameraArm->TargetArmLength,Flight?FlightArm:StoredArm,Dt,1.2f);
 C->CameraArm->TargetOffset=FMath::VInterpTo(C->CameraArm->TargetOffset,Flight?FVector(0,0,FlightArm*.24f):StoredOffset,Dt,1.2f);
}
void AZeppelinService::Tick(float Dt)
{
 Super::Tick(Dt);if(!Ready)return;
 if(Fabric&&Sun.IsValid())
 {
  const FVector Direction=-Sun->GetActorForwardVector();
  if(!Direction.Equals(LastSunDirection,.0001f)){Fabric->SetVectorParameterValue(TEXT("SunDirection"),FLinearColor(Direction.X,Direction.Y,Direction.Z,0));LastSunDirection=Direction;}
 }
 const float TargetRPM=IsFlying()?(Phase==5?90.f:480.f)*FMath::Sqrt(FlightSpeed):55.f;
 RPM=FMath::FInterpTo(RPM,TargetRPM,Dt,1.2f);PropAngle=FMath::Fmod(PropAngle+RPM*6.f*Dt,360.f);
 for(int32 I=0;I<Propellers.Num();++I)Propellers[I]->SetRelativeRotation(FRotator(0,0,PropAngle*(I?-1:1)));
 if(Passenger&&Passenger->bMenuOpen)return;
 PhaseTime+=IsFlying()?Dt*FlightSpeed:Dt;
 if(Phase==1)
 {
  ShipRoot->SetWorldLocation(Stations[Dock].Ship+FVector(0,0,3500*(1-Ease(PhaseTime/5.f))));
  if(PhaseTime>=5)DockAt(Dock);
 }
 else if(Phase==2)
 {
  PlacePassenger(true,Dt);if(WalkIndex>=WalkPoints.Num()){WalkSpeed=0;SetPhase(3);}
 }
 else if(Phase==3)
 {
  const float Climb=ClimbSeconds(),T=Ease(FMath::Max(0.f,PhaseTime-.8f)/Climb);
  FVector P=Stations[Dock].Ship;P.Z=FMath::Lerp<double>(P.Z,Leg().X,T);
  ShipRoot->SetWorldLocationAndRotation(P,FRotator(0,Heading()*T,0));PlacePassenger(false,Dt);
  if(PhaseTime>=Climb+.8f)SetPhase(4);
 }
 else if(Phase==4)
 {
  const float Cruise=Leg().Y,T=Ease(PhaseTime/Cruise);FVector P=FMath::Lerp(Stations[Dock].Ship,Stations[Destination].Ship,T);P.Z=Leg().X+200*FMath::Sin(PI*T);
  ShipRoot->SetWorldLocationAndRotation(P,FRotator(0,Heading(),1.3f*FMath::Sin(PI*T)));PlacePassenger(false,Dt);
  if(PhaseTime>=Cruise)SetPhase(5);
 }
 else if(Phase==5)
 {
  const float Land=LandSeconds(),T=Ease(PhaseTime/Land);FVector P=Stations[Destination].Ship;P.Z=FMath::Lerp<double>(Leg().X,P.Z,T);
  ShipRoot->SetWorldLocationAndRotation(P,FRotator(0,Heading()*(1-T),0));PlacePassenger(false,Dt);
  if(PhaseTime>=Land+.7f)
  {
   Came=Dock;Dock=Destination;WalkPoints={Stations[Dock].Ship+Local(0,-1.1,0),Stations[Dock].Origin+Local(6,.55,1.65),Stations[Dock].Entry};WalkIndex=0;SetPhase(6);
  }
 }
 else if(Phase==6)
 {
  PlacePassenger(true,Dt);if(WalkIndex>=WalkPoints.Num()){RestorePassenger();DockAt(Dock);}
 }
 Hull->SetCollisionEnabled(Phase==0?ECollisionEnabled::QueryAndPhysics:ECollisionEnabled::NoCollision);
 const bool Landed=Phase==5&&PhaseTime>=LandSeconds();
 const bool Open=Phase==2||Phase==6||Landed;
 GateOpen=FMath::FInterpConstantTo(GateOpen,Open?1.f:0.f,Dt,2.5f);Gate->SetRelativeRotation(FRotator(0,-90*GateOpen,0));
 for(int32 I=0;I<DockGates.Num();++I)
 {
  const bool At=(I==Dock&&(Phase==0||Phase==2||Phase==6))||(I==Destination&&Landed);
  auto* G=DockGates[I].Get();const float Yaw=FMath::FInterpConstantTo(G->GetRelativeRotation().Yaw,(At&&Open)?-90.f:0.f,Dt,180.f);G->SetRelativeRotation(FRotator(0,Yaw,0));
  const float Fold=FMath::FInterpConstantTo(Gangways[I]->GetRelativeRotation().Roll,At?0.f:-90.f,Dt,150.f);
  Gangways[I]->SetRelativeRotation(FRotator(0,0,Fold));Gangways[I]->SetVisibility(Fold>-89.f);
  const bool Walkable=At&&FMath::Abs(Fold)<1.f;
  G->SetCollisionEnabled((Walkable&&FMath::Abs(Yaw)>89.f)?ECollisionEnabled::NoCollision:ECollisionEnabled::QueryAndPhysics);
  Gangways[I]->SetCollisionEnabled(Walkable?ECollisionEnabled::QueryAndPhysics:ECollisionEnabled::NoCollision);
 }
}

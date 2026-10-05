#include "BikeComponent.h"
#include "WandererCharacter.h"
#include "AtelierData.h"
#include "Components/StaticMeshComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Animation/AnimSequence.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Misc/FileHelper.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
 // rider.py and the bike's manifest work in Blender metres (+X forward, +Y left); the mesh frame is Unreal centimetres
 // with +Y right. A rotation keeps its matrix under that mirror once its axis is mirrored and its angle negated.
 FVector FromBlender(const TArray<TSharedPtr<FJsonValue>>& V){return FVector(V[0]->AsNumber()*100.,-V[1]->AsNumber()*100.,V[2]->AsNumber()*100.);}
 FQuat Turn(FVector BlenderAxis,float Degrees){return FQuat(FVector(BlenderAxis.X,-BlenderAxis.Y,BlenderAxis.Z).GetSafeNormal(),-FMath::DegreesToRadians(Degrees));}
 enum{ChCrank,ChStand,ChLift,ChPitch,ChLean,ChYaw,ChSteer,ChannelCount};   // a clip frame's bike channels
 const TCHAR* LimbNames[]={TEXT("hand_L"),TEXT("hand_R"),TEXT("foot_L"),TEXT("foot_R")};
 constexpr float TopSpeed=600.f,SprintSpeed=850.f,CrashSpeed=450.f,BarDegrees=18.f,ClipBlend=.2f;
 // BikeCrash throws him over the bars: his hands land 1.64 m ahead of where the bike stopped (rider.py). Against a wall the
 // bike and he rebound in the first CrashRecoil seconds to make that room.
 constexpr float CrashRoom=185.f,CrashRecoil=.3f;   // ClipBlend: the anim instance's
}

UBikeComponent::UBikeComponent(){PrimaryComponentTick.bCanEverTick=true;}

bool UBikeComponent::LoadData()
{
 FString Text;TSharedPtr<FJsonObject> Manifest,Export;
 if(!FFileHelper::LoadFileToString(Text,*AtelierDataPath(TEXT("bike/manifest.json")))||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Manifest)||!Manifest)return false;
 if(!FFileHelper::LoadFileToString(Text,*AtelierDataPath(TEXT("cairo/bike/export.json")))||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Export)||!Export)return false;
 const TSharedPtr<FJsonObject> Pivots=Manifest->GetObjectField(TEXT("pivots")),Seat=Manifest->GetObjectField(TEXT("rider"));
 HeadPivot=FromBlender(Pivots->GetArrayField(TEXT("BK_Steer")));
 FrontAxle=FromBlender(Pivots->GetArrayField(TEXT("BK_WheelFront")));RearAxle=FromBlender(Pivots->GetArrayField(TEXT("BK_WheelRear")));
 BottomBracket=FromBlender(Pivots->GetArrayField(TEXT("BK_Crank")));StandPivot=FromBlender(Pivots->GetArrayField(TEXT("BK_Kickstand")));
 RearContact=FVector(RearAxle.X,0,0);
 const float Tilt=FMath::DegreesToRadians(Manifest->GetNumberField(TEXT("steer_axis_tilt_degrees")));
 SteerAxis=FVector(-FMath::Sin(Tilt),0,FMath::Cos(Tilt));   // leaning back; no Y, so the mirror leaves it
 // build.py frame_along(AXIS): the steer part's Z runs up the steering axis, its X forward in the bike's plane.
 SteerRest=FRotationMatrix::MakeFromXZ((FVector::ForwardVector-SteerAxis*SteerAxis.X).GetSafeNormal(),SteerAxis).ToQuat();
 const TArray<TSharedPtr<FJsonValue>>& Grips=Seat->GetArrayField(TEXT("grips"));
 Grip[0]=FromBlender(Grips[0]->AsArray());Grip[1]=FromBlender(Grips[1]->AsArray());
 WheelRadius=Manifest->GetNumberField(TEXT("wheel_radius"))*100.f;CrankLength=Manifest->GetNumberField(TEXT("crank_length"))*100.f;
 PedalOffset=Manifest->GetNumberField(TEXT("pedal_offset_y"))*100.f;StowedDegrees=Manifest->GetNumberField(TEXT("kickstand_stowed_degrees"));
 Fps=Export->GetIntegerField(TEXT("fps"));
 for(const auto& Pair:Export->GetObjectField(TEXT("clips"))->Values)
 {
  const TSharedPtr<FJsonObject> J=Pair.Value->AsObject();FClip& C=Clips.Add(FName(Pair.Key));
  C.Duration=J->GetNumberField(TEXT("duration"));C.bLoop=J->GetBoolField(TEXT("loop"));
  for(const auto& Row:J->GetArrayField(TEXT("bike"))){TArray<float>& F=C.Frames.AddDefaulted_GetRef();for(const auto& V:Row->AsArray())F.Add(V->AsNumber());check(F.Num()==ChannelCount);}
  const TSharedPtr<FJsonObject> Contacts=J->GetObjectField(TEXT("contacts"));
  for(int32 L=0;L<4;++L)for(const auto& Span:Contacts->GetArrayField(LimbNames[L])){const auto& S=Span->AsArray();C.Contacts[L].Add(FVector2D(S[0]->AsNumber(),S[1]->AsNumber()));}
  const TArray<TSharedPtr<FJsonValue>>* End;
  if(J->TryGetArrayField(TEXT("end_offset"),End)){C.EndOffset=FVector2D((*End)[0]->AsNumber()*100.,-(*End)[1]->AsNumber()*100.);C.bEndOffset=true;}
 }
 // Beside the bike, as BikeMount starts and BikeKickstand ends: where his feet are when the bike stands parked.
 if(const FClip* Park=Clips.Find(TEXT("BikeKickstand")))Beside=FVector(Park->EndOffset,0);
 return Clips.Contains(TEXT("BikeRide"))&&Clips.Contains(TEXT("BikeMount"));
}

void UBikeComponent::Initialize(AWandererCharacter* C)
{
 Rider=C;
 auto* Movement=C->GetCharacterMovement();
 // Speed and heading are set here before the movement component moves him, and the parts are posed before the mesh.
 Movement->AddTickPrerequisiteComponent(this);C->GetMesh()->AddTickPrerequisiteComponent(this);
 BikeRoot=NewObject<USceneComponent>(C,TEXT("BikeRoot"));BikeRoot->SetupAttachment(C->GetMesh());BikeRoot->RegisterComponent();
 auto Part=[&](const TCHAR* Name,const TCHAR* Asset)
 {
  auto* P=NewObject<UStaticMeshComponent>(C,Name);P->SetupAttachment(BikeRoot);P->SetCollisionEnabled(ECollisionEnabled::NoCollision);P->SetGenerateOverlapEvents(false);
  P->SetCanEverAffectNavigation(false);P->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,Asset));P->RegisterComponent();return P;
 };
 Frame=Part(TEXT("BikeFrame"),TEXT("/Game/Japan/Assets/BK_Frame.BK_Frame"));
 Steer=Part(TEXT("BikeSteer"),TEXT("/Game/Japan/Assets/BK_Steer.BK_Steer"));
 WheelFront=Part(TEXT("BikeWheelFront"),TEXT("/Game/Japan/Assets/BK_WheelFront.BK_WheelFront"));
 WheelRear=Part(TEXT("BikeWheelRear"),TEXT("/Game/Japan/Assets/BK_WheelRear.BK_WheelRear"));
 Crank=Part(TEXT("BikeCrank"),TEXT("/Game/Japan/Assets/BK_Crank.BK_Crank"));
 PedalL=Part(TEXT("BikePedalL"),TEXT("/Game/Japan/Assets/BK_Pedal.BK_Pedal"));
 PedalR=Part(TEXT("BikePedalR"),TEXT("/Game/Japan/Assets/BK_Pedal.BK_Pedal"));
 Kickstand=Part(TEXT("BikeKickstand"),TEXT("/Game/Japan/Assets/BK_Kickstand.BK_Kickstand"));
 RackBoard=Part(TEXT("BikeRackBoard"),TEXT("/Game/Japan/Assets/BK_RackBoard.BK_RackBoard"));
 BikeRoot->SetVisibility(false,true);
 bool bParts=true;for(const UStaticMeshComponent* P:TArray<UStaticMeshComponent*>{Frame,Steer,WheelFront,WheelRear,Crank,PedalL,Kickstand,RackBoard})bParts&=P->GetStaticMesh()!=nullptr;
 bAssetsReady=bParts&&LoadData();
 if(bAssetsReady)for(const auto& Pair:Clips)
 {
  const FString Name=Pair.Key.ToString();
  if(UAnimSequence* S=LoadObject<UAnimSequence>(nullptr,*FString::Printf(TEXT("/Game/CairoBike/A_%s.A_%s"),*Name,*Name)))Sequences.Add(Pair.Key,S);
 }
 MeshLocation=C->GetMesh()->GetRelativeLocation();MeshRotation=C->GetMesh()->GetRelativeRotation();
}

UAnimSequence* UBikeComponent::GetSequence() const{const TObjectPtr<UAnimSequence>* S=Sequences.Find(Clip);return S?S->Get():nullptr;}

FTransform UBikeComponent::BikeMatrix(const TArray<float>& C) const
{
 // rider.py bike_matrix: lift, pitch about the rear contact (nose up positive), lean about the ground line (left positive).
 return FTransform(Turn(FVector(1,0,0),-C[ChLean]))*FTransform(-RearContact)*FTransform(Turn(FVector(0,1,0),-C[ChPitch]))*FTransform(RearContact)*FTransform(FVector(0,0,C[ChLift]*100.f));
}
FQuat UBikeComponent::SteerQuat(float Degrees) const{return FQuat(SteerAxis,-FMath::DegreesToRadians(Degrees));}

const TArray<float>* UBikeComponent::Channels(TArray<float>& Out) const
{
 const FClip* C=Clips.Find(Clip);if(!C||C->Frames.IsEmpty())return nullptr;
 const int32 N=C->Frames.Num();const float F=ClipTime*Fps;
 int32 A=FMath::FloorToInt(F);const float S=F-A;int32 B=A+1;
 if(C->bLoop){A=((A%N)+N)%N;B=(A+1)%N;}else{A=FMath::Clamp(A,0,N-1);B=FMath::Clamp(B,0,N-1);}
 Out.SetNum(ChannelCount);
 for(int32 I=0;I<ChannelCount;++I)
 {
  float V0=C->Frames[A][I],V1=C->Frames[B][I];
  if(I==ChCrank&&C->bLoop&&B==0)V1=C->Frames[N-1][I]+(C->Frames[N-1][I]-C->Frames[FMath::Max(N-2,0)][I]);   // one cycle on
  Out[I]=FMath::Lerp(V0,V1,S);
 }
 return &Out;
}

float UBikeComponent::ContactWeight(int32 Limb) const
{
 const FClip* C=Clips.Find(Clip);if(!C)return 0.f;
 const float T=C->bLoop?FMath::Fmod(ClipTime,C->Duration):ClipTime;float W=0.f;
 for(const FVector2D& Span:C->Contacts[Limb])
 {
  const float In=Span.X<=0.f?1.f:FMath::Clamp((T-Span.X)/.1f+1.f,0.f,1.f),Out=Span.Y>=C->Duration-.001f?1.f:FMath::Clamp((Span.Y-T)/.1f+1.f,0.f,1.f);
  W=FMath::Max(W,FMath::Min(In,Out)*(T>=Span.X-.1f&&T<=Span.Y+.1f?1.f:0.f));
 }
 return W;
}

void UBikeComponent::GetGrip(int32 Side,float& Weight,FVector& Offset,FQuat& TurnOut) const
{
 Weight=0.f;Offset=FVector::ZeroVector;TurnOut=FQuat::Identity;
 TArray<float> C;if(State==EState::Off||!Channels(C)||FMath::Abs(Steering)<.01f)return;
 const float Extra=-Steering*BarDegrees;   // right on the stick turns the bars right: Blender's negative steer
 const FTransform B=BikeMatrix(C);
 auto About=[&](float Degrees){return FTransform(-HeadPivot)*FTransform(SteerQuat(Degrees))*FTransform(HeadPivot);};
 const FVector Authored=B.TransformPosition(About(C[ChSteer]).TransformPosition(Grip[Side]));
 const FVector Live=B.TransformPosition(About(C[ChSteer]+Extra).TransformPosition(Grip[Side]));
 Weight=ContactWeight(Side);Offset=Live-Authored;
 TurnOut=B.GetRotation()*SteerQuat(Extra)*B.GetRotation().Inverse();
}

void UBikeComponent::Pose(const TArray<float>& C)
{
 Displayed=C;
 BikeRoot->SetRelativeTransform(BikeMatrix(C));
 const FTransform S=FTransform(-HeadPivot)*FTransform(SteerQuat(C[ChSteer]-Steering*BarDegrees))*FTransform(HeadPivot);
 Steer->SetRelativeTransform(FTransform(SteerRest,HeadPivot)*S);
 // Rolling forward turns the wheels' tops forward (rider.py: +angle about Blender Y).
 const FQuat Roll=Turn(FVector(0,1,0),FMath::RadiansToDegrees(WheelAngle));
 WheelFront->SetRelativeTransform(FTransform(Roll,FrontAxle)*S);
 WheelRear->SetRelativeTransform(FTransform(Roll,RearAxle));
 Crank->SetRelativeTransform(FTransform(Turn(FVector(0,1,0),-C[ChCrank]),BottomBracket));
 for(int32 Side=0;Side<2;++Side)
 {
  const float A=FMath::DegreesToRadians(C[ChCrank])+(Side?0.f:PI);   // 0 left, 1 right; the right crank is at the angle
  const FVector At=BottomBracket+FVector(CrankLength*FMath::Cos(A),(Side?1.f:-1.f)*PedalOffset,CrankLength*FMath::Sin(A));
  (Side?PedalR:PedalL)->SetRelativeTransform(FTransform(Side?FQuat::Identity:Turn(FVector(0,0,1),180.f),At));
 }
 Kickstand->SetRelativeTransform(FTransform(Turn(FVector(0,1,0),StowedDegrees*C[ChStand]),StandPivot));
}

bool UBikeComponent::ClearFor(const FVector& Origin,float Yaw) const
{
 const FQuat R=FRotator(0,Yaw,0).Quaternion();
 FCollisionQueryParams Q(SCENE_QUERY_STAT(BikeClear),false,Rider);
 if(GetWorld()->OverlapBlockingTestByChannel(Origin+R.RotateVector(FVector(5,0,62)),R,ECC_WorldStatic,FCollisionShape::MakeBox(FVector(70,22,48)),Q))return false;
 for(const FVector& Axle:{FrontAxle,RearAxle})
 {
  const FVector P=Origin+R.RotateVector(FVector(Axle.X,0,0));FHitResult H;
  if(!GetWorld()->LineTraceSingleByChannel(H,P+FVector(0,0,50),P-FVector(0,0,40),ECC_Visibility,Q))return false;
 }
 return true;
}

void UBikeComponent::Play(FName Name,FName Then)
{
 Clip=Name;Resume=Then;ClipTime=0.f;AppliedYaw=0.f;++Serial;
 BlendFrom=Displayed;BlendLeft=BlendFrom.Num()==ChannelCount?ClipBlend:0.f;
 // Into the ride loop at the crank's current angle, so the pedals and his legs carry on where they were.
 const FClip* C=Clips.Find(Name);
 if(C&&C->bLoop&&Name==TEXT("BikeRide")&&BlendFrom.Num()==ChannelCount&&C->Frames.Num()>1)
 {
  const float PerSecond=(C->Frames.Last()[ChCrank]-C->Frames[0][ChCrank])/(C->Duration*(C->Frames.Num()-1)/C->Frames.Num());
  if(FMath::Abs(PerSecond)>1.f){const float Phase=(BlendFrom[ChCrank]-C->Frames[0][ChCrank])/(PerSecond*C->Duration);ClipTime=(Phase-FMath::FloorToFloat(Phase))*C->Duration;}
 }
}

bool UBikeComponent::Toggle()
{
 if(!bAssetsReady||!Rider){Hint=TEXT("The bike is not installed");return false;}
 UAnimSequence* Ride=Sequences.FindRef(TEXT("BikeRide"));
 const USkeletalMesh* Body=Rider->GetMesh()->GetSkeletalMeshAsset();
 if(!Ride||!Body||Ride->GetSkeleton()!=Body->GetSkeleton()){Hint=TEXT("Only Cairo rides the bike");return false;}
 if(State==EState::Riding)
 {
  if(Speed>40.f){Hint=TEXT("Slow down to get off");return false;}
  State=EState::Dismounting;Speed=0;Play(TEXT("BikeDismount"),TEXT("BikeKickstand"));Hint=TEXT("Parking");return true;
 }
 if(State!=EState::Off)return false;
 auto* M=Rider->GetCharacterMovement();
 if(!M->IsMovingOnGround()||Rider->bIsCrouched){Hint=TEXT("Stand on level ground to get the bike");return false;}
 const float Half=Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
 const FVector Feet=Rider->GetActorLocation()-FVector(0,0,Half);
 FVector Origin;float Yaw;
 if(bParked&&FVector::Dist2D(BikeRoot->GetComponentLocation(),Feet)<300.f&&FMath::Abs(BikeRoot->GetComponentLocation().Z-Feet.Z)<80.f&&
    FMath::Abs(BikeRoot->GetComponentRotation().Roll)<5.f)
 {Origin=BikeRoot->GetComponentLocation();Yaw=BikeRoot->GetComponentRotation().Yaw;}
 else
 {
  // The bike appears with him at its left side, where BikeMount starts, facing his way (or the nearest clear way).
  bool Found=false;Yaw=Rider->GetActorRotation().Yaw;
  for(float Swing:{0.f,-30.f,30.f,-60.f,60.f,180.f})
  {
   const float A=Rider->GetActorRotation().Yaw+Swing;const FVector O=Feet-FRotator(0,A,0).RotateVector(Beside);
   if(ClearFor(O,A)){Origin=O;Yaw=A;Found=true;break;}
  }
  if(!Found){Hint=TEXT("Find some open ground for the bike");return false;}
 }
 bParked=false;
 BikeRoot->AttachToComponent(Rider->GetMesh(),FAttachmentTransformRules::SnapToTargetNotIncludingScale);
 M->StopMovementImmediately();
 Rider->SetActorLocationAndRotation(Origin+FVector(0,0,Half),FRotator(0,Yaw,0),false,nullptr,ETeleportType::TeleportPhysics);
 SavedFriction=M->GroundFriction;SavedBraking=M->BrakingDecelerationWalking;M->GroundFriction=0.f;M->BrakingDecelerationWalking=0.f;
 State=EState::Mounting;Speed=Steering=Lean=StillTime=0.f;Play(TEXT("BikeMount"),TEXT("BikeRide"));
 BikeRoot->SetVisibility(true,true);Hint=TEXT("Getting on");
 TArray<float> C;if(Channels(C))Pose(C);
 return true;
}

void UBikeComponent::Park()
{
 // He steps off where the clip leaves him, beside the bike; the bike stays standing where it is.
 const FClip* C=Clips.Find(Clip);
 const FTransform Bike=BikeRoot->GetComponentTransform();
 BikeRoot->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);bParked=true;
 auto* M=Rider->GetCharacterMovement();M->GroundFriction=SavedFriction;M->BrakingDecelerationWalking=SavedBraking;M->StopMovementImmediately();
 Rider->GetMesh()->SetRelativeLocationAndRotation(MeshLocation,MeshRotation);
 if(C&&C->bEndOffset)
 {
  const float Half=Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
  const FVector Feet=FVector(Bike.GetLocation().X,Bike.GetLocation().Y,Rider->GetActorLocation().Z-Half)+FRotator(0,Rider->GetActorRotation().Yaw,0).RotateVector(FVector(C->EndOffset,0));
  FCollisionQueryParams Q(SCENE_QUERY_STAT(BikeStepOff),false,Rider);
  const FVector At=Feet+FVector(0,0,Half+2.f);
  if(!GetWorld()->OverlapBlockingTestByChannel(At,FQuat::Identity,ECC_Pawn,Rider->GetCapsuleComponent()->GetCollisionShape(),Q))
   Rider->SetActorLocation(At,false,nullptr,ETeleportType::TeleportPhysics);
 }
 M->bForceNextFloorCheck=true;
 State=EState::Off;Speed=Steering=Lean=BlendLeft=0.f;Clip=NAME_None;Displayed.Reset();++Serial;Hint=TEXT("V bike");
}

void UBikeComponent::StowImmediately()
{
 if(State!=EState::Off)
 {
  auto* M=Rider->GetCharacterMovement();M->GroundFriction=SavedFriction;M->BrakingDecelerationWalking=SavedBraking;M->StopMovementImmediately();
  Rider->GetMesh()->SetRelativeLocationAndRotation(MeshLocation,MeshRotation);
  State=EState::Off;Clip=NAME_None;++Serial;
 }
 if(BikeRoot)
 {
  if(bParked)BikeRoot->AttachToComponent(Rider->GetMesh(),FAttachmentTransformRules::SnapToTargetNotIncludingScale);
  BikeRoot->SetVisibility(false,true);
 }
 bParked=false;Speed=Steering=Lean=BlendLeft=0.f;Displayed.Reset();Hint=TEXT("V bike");
}

void UBikeComponent::SetInput(FVector2D V,bool bSprintHeld,bool Menu){Input=Menu?FVector2D::ZeroVector:V;bSprint=bSprintHeld;bMenu=Menu;}
bool UBikeComponent::Hop(){if(State!=EState::Riding||Clip==TEXT("BikeHop")||Clip==TEXT("BikeSkid"))return false;Play(TEXT("BikeHop"),TEXT("BikeRide"));return true;}
bool UBikeComponent::Skid(){if(State!=EState::Riding||Speed<250.f||Clip==TEXT("BikeSkid"))return false;Play(TEXT("BikeSkid"),TEXT("BikeFootDown"));return true;}
bool UBikeComponent::Bell(){if(State!=EState::Riding||Clip!=TEXT("BikeRide"))return false;Play(TEXT("BikeBell"),TEXT("BikeRide"));return true;}
bool UBikeComponent::Wave(){if(State!=EState::Riding||Clip!=TEXT("BikeRide"))return false;Play(TEXT("BikeWave"),TEXT("BikeRide"));return true;}

void UBikeComponent::EndClip()
{
 switch(State)
 {
 case EState::Mounting: State=EState::Riding;Play(TEXT("BikeRide"));Hint=TEXT("Riding");break;
 case EState::Dismounting: State=EState::Parking;Play(TEXT("BikeKickstand"));break;
 case EState::Parking: case EState::Crashing: Park();break;
 default: Play(Resume.IsNone()?FName(TEXT("BikeRide")):Resume);break;
 }
}

void UBikeComponent::TickComponent(float Dt,ELevelTick Type,FActorComponentTickFunction* Tick)
{
 Super::TickComponent(Dt,Type,Tick);
 if(State==EState::Off||!Rider)return;
 auto* M=Rider->GetCharacterMovement();
 const FClip* C=Clips.Find(Clip);if(!C){StowImmediately();return;}
 // Walls: the movement component slid or stopped him last frame; a hard stop at speed throws him over the bars.
 if(State==EState::Riding)
 {
  const float Moved=FVector::DotProduct(M->Velocity,Rider->GetActorForwardVector());
  FHitResult Hit;FCollisionQueryParams Q(SCENE_QUERY_STAT(BikeAhead),false,Rider);
  const FVector From=Rider->GetActorLocation()-FVector(0,0,Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()-40.f);
  const float Reach=Speed>CrashSpeed?190.f:FrontAxle.X+WheelRadius+Speed*Dt;
  const bool Ahead=GetWorld()->LineTraceSingleByChannel(Hit,From,From+Rider->GetActorForwardVector()*Reach,ECC_Visibility,Q)&&Hit.ImpactNormal.Z<.6f;
  if(Ahead&&Speed>CrashSpeed&&Clip!=TEXT("BikeSkid"))
  {State=EState::Crashing;Play(TEXT("BikeCrash"));Hint=TEXT("Ouch");C=Clips.Find(Clip);Recoil=FMath::Max(0.f,CrashRoom-Hit.Distance);Speed=0.f;}
  else if(Ahead||(M->IsMovingOnGround()&&Speed>60.f&&Moved<Speed*.4f)){Speed=FMath::Min(Speed,FMath::Max(0.f,Moved));}
 }
 // The clock: the ride loop turns at the cadence of the wheels; everything else plays in real time.
 const bool bPedal=Input.Y>.1f&&!bMenu;
 if(State==EState::Riding&&!bMenu)
 {
  const float Top=bSprint?SprintSpeed:TopSpeed;
  // The skid locks the back wheel and stops him inside the clip; a foot down at a roll drags him to a stop.
  if(Clip==TEXT("BikeSkid"))Speed=FMath::FInterpConstantTo(Speed,0.f,Dt,950.f);
  else if(Clip==TEXT("BikeFootDown")&&!bPedal)Speed=FMath::FInterpConstantTo(Speed,0.f,Dt,500.f);
  else if(bPedal)Speed=FMath::FInterpConstantTo(Speed,Top*FMath::Clamp(Input.Y,0.f,1.f),Dt,Speed>Top?220.f:260.f);
  else if(Input.Y<-.1f)Speed=FMath::FInterpConstantTo(Speed,0.f,Dt,700.f*-Input.Y);
  else Speed=FMath::FInterpConstantTo(Speed,0.f,Dt,40.f);
  Steering=FMath::FInterpTo(Steering,Clip==TEXT("BikeSkid")?0.f:Input.X,Dt,5.f);
  // Tighter at a crawl, wider when fast; a stopped rider shuffles round on his planted foot.
  const float TurnRate=Speed<30.f?60.f*Steering:FMath::Clamp(FMath::RadiansToDegrees(Speed/260.f),0.f,110.f)*Steering;
  Rider->AddActorWorldRotation(FRotator(0,TurnRate*Dt,0));
  if(Clip==TEXT("BikeRide")&&Speed<15.f&&!bPedal){StillTime+=Dt;if(StillTime>.25f)Play(TEXT("BikeFootDown"));}
  else StillTime=0.f;
  if(Clip==TEXT("BikeFootDown")&&bPedal)Play(TEXT("BikeRide"));
  Hint=Speed<15.f?TEXT("V get off"):bSprint?TEXT("Pedalling hard"):TEXT("Riding");
 }
 else if(State==EState::Crashing)Speed=ClipTime<CrashRecoil?-Recoil/CrashRecoil:0.f;
 else Speed=0.f;
 // One crank turn carries the mamachari about 2.3 m; freewheeling, the cranks stop.
 const float Cadence=Clip==TEXT("BikeRide")?(bPedal?Speed/230.f:0.f):1.f;
 ClipTime+=Dt*Cadence;
 if(!C->bLoop&&ClipTime>=C->Duration){ClipTime=C->Duration;TArray<float> Last;if(Channels(Last))Pose(Last);EndClip();if(State==EState::Off)return;C=Clips.Find(Clip);}
 TArray<float> Ch;if(!Channels(Ch))return;
 if(BlendLeft>0.f)
 {
  // The rider blends into a new clip over ClipBlend; the bike's channels follow on the same curve (the crank the short way).
  const float A=FMath::SmoothStep(0.f,1.f,1.f-BlendLeft/ClipBlend);
  for(int32 I=0;I<ChannelCount;++I)if(I!=ChYaw)
   Ch[I]=I==ChCrank?Ch[I]-FMath::FindDeltaAngleDegrees(Ch[I],BlendFrom[I])*(1.f-A):FMath::Lerp(BlendFrom[I],Ch[I],A);
  BlendLeft-=Dt;
 }
 // A clip's yaw (the skid's quarter turn) turns him and the bike together; Blender's left turn is Unreal's negative yaw.
 Rider->AddActorWorldRotation(FRotator(0,-(Ch[ChYaw]-AppliedYaw),0));AppliedYaw=Ch[ChYaw];
 if(State==EState::Riding||State==EState::Crashing)
 {
  FVector V=Rider->GetActorForwardVector()*Speed;V.Z=M->Velocity.Z;M->Velocity=V;
 }
 else M->Velocity=FVector(0,0,M->Velocity.Z);
 WheelAngle=FMath::Fmod(WheelAngle+Speed*Dt/WheelRadius,2.f*PI);
 // Into the turn: he and the bike lean together about the ground line under them.
 Lean=FMath::FInterpTo(Lean,State==EState::Riding?-Steering*FMath::Clamp(Speed/TopSpeed,0.f,1.f)*14.f:0.f,Dt,4.f);
 Rider->GetMesh()->SetRelativeLocationAndRotation(MeshLocation,(FQuat(FVector::ForwardVector,FMath::DegreesToRadians(Lean))*MeshRotation.Quaternion()).Rotator());
 Pose(Ch);
}

float UBikeComponent::GetPoseTime() const
{
 const FClip* C=Clips.Find(Clip);const UAnimSequence* S=GetSequence();if(!C||!S)return 0.f;
 const float T=C->bLoop?FMath::Fmod(ClipTime,C->Duration):ClipTime;
 return FMath::Clamp(T,0.f,S->GetPlayLength());
}

FTransform UBikeComponent::GetBikeTransform() const{return BikeRoot?BikeRoot->GetComponentTransform():FTransform::Identity;}

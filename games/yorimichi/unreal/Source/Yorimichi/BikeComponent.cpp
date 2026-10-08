#include "BikeComponent.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PhysicsEngine/SkeletalBodySetup.h"
#include "JapanVehicleTelemetry.h"
#include "JapanVehicleVisuals.h"
#include "JapanBikeGround.h"
#include "JapanNetwork.h"
#include "JapanGameplayCollision.h"
#include "WandererCharacter.h"
#include "ModoriCharacter.h"
#include "AtelierData.h"
#include "Components/StaticMeshComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Animation/AnimSequence.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Engine/OverlapResult.h"
#include "Misc/FileHelper.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Components/AudioComponent.h"
#include "Sound/SoundWave.h"
#include "Sound/SoundAttenuation.h"
#include "Kismet/GameplayStatics.h"
#include "SkateSettings.h"
#include "AtelierFX.h"
#include "MaterialShared.h"
#include "RHIShaderPlatform.h"
#include "Materials/MaterialInterface.h"

namespace
{
 // rider.py and the bike's manifest work in Blender metres (+X forward, +Y left); the mesh frame is Unreal centimetres
 // with +Y right. A rotation keeps its matrix under that mirror once its axis is mirrored and its angle negated.
 FVector FromBlender(const TArray<TSharedPtr<FJsonValue>>& V){return FVector(V[0]->AsNumber()*100.,-V[1]->AsNumber()*100.,V[2]->AsNumber()*100.);}
 FQuat Turn(FVector BlenderAxis,float Degrees){return FQuat(FVector(BlenderAxis.X,-BlenderAxis.Y,BlenderAxis.Z).GetSafeNormal(),-FMath::DegreesToRadians(Degrees));}
 enum{ChCrank,ChStand,ChLift,ChPitch,ChLean,ChYaw,ChSteer,ChannelCount};   // a clip frame's bike channels
 const TCHAR* LimbNames[]={TEXT("hand_L"),TEXT("hand_R"),TEXT("foot_L"),TEXT("foot_R")};
 constexpr float TopSpeed=600.f,SprintSpeed=1200.f,CrashSpeed=450.f,BarDegrees=18.f,ClipBlend=.2f;
 // BikeCrash throws him over the bars: his hands land 1.64 m ahead of where the bike stopped (rider.py). Against a wall the
 // bike and he rebound in the first CrashRecoil seconds to make that room.
 constexpr float CrashRoom=185.f,CrashRecoil=.3f;   // ClipBlend: the anim instance's
 // The one-shots on each clip, at rider.py's key times: the saddle taking his weight, the stand flipping up (stowed at
 // 1.38 s) and down (on the ground at .60 s), the hop's take-off and landing, the bell's two thumb strikes, the crash
 // into the wall and the bike falling on its side (lean_bike 84 at 1.15 s).
 struct FClipSound{const TCHAR* Clip;float Time;const TCHAR* Cue;float Volume;};
 const FClipSound ClipSounds[]={
  {TEXT("BikeMount"),.95f,TEXT("creak"),.6f},{TEXT("BikeMount"),1.38f,TEXT("stand_up"),.8f},{TEXT("BikeDismount"),.48f,TEXT("creak"),.5f},
  {TEXT("BikeKickstand"),.60f,TEXT("stand_down"),.9f},{TEXT("BikeHop"),.42f,TEXT("creak"),.45f},{TEXT("BikeHop"),.74f,TEXT("land"),.9f},
  {TEXT("BikeBell"),.20f,TEXT("bell"),1.f},{TEXT("BikeBell"),.38f,TEXT("bell"),.85f},{TEXT("BikeCrash"),0.f,TEXT("crash"),1.f},
  {TEXT("BikeCrash"),1.15f,TEXT("fall"),.9f}};
 // The loops, in UBikeComponent::Loops order: the tyre on smooth ground (concrete, asphalt, metal), then on wood,
 // stone, dirt (and sand) and grass; the freewheel, chain, wind and the skid on hard and on soft ground.
 const TCHAR* LoopNames[]={TEXT("tyre"),TEXT("tyre_wood"),TEXT("tyre_stone"),TEXT("tyre_dirt"),TEXT("tyre_grass"),TEXT("freewheel"),TEXT("chain"),TEXT("wind"),TEXT("skid"),TEXT("skid_dirt")};
 enum{LoopTyre,LoopFreewheel=5,LoopChain,LoopWind,LoopSkid,LoopSkidDirt,LoopCount};
 int32 TyreLoop(ESkateSurface S)
 {
  switch(S){case ESkateSurface::Wood:return 1;case ESkateSurface::Stone:return 2;case ESkateSurface::Dirt:case ESkateSurface::Sand:return 3;case ESkateSurface::Grass:return 4;default:return 0;}
 }
 constexpr float ChainTurn=.75f,FreewheelTeeth=12.f,FreewheelLoopTicks=30.f;   // assets/audio/bike/make.py
}

// Before physics: the movement component and the mesh wait on it (Initialize), and a later group would carry them, and
// the skate ride and its physical rider after them, past the physics step: every body a frame behind its board.
UBikeComponent::UBikeComponent(){PrimaryComponentTick.bCanEverTick=true;PrimaryComponentTick.TickGroup=TG_PrePhysics;}

bool UBikeComponent::LoadData()
{
 FString Text;TSharedPtr<FJsonObject> Manifest,Export;
 if(!FFileHelper::LoadFileToString(Text,*AtelierDataPath(TEXT("bike/manifest.json")))||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Manifest)||!Manifest)return false;
 // Each playable character has its own clips on its own rig (rider.py --character): Cairo's, or Modori's.
 if(!FFileHelper::LoadFileToString(Text,*AtelierDataPath(RiderRig().ToLower()/TEXT("bike/export.json")))||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Export)||!Export)return false;
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

FString UBikeComponent::RiderRig() const { return Rider&&Rider->IsA<AModoriCharacter>()?TEXT("Modori"):TEXT("Cairo"); }

void UBikeComponent::Initialize(AWandererCharacter* C)
{
 if (Rider) return; // Possession and world readiness may both initialize the same replicated pawn.
 Rider=C;
 // Speed and heading are set here before the movement component moves him, and the parts are posed before the mesh.
 RefreshTickOrder();
 C->GetMesh()->AddTickPrerequisiteComponent(this);
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
 if(!bAssetsReady)UE_LOG(LogTemp,Warning,TEXT("BIKE not installed for %s: parts %d, data %s (rig %s)"),*C->GetName(),bParts?1:0,
     *AtelierDataPath(RiderRig().ToLower()/TEXT("bike/export.json")),*RiderRig());
 if(bAssetsReady)for(const auto& Pair:Clips)
 {
  const FString Name=Pair.Key.ToString();
  if(UAnimSequence* S=LoadObject<UAnimSequence>(nullptr,*FString::Printf(TEXT("/Game/%sBike/A_%s.A_%s"),*RiderRig(),*Name,*Name)))Sequences.Add(Pair.Key,S);
 }
 MeshLocation=C->GetMesh()->GetRelativeLocation();MeshRotation=C->GetMesh()->GetRelativeRotation();
 if(bAssetsReady)LoadSounds();
 // The parts stay hidden until the bike comes out, and the first summon drew a frame or two in the default material
 // while M_Bike's shaders were still being made. Finish them now, while the island loads.
 MaterialsReady(true);
}

bool UBikeComponent::MaterialsReady(bool bFinish) const
{
 bool bReady=true;
#if WITH_EDITOR
 for(const UStaticMeshComponent* P:TArray<UStaticMeshComponent*>{Frame,Steer,WheelFront,WheelRear,Crank,PedalL,PedalR,Kickstand,RackBoard})
  for(int32 I=0;P&&I<P->GetNumMaterials();++I)
   if(UMaterialInterface* Material=P->GetMaterial(I))
    if(FMaterialResource* Resource=Material->GetMaterialResource(GMaxRHIShaderPlatform))
    {
     if(bFinish)Resource->FinishCompilation();
     bReady&=Resource->IsCompilationFinished();
    }
#endif
 return bReady;
}

void UBikeComponent::LoadSounds()
{
 auto Load=[](const FString& Name){return LoadObject<USoundWave>(nullptr,*FString::Printf(TEXT("/Game/Audio/Bike/%s.%s"),*Name,*Name),nullptr,LOAD_NoWarn|LOAD_Quiet);};
 Attenuation=NewObject<USoundAttenuation>(this);
 FSoundAttenuationSettings& A=Attenuation->Attenuation;
 A.bAttenuate=true;A.bSpatialize=true;A.AttenuationShape=EAttenuationShape::Sphere;
 A.AttenuationShapeExtents=FVector(500.f,0.f,0.f);A.FalloffDistance=4000.f;A.DistanceAlgorithm=EAttenuationDistanceModel::NaturalSound;A.dBAttenuationAtMax=-48.f;
 for(const TCHAR* Cue:{TEXT("bell"),TEXT("stand_up"),TEXT("stand_down"),TEXT("creak"),TEXT("land"),TEXT("rattle"),TEXT("crash"),TEXT("fall")})
 {
  const int32 First=Waves.Num();
  for(int32 I=1;I<=8;++I)if(USoundWave* W=Load(FString::Printf(TEXT("%s_%02d"),Cue,I)))Waves.Add(W);
  if(Waves.Num()>First)CueRange.Add(FName(Cue),FIntPoint(First,Waves.Num()-First));
 }
 for(int32 I=0;I<LoopCount;++I)
 {
  auto* L=NewObject<UAudioComponent>(Rider,*FString::Printf(TEXT("BikeLoop%d"),I));
  L->SetupAttachment(BikeRoot);L->bAutoActivate=false;L->bAllowSpatialization=true;
  L->AttenuationSettings=Attenuation;L->SetSound(Load(FString::Printf(TEXT("%s_01"),LoopNames[I])));L->RegisterComponent();
  Loops.Add(L);
 }
 LoopVolume.Init(0.f,Loops.Num());
 UE_LOG(LogTemp,Display,TEXT("BIKE sounds: %d one-shots, %d loops"),Waves.Num(),Loops.FilterByPredicate([](const UAudioComponent* L){return L->Sound!=nullptr;}).Num());
}

void UBikeComponent::PlayCue(FName Cue,float Volume,float Pitch)
{
 const FIntPoint* Range=CueRange.Find(Cue);if(!Range||Range->Y<=0)return;
 int32 Pick=Range->X+FMath::RandHelper(Range->Y);
 if(Range->Y>1&&Pick==LastVariant)Pick=Range->X+(Pick-Range->X+1)%Range->Y;   // no back-to-back repeat
 LastVariant=Pick;
 const FVector At=BikeRoot->GetComponentLocation()+FVector(0,0,50.f);
 UGameplayStatics::PlaySoundAtLocation(this,Waves[Pick],At,FRotator::ZeroRotator,Volume,Pitch,0.f,Attenuation);
 FAtelierAudioLog::Record(Waves[Pick],At,Volume,Pitch,false);
}

void UBikeComponent::ClipCues()
{
 const FClip* C=Clips.Find(Clip);
 if(C&&!C->bLoop)for(const FClipSound& S:ClipSounds)if(Clip==S.Clip&&S.Time>CueClock&&S.Time<=ClipTime)PlayCue(S.Cue,S.Volume,FMath::FRandRange(.96f,1.04f));
 CueClock=ClipTime;
}

void UBikeComponent::UpdateAudio(float Dt,bool bPedal,float Cadence)
{
 if(Loops.Num()!=LoopCount)return;
 auto* M=Rider->GetCharacterMovement();
 // The ground under the wheels, a few times a second (the material needs the complex trace's face).
 if((GroundCheck-=Dt)<=0.f)
 {
  GroundCheck=.1f;
  FCollisionQueryParams Q(SCENE_QUERY_STAT(BikeGround),true,Rider);Q.bReturnFaceIndex=true;
  const FVector From=Rider->GetActorLocation(),To=From-FVector(0,0,Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+40.f);
  FHitResult Hit;
  Ground=uint8(GetWorld()->LineTraceSingleByChannel(Hit,From,To,ECC_Visibility,Q)?USkateSettings::SurfaceAt(Hit):ESkateSurface::None);
 }
 const ESkateSurface S=ESkateSurface(Ground);
 const bool bLifted=Displayed.Num()==ChannelCount&&Displayed[ChLift]>.01f;
 // Off the ground (a drop, not the hop, which the clip sounds): the landing thumps by how fast he came down.
 if(!M->IsMovingOnGround()){Airborne+=Dt;FallSpeed=FMath::Max(FallSpeed,-M->Velocity.Z);}
 else{if(Airborne>.2f&&State==EState::Riding)PlayCue(TEXT("land"),FMath::Clamp(FallSpeed/600.f,.3f,1.f));Airborne=FallSpeed=0.f;}
 const bool bRolling=State==EState::Riding&&M->IsMovingOnGround()&&!bLifted&&Speed>5.f;
 const bool bSkid=State==EState::Riding&&Clip==TEXT("BikeSkid")&&ClipTime>.1f&&Speed>30.f;
 const float Fast=FMath::Clamp(Speed/SprintSpeed,0.f,1.f);
 // A bump now and then on rough ground: the basket and chain case knocking.
 if(bRolling&&(S==ESkateSurface::Stone||S==ESkateSurface::Dirt)&&Speed>300.f&&(RattleWait-=Dt)<=0.f)
 {PlayCue(TEXT("rattle"),.35f+.4f*Fast);RattleWait=FMath::FRandRange(.5f,1.6f)*FMath::Clamp(700.f/Speed,.5f,2.f);}
 float Want[LoopCount]={},Pitch[LoopCount];
 const float WheelTurns=Speed/(2.f*PI*WheelRadius);
 for(int32 I=0;I<LoopCount;++I)Pitch[I]=1.f;
 if(bRolling&&!bSkid){const int32 T=TyreLoop(S);Want[T]=FMath::Clamp(Speed/250.f,0.f,1.f)*(.35f+.45f*Fast);Pitch[T]=.75f+.45f*Fast;}
 if(bRolling&&!bPedal&&!bSkid&&Speed>20.f){Want[LoopFreewheel]=.3f*FMath::Clamp(Speed/200.f,0.f,1.f);Pitch[LoopFreewheel]=FMath::Clamp(WheelTurns*FreewheelTeeth/FreewheelLoopTicks,.3f,2.5f);}
 if(Clip==TEXT("BikeRide")&&bPedal&&Speed>10.f){Want[LoopChain]=(bSprint?.45f:.3f)*FMath::Clamp(Speed/200.f,0.f,1.f);Pitch[LoopChain]=FMath::Clamp(Cadence*ChainTurn,.4f,2.5f);}
 if(State==EState::Riding){Want[LoopWind]=.7f*FMath::Clamp((Speed-350.f)/850.f,0.f,1.f);Pitch[LoopWind]=.8f+.4f*Fast;}
 if(bSkid){const bool bSoft=S==ESkateSurface::Dirt||S==ESkateSurface::Sand||S==ESkateSurface::Grass;const int32 K=bSoft?LoopSkidDirt:LoopSkid;Want[K]=.9f*FMath::Clamp(Speed/600.f,.3f,1.f);Pitch[K]=.9f+.2f*FMath::Clamp(Speed/800.f,0.f,1.f);}
 for(int32 I=0;I<LoopCount;++I)
 {
  UAudioComponent* L=Loops[I];if(!L||!L->Sound)continue;
  // A quick attack (a skid starts at once), a softer release.
  LoopVolume[I]=FMath::FInterpTo(LoopVolume[I],Want[I],Dt,Want[I]>LoopVolume[I]?25.f:8.f);
  if(LoopVolume[I]>.01f){if(!L->IsPlaying())L->Play(FMath::FRand()*1.5f);L->SetVolumeMultiplier(LoopVolume[I]);L->SetPitchMultiplier(Pitch[I]);}
  else if(L->IsPlaying())L->Stop();
 }
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
 if(JapanNetwork::IsOnline(GetWorld()))
 {
  // Fixed-geometry traces intentionally ignore players. Mount admission is a host
  // decision and separately excludes occupied space even though capsules ignore Pawn.
  TArray<FOverlapResult> Occupants;
  FCollisionObjectQueryParams People;People.AddObjectTypesToQuery(ECC_Pawn);
  GetWorld()->OverlapMultiByObjectType(Occupants,Origin+R.RotateVector(FVector(5,0,62)),R,People,
      FCollisionShape::MakeBox(FVector(90,45,62)),Q);
  if(!Occupants.IsEmpty())return false;
 }
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
 const bool Online=JapanNetwork::IsOnline(GetWorld());
 Clip=Name;Resume=Then;ClipTime=0.f;AppliedYaw=0.f;++Serial;
 if(!Online){CueClock=-1.f;BlendFrom=Displayed;BlendLeft=BlendFrom.Num()==ChannelCount?ClipBlend:0.f;}
 // Network simulation has its own phase: a correction must not sample the rendered blend.
 const FClip* C=Clips.Find(Name);
 if(C&&C->bLoop&&Name==TEXT("BikeRide")&&(Online||BlendFrom.Num()==ChannelCount)&&C->Frames.Num()>1)
 {
  const float PerSecond=(C->Frames.Last()[ChCrank]-C->Frames[0][ChCrank])/(C->Duration*(C->Frames.Num()-1)/C->Frames.Num());
  const float CrankPhase=Online?SimCrank:BlendFrom[ChCrank];
  if(FMath::Abs(PerSecond)>1.f){const float Phase=(CrankPhase-C->Frames[0][ChCrank])/(PerSecond*C->Duration);ClipTime=(Phase-FMath::FloorToFloat(Phase))*C->Duration;}
 }
}

bool UBikeComponent::Toggle()
{
 if(JapanNetwork::IsOnline(GetWorld())&&(!Rider||!Rider->HasAuthority()))return false;
 if(!bAssetsReady||!Rider){Hint=TEXT("The bike is not installed");return false;}
 UAnimSequence* Ride=Sequences.FindRef(TEXT("BikeRide"));
 const USkeletalMesh* Body=Rider->GetMesh()->GetSkeletalMeshAsset();
 if(!Ride||!Body||Ride->GetSkeleton()!=Body->GetSkeleton()){Hint=TEXT("Only Cairo and Modori ride the bike");return false;}
 if(State==EState::Riding)
 {
  if(Speed>40.f){Hint=TEXT("Slow down to get off");return false;}
  State=EState::Dismounting;Speed=0;Play(TEXT("BikeDismount"),TEXT("BikeKickstand"));Hint=TEXT("Parking");ClothColliders(false);return true;
 }
 if(State!=EState::Off)return false;
 auto* M=Rider->GetCharacterMovement();
 if(!M->IsMovingOnGround()||Rider->bIsCrouched){Hint=TEXT("Stand on level ground to get the bike");return false;}
 const float Half=Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
 const FVector Feet=Rider->GetActorLocation()-FVector(0,0,Half);
 FVector Origin;float Yaw;
 if(bParked&&FVector::Dist2D(BikeRoot->GetComponentLocation(),Feet)<300.f&&FMath::Abs(BikeRoot->GetComponentLocation().Z-Feet.Z)<80.f&&
    FMath::Abs(BikeRoot->GetComponentRotation().Roll)<5.f)
 {Origin=BikeRoot->GetComponentLocation();Yaw=BikeRoot->GetComponentRotation().Yaw;
  if(JapanNetwork::IsOnline(GetWorld())&&!ClearFor(Origin,Yaw)){Hint=TEXT("The parked bike needs some space");return false;}}
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
 bTerminal=false;SimCrank=Coast=Recoil=0.f;
 State=EState::Mounting;Speed=Steering=Lean=StillTime=0.f;bSnapGround=true;Play(TEXT("BikeMount"),TEXT("BikeRide"));
 BikeRoot->SetVisibility(true,true);Hint=TEXT("Getting on");
 UE_LOG(LogTemp,Display,TEXT("BIKE summon: materials ready=%d"),MaterialsReady(false)?1:0);
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
 JapanVehicleVisuals::SetRiderPose(Rider,MeshLocation,MeshRotation.Quaternion(),false);
 if(C&&C->bEndOffset)
 {
  const float Half=Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
  const FVector Feet=FVector(Bike.GetLocation().X,Bike.GetLocation().Y,Rider->GetActorLocation().Z-Half)+FRotator(0,Rider->GetActorRotation().Yaw,0).RotateVector(FVector(C->EndOffset,0));
  FCollisionQueryParams Q(SCENE_QUERY_STAT(BikeStepOff),false,Rider);
  // A little higher on a slope, where the capsule just above his feet already meets the rising ground; the floor check
  // then sets him down.
  for(const float Lift:{2.f,12.f,25.f})
  {
   const FVector At=Feet+FVector(0,0,Half+Lift);
   FCollisionObjectQueryParams People;People.AddObjectTypesToQuery(ECC_Pawn);
   TArray<FOverlapResult> OtherRiders;
   if(JapanNetwork::IsOnline(GetWorld()))GetWorld()->OverlapMultiByObjectType(OtherRiders,At,FQuat::Identity,People,Rider->GetCapsuleComponent()->GetCollisionShape(),Q);
   if(OtherRiders.IsEmpty()&&!GetWorld()->OverlapBlockingTestByChannel(At,FQuat::Identity,ECC_Pawn,Rider->GetCapsuleComponent()->GetCollisionShape(),Q))
   {Rider->SetActorLocation(At,false,nullptr,ETeleportType::TeleportPhysics);break;}
  }
 }
 M->bForceNextFloorCheck=true;
 State=EState::Off;Speed=Steering=Lean=BlendLeft=GroundPitch=GroundOffset=WheelGround[0]=WheelGround[1]=WheelFall[0]=WheelFall[1]=0.f;Clip=NAME_None;Displayed.Reset();++Serial;Hint=TEXT("V bike");bSprint=false;ClothColliders(false);
 if(JapanNetwork::IsOnline(GetWorld()))JapanBikeGround::SettlePark(Rider);
 for(int32 I=0;I<Loops.Num();++I){if(Loops[I])Loops[I]->Stop();LoopVolume[I]=0.f;}
}

void UBikeComponent::StowImmediately()
{
 if(State!=EState::Off)
 {
  auto* M=Rider->GetCharacterMovement();M->GroundFriction=SavedFriction;M->BrakingDecelerationWalking=SavedBraking;M->StopMovementImmediately();
  JapanVehicleVisuals::SetRiderPose(Rider,MeshLocation,MeshRotation.Quaternion(),false);
  State=EState::Off;Clip=NAME_None;++Serial;ClothColliders(false);
 }
 if(BikeRoot)
 {
  if(bParked)BikeRoot->AttachToComponent(Rider->GetMesh(),FAttachmentTransformRules::SnapToTargetNotIncludingScale);
  BikeRoot->SetVisibility(false,true);
 }
 bParked=false;Speed=Steering=Lean=BlendLeft=GroundPitch=GroundOffset=WheelGround[0]=WheelGround[1]=WheelFall[0]=WheelFall[1]=0.f;Displayed.Reset();Hint=TEXT("V bike");bSprint=false;
 for(int32 I=0;I<Loops.Num();++I){if(Loops[I])Loops[I]->Stop();LoopVolume[I]=0.f;}
}

void UBikeComponent::SetInput(FVector2D V,bool Menu){Input=Menu?FVector2D::ZeroVector:V;bMenu=Menu;}
bool UBikeComponent::ToggleSprint(){bool Accepted=false;if(QueueNetworkAction(TEXT("bike_sprint"),Accepted))return Accepted;if(State!=EState::Riding||bMenu)return false;bSprint=!bSprint;Coast=0.f;return true;}
bool UBikeComponent::Hop(){bool Accepted=false;if(QueueNetworkAction(TEXT("jump"),Accepted))return Accepted;if(State!=EState::Riding||Clip==TEXT("BikeHop")||Clip==TEXT("BikeSkid"))return false;Play(TEXT("BikeHop"),TEXT("BikeRide"));return true;}
bool UBikeComponent::Skid(){bool Accepted=false;if(QueueNetworkAction(TEXT("dodge"),Accepted))return Accepted;if(State!=EState::Riding||Speed<250.f||Clip==TEXT("BikeSkid"))return false;Play(TEXT("BikeSkid"),TEXT("BikeFootDown"));return true;}
bool UBikeComponent::Bell(){bool Accepted=false;if(QueueNetworkAction(TEXT("attack"),Accepted))return Accepted;if(State!=EState::Riding||Clip!=TEXT("BikeRide"))return false;Play(TEXT("BikeBell"),TEXT("BikeRide"));return true;}
bool UBikeComponent::Wave(){bool Accepted=false;if(QueueNetworkAction(TEXT("wave"),Accepted))return Accepted;if(State!=EState::Riding||Clip!=TEXT("BikeRide"))return false;Play(TEXT("BikeWave"),TEXT("BikeRide"));return true;}

void UBikeComponent::EndClip()
{
 switch(State)
 {
 case EState::Mounting: State=EState::Riding;Play(TEXT("BikeRide"));Hint=TEXT("Riding");if(!JapanNetwork::IsOnline(GetWorld()))ClothColliders(true);break;
 case EState::Dismounting: State=EState::Parking;Play(TEXT("BikeKickstand"));break;
 case EState::Parking: case EState::Crashing:
  if(JapanNetwork::IsOnline(GetWorld())){bTerminal=true;Speed=0.f;}else Park();break;
 default: Play(Resume.IsNone()?FName(TEXT("BikeRide")):Resume);break;
 }
}

void UBikeComponent::TickComponent(float Dt,ELevelTick Type,FActorComponentTickFunction* Tick)
{
 Super::TickComponent(Dt,Type,Tick);
 RefreshTickOrder();
 if(State==EState::Off||!Rider)return;
 if(JapanNetwork::IsOnline(GetWorld())){PresentNetwork(Dt);return;}
 bool Pedal=false;float Cadence=0.f;
 if(!AdvanceSimulation(Dt,Pedal,Cadence)){if(State!=EState::Off)StowImmediately();return;}
 TArray<float> Ch;if(Channels(Ch))PresentParts(Dt,Ch,Pedal,Cadence);
}

bool UBikeComponent::AdvanceSimulation(float Dt,bool& bPedal,float& Cadence)
{
 auto* M=Rider->GetCharacterMovement();
 const FClip* C=Clips.Find(Clip);if(!C)return false;
 // Walls: the movement component slid or stopped him last frame; a hard stop at speed throws him over the bars.
 if(State==EState::Riding)
 {
  const float Moved=FVector::DotProduct(M->Velocity,Rider->GetActorForwardVector());
  FHitResult Hit;
  const bool Online=JapanNetwork::IsOnline(GetWorld());
  FCollisionQueryParams Q=Online?JapanGameplayCollision::Query(GetWorld(),SCENE_QUERY_STAT(BikeAhead),false):FCollisionQueryParams(SCENE_QUERY_STAT(BikeAhead),false,Rider);Q.AddIgnoredActor(Rider);
  const FVector From=Rider->GetActorLocation()-FVector(0,0,Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()-40.f);
  const float Reach=Speed>CrashSpeed?190.f:FrontAxle.X+WheelRadius+Speed*Dt;
  const bool Ahead=GetWorld()->LineTraceSingleByChannel(Hit,From,From+Rider->GetActorForwardVector()*Reach,Online?JapanGameplayCollision::Channel:ECC_Visibility,Q)&&Hit.ImpactNormal.Z<.6f;
  if(Ahead&&Speed>CrashSpeed&&Clip!=TEXT("BikeSkid"))
  {JapanVehicleTelemetry::Crash(Rider,Hit,Speed);State=EState::Crashing;Play(TEXT("BikeCrash"));Hint=TEXT("Ouch");C=Clips.Find(Clip);Recoil=FMath::Max(0.f,CrashRoom-Hit.Distance);Speed=0.f;}
  // Slower, he stops as the front wheel meets it (the capsule alone stopped half a bike length on, the wheel and basket
  // through the wall).
  else if(Ahead)Speed=0.f;
  else if(M->IsMovingOnGround()&&Speed>60.f&&Moved<Speed*.4f)Speed=FMath::Min(Speed,FMath::Max(0.f,Moved));
 }
 // The clock: the ride loop turns at the cadence of the wheels; everything else plays in real time.
 bPedal=Input.Y>.1f&&!bMenu;
 if(State==EState::Riding&&!bMenu)
 {
  // The sprint is a toggle: it lasts while he keeps pedalling (a moment's let-go is fine) and ends at a brake or stop.
  Coast=bPedal?0.f:Coast+Dt;
  if(Coast>.6f||Input.Y<-.1f||Clip==TEXT("BikeSkid")||Clip==TEXT("BikeFootDown"))bSprint=false;
  const float Top=bSprint?SprintSpeed:TopSpeed;
  // The skid locks the back wheel and stops him inside the clip; a foot down at a roll drags him to a stop.
  if(Clip==TEXT("BikeSkid"))Speed=FMath::FInterpConstantTo(Speed,0.f,Dt,950.f);
  else if(Clip==TEXT("BikeFootDown")&&!bPedal)Speed=FMath::FInterpConstantTo(Speed,0.f,Dt,500.f);
  else if(bPedal)Speed=FMath::FInterpConstantTo(Speed,Top*FMath::Clamp(Input.Y,0.f,1.f),Dt,Speed>Top?300.f:bSprint?420.f:260.f);
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
 // One crank turn carries the mamachari about 2.3 m up to his cruising speed; faster, he is in the hub's higher gears
 // and his legs spin up more slowly than the wheels. Freewheeling, the cranks stop.
 Cadence=Clip==TEXT("BikeRide")?(bPedal?Speed/(230.f*FMath::Pow(FMath::Max(1.f,Speed/TopSpeed),.8f)):0.f):1.f;
 ClipTime+=Dt*Cadence;
 if(!JapanNetwork::IsOnline(GetWorld()))ClipCues();
 if(!C->bLoop&&ClipTime>=C->Duration){ClipTime=C->Duration;TArray<float> Last;if(Channels(Last)){if(JapanNetwork::IsOnline(GetWorld()))SimCrank=Last[ChCrank];else Pose(Last);}EndClip();if(State==EState::Off)return false;C=Clips.Find(Clip);}
 TArray<float> Ch;if(!Channels(Ch))return false;
 // A clip's yaw (the skid's quarter turn) turns him and the bike together; Blender's left turn is Unreal's negative yaw.
 Rider->AddActorWorldRotation(FRotator(0,-(Ch[ChYaw]-AppliedYaw),0));AppliedYaw=Ch[ChYaw];
 if(State==EState::Riding||State==EState::Crashing)
 {
  FVector V=Rider->GetActorForwardVector()*Speed;V.Z=M->Velocity.Z;M->Velocity=V;
 }
 else M->Velocity=FVector(0,0,M->Velocity.Z);
 if(JapanNetwork::IsOnline(GetWorld()))
 {
  SimCrank=Ch[ChCrank];Coast=FMath::Min(Coast,10.f);StillTime=FMath::Min(StillTime,10.f);
  if(C&&C->bLoop&&C->Duration>0.f)ClipTime=FMath::Fmod(ClipTime,C->Duration);
 }
 return true;
}

void UBikeComponent::PresentParts(float Dt,TArray<float>& Ch,bool bPedal,float Cadence)
{
 if(BlendLeft>0.f)
 {
  // The rider blends into a new clip over ClipBlend; the bike's channels follow on the same curve (the crank the short way).
  const float A=FMath::SmoothStep(0.f,1.f,1.f-BlendLeft/ClipBlend);
  for(int32 I=0;I<ChannelCount;++I)if(I!=ChYaw)
   Ch[I]=I==ChCrank?Ch[I]-FMath::FindDeltaAngleDegrees(Ch[I],BlendFrom[I])*(1.f-A):FMath::Lerp(BlendFrom[I],Ch[I],A);
  BlendLeft-=Dt;
 }
 WheelAngle=FMath::Fmod(WheelAngle+Speed*Dt/WheelRadius,2.f*PI);
 // Into the turn: he and the bike lean together about the ground line under them.
 Lean=FMath::FInterpTo(Lean,State==EState::Riding?-Steering*FMath::Clamp(Speed/TopSpeed,0.f,1.5f)*14.f:0.f,Dt,4.f);
 FollowGround(Dt);
 JapanVehicleVisuals::SetRiderPose(Rider,MeshLocation+FVector(0,0,GroundOffset),
  (FQuat(FVector::ForwardVector,FMath::DegreesToRadians(Lean))*MeshRotation.Quaternion()*FRotator(GroundPitch,0,0).Quaternion()).GetNormalized());   // pitch in the bike's frame
 Pose(Ch);
 UpdateAudio(Dt,bPedal,Cadence);
}

void UBikeComponent::PresentNetwork(float Dt)
{
 SampleNetworkPresentation();
 // Both prediction and proxy snapshots reach this once after movement replay.
 // A late join can start already Riding, without ever running EndClip(Mounting).
 ClothColliders(State==EState::Riding);
 const uint32 Epoch=Rider->GetActivityEpoch();
 if(PresentedEpoch!=Epoch)
 {PresentedEpoch=Epoch;PresentedSerial=0;PlayedNetworkCues.Reset();NetworkCueOrder.Reset();}
 if(PresentedSerial!=Serial)
 {
  PresentedSerial=Serial;CueClock=-1.f;
  BlendFrom=Displayed;BlendLeft=BlendFrom.Num()==ChannelCount?ClipBlend:0.f;
 }
 // Presentation runs once after CMC has finished any correction replay. A replay
 // can cross the same sound marker again; epoch/clip-serial/marker emits it once.
 const FClip* C=Clips.Find(Clip);
 if(C&&!C->bLoop)for(int32 I=0;I<UE_ARRAY_COUNT(ClipSounds);++I)
 {
  const FClipSound& S=ClipSounds[I];
  const uint64 Key=(uint64(Serial)<<8)|uint64(I);
  if(Clip==S.Clip&&S.Time>CueClock&&S.Time<=ClipTime&&!PlayedNetworkCues.Contains(Key))
  {
   PlayedNetworkCues.Add(Key);NetworkCueOrder.Add(Key);
   if(NetworkCueOrder.Num()>256){PlayedNetworkCues.Remove(NetworkCueOrder[0]);NetworkCueOrder.RemoveAt(0);}
   PlayCue(S.Cue,S.Volume);
  }
 }
 CueClock=ClipTime;
 TArray<float> Ch;if(!Channels(Ch))return;
 const bool Pedal=bNetworkPedalling;
 const float Cadence=Clip==TEXT("BikeRide")?(Pedal?Speed/(230.f*FMath::Pow(FMath::Max(1.f,Speed/TopSpeed),.8f)):0.f):1.f;
 PresentParts(Dt,Ch,Pedal,Cadence);
}

float UBikeComponent::GetPoseTime() const
{
 const FClip* C=Clips.Find(Clip);const UAnimSequence* S=GetSequence();if(!C||!S)return 0.f;
 const float T=C->bLoop?FMath::Fmod(ClipTime,C->Duration):ClipTime;
 return FMath::Clamp(T,0.f,S->GetPlayLength());
}

void UBikeComponent::FollowGround(float Dt)
{
 // The walking capsule stands level on one point under him, so on a rise the front wheel sank into the ground (and on
 // a dip it hung in the air). Find the ground under each wheel: each wheel rises with it at once (so it never trails
 // into a rise) and, when it drops away, falls no faster than gravity (off a ramp's top at speed he carries on nearly
 // straight rather than diving).
 float Want[2]={0.f,0.f};
 if(Rider->GetCharacterMovement()->IsMovingOnGround()&&State!=EState::Crashing)
 {
  const FTransform Base=FTransform(MeshRotation,MeshLocation)*Rider->GetActorTransform();
  const bool Online=JapanNetwork::IsOnline(GetWorld());
  FCollisionQueryParams Q=Online?JapanGameplayCollision::Query(GetWorld(),SCENE_QUERY_STAT(BikeWheels),false):FCollisionQueryParams(SCENE_QUERY_STAT(BikeWheels),false,Rider);Q.AddIgnoredActor(Rider);
  // Under each wheel: the ground, or (nothing within reach) a drop it eases down over, or (higher than a curb, or a
  // wall's face) the top of something the wheel has met, which leaves that wheel where it was.
  for(int32 I=0;I<2;++I)
  {
   const FVector P=Base.TransformPosition(FVector(I?RearAxle.X:FrontAxle.X,0,0));FHitResult H;
   if(!GetWorld()->LineTraceSingleByChannel(H,P+FVector(0,0,60),P-FVector(0,0,90),Online?JapanGameplayCollision::Channel:ECC_Visibility,Q))Want[I]=-40.f;
   else if(H.ImpactNormal.Z<.6f||H.ImpactPoint.Z-Base.GetLocation().Z>25.f)Want[I]=WheelGround[I];
   else Want[I]=FMath::Max(H.ImpactPoint.Z-Base.GetLocation().Z,-40.f);
  }
 }
 for(int32 I=0;I<2;++I)
 {
  if(bSnapGround||Want[I]>=WheelGround[I]){WheelGround[I]=Want[I];WheelFall[I]=0.f;}
  else{WheelFall[I]+=980.f*Dt;WheelGround[I]=FMath::Max(Want[I],WheelGround[I]-WheelFall[I]*Dt);}
 }
 bSnapGround=false;
 // He and the bike pitch about the ground line under him to the slope between the wheels and sit on it there.
 const float Wheelbase=FrontAxle.X-RearAxle.X;
 GroundPitch=FMath::Clamp(FMath::RadiansToDegrees(FMath::Atan2(WheelGround[0]-WheelGround[1],Wheelbase)),-25.f,25.f);
 GroundOffset=FMath::Clamp(WheelGround[1]-(WheelGround[0]-WheelGround[1])*RearAxle.X/Wheelbase,-25.f,25.f);
}

FVector2D UBikeComponent::GetWheelGaps() const
{
 FVector2D Gaps(0,0);if(!BikeRoot)return Gaps;
 FCollisionQueryParams Q(SCENE_QUERY_STAT(BikeGaps),false,Rider);
 for(int32 I=0;I<2;++I)
 {
  const FVector Axle=BikeRoot->GetComponentTransform().TransformPosition(I?RearAxle:FrontAxle);FHitResult H;
  if(GetWorld()->LineTraceSingleByChannel(H,Axle+FVector(0,0,60),Axle-FVector(0,0,150),ECC_Visibility,Q))Gaps[I]=Axle.Z-WheelRadius-H.ImpactPoint.Z;
 }
 return Gaps;
}

FString UBikeComponent::GetLoopState() const
{
 FString Out;
 for(int32 I=0;I<Loops.Num();++I)Out+=FString::Printf(TEXT("%.3f %.3f "),Loops[I]&&Loops[I]->IsPlaying()?LoopVolume[I]:0.f,Loops[I]?Loops[I]->PitchMultiplier:1.f);
 return Out;
}

FTransform UBikeComponent::GetBikeTransform() const{return BikeRoot?BikeRoot->GetComponentTransform():FTransform::Identity;}

void UBikeComponent::ClothColliders(bool bOn)
{
 if(bOn==bClothCollidersOn)return;
 USkeletalMeshComponent* Mesh=Rider?Rider->GetMesh():nullptr;
 if(!Mesh||!Mesh->GetSkeletalMeshAsset()||!Mesh->GetSkeletalMeshAsset()->GetMeshClothingAssets().Num())return;
 if(bOn&&!ClothBodies&&BikeRoot)
 {
  // Capsules on the root bone where the rack, its board and the rear wheel sit while he rides (the bike stands still
  // relative to him but for its lean), in the bone's own units: its x100 import scale divides them (Chaos scales back).
  const FTransform Root=Mesh->GetBoneTransform(0,FTransform::Identity);
  const float Unit=FMath::Max(Root.GetScale3D().GetAbsMax(),KINDA_SMALL_NUMBER);
  ClothBodies=NewObject<UPhysicsAsset>(this,TEXT("BikeCloth"));
  USkeletalBodySetup* Setup=NewObject<USkeletalBodySetup>(ClothBodies);
  Setup->BoneName=Mesh->GetBoneName(0);Setup->PhysicsType=PhysType_Kinematic;
  for(const UStaticMeshComponent* Part:{RackBoard.Get(),WheelRear.Get()})
  {
   if(!Part||!Part->GetStaticMesh())continue;
   const FBox Box=Part->GetStaticMesh()->GetBoundingBox();const FVector E=Box.GetExtent();
   const FTransform ToComponent=Part->GetComponentTransform().GetRelativeTransform(Mesh->GetComponentTransform());
   // The board: a capsule along its length, its width across. The wheel: along its axle, its rim round.
   const int32 Long=Part==RackBoard?(E.X>=E.Y&&E.X>=E.Z?0:E.Y>=E.Z?1:2):(E.X<=E.Y&&E.X<=E.Z?0:E.Y<=E.Z?1:2);
   FVector Half=FVector::ZeroVector;Half[Long]=E[Long];
   float Radius=0.f;for(int32 K=0;K<3;++K)if(K!=Long)Radius=FMath::Max(Radius,E[K]);
   if(Part==RackBoard)Radius=FMath::Min(Radius,12.f);
   const FVector A=Root.InverseTransformPosition(ToComponent.TransformPosition(Box.GetCenter()-Half));
   const FVector B=Root.InverseTransformPosition(ToComponent.TransformPosition(Box.GetCenter()+Half));
   FKSphylElem Capsule;Capsule.Radius=Radius*ToComponent.GetScale3D().GetAbsMax()/Unit;Capsule.Center=(A+B)*.5f;
   Capsule.Rotation=FRotationMatrix::MakeFromZ((B-A).GetSafeNormal()).Rotator();Capsule.Length=FMath::Max((B-A).Size()-2.f*Capsule.Radius,0.f);
   Setup->AggGeom.SphylElems.Add(Capsule);
  }
  ClothBodies->SkeletalBodySetups.Add(Setup);ClothBodies->UpdateBodySetupIndexMap();
 }
 if(!ClothBodies)return;
 Mesh->RemoveClothCollisionSource(Mesh,ClothBodies);
 if(bOn)Mesh->AddClothCollisionSource(Mesh,ClothBodies);
 bClothCollidersOn=bOn;
}

float UBikeComponent::GetAuthoredLift() const
{
 TArray<float> Sample;const auto* Value=Channels(Sample);
 return Value&&Value->IsValidIndex(ChLift)?(*Value)[ChLift]*100.f:0.f;
}

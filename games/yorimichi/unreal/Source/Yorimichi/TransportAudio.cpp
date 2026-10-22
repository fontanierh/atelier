#include "TransportAudio.h"
#include "Components/AudioComponent.h"
#include "Sound/SoundWave.h"
#include "Sound/SoundAttenuation.h"
#include "Engine/World.h"

namespace
{
USoundWave* LoadTransportWave(const FString& Name)
{
 return LoadObject<USoundWave>(nullptr,*FString::Printf(TEXT("/Game/Audio/Transport/%s.%s"),*Name,*Name),nullptr,LOAD_NoWarn|LOAD_Quiet);
}
USoundAttenuation* MakeAttenuation(UObject* Outer,float Inner,float Falloff)
{
 auto* Out=NewObject<USoundAttenuation>(Outer);
 FSoundAttenuationSettings& A=Out->Attenuation;
 A.bAttenuate=true;A.bSpatialize=true;A.AttenuationShape=EAttenuationShape::Sphere;
 A.AttenuationShapeExtents=FVector(Inner,0.f,0.f);A.FalloffDistance=Falloff;
 A.DistanceAlgorithm=EAttenuationDistanceModel::NaturalSound;A.dBAttenuationAtMax=-48.f;
 // Air takes the highs off with distance: a far engine is a low drone, a near one has its clatter.
 A.bAttenuateWithLPF=true;A.LPFRadiusMin=Inner;A.LPFRadiusMax=Inner+Falloff;A.LPFFrequencyAtMin=20000.f;A.LPFFrequencyAtMax=2500.f;
 return Out;
}
}

UTransportAudioComponent::UTransportAudioComponent()
{
 PrimaryComponentTick.bCanEverTick=true;PrimaryComponentTick.bStartWithTickEnabled=true;
 // After the vehicle has moved and reported its state this frame.
 PrimaryComponentTick.TickGroup=TG_PostPhysics;
 SetIsReplicatedByDefault(false);
}

bool UTransportAudioComponent::EnsureLoaded()
{
 if(bTried)return bLoaded;
 bTried=true;
 if(GetNetMode()==NM_DedicatedServer||!GetOwner())return false;
 const FBankSpec Spec=Bank();
 Near=MakeAttenuation(this,Spec.InnerRadius,Spec.Falloff);
 Far=MakeAttenuation(this,Spec.InnerRadius*Spec.Far,Spec.Falloff*Spec.Far);
 for(const TCHAR* Cue:Spec.Cues)
 {
  const int32 First=Waves.Num();
  for(int32 I=1;I<=8;++I)
  {
   USoundWave* W=LoadTransportWave(FString::Printf(TEXT("%s_%02d"),Cue,I));
   if(!W)break;
   Waves.Add(W);
  }
  if(Waves.Num()>First)CueRange.Add(FName(Cue),FIntPoint(First,Waves.Num()-First));
 }
 int32 Found=0;
 for(const FLoopSpec& S:Spec.Loops)
 {
  auto* L=NewObject<UAudioComponent>(GetOwner(),*FString::Printf(TEXT("%s_%s"),*GetName(),S.Cue));
  L->SetupAttachment(this);L->bAutoActivate=false;L->bAllowSpatialization=true;L->AttenuationSettings=Near;
  L->SetSound(LoadTransportWave(FString::Printf(TEXT("%s_01"),S.Cue)));L->RegisterComponent();
  Found+=L->Sound!=nullptr;
  FLoopState State;State.FadeIn=S.FadeIn;State.FadeOut=S.FadeOut;
  Loops.Add(L);LoopStates.Add(State);LoopNames.Add(FName(S.Cue));
 }
 bLoaded=Found>0||CueRange.Num()>0;
 UE_LOG(LogTemp,Display,TEXT("TRANSPORT AUDIO %s: %d of %d cues, %d of %d loops"),*GetClass()->GetName(),CueRange.Num(),Spec.Cues.Num(),Found,Spec.Loops.Num());
 return bLoaded;
}

void UTransportAudioComponent::SetLoop(int32 Index,float Volume,float Pitch)
{
 if(!LoopStates.IsValidIndex(Index))return;
 LoopStates[Index].Target=FMath::Clamp(Volume,0.f,1.f);LoopStates[Index].TargetPitch=FMath::Clamp(Pitch,.25f,3.f);
}

void UTransportAudioComponent::PlayCue(FName Cue,float Volume,bool bFar,float Delay,FVector Offset)
{
 if(!EnsureLoaded())return;
 FPending P;P.Cue=Cue;P.Volume=Volume;P.Wait=Delay;P.bFar=bFar;P.Offset=Offset;
 if(Delay>0.f)Pending.Add(P);else Fire(P);
}

void UTransportAudioComponent::Fire(const FPending& P)
{
 const FIntPoint* Range=CueRange.Find(P.Cue);if(!Range||Range->Y<=0)return;
 const int32 Pick=Bags.FindOrAdd(P.Cue).Draw(Range->Y);   // the bag never repeats a variant back to back
 AtelierPlaySound(this,Waves[Range->X+Pick],GetComponentTransform().TransformPosition(P.Offset),P.Volume,FMath::FRandRange(.97f,1.03f),P.bFar?Far:Near);
}

void UTransportAudioComponent::TickComponent(float Dt,ELevelTick TickType,FActorComponentTickFunction* ThisTickFunction)
{
 Super::TickComponent(Dt,TickType,ThisTickFunction);
 if(!EnsureLoaded()){SetComponentTickEnabled(false);return;}   // no bank here, or a dedicated server: stay silent
 if(Dt<=0.f)return;
 const FVector Here=GetComponentLocation();
 if(bHasLocation)
 {
  // A docking snap or a skipped ride moves the vehicle in one frame: that is not speed.
  const float Step=float(FVector::Dist(Here,LastLocation));
  if(Step<2000.f)Speed=FMath::FInterpTo(Speed,FMath::Min(Step/Dt,20000.f),Dt,3.f);
 }
 LastLocation=Here;bHasLocation=true;
 Evaluate(Dt);
 for(int32 I=Pending.Num()-1;I>=0;--I)
  if((Pending[I].Wait-=Dt)<=0.f){const FPending P=Pending[I];Pending.RemoveAt(I);Fire(P);}
 for(int32 I=0;I<Loops.Num();++I)
 {
  UAudioComponent* L=Loops[I];FLoopState& S=LoopStates[I];
  if(!L||!L->Sound)continue;
  // Fade towards the state's target (a quick attack where the loop says so, a slower release) and stop only once
  // the voice is inaudible, so a state change never cuts a loop off.
  S.Volume=FMath::FInterpTo(S.Volume,S.Target,Dt,S.Target>S.Volume?S.FadeIn:S.FadeOut);
  if(S.Target>0.f||S.Volume>.002f)
  {
   if(!L->IsPlaying())
   {
    S.Pitch=S.TargetPitch;L->SetVolumeMultiplier(FMath::Max(S.Volume,.001f));L->SetPitchMultiplier(S.Pitch);
    L->Play(FMath::FRand()*.9f*L->Sound->GetDuration());
   }
   S.Pitch=FMath::FInterpTo(S.Pitch,S.TargetPitch,Dt,2.f);
   L->SetVolumeMultiplier(FMath::Max(S.Volume,.001f));L->SetPitchMultiplier(S.Pitch);
  }
  else if(L->IsPlaying()){S.Volume=0.f;L->Stop();}
 }
}

void UTransportAudioComponent::OnComponentDestroyed(bool bDestroyingHierarchy)
{
 for(UAudioComponent* L:Loops)if(IsValid(L)){L->Stop();if(!bDestroyingHierarchy)L->DestroyComponent();}
 Loops.Reset();LoopStates.Reset();Pending.Reset();
 Super::OnComponentDestroyed(bDestroyingHierarchy);
}

FString UTransportAudioComponent::GetLoopState() const
{
 FString Out;
 for(int32 I=0;I<LoopNames.Num()&&I<LoopStates.Num();++I)
  Out+=FString::Printf(TEXT("%s%s %.3f %.3f"),Out.IsEmpty()?TEXT(""):TEXT(", "),*LoopNames[I].ToString(),LoopStates[I].Volume,LoopStates[I].Pitch);
 return Out;
}

// --------------------------------------------------------------------------------------------- zeppelin
namespace { enum { ZeppelinIdle, ZeppelinCruise, ZeppelinEnvelope }; }

UTransportAudioComponent::FBankSpec UZeppelinAudioComponent::Bank() const
{
 FBankSpec S;
 S.Loops={{TEXT("zeppelin_engine_idle"),1.2f,.8f},{TEXT("zeppelin_engine"),1.2f,.8f},{TEXT("zeppelin_envelope"),.8f,.6f}};
 S.Cues={TEXT("zeppelin_gate_open"),TEXT("zeppelin_gate_close"),TEXT("zeppelin_moor"),TEXT("zeppelin_bell")};
 // In flight the passenger's camera pulls back 42-70 m: the motors stay full there, and carry across the station.
 S.InnerRadius=3000.f;S.Falloff=22000.f;S.Far=2.f;
 return S;
}

void UZeppelinAudioComponent::SetState(int32 NewPhase,float NewRPM,float GateOpen,bool bNowLanded)
{
 RPM=NewRPM;
 if(!bPrimed){bPrimed=true;Phase=NewPhase;Gate=GateOpen;bLanded=bNowLanded;bGateHeardOpen=GateOpen>.5f;return;}
 if(NewPhase!=Phase)
 {
  if(NewPhase==3)PlayCue(TEXT("zeppelin_bell"),1.f,true);                                        // casting off
  else if(Phase==1&&NewPhase==0){PlayCue(TEXT("zeppelin_moor"));PlayCue(TEXT("zeppelin_bell"),.8f,true,.6f);}  // the called ship is down
  Phase=NewPhase;
 }
 if(bNowLanded&&!bLanded){PlayCue(TEXT("zeppelin_moor"));PlayCue(TEXT("zeppelin_bell"),.8f,true,.6f);}   // down at the destination
 bLanded=bNowLanded;
 if(!bGateHeardOpen&&GateOpen>.05f&&GateOpen>Gate){PlayCue(TEXT("zeppelin_gate_open"),.9f,false,0.f,GateOffset);bGateHeardOpen=true;}
 else if(bGateHeardOpen&&GateOpen<.95f&&GateOpen<Gate){PlayCue(TEXT("zeppelin_gate_close"),.9f,false,0.f,GateOffset);bGateHeardOpen=false;}
 Gate=GateOpen;
}

void UZeppelinAudioComponent::Evaluate(float Dt)
{
 if(!bPrimed)return;
 // An equal-power crossfade from the idle tick-over to the cruise drone as the propellers spool up; each loop is
 // pitched by the RPM over the RPM it was made at (make.py ZEPPELIN_IDLE_RPM 90, ZEPPELIN_CRUISE_RPM 480).
 const float Spool=FMath::SmoothStep(110.f,330.f,RPM);
 const float Level=Phase==0?.35f:.75f;   // moored, the propellers tick over: heard on the platform, not across town
 SetLoop(ZeppelinIdle,Level*FMath::Cos(Spool*HALF_PI),FMath::Clamp(RPM/90.f,.55f,1.6f));
 SetLoop(ZeppelinCruise,.85f*FMath::Sin(Spool*HALF_PI),FMath::Clamp(RPM/480.f,.55f,1.8f));
 const bool bAirborne=Phase==1||(Phase>=3&&Phase<=5&&!bLanded);
 const float Wind=FMath::Clamp(GetMeasuredSpeed()/4000.f,0.f,1.f);
 SetLoop(ZeppelinEnvelope,bAirborne?.2f+.6f*Wind:0.f,.9f+.25f*Wind);
}

// --------------------------------------------------------------------------------------------- ferry
namespace { enum { FerryEngineIdle, FerryEngine, FerryThruster, FerryWash, FerryMoorings }; }

UTransportAudioComponent::FBankSpec UFerryAudioComponent::Bank() const
{
 FBankSpec S;
 S.Loops={{TEXT("ferry_engine_idle"),.8f,.5f},{TEXT("ferry_engine"),.8f,.5f},{TEXT("ferry_thruster"),2.f,1.f},{TEXT("ferry_wash"),1.f,.7f},{TEXT("ferry_moorings"),.5f,.6f}};
 S.Cues={TEXT("ferry_horn_depart"),TEXT("ferry_horn_arrive"),TEXT("ferry_brow_open"),TEXT("ferry_brow_close"),TEXT("ferry_fender")};
 // A ship some 60 m long: full volume along her side, and the horn carries across the harbour.
 S.InnerRadius=2500.f;S.Falloff=18000.f;S.Far=3.f;
 return S;
}

void UFerryAudioComponent::SetPhase(EFerryAudioPhase NewPhase)
{
 if(!bPrimed){bPrimed=true;Phase=NewPhase;return;}
 if(NewPhase==Phase)return;
 if(Phase==EFerryAudioPhase::Berthed&&NewPhase==EFerryAudioPhase::Departing)PlayCue(TEXT("ferry_horn_depart"),1.f,true);
 else if(NewPhase==EFerryAudioPhase::Approach)PlayCue(TEXT("ferry_horn_arrive"),1.f,true);
 else if(NewPhase==EFerryAudioPhase::Berthed)PlayCue(TEXT("ferry_fender"));
 Phase=NewPhase;
}

void UFerryAudioComponent::OnBoardingOpen() { PlayCue(TEXT("ferry_brow_open")); }
void UFerryAudioComponent::OnBoardingClose() { PlayCue(TEXT("ferry_brow_close")); }

void UFerryAudioComponent::Evaluate(float Dt)
{
 if(!bPrimed)return;
 const bool bBerthed=Phase==EFerryAudioPhase::Berthed;
 // Equal-power crossfade from the slow 6-cylinder idle chug to the loaded cruise diesel as throttle rises.
 const float Spool=FMath::SmoothStep(0.08f,0.65f,Throttle01);
 const float IdleGain=bBerthed?.26f:.65f*FMath::Cos(Spool*HALF_PI);
 const float CruiseGain=bBerthed?0.f:(.35f+.55f*Throttle01)*FMath::Sin(Spool*HALF_PI);
 SetLoop(FerryEngineIdle,IdleGain,bBerthed?.96f:.98f+.14f*Throttle01);
 SetLoop(FerryEngine,CruiseGain,.88f+.20f*FMath::Pow(Throttle01,.8f));
 SetLoop(FerryThruster,.8f*Thruster,.85f+.3f*Thruster);
 const float Wash=FMath::Clamp((WaterSpeed>=0.f?WaterSpeed:GetMeasuredSpeed())/1200.f,0.f,1.f);
 SetLoop(FerryWash,.85f*Wash,.8f+.3f*Wash);
 SetLoop(FerryMoorings,bBerthed?.6f:0.f);
}

// --------------------------------------------------------------------------------------------- gondola
UTransportAudioComponent::FBankSpec UGondolaAudioComponent::Bank() const
{
 FBankSpec S;
 S.Loops={{TEXT("gondola_cabin"),1.5f,1.5f}};
 S.Cues={TEXT("gondola_sheave"),TEXT("gondola_grip_attach"),TEXT("gondola_grip_release"),TEXT("gondola_door_open"),TEXT("gondola_door_close"),TEXT("gondola_chime")};
 // A small cabin: loud only to its riders and the station platform; many share a line.
 S.InnerRadius=800.f;S.Falloff=6000.f;S.Far=2.f;
 return S;
}

void UGondolaAudioComponent::Evaluate(float Dt)
{
 const float Run=FMath::Clamp(LineSpeed/600.f,0.f,1.2f);
 SetLoop(0,.75f*FMath::Min(Run,1.f),.85f+.25f*Run);
}

void UGondolaAudioComponent::OnTowerPass(float Strength) { PlayCue(TEXT("gondola_sheave"),FMath::Clamp(.4f+.6f*Strength,.2f,1.f)); }
void UGondolaAudioComponent::OnGripAttach() { PlayCue(TEXT("gondola_grip_attach")); }
void UGondolaAudioComponent::OnGripRelease() { PlayCue(TEXT("gondola_grip_release")); }
void UGondolaAudioComponent::OnDoorOpen() { PlayCue(TEXT("gondola_chime"),.7f);PlayCue(TEXT("gondola_door_open"),1.f,false,.15f); }
void UGondolaAudioComponent::OnDoorClose() { PlayCue(TEXT("gondola_chime"),.7f);PlayCue(TEXT("gondola_door_close"),1.f,false,.9f); }

UTransportAudioComponent::FBankSpec UGondolaStationAudioComponent::Bank() const
{
 FBankSpec S;
 S.Loops={{TEXT("gondola_station"),.6f,.4f}};
 S.InnerRadius=1500.f;S.Falloff=8000.f;S.Far=1.f;
 return S;
}

void UGondolaStationAudioComponent::Evaluate(float Dt)
{
 SetLoop(0,Running>.01f?.35f+.5f*FMath::Min(Running,1.f):0.f,.7f+.3f*Running);
}

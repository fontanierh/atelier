#pragma once
#include "CoreMinimal.h"
#include "Components/SceneComponent.h"
#include "AtelierFX.h"
#include "TransportAudio.generated.h"
class UAudioComponent; class USoundWave; class USoundAttenuation;

/** The sounds of a passenger vehicle: the ferry, a gondola cabin or station, the zeppelin (/Game/Audio/Transport, built
 *  by assets/audio/transport/make.py; the calls each vehicle makes are in that folder's README). Presentation only:
 *  every machine drives it from the vehicle's replicated or deterministic state, so clients hear what the host hears
 *  and nothing here replicates or feeds back into the simulation. Loops fade towards the targets the state sets and
 *  stop only once silent; one-shots mark state changes. Attach it where the sound comes from. Without the imported
 *  bank (or on a dedicated server) it stays silent. */
UCLASS(Abstract)
class YORIMICHI_API UTransportAudioComponent : public USceneComponent
{
 GENERATED_BODY()
public:
 UTransportAudioComponent();
 virtual void TickComponent(float Dt,ELevelTick TickType,FActorComponentTickFunction* ThisTickFunction) override;
 virtual void OnComponentDestroyed(bool bDestroyingHierarchy) override;
 bool IsLoaded() const { return bLoaded; }
 /** Each loop's "name volume pitch", for tests and filmed takes. */
 FString GetLoopState() const;
protected:
 struct FLoopSpec { const TCHAR* Cue; float FadeIn; float FadeOut; };
 struct FBankSpec
 {
  TArray<FLoopSpec> Loops;
  TArray<const TCHAR*> Cues;
  /** Full volume within InnerRadius (cm), then a natural falloff over Falloff cm. Signals (horns, bells) carry Far x further. */
  float InnerRadius = 1000.f, Falloff = 8000.f, Far = 3.f;
 };
 virtual FBankSpec Bank() const PURE_VIRTUAL(UTransportAudioComponent::Bank, return {};);
 /** Sets each loop's target from the vehicle's state; runs every tick before the fades. */
 virtual void Evaluate(float Dt) {}
 /** The loop's target volume and pitch; the voice fades and glides towards them. */
 void SetLoop(int32 Index,float Volume,float Pitch=1.f);
 /** One variant of the cue, at this component (or Offset from it, in its frame), never the one just played. */
 void PlayCue(FName Cue,float Volume=1.f,bool bFar=false,float Delay=0.f,FVector Offset=FVector::ZeroVector);
 /** How fast this component is moving (cm/s), smoothed; teleports are ignored. */
 float GetMeasuredSpeed() const { return Speed; }
 bool EnsureLoaded();
private:
 struct FLoopState { float Volume=0.f,Target=0.f,Pitch=1.f,TargetPitch=1.f,FadeIn=1.f,FadeOut=1.f; };
 struct FPending { FName Cue; float Volume=1.f,Wait=0.f; bool bFar=false; FVector Offset=FVector::ZeroVector; };
 UPROPERTY() TArray<TObjectPtr<UAudioComponent>> Loops;
 UPROPERTY() TArray<TObjectPtr<USoundWave>> Waves;
 UPROPERTY() TObjectPtr<USoundAttenuation> Near;
 UPROPERTY() TObjectPtr<USoundAttenuation> Far;
 TMap<FName,FIntPoint> CueRange;
 TMap<FName,FAtelierShuffleBag> Bags;
 TArray<FLoopState> LoopStates;
 TArray<FName> LoopNames;
 TArray<FPending> Pending;
 FVector LastLocation=FVector::ZeroVector;
 float Speed=0.f;
 bool bLoaded=false,bTried=false,bHasLocation=false;
 void Fire(const FPending& P);
};

/** The zeppelin (AZeppelinService). The service reports its state every tick on host and clients alike, from the
 *  replicated FZeppelinNetworkState or the offline ride: the engines follow the propellers' RPM (55 moored, 480
 *  cruising, 90 landing), the envelope's wind follows the ship's speed in the air, and phase, landing and gate changes
 *  ring the bell, thump the mooring and swing the gate. */
UCLASS()
class YORIMICHI_API UZeppelinAudioComponent : public UTransportAudioComponent
{
 GENERATED_BODY()
public:
 /** Phase: 0 docked, 1 arriving, 2 boarding, 3 climb, 4 cruise, 5 landing, 6 disembarking. GateOpen 0-1. Landed: the
  *  ship is down at the end of phase 5. The first call only records the state, so a late joiner hears no stale cue. */
 void SetState(int32 NewPhase,float NewRPM,float GateOpen,bool bNowLanded);
 /** Where the deck gate is, in this component's frame: its latch and swing sound there. */
 void SetGateOffset(const FVector& Offset) { GateOffset=Offset; }
protected:
 virtual FBankSpec Bank() const override;
 virtual void Evaluate(float Dt) override;
private:
 int32 Phase=0; float RPM=55.f,Gate=0.f; bool bLanded=false,bPrimed=false,bGateHeardOpen=false;
 FVector GateOffset=FVector::ZeroVector;
};

/** The ferry's voyage as its sounds see it: at the berth, casting off and leaving harbour, at sea, coming in. */
UENUM()
enum class EFerryAudioPhase : uint8 { Berthed, Departing, Cruise, Approach };

/** The ferry (batch B3). Call on every machine from its replicated state: SetPhase on each change, SetThrottle,
 *  SetSpeed and SetThruster every tick, OnBoardingOpen/OnBoardingClose when the brow lands on and lifts off the quay. */
UCLASS()
class YORIMICHI_API UFerryAudioComponent : public UTransportAudioComponent
{
 GENERATED_BODY()
public:
 /** Berthed to Departing sounds the departure horn, Cruise to Approach the arrival horn, Approach (or Departing) to
  *  Berthed the fenders taking the hull. The first call only records the phase. */
 void SetPhase(EFerryAudioPhase NewPhase);
 /** 0 idle, about .35 manoeuvring, 1 cruise ahead (the sign is ignored: astern sounds the same). */
 void SetThrottle(float Throttle) { Throttle01=FMath::Clamp(FMath::Abs(Throttle),0.f,1.f); }
 /** Speed through the water, cm/s; drives the hull wash. Negative uses the component's own measured speed. */
 void SetSpeed(float CmPerSecond) { WaterSpeed=CmPerSecond; }
 /** The bow thruster's effort while crabbing onto or off the berth, 0-1. */
 void SetThruster(float Effort) { Thruster=FMath::Clamp(FMath::Abs(Effort),0.f,1.f); }
 void OnBoardingOpen();
 void OnBoardingClose();
protected:
 virtual FBankSpec Bank() const override;
 virtual void Evaluate(float Dt) override;
private:
 EFerryAudioPhase Phase=EFerryAudioPhase::Berthed; bool bPrimed=false;
 float Throttle01=0.f,WaterSpeed=-1.f,Thruster=0.f;
};

/** A gondola cabin (batch B4), attached to the cabin. Call on every machine from the line's shared clock: SetSpeed
 *  every tick, and the events as the cabin meets them. */
UCLASS()
class YORIMICHI_API UGondolaAudioComponent : public UTransportAudioComponent
{
 GENERATED_BODY()
public:
 /** The cabin's speed along the line, cm/s (0 parked; slow through a station's loop). */
 void SetSpeed(float CmPerSecond) { LineSpeed=FMath::Max(0.f,CmPerSecond); }
 /** The grip crossing a tower's sheave train; Strength 0-1 (a support tower 1, a hold-down tower lighter). */
 void OnTowerPass(float Strength=1.f);
 void OnGripAttach();
 void OnGripRelease();
 /** Each door movement chimes; the close chime sounds as a warning just before the door rolls shut. */
 void OnDoorOpen();
 void OnDoorClose();
protected:
 virtual FBankSpec Bank() const override;
 virtual void Evaluate(float Dt) override;
private:
 float LineSpeed=0.f;
};

/** A gondola station's drive (batch B4), attached at the bullwheel: the machinery hums while the line runs. */
UCLASS()
class YORIMICHI_API UGondolaStationAudioComponent : public UTransportAudioComponent
{
 GENERATED_BODY()
public:
 /** The haul rope's speed as a fraction of the line's nominal speed: 0 stopped, 1 running. */
 void SetRunning(float LineSpeed01) { Running=FMath::Clamp(LineSpeed01,0.f,1.5f); }
protected:
 virtual FBankSpec Bank() const override;
 virtual void Evaluate(float Dt) override;
private:
 float Running=0.f;
};

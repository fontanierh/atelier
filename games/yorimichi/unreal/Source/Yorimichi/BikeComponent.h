#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "BikeComponent.generated.h"
class AWandererCharacter; class UStaticMeshComponent; class USceneComponent; class UAnimSequence; class UAudioComponent; class USoundWave; class USoundAttenuation; class UPhysicsAsset;

/** Cairo's teal mamachari (assets/vehicles/bike, docs/BIKE.md). Summoned beside him, mounted, ridden with walking
 *  physics (floors, slopes and walls stay the movement component's), parked on its stand or crashed. Every rider move
 *  is a clip authored on the bike (assets/vehicles/bike/rider.py); the clip's per-frame bike channels (crank, stand,
 *  lift, pitch, lean, yaw, steer) pose the parts here, on the same clock the animation instance plays the clip on. */
UCLASS()
class YORIMICHI_API UBikeComponent : public UActorComponent
{
 GENERATED_BODY()
public:
 enum class EState : uint8 { Off, Mounting, Riding, Dismounting, Parking, Crashing };
 UBikeComponent();
 void Initialize(AWandererCharacter*);
 /** V / hold Y: summon and mount, or (stopped) step off and park. False with the reason in GetStatus(). */
 bool Toggle();
 void StowImmediately();
 void SetInput(FVector2D Intent,bool bMenuOpen);
 /** Sprint (Shift, left stick press): pedal hard until pressed again, or until he stops pedalling, brakes, skids or
  *  gets off. False when he is not riding. */
 bool ToggleSprint();
 bool IsSprinting() const { return bSprint; }
 bool Hop(); bool Skid(); bool Bell(); bool Wave();
 virtual void TickComponent(float,ELevelTick,FActorComponentTickFunction*) override;
 bool IsAvailable() const { return bAssetsReady; }
 /** He is on (or getting on or off) the bike: the bike owns his movement and his animation. */
 bool IsEquipped() const { return State!=EState::Off; }
 bool IsRiding() const { return State==EState::Riding; }
 EState GetState() const { return State; }
 float GetSpeed() const { return Speed; }
 float GetSteering() const { return Steering; }
 uint32 GetSerial() const { return Serial; }
 UAnimSequence* GetSequence() const;
 FName GetClip() const { return Clip; }
 float GetClipTime() const { return ClipTime; }
 /** Where the animation should be in the clip: the clock wrapped for loops, held at the end for one-shots. */
 float GetPoseTime() const;
 FString GetStatus() const { return Hint; }
 /** Per hand (0 left, 1 right): contact weight, the live grip's offset from the authored one and the bars' extra turn,
  *  in the mesh's component space. */
 void GetGrip(int32 Side,float& Weight,FVector& Offset,FQuat& Turn) const;
 /** The bike's assembled world transform and its parts, for QA and reviews. */
 FTransform GetBikeTransform() const;
 bool IsParked() const { return bParked; }
 /** How far each wheel's lowest point is above the ground straight under it (cm; negative: sunk in), front then rear. */
 FVector2D GetWheelGaps() const;
 /** The pitch (degrees, nose up) the bike and he take from the ground under the wheels. */
 float GetGroundPitch() const { return GroundPitch; }
 /** Each loop's "volume pitch" (tyre, tyre_wood, tyre_stone, tyre_dirt, tyre_grass, freewheel, chain, wind, skid,
  *  skid_dirt), for mixing filmed takes offline (scenarios/bike_live.py). */
 FString GetLoopState() const;
private:
 struct FClip { float Duration=0; bool bLoop=false; TArray<TArray<float>> Frames; TArray<FVector2D> Contacts[4]; FVector2D EndOffset=FVector2D::ZeroVector; bool bEndOffset=false; };
 UPROPERTY() TObjectPtr<AWandererCharacter> Rider;
 UPROPERTY() TObjectPtr<USceneComponent> BikeRoot;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> Frame;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> Steer;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> WheelFront;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> WheelRear;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> Crank;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> PedalL;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> PedalR;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> Kickstand;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> RackBoard;
 /** A rider's cloth (Modori's coat) collides with the bike while he rides it: the rack and its board, the rear wheel. */
 UPROPERTY() TObjectPtr<UPhysicsAsset> ClothBodies;
 void ClothColliders(bool bOn);
 UPROPERTY() TMap<FName,TObjectPtr<UAnimSequence>> Sequences;
 TMap<FName,FClip> Clips;
 int32 Fps=60;
 // From the bike's manifest, in centimetres in the mesh's frame (Unreal axes: +Y is the bike's right).
 FVector HeadPivot,SteerAxis,FrontAxle,RearAxle,BottomBracket,StandPivot,Grip[2],RearContact,Beside;
 float WheelRadius=23.f,CrankLength=12.f,PedalOffset=8.f,StowedDegrees=96.f;
 FQuat SteerRest=FQuat::Identity;
 EState State=EState::Off;
 FName Clip,Resume;
 float ClipTime=0,Speed=0,Steering=0,Lean=0,WheelAngle=0,StillTime=0,AppliedYaw=0,CrankAngle=0;
 FVector2D Input=FVector2D::ZeroVector;
 bool bSprint=false,bMenu=false,bAssetsReady=false,bParked=false;
 float Coast=0;   // s since he last pedalled, for ending the sprint
 // The ground under the wheels: he and the bike pitch to it and sit on it between them (cm), snapped on getting on.
 float GroundPitch=0,GroundOffset=0,WheelGround[2]={0,0},WheelFall[2]={0,0}; bool bSnapGround=false;   // front, rear: cm, cm/s
 void FollowGround(float Dt);
 /** M_Bike's shaders are made (editor builds; bFinish: wait for them). */
 bool MaterialsReady(bool bFinish) const;
 uint32 Serial=0;
 // The channels last posed, and what is left of the blend from them into a new clip (the rider's own clip blend).
 TArray<float> Displayed,BlendFrom; float BlendLeft=0;
 FString Hint=TEXT("V bike");
 float SavedFriction=0,SavedBraking=0;
 float Recoil=0;   // cm the crash backs off from what he hit, over CrashRecoil s
 FVector MeshLocation=FVector::ZeroVector; FRotator MeshRotation=FRotator::ZeroRotator;
 // Sounds (/Game/Audio/Bike, assets/audio/bike/make.py): loops on the bike, one-shot banks played at the bike.
 UPROPERTY() TArray<TObjectPtr<UAudioComponent>> Loops;
 UPROPERTY() TArray<TObjectPtr<USoundWave>> Waves;
 UPROPERTY() TObjectPtr<USoundAttenuation> Attenuation;
 TMap<FName,FIntPoint> CueRange; TArray<float> LoopVolume; int32 LastVariant=-1;
 uint8 Ground=0;   // ESkateSurface under the wheels
 float GroundCheck=0,CueClock=-1,Airborne=0,FallSpeed=0,RattleWait=0;
 void LoadSounds();
 void PlayCue(FName Cue,float Volume=1.f,float Pitch=1.f);
 void ClipCues();
 void UpdateAudio(float Dt,bool bPedal,float Cadence);
 bool LoadData();
 /** The rider's rig, naming its bike clips and data: "Cairo" or "Modori" (rider.py --character). */
 FString RiderRig() const;
 void Play(FName Name,FName Then=NAME_None);
 const TArray<float>* Channels(TArray<float>& Out) const;
 float ContactWeight(int32 Limb) const;
 void BeginRide();
 void EndClip();
 void Park();
 bool ClearFor(const FVector& Origin,float Yaw) const;
 void Pose(const TArray<float>& C);
 FTransform BikeMatrix(const TArray<float>& C) const;
 FQuat SteerQuat(float Degrees) const;
};

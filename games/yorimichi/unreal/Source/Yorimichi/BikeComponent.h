#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "BikeComponent.generated.h"
class AWandererCharacter; class UStaticMeshComponent; class USceneComponent; class UAnimSequence;

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
 void SetInput(FVector2D Intent,bool bSprint,bool bMenuOpen);
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
 uint32 Serial=0;
 // The channels last posed, and what is left of the blend from them into a new clip (the rider's own clip blend).
 TArray<float> Displayed,BlendFrom; float BlendLeft=0;
 FString Hint=TEXT("V bike");
 float SavedFriction=0,SavedBraking=0;
 float Recoil=0;   // cm the crash backs off from what he hit, over CrashRecoil s
 FVector MeshLocation=FVector::ZeroVector; FRotator MeshRotation=FRotator::ZeroRotator;
 bool LoadData();
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

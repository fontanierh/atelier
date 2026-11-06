#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "JapanSailState.h"
#include "JapanSkateClock.h"
#include "SailboatComponent.generated.h"
struct FCollisionShape;
class UMaterialInstanceDynamic; class AWandererCharacter; class AJapanWorld; class UStaticMeshComponent; class USceneComponent; class UAnimSequence;
/** Shore-launched dinghy with deliberately forgiving sailing, hull clearance and safe landing. */
UCLASS()
class YORIMICHI_API USailboatComponent : public UActorComponent
{
 GENERATED_BODY()
public:
 USailboatComponent();
 void Initialize(AWandererCharacter*,AJapanWorld*);
 bool Toggle();
 bool IsAvailable() const {return bAssetsReady;}
 void SimulateNetwork(float Dt,FVector2D Stick,bool Menu);
 FJapanSailState CaptureNetworkState() const;
 bool ApplyNetworkState(const FJapanSailState& Snapshot,bool RestoreFacing=true);
 void ReceiveNetworkPresentation(uint32 Epoch,double Stamp,const FJapanSailState& Snapshot);
 bool ApplyNetworkActivity(const FJapanSailState& Snapshot);
 void StowImmediately();
 void EmergencyStop();
 void SetInput(FVector2D Intent,bool bMenuOpen);
 virtual void TickComponent(float,ELevelTick,FActorComponentTickFunction*) override;
 bool IsEquipped() const { return bEquipped; }
 bool IsOnWater() const { return bEquipped; }
 FVector GetRideVelocity() const { return RideVelocity; }
 float GetSpeed() const { return Speed; }
 /** Depth below the sea, using the same fixed-world query as the hull. Negative means no ground. */
 float GetWaterDepth() const;
 uint32 GetSerial() const { return Serial; }
 UAnimSequence* GetSequence() const;
 FString GetStatus() const { return Hint; }
 float GetSailAmount() const { return SailAmount; }
 void SetCameraDistance(float Distance);
 FVector PosePoint(FVector Local) const;
 FVector HandPoint(int32 Side) const;
 FVector TillerDirection() const;
 FVector TillerUp() const;
 float GetSteering() const { return Steering; }
private:
 UPROPERTY() TObjectPtr<AWandererCharacter> Rider;
 UPROPERTY() TObjectPtr<AJapanWorld> Landscape;
 UPROPERTY() TObjectPtr<USceneComponent> HullRoot;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> Hull;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> Sail;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> Boom;
 UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> ClothMaterial;
 UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> FoamMaterial;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> Rudder;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> Wake;
 FVector2D Input=FVector2D::ZeroVector;
 FVector RideVelocity=FVector::ZeroVector;
 FVector OriginalMeshLocation,OriginalSocketOffset;
 FQuat OriginalMeshRotation;
 float Speed=0,Steering=0,SailAmount=0,SailTarget=0,BoomAngle=0,Phase=0,WakeAmount=0,OriginalArmLength=0;
 bool bEquipped=false,bMenu=false,bAssetsReady=false;
 uint32 Serial=0;
 FString Hint=TEXT("Launch near a shore or low dock");
 void QueryParams(FCollisionQueryParams&) const;
 bool GroundAt(FVector,FHitResult&) const;
 bool ClearWater(FVector Center,float Yaw) const;
 bool PawnClear(FVector At,FQuat Rotation,const FCollisionShape& Shape) const;
 bool FindLanding(FVector& Point) const;
 struct FNetworkPose {double At;FJapanSailState State;};
 TArray<FNetworkPose> NetworkPoses;FJapanSkatePlayout NetworkPlayout;
 uint32 PresentationEpoch=0;double LastPresentationStamp=-1.;
 void SampleNetworkPresentation();
 void AdvanceSimulation(float Dt);
 void UpdateVisuals(float Dt);
};

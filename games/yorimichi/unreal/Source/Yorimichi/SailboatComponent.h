#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "SailboatComponent.generated.h"
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
 void StowImmediately();
 void EmergencyStop();
 void SetInput(FVector2D Intent,bool bMenuOpen);
 virtual void TickComponent(float,ELevelTick,FActorComponentTickFunction*) override;
 bool IsEquipped() const { return bEquipped; }
 bool IsOnWater() const { return bEquipped; }
 FVector GetRideVelocity() const { return RideVelocity; }
 float GetSpeed() const { return Speed; }
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
 bool FindLanding(FVector& Point) const;
 void UpdateVisuals(float Dt);
};

#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ZeppelinService.generated.h"
class AWandererCharacter;
class UStaticMeshComponent;
class USceneComponent;
class FJsonObject;
class ADirectionalLight;
class UMaterialInstanceDynamic;

USTRUCT()
struct FZeppelinStation
{
 GENERATED_BODY()
 FString Name;
 FVector Origin=FVector::ZeroVector, Ship=FVector::ZeroVector, Entry=FVector::ZeroVector, Safe=FVector::ZeroVector;
};

/** One shared passenger airship on a line of stations. Every station keeps its dock interface; all travel is reversible. */
UCLASS()
class YORIMICHI_API AZeppelinService : public AActor
{
 GENERATED_BODY()
public:
 AZeppelinService();
 void Initialize(const TSharedPtr<FJsonObject>& Data);
 virtual void Tick(float Dt) override;
 virtual void EndPlay(const EEndPlayReason::Type Reason) override;
 bool TryInteract(AWandererCharacter* Character);
 bool IsPassenger(const AWandererCharacter* Character) const;
 void Cancel(AWandererCharacter* Character);
 FString Hint(const AWandererCharacter* Character) const;
 /** With more than two stops, someone at the docked ship can choose where it flies next: -1 previous, +1 next stop. */
 bool CanChooseStop(const AWandererCharacter* Character) const;
 bool ChooseDestination(const AWandererCharacter* Character,int32 Direction);
 void SetPassengerCameraDistance(float Distance) { if(Passenger)StoredArm=Distance; }
 int32 GetStage() const { return Phase; }
 /** Passenger control over the ride: -1 slower, +1 faster. The choice persists between flights. */
 void AdjustFlightSpeed(int32 Direction);
 float GetFlightSpeed() const { return FlightSpeed; }
 bool IsFlying() const { return Phase>=3&&Phase<=5; }
 float GetWalkSpeed() const { return WalkSpeed; }
 float GetPropellerAngle() const { return PropAngle; }
 int32 GetDock() const { return Dock; }
 int32 GetDestination() const { return Destination; }
 const TArray<FZeppelinStation>& GetStations() const { return Stations; }
 FVector ShipPosition() const;
private:
 UPROPERTY() TObjectPtr<USceneComponent> ShipRoot;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> Hull;
 UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> Fabric;
 TWeakObjectPtr<ADirectionalLight> Sun;
 FVector LastSunDirection=FVector::ZeroVector;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> Motors;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> Gate;
 UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Propellers;
 UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> DockGates;
 UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Gangways;
 UPROPERTY() TObjectPtr<AWandererCharacter> Passenger;
 TArray<FZeppelinStation> Stations;
 TArray<FVector> WalkPoints;
 /** Cruise height (cm) and seconds of the leg between stops A and B, at A*Stations.Num()+B. */
 TArray<FVector2f> Legs;
 int32 Phase=0,Dock=0,Destination=1,Came=INDEX_NONE,WalkIndex=0;
 float PhaseTime=0,PropAngle=0,RPM=55,WalkSpeed=0,GateOpen=1;
 float FlightSpeed=1.f;
 float StoredArm=420;FVector StoredOffset=FVector::ZeroVector;bool StoredCameraCollision=true;
 bool Ready=false;
 UStaticMeshComponent* Mesh(const TCHAR* Name,const TCHAR* Asset,USceneComponent* Parent);
 void SetPhase(int32 NewPhase);
 void DockAt(int32 Index);
 int32 NextStop(int32 At) const;
 FVector2f Leg() const { return Legs[Dock*Stations.Num()+Destination]; }
 float Heading() const;
 float ClimbSeconds() const;
 float LandSeconds() const;
 void BeginBoarding(AWandererCharacter* Character);
 void RestorePassenger();
 void WalkPassenger(float Dt);
 void PlacePassenger(bool Walking,float Dt);
 int32 Nearby(const AWandererCharacter* Character,float Radius) const;
};

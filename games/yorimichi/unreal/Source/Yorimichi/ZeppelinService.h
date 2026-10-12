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

USTRUCT()
struct FZeppelinPassenger
{
 GENERATED_BODY()
 UPROPERTY() TObjectPtr<AWandererCharacter> Rider;
 UPROPERTY() FVector Start = FVector::ZeroVector;
 UPROPERTY() float BoardedAt = 0.f;
 UPROPERTY() int32 Seat = 0;
};

/** One coherent host snapshot; clients derive ship and passenger presentation from its clock. */
USTRUCT()
struct FZeppelinNetworkState
{
 GENERATED_BODY()
 UPROPERTY() uint32 Serial = 0;
 UPROPERTY() int32 Phase = 0;
 UPROPERTY() int32 Dock = 0;
 UPROPERTY() int32 Destination = 1;
 UPROPERTY() int32 Came = INDEX_NONE;
 UPROPERTY() float PhaseTime = 0.f;
 UPROPERTY() float Stamp = 0.f;
 UPROPERTY() float FlightSpeed = 1.f;
 UPROPERTY() TArray<FZeppelinPassenger> Passengers;
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
 virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
 bool IsReady() const { return Ready; }
 bool ReplacePassenger(AWandererCharacter* From, AWandererCharacter* To);
 bool TryInteract(AWandererCharacter* Character);
 bool IsPassenger(const AWandererCharacter* Character) const;
 void Cancel(AWandererCharacter* Character);
 FString Hint(const AWandererCharacter* Character) const;
 /** With more than two stops, someone at the docked ship can choose where it flies next: -1 previous, +1 next stop. */
 bool CanChooseStop(const AWandererCharacter* Character) const;
 bool ChooseDestination(const AWandererCharacter* Character,int32 Direction);
 void SetPassengerCameraDistance(float Distance);
 int32 GetStage() const { return Phase; }
 /** Passenger control over the ride: -1 slower, +1 faster. The choice persists between flights. */
 void AdjustFlightSpeed(int32 Direction);
 float GetFlightSpeed() const { return FlightSpeed; }
 bool IsFlying() const { return Phase>=3&&Phase<=5; }
 float GetWalkSpeed(const AWandererCharacter* Character = nullptr) const;
 float GetPropellerAngle() const { return PropAngle; }
 int32 GetDock() const { return Dock; }
 int32 GetDestination() const { return Destination; }
 const TArray<FZeppelinStation>& GetStations() const { return Stations; }
 FVector ShipPosition() const;
private:
 UPROPERTY(ReplicatedUsing=OnRep_NetworkState) FZeppelinNetworkState NetworkState;
 UFUNCTION() void OnRep_NetworkState();
 double LastNetworkPublication = -1.;
 bool bNetworkStateReceived = false;
 struct FPassengerCamera
 {
  float Arm = 420.f;
  FVector Offset = FVector::ZeroVector;
  bool Collision = true;
 };
 TMap<TWeakObjectPtr<AWandererCharacter>, FPassengerCamera> PassengerCameras;
 TMap<TWeakObjectPtr<AWandererCharacter>, float> PassengerWalkSpeeds;
 void TickNetwork(float Dt);
 void PublishNetworkState();
 bool InteractNetwork(AWandererCharacter* Character);
 void CancelNetwork(AWandererCharacter* Character);
 bool PlaceNetworkPassengers(float Dt);
 void RestoreNetworkCamera(AWandererCharacter* Character);
 FVector PassengerSeat(int32 Index) const;
 FVector WalkPath(const TArray<FVector>& Points, float Distance, bool& Complete) const;
 void AdvanceShip(float Dt);
 void AdvanceParts(float Dt);
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

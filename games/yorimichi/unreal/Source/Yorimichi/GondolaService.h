#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "TransportRiders.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/AssetUserData.h"
#include "GondolaService.generated.h"

class UStaticMesh;
class UStaticMeshComponent;
class UBoxComponent;
class UGondolaAudioComponent;
class UGondolaStationAudioComponent;
class FJsonObject;

/** Native measured complete logical rope bounds, serialized with every bounded child. */
UCLASS(EditInlineNew, DefaultToInstanced)
class YORIMICHI_API UGondolaRopeBoundsData : public UAssetUserData
{
    GENERATED_BODY()
public:
    UPROPERTY() FString LogicalParent;
    UPROPERTY() TArray<FString> Family;
    UPROPERTY() FVector Origin = FVector::ZeroVector;
    UPROPERTY() FVector Extent = FVector::ZeroVector;
    UPROPERTY() double Radius = 0.;
};

/** One bounded rope child with the original logical parent's exact culling bounds. */
UCLASS()
class YORIMICHI_API UGondolaRopeMeshComponent : public UStaticMeshComponent
{
    GENERATED_BODY()
public:
    /** Measure actual final native buffers in all three LODs and persist the original
     * MeshBuilder per-LOD sphere/box union on every member. Empty refuses missing proof. */
    UFUNCTION(BlueprintCallable, Category="Yorimichi|Import")
    static FString FinishLogicalRope(const FString& Parent, const TArray<UStaticMesh*>& Parts);
    bool ConfigureLogicalFamily(const FString& Parent, const TArray<FString>& Family);
    virtual FBoxSphereBounds CalcBounds(const FTransform& LocalToWorld) const override;
private:
    FBoxSphereBounds LogicalBounds = FBoxSphereBounds(ForceInit);
};

/** Clock interval: constant acceleration along the audited circuit, metres/seconds. */
struct FGondolaInterval { double Start=0., End=0., From=0., To=0., Speed=0., Acceleration=0.; };
struct FGondolaStop { double Start=0., End=0., Arc=0.; FString Station; int32 Side=0; };
struct FGondolaEvent { double Time=0.; FString Kind; };
struct FGondolaPose
{
    FTransform Grip, Body;
    double Arc=0., Speed=0., CycleTime=0.;
    int32 Stop=INDEX_NONE;
    float Door=0.f;
};
struct YORIMICHI_API FGondolaLine
{
    FString Id;
    double Cycle=0.;
    int32 CabinCount=0;
    TArray<FVector> Points;
    TArray<double> Arc;
    TArray<FGondolaInterval> Intervals;
    TArray<FGondolaStop> Stops;
    TArray<FGondolaEvent> Events;
    bool Parse(const TSharedPtr<FJsonObject>& Data);
    FVector Point(double Distance) const;
    FGondolaPose State(double Time, const FVector& Pivot) const;
};

USTRUCT()
struct FGondolaPassenger
{
    GENERATED_BODY()
    UPROPERTY() TObjectPtr<AWandererCharacter> Rider;
    UPROPERTY() int16 Cabin=INDEX_NONE;
    UPROPERTY() int16 Seat=INDEX_NONE;
};
USTRUCT()
struct FGondolaNetworkState
{
    GENERATED_BODY()
    UPROPERTY() uint32 Serial=0;
    UPROPERTY() double Offset=0.;
    UPROPERTY() double Stamp=0.;
    UPROPERTY() float Scale=1.f;
    UPROPERTY() TArray<FGondolaPassenger> Passengers;
};

/** Three source-fitted two-way ropeways. Every machine samples the same server clock.
 * Grip follows the audited rope; the cabin/hanger hang level from its pivot.
 * Physical doors open only during platform dwell. Riders reuse the train/ferry mechanism. */
UCLASS()
class YORIMICHI_API AGondolaService : public AActor
{
    GENERATED_BODY()
public:
    AGondolaService();
    static AGondolaService* Spawn(UWorld* World,const FString& Path);
    static AGondolaService* Find(const UObject* Context);
    virtual void BeginPlay() override;
    virtual void Tick(float Dt) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& Out) const override;
    bool GoTo(const FString& Station);
    static bool TryInteract(AWandererCharacter* Character);
    bool SitPlayer(AWandererCharacter* Character,int32 PreferredSeat=INDEX_NONE);
    bool StandPlayer(AWandererCharacter* Character);
    FString StateJson() const;
    FVector Point(const FString& What) const;
    struct FSeat { FString Id; FVector Location=FVector::ZeroVector; float Yaw=0.f; };
    static void BuildCabinSeats(const FVector& CabinSize,float CabinFloorZ,TArray<FSeat>& OutSeats);
private:
    struct FCabin
    {
        int32 Line=0, Index=0;
        TObjectPtr<UStaticMeshComponent> Body, Grip;
        TArray<TObjectPtr<UStaticMeshComponent>> Parts;
        TArray<TObjectPtr<UStaticMeshComponent>> Doors;
        TArray<FVector> DoorOffsets;
        TObjectPtr<UBoxComponent> DoorBlock;
        TObjectPtr<UGondolaAudioComponent> Audio;
        FTransform Previous;
        FGondolaPose Pose;
        double LastTime=0.;
        bool bPrimed=false;
        TArray<uint8> SeatTaken;
    };
    struct FRiderSeat
    {
        TWeakObjectPtr<AWandererCharacter> Character;
        int32 Cabin=INDEX_NONE, Seat=INDEX_NONE;
        float Seated=0.f;
        bool bSailed=false, bManualStand=false;
        FVector SeatedAt=FVector::ZeroVector;
    };
    struct FStation
    {
        FString Id;
        TArray<FVector> Walk;
        TObjectPtr<UGondolaStationAudioComponent> Audio;
    };
    struct FRope { TObjectPtr<UStaticMeshComponent> Mesh; int32 Line=0; };
    bool Initialize(const FString& Path);
    UStaticMeshComponent* MeshPart(const FString& Name,const FString& Path,bool Collision,bool Movable,bool Rope=false);
    void Place(double Time,bool First=false);
    void UpdateRiders(float Dt);
    FRiderSeat& SeatFor(AWandererCharacter* Character);
    const FRiderSeat* FindSeat(const AWandererCharacter* Character) const;
    int32 NearestFreeSeat(int32 CabinIndex,const FVector& WorldFeet) const;
    void SitDown(FTransportRider& R,FRiderSeat& S,int32 CabinIndex,int32 SeatIndex);
    void StandUp(FTransportRider& R,FRiderSeat& S);
    void Publish();
    void ApplyRemote();
    double ServiceTime() const;
    UFUNCTION() void OnRep_NetworkState();
    UPROPERTY(ReplicatedUsing=OnRep_NetworkState) FGondolaNetworkState NetworkState;
    UPROPERTY() TArray<TObjectPtr<UActorComponent>> Components;
    TArray<FGondolaLine> Lines;
    TArray<FCabin> Cabins;
    TArray<FStation> Stations;
    TArray<FRope> Ropes;
    TArray<FTransportRider> Riders;
    TArray<FRiderSeat> SeatsByRider;
    TArray<FSeat> Seats;
    FVector Pivot=FVector::ZeroVector, DoorCentre=FVector::ZeroVector, Size=FVector::ZeroVector;
    float FloorZ=0.f, DoorWidth=0.f, DoorHeight=0.f;
    double Offset=0.;
    float PublishElapsed=0.f;
    bool bReady=false,bFailed=false;
    friend class FGondolaClockTest;
};

UCLASS()
class YORIMICHI_API UGondolaLive : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable,Category="Live") static FString GondolaState();
    UFUNCTION(BlueprintCallable,Category="Live") static bool GondolaGo(const FString& Station);
    UFUNCTION(BlueprintCallable,Category="Live") static FVector GondolaPoint(const FString& What);
    UFUNCTION(BlueprintCallable,Category="Live") static bool GondolaSit(int32 SeatIndex=-1);
    UFUNCTION(BlueprintCallable,Category="Live") static bool GondolaStand();
};

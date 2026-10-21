#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "TransportRiders.h"
#include "TransportAudio.h"
#include "FerryService.generated.h"

class FJsonObject;
class UStaticMeshComponent;
class UBoxComponent;
class UTextRenderComponent;
class AWandererCharacter;

/** One sample of a ship's cycle: where it is (cm), its heading (Unreal yaw, degrees), how it moves (cm/s, deg/s) and what
 *  its engines do (throttle 0-1, bow thruster 0-1). */
struct YORIMICHI_API FFerrySample
{
    FVector2D At = FVector2D::ZeroVector, Velocity = FVector2D::ZeroVector;
    double Yaw = 0., YawRate = 0.;
    float Throttle = 0.f, Thruster = 0.f;
};

/** A span of the cycle with one voyage phase; Berth is the berth index while alongside, else INDEX_NONE. */
struct YORIMICHI_API FFerryPhase
{
    double Start = 0., End = 0.;
    EFerryAudioPhase Phase = EFerryAudioPhase::Berthed;
    int32 Berth = INDEX_NONE;
};

/** Where a ship is and what it does at a service time. */
struct YORIMICHI_API FFerryState
{
    FVector Location = FVector::ZeroVector;
    double Yaw = 0.;
    FVector Velocity = FVector::ZeroVector;
    double YawRate = 0.;
    float Throttle = 0.f, Thruster = 0.f;
    EFerryAudioPhase Phase = EFerryAudioPhase::Berthed;
    int32 Berth = INDEX_NONE;
    /** Seconds into the ship's own cycle. */
    double CycleTime = 0.;
};

/**
 * The ferry line and its timetable (Content/Data/ferry/service.json, world/regions/ferry/service.py): a pure function
 * of the service time, so every machine places the ships alike from the replicated server clock without replicating
 * their movement. One cycle (alongside at Hidamari, the voyage west, alongside at Brinecove, the voyage back) is sampled
 * every half second; each ship sails it offset in time. Positions interpolate as cubic Hermite curves through the
 * samples' positions and velocities, so a rider feels no step between samples.
 */
struct YORIMICHI_API FFerryLine
{
    double Cycle = 0., ClockStart = 0., Step = .5;
    TArray<FFerrySample> Samples;
    TArray<FString> ShipNames;
    TArray<double> ShipOffsets;
    TArray<FFerryPhase> Phases;
    /** Per berth: its brow's windows in ship cycle time (lowering starts, down, raising starts, up). */
    TArray<TArray<FVector4>> BrowWindows;

    bool Parse(const TSharedPtr<FJsonObject>& Root, FString& Error);
    /** Seconds into a ship's cycle at a service time. */
    double ShipTime(int32 Ship, double Time) const;
    FFerryState State(int32 Ship, double Time) const;
    /** How far a berth's brow is down, 0 raised .. 1 resting on the ship's landing plate (eased), from every ship. */
    float BrowDown(int32 Berth, double Time) const;
    /** The next service time at or after From when a ship comes alongside a berth (its dwell starts), and which ship. */
    double NextAlongside(int32 Berth, double From, int32* Ship = nullptr) const;
};

USTRUCT()
struct FFerryPassenger
{
    GENERATED_BODY()
    UPROPERTY() TObjectPtr<AWandererCharacter> Rider;
    UPROPERTY() int16 Ship = INDEX_NONE;
};

USTRUCT()
struct FFerryNetworkState
{
    GENERATED_BODY()
    UPROPERTY() uint32 Serial = 0;
    /** The host's dev clock offset (ferry.Go, ferry.TimeScale): clients place the ships from the same time. */
    UPROPERTY() double DevOffset = 0.;
    UPROPERTY() float TimeScale = 1.f;
    UPROPERTY() TArray<FFerryPassenger> Passengers;
};

/**
 * The ferry between Hidamari and Brinecove (assets/vehicles/ferry/README.md): one ship sailing a two-way timetable, and the
 * two terminals they berth at. One actor ticks for the service before the characters: it places each ship from the
 * service time, swings each terminal's brow down onto the ship alongside and up before it leaves, closes a ship's
 * boarding gates whenever no brow rests on them, and carries the players aboard (FTransportRiders, the rider mechanism
 * it shares with the Belmonte train): anyone walking over the brow onto the deck rides with the ship, on foot, and can
 * walk off again at the other harbour. The ships' sounds (UFerryAudioComponent) follow each ship's phase, throttle,
 * speed, thruster and brow on every machine.
 *
 * Online the host spawns the service and replicates it (always relevant); every machine builds the ships and terminals
 * from the staged data with stable component names, so a ship's deck is a network movement base like a train coach's.
 *
 * Dev: `ferry.Go [hidamari|brinecove]` jumps the clock to the next ship coming alongside there and travels to the
 * terminal's walk; `ferry.TimeScale` runs the clock faster. Launch flags: -ferrygo[=harbour], -ferrytimescale=N.
 */
UCLASS()
class YORIMICHI_API AFerryService : public AActor
{
    GENERATED_BODY()
public:
    AFerryService();
    static AFerryService* Spawn(UWorld* World, const FString& Path);
    static AFerryService* Find(const UObject* WorldContext);
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
    double ServiceTime() const;
    const FFerryLine& GetLine() const { return Line; }
    /** Jumps the clock (offline, with nobody aboard) to the next ship coming alongside a harbour and travels to the start
     *  of its terminal's walk. */
    bool GoTo(const FString& Harbour);
    FString StateJson() const;
    /** A point in world cm: "ship:<index>:<x m>:<y m>:<z m>" (ship metres, x to the bow, y to port), "walk:<terminal>:<index>"
     *  (the terminal's audited walk, -1 its last point). */
    FVector Point(const FString& What) const;
    /** The ship whose deck carries this player, or INDEX_NONE. */
    int32 ShipOf(const AWandererCharacter* Character) const;

private:
    struct FShip
    {
        TObjectPtr<UStaticMeshComponent> Body;
        TArray<TObjectPtr<UStaticMeshComponent>> Parts;
        TArray<TObjectPtr<UBoxComponent>> Gates;
        TArray<TObjectPtr<UStaticMeshComponent>> GateVisuals;
        TArray<float> GateYaw;
        bool bGatesPlaced = false;
        TObjectPtr<UFerryAudioComponent> Audio;
        FTransform Previous = FTransform::Identity;
        bool bMoved = false, bPlaced = false;
        FFerryState State;
        bool bBrowHeardDown = false;
    };
    struct FGate { FVector Centre = FVector::ZeroVector, Extent = FVector::ZeroVector, Hinge = FVector::ZeroVector; float OpenYaw = 90.f; bool bStarboard = true; };
    struct FTerminal
    {
        FString Key, Name;
        FVector Anchor = FVector::ZeroVector;
        TArray<TObjectPtr<UStaticMeshComponent>> Parts;
        TObjectPtr<USceneComponent> Hinge;
        TObjectPtr<UStaticMeshComponent> Brow;
        TObjectPtr<UTextRenderComponent> Board;
        FVector HingeAt = FVector::ZeroVector, Axis = FVector::ForwardVector;
        float Raised = 78.f, Down = -1.f;
        bool bStarboard = true;
        TArray<FVector> Walk;
        float WalkYaw = 0.f;
    };
    struct FRider : FTransportRider {};

    bool Initialize(const FString& Path);
    UStaticMeshComponent* MeshPart(const FString& Name, const FString& Asset, USceneComponent* Parent, bool bCollision, bool bMovable);
    void PlaceShips(double Time, bool bForce);
    void UpdateBrows(double Time);
    void UpdateGates();
    void UpdateBoards(double Time);
    void UpdateRiders(float Dt);
    void UpdateAudio();
    void Report(double Time) const;
    FRider& RiderFor(AWandererCharacter* Character);
    const FRider* FindRider(const AWandererCharacter* Character) const;
    /** The ship whose deck volume (in last frame's ship frame) holds Feet, or INDEX_NONE. */
    int32 DeckAt(const FVector& Feet) const;
    int32 ShipOfComponent(const UPrimitiveComponent* Component) const;
    bool AnyRiderAboard() const;
    friend class FFerryRemotePassengerTest;
    void ApplyRemotePassengers();
    void PublishNetworkState();
    UFUNCTION() void OnRep_NetworkState();

    FFerryLine Line;
    TArray<FShip> Ships;
    TArray<FTerminal> Terminals;
    TArray<FRider> Riders;
    TArray<FGate> GateSpecs;
    FBox Deck = FBox(ForceInit);
    UPROPERTY() TArray<TObjectPtr<UPrimitiveComponent>> Components;
    UPROPERTY(ReplicatedUsing = OnRep_NetworkState) FFerryNetworkState NetworkState;
    double DevOffset = 0.;
    double NextReport = 0., NextBoardUpdate = 0.;
    float PendingGoDelay = -1.f;
    FString PendingGo;
    bool bInitialized = false, bInitFailed = false;
};

/** Live-bridge helpers (atelier live py) for scripted ferry checks and drives. */
UCLASS()
class YORIMICHI_API UFerryLive : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** The service clock, each ship (position, yaw, speed, phase, berth), the brows and the player's ride state, as JSON. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FString FerryState();
    /** AFerryService::Point: a point on a ship or a terminal's walk in world cm; zero when unknown. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FVector FerryPoint(const FString& What);
    /** AFerryService::GoTo. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool FerryGo(const FString& Harbour);
    /** Each ship's sound loops ("name volume pitch", UTransportAudioComponent::GetLoopState), one line per ship. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FString FerryLoops();
};

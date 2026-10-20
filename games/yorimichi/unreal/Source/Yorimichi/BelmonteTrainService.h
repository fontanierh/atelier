#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "BelmonteTrainRules.h"
#include "BelmonteTrainService.generated.h"

class FJsonObject;
class UStaticMesh;
class UStaticMeshComponent;
class UInstancedStaticMeshComponent;
class UBoxComponent;
class UTextRenderComponent;
class AWandererCharacter;

/** A track's centreline: chainage (metres) and rail-top points (Unreal cm), in chainage order. */
struct YORIMICHI_API FBelmonteTrainTrack
{
    TArray<double> S;
    TArray<FVector> P;
    bool IsEmpty() const { return S.Num() < 2; }
    bool Covers(double Chainage) const { return !IsEmpty() && Chainage >= S[0] && Chainage <= S.Last(); }
    /** The point at Chainage, clamped to the ends. */
    FVector At(double Chainage) const;
};

/** One train's cycle: its chainage sampled every Dt seconds from T0, and the times it runs on the loop's second track. */
struct YORIMICHI_API FBelmonteTrainRun
{
    FString Name;
    double T0 = 0., Dt = .5;
    TArray<float> S;
    TArray<FVector2D> LoopTrack;
};

/** A train's stand at a terminus within the cycle: the service times (0 .. Cycle) it arrives and leaves. */
struct YORIMICHI_API FBelmonteTrainStop
{
    int32 Train = 0;
    double Arrive = 0., Depart = 0.;
};

/** An arrival on a station board: the train and the service seconds until it arrives (0 while it stands there). */
struct YORIMICHI_API FBelmonteTrainArrival
{
    int32 Train = INDEX_NONE;
    double In = 0.;
    bool bAtPlatform = false;
};

/**
 * The Belmonte line and its timetable (Content/Data/belmonte_train/service.json, tools/belmonte_train_service.py):
 * everything here is a pure function of the service time, so every machine places the trains alike from the
 * replicated server clock without replicating their movement.
 */
struct YORIMICHI_API FBelmonteTrainLine
{
    FBelmonteTrainTrack Main, Loop;
    double LoopStart = 0., LoopEnd = 0., Cycle = 0., ClockStart = 0.;
    TArray<FBelmonteTrainRun> Trains;
    /** Chainages (m) where the rails stand at or above today's ground, longest stretch first. */
    TArray<double> Viewpoints;
    /** Chainage ranges (m, start..end) where nobody can be set down beside a coach: the viaducts (from the viewpoints'
     *  class) and the tunnels (AddTunnels, from the track's runtime data). */
    TArray<FVector2D> Enclosed;

    bool Parse(const TSharedPtr<FJsonObject>& Root, FString& Error);
    /** Adds the tunnels (`tunnels[].start/end`, chainage m) of the track's runtime data (belmonte_track/track.json);
     *  returns how many. */
    int32 AddTunnels(const TSharedPtr<FJsonObject>& Track);
    /** True when any part of From..To (chainage m) is in a tunnel or on a viaduct. */
    bool IsEnclosed(double From, double To) const;
    /** The train's reference (consist centre) chainage at a service time. */
    double Chainage(int32 Train, double Time) const;
    /** Metres per second along the line, signed (+ toward Belmonte). */
    double Speed(int32 Train, double Time) const;
    bool OnLoopTrack(int32 Train, double Time) const;
    /** The rail-top point at a chainage, on the loop's second track when asked and inside the loop. */
    FVector Point(double Chainage, bool bLoopTrack) const;
    /** A vehicle placed by its two bogie centres (local x, metres) when its centre is at Chainage: location of its
     *  origin (top of rail) and its heading along +x. */
    FTransform Place(double Chainage, double BogieA, double BogieB, bool bLoopTrack) const;
    /** The first service time after From when the two trains pass each other, or -1. */
    double NextCrossing(double From, double* Where = nullptr) const;
    /** The first service time after From when any train's centre passes Chainage, or -1. */
    double NextPassing(double From, double Chainage, int32* Which = nullptr) const;
    /** Every train's stands at the terminus at Chainage over one cycle (from the samples), by arrival time. */
    TArray<FBelmonteTrainStop> Stops(double Chainage) const;
    /** The next Count arrivals at a terminus with these stops at a service time: trains standing there first, then the
     *  trains to come, cycle after cycle. */
    static TArray<FBelmonteTrainArrival> NextArrivals(const TArray<FBelmonteTrainStop>& Stops, double Cycle, double Time, int32 Count);
    /** A board's countdown in real minutes: "à quai" while the train stands there, "arrive" under a minute, otherwise
     *  "dans N min" (whole minutes left). Scale is the service clock's speed (service seconds per real second). */
    static FString Countdown(const FBelmonteTrainArrival& Arrival, double Scale);
};

/**
 * Watch-only Belmonte trains (docs/BELMONTE_TRAIN_SHELL.md): two seven-vehicle consists running the timetable along the
 * route, crossing at the passing loop. One actor ticks for the whole service; vehicles are static meshes with their
 * simple box collision, furniture is instanced per asset per vehicle. Spawned on every machine from the staged data.
 *
 * Riding (offline and on the host): the vehicles are the riders' movement base, moved before the characters each
 * frame; aboard (inside an interior volume) the rider ignores world-static collision so terrain the line still clips
 * cannot push them out, and cannot sprint. On foot only: the one way aboard is the boarding walk at a station door;
 * aboard no vehicle comes out, and anyone else found inside a coach (on a bike or horse through an open door, a jump,
 * the paraglider) is put back on the ground beside it by the host (BelmonteTrainRules.h). Interact opens doors (exterior ones only at a terminus, on the platform
 * side), sits on the nearest free seat and stands up.
 *
 * Stations: at each terminus, arrival boards count down to the next train and the one after in real minutes, from the
 * same shared clock (BelmonteTrainBoards.cpp, docs/BELMONTE_STATION.md).
 *
 * Dev: `train.View [view|loop|a|b|<chainage>]` jumps the service clock and puts the player beside the line where a
 * train is about to pass; `train.TimeScale` runs the service clock faster. `train.Go [belmonte|hidamari]` travels to
 * a terminus platform at the start of the next dwell. Launch flags: -trainview[=where], -traingo[=station],
 * -traintimescale=N.
 */
USTRUCT()
struct FBelmonteTrainPassenger
{
    GENERATED_BODY()
    UPROPERTY() TObjectPtr<AWandererCharacter> Rider;
    UPROPERTY() int16 Vehicle = INDEX_NONE;
    UPROPERTY() int16 Seat = INDEX_NONE;
    UPROPERTY() int16 BoardVehicle = INDEX_NONE;
    UPROPERTY() int16 BoardDoor = INDEX_NONE;
    UPROPERTY() bool bBoardUp = true;
    UPROPERTY() bool bAboard = false;
    /** The host's admission (BelmonteTrainRules::FAdmission): clients carry only admitted riders. */
    UPROPERTY() bool bAdmitted = false;
    UPROPERTY() float BoardTime = 0.f;
    UPROPERTY() float BoardLength = 0.f;
    UPROPERTY() TArray<FVector> BoardPath;
};

USTRUCT()
struct FBelmonteTrainNetworkState
{
    GENERATED_BODY()
    UPROPERTY() uint32 Serial = 0;
    UPROPERTY() double DevOffset = 0.;
    /** The host's train.TimeScale: the station boards turn service seconds into real ones with it. */
    UPROPERTY() float TimeScale = 1.f;
    UPROPERTY() TArray<uint8> OpenDoors;
    UPROPERTY() TArray<FBelmonteTrainPassenger> Passengers;
};

UCLASS()
class YORIMICHI_API ABelmonteTrainService : public AActor
{
    GENERATED_BODY()
public:
    ABelmonteTrainService();
    /** True: the Belmonte railway is part of the default world. */
    static bool IsEnabled();
    static ABelmonteTrainService* Spawn(UWorld* World, const FString& Path);
    static ABelmonteTrainService* Find(const UObject* WorldContext);
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
    static bool CanInteract(const AWandererCharacter* Character);
    static bool IsDrivingRider(const AWandererCharacter* Character);
    static bool IsBoardingRider(const AWandererCharacter* Character);
    void Cancel(AWandererCharacter* Character);
    bool ReplacePassenger(AWandererCharacter* From, AWandererCharacter* To);
    double ServiceTime() const;
    /** Puts the player beside the line where a train passes soon; returns false when there is no player yet. */
    bool View(const FString& Where);
    /** Travels to a terminus platform (station key or "belmonte" / "hidamari"), jumping the clock to the start of the
     *  next dwell there when bWaitForTrain. */
    bool GoToStation(const FString& Where, bool bWaitForTrain);
    /** Interact (D-pad down) near a train door or seat: opens or closes the door, sits down or stands up. */
    static bool TryInteract(AWandererCharacter* Character);
    /** The Interact prompt for the nearest door or seat ("Use" stands for the button), or empty. */
    static FString Hint(const AWandererCharacter* Character);
    const FBelmonteTrainLine& GetLine() const { return Line; }
    int32 NumVehicles() const { return Vehicles.Num(); }
    /** True while the train stands at a terminus and stays there at least a few more seconds. */
    bool AtStation(int32 Train, double Time) const;
    FString Status(const AWandererCharacter* Character) const;
    FString StateJson() const;
    FVector PointOn(int32 Train, const FString& Vehicle, const FString& What) const;

private:
    struct FLeaf
    {
        TObjectPtr<UStaticMeshComponent> Mesh;
        FVector Pivot = FVector::ZeroVector, Offset = FVector::ZeroVector;
        float Yaw = 0.f;
        bool bSliding = false;
    };
    struct FDoor
    {
        FString Id, Kind;
        bool bStation = false, bLocked = false, bPlatformSide = false, bLeft = false;
        TArray<FVector> Handles;
        TObjectPtr<UBoxComponent> Box;
        TArray<FLeaf> Leaves;
        bool bOpen = false;
        /** A rider is stepping through: the door stays open until they are done. */
        bool bBusy = false;
        float Open = 0.f;
        /** Exterior doors and gates at a terminus: the way up, outside to inside, in vehicle cm (empty elsewhere). */
        TArray<FVector> Boarding;
    };
    struct FSeat { FString Id; FVector Location = FVector::ZeroVector; float Yaw = 0.f; };
    struct FInterior { FBox Box; bool bNoSprint = true, bNoClimb = true, bCamera = true; };
    struct FVehicle
    {
        TObjectPtr<UStaticMeshComponent> Body;
        int32 Train = 0;
        FString Id;
        double Offset = 0., BogieA = 0., BogieB = 0.;
        double Placed = TNumericLimits<double>::Max();
        bool bPlacedOnLoop = false;
        /** Where the vehicle stood last frame (riders' positions still match it when the service ticks) and whether it
         *  moved this frame. */
        FTransform Previous = FTransform::Identity;
        bool bMoved = false;
        TArray<FDoor> Doors;
        TArray<FSeat> Seats;
        TArray<FInterior> Interiors;
        TArray<int32> SeatTaken;
    };
    struct FRider
    {
        TWeakObjectPtr<AWandererCharacter> Character;
        int32 Vehicle = INDEX_NONE, Seat = INDEX_NONE;
        bool bAboard = false, bCameraLag = true, bTickOrdered = false;
        /** Boarded through a door (the boarding walk): only an admitted rider is carried as a passenger. Anyone else
         *  riding inside a coach is put back outside (Eject). The host owns it; clients follow the passenger list. */
        BelmonteTrainRules::FAdmission Admission;
        float EjectCooldown = 0.f;
        /** Host or offline: where the rider last stood on foot on walkable ground off the train (feet, world cm), a
         *  recovery candidate (BelmonteTrainRules::ERecovery::LastSafe). */
        FVector LastSafe = FVector::ZeroVector;
        bool bHasLastSafe = false;
        /** The rider's feet in the frame of the coach whose room held them last frame (unadmitted riders only): their
         *  speed in that frame tells a rider from a bystander the coach sweeps through. */
        int32 TrackedVehicle = INDEX_NONE;
        FVector TrackedLocal = FVector::ZeroVector;
        /** That speed (cm/s), smoothed; negative until measured. */
        double TrackedSpeed = -1.;
        float Seated = 0.f;
        /** Where the service last put the seated rider: moved elsewhere (a teleport, a respawn), they are let go. */
        FVector SeatedAt = FVector::ZeroVector;
        /** The capsule's responses before boarding (aboard, only the train holds the rider). */
        FCollisionResponseContainer Responses;
        /** The short train camera's blend (0 outside, 1 inside a coach) and the arm it came from. */
        float Camera = 0.f, SavedArm = -1.f, LastAppliedArm = -1.f;
        /** The scripted step up or down at a door: the path in vehicle cm, the time along it and its length. */
        int32 BoardVehicle = INDEX_NONE, BoardDoor = INDEX_NONE;
        TArray<FVector> BoardPath;
        float BoardTime = 0.f, BoardLength = 0.f;
        bool bBoardUp = true, bBoardMoving = false;
    };
    struct FStation
    {
        FString Key, Name;
        double Chainage = 0.;
        FVector Arrival = FVector::ZeroVector;
        float Yaw = 0.f;
        bool bLeft = true;
        TArray<FBelmonteTrainStop> Stops;
    };
    /** A station's arrival board (BelmonteTrainBoards.cpp): the next train and the one after, counted down in real
     *  minutes from the shared service clock, so every player reads the same. Text changes at most once a second. */
    struct FBoard
    {
        FString Id;
        int32 Station = INDEX_NONE;
        TArray<TObjectPtr<UTextRenderComponent>> Next, After;
        FString Shown[2];
    };
    bool Initialize(const FString& Path);
    void BuildStations(const TSharedPtr<FJsonObject>& Root);
    void BuildBoards(const TSharedPtr<FJsonObject>& Root);
    void UpdateBoards(double Time);
    /** Service seconds per real second: train.TimeScale here, the host's on a client. */
    double ClockScale() const;
    void PlaceVehicles(double Time, bool bForce);
    void UpdateDoors(double Time, float Dt);
    void UpdateRiders(float Dt);
    void Board(FRider& Rider, bool bAboard);
    void SitDown(FRider& Rider, int32 Vehicle, int32 Seat);
    /** Monter / Descendre: opens the door, walks the rider up or down the steps along the door's boarding path, closes
     *  the door. Collision is off and movement held for the move, so it cannot snag or be left halfway. */
    bool StartBoarding(FRider& Rider, int32 Vehicle, int32 Door);
    void UpdateBoarding(FRider& Rider, float Dt);
    void FinishBoarding(FRider& Rider);
    /** The world's ground (WorldStatic: terrain, platform, ballast; never the train) under a world point, within MaxOff cm
     *  of Near (a world z); the nearest such ground in a small ring around it when the point itself has none. */
    bool GroundNear(const FVector& Point, double Near, double MaxOff, const AActor* Ignore, double& Z) const;
    /** Inside a coach, the short train camera; it blends back to the rider's own outside. */
    void UpdateCamera(FRider& Rider, bool bInside, float Dt);
    void StandUp(FRider& Rider);
    /** The vehicle whose interior room (in last frame's vehicle frame, grown by Margin cm) holds Feet, or INDEX_NONE. */
    int32 InteriorAt(const FVector& Feet, const FVector& Margin, bool& bNoSprint, bool& bCamera) const;
    /** Host or offline: puts a player riding inside a coach without the ticket back on safe ground, off any vehicle
     *  (AWandererCharacter::TravelTo stows it and, online, hands the new foot activity to the owner). The destination
     *  follows BelmonteTrainRules::RecoveryOrder and is accepted only by BelmonteTrainRecovery::SafeStand; with none,
     *  the player is not moved (retried a second later). */
    bool Eject(FRider& Rider, int32 Vehicle);
    /** The vehicle a component belongs to (its body, a door box or a leaf), or INDEX_NONE. */
    int32 VehicleOf(const UPrimitiveComponent* Component) const;
    /** One of the train's own parts (never ground to set anyone down on); the station platforms are not. */
    bool IsTrainPart(const UPrimitiveComponent* Component) const;
    /** A vehicle's chainage (m) now and its half length (m). */
    double VehicleChainage(int32 Vehicle) const;
    double VehicleHalfLength(int32 Vehicle) const;
    /** The player is on any vehicle: online the authoritative activity (a remote skater's host capsule follows the
     *  trusted root, not the rendered skater), offline the local components. */
    static bool OnAnyVehicle(const AWandererCharacter* Character, bool bOnline);
    /** Host or offline, about once a second: a verified door-side point beside each train running in the open. */
    void RecordTrainSafe(double Time);
    /** Releases what a rider holds (the seat, the door they walk through) before their entry is dropped. */
    void ReleaseRider(FRider& Rider);
    FRider& RiderFor(AWandererCharacter* Character);
    const FRider* FindRider(const AWandererCharacter* Character) const;
    /** The nearest door handle or free seat within reach: (vehicle, door or seat, true for a seat), or INDEX_NONE. */
    bool Nearest(const AWandererCharacter* Character, int32& Vehicle, int32& Index, bool& bSeat) const;
    void Report(double Time) const;
    FBelmonteTrainLine Line;
    TArray<FVehicle> Vehicles;
    TArray<FRider> Riders;
    TArray<FStation> Stations;
    TArray<FBoard> Boards;
    double NextBoardUpdate = 0.;
    TArray<bool> TrainAtStation;
    /** Per train: the last door-side point verified while it ran in the open (ERecovery::TrainLastSafe). */
    TArray<FVector> TrainSafe;
    TArray<bool> bTrainSafe;
    double NextSafeRecord = 0.;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Bodies;
    UPROPERTY() TArray<TObjectPtr<UInstancedStaticMeshComponent>> Furniture;
    UPROPERTY() TArray<TObjectPtr<UPrimitiveComponent>> Parts;
    /** The vehicles' outer boxes (train_exterior): no climbing onto the train (the actor's NoClimb tag does it today). */
    int32 Exteriors = 0;
    UPROPERTY(ReplicatedUsing=OnRep_NetworkState) FBelmonteTrainNetworkState NetworkState;
    UFUNCTION() void OnRep_NetworkState();
    void PublishNetworkState();
    void CancelLocal(FRider& Rider);
    bool AnyRiderAboard() const;
    bool bInitialized = false, bInitFailed = false;
    double LastNetworkPublication = -1.;
    double DevOffset = 0.;
    double NextReport = 0.;
    float PendingViewDelay = -1.f;
    FString PendingView;
};

/** Live-bridge helpers (atelier live py) for scripted train checks. */
UCLASS()
class YORIMICHI_API UBelmonteTrainLive : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** The service clock, each train (chainage, km/h, at a station), the station boards and the player's rider state,
     *  as JSON. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FString TrainState();
    /** A point on a vehicle of a train in world cm: What = "centre", "door:<id>:<handle index>", "board:<door id>:<path index, -1 last>", "seat:<index>",
     *  "floor:<local x m>". Zero when unknown. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FVector TrainPoint(int32 Train, const FString& Vehicle, const FString& What);
    /** The Interact prompt the player sees now (empty when none). */
    UFUNCTION(BlueprintCallable, Category = "Live") static FString TrainPrompt();
};

/** Editor helpers for import_belmonte_train.py. */
UCLASS()
class YORIMICHI_API UBelmonteTrainImportLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Replaces the mesh's simple collision with these boxes (mesh space, cm) and uses it as complex collision.
     *  Returns the number of boxes, or -1 outside the editor. */
    UFUNCTION(BlueprintCallable, Category = "Yorimichi|Editor")
    static int32 SetSimpleBoxes(UStaticMesh* Mesh, const TArray<FBox>& Boxes);
};

#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "HRTypes.h"
#include "RacingCourse.h"
#include "RacingMotion.h"
#include "RacingService.generated.h"

class AWandererCharacter;
class UAnimSequence;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class USkeletalMesh;
class USkeletalMeshComponent;

/** One runner of the race in focus, as every machine sees it (docs/RACING.md, "Snapshot"). */
USTRUCT()
struct FRacingNetRunner
{
    GENERATED_BODY()
    UPROPERTY() FString Horse;
    UPROPERTY() FString Stable;
    UPROPERTY() FString Jockey;
    /** The stable's colour: the saddle and its cloth. */
    UPROPERTY() FColor Silks = FColor::White;
    /** Win odds for one coin, in tenths (35 = 3.5). */
    UPROPERTY() int32 OddsTenths = 0;
    /** The look: RacingLooks::Breeds index, coat (0 the breed's own, k the roster's coat variant k-1), scale in percent. */
    UPROPERTY() uint8 Breed = 0;
    UPROPERTY() uint8 Coat = 0;
    UPROPERTY() uint8 Scale = 100;
    /** Official place once run (1 = winner), 0 before. */
    UPROPERTY() uint8 Place = 0;
    /** Cumulative time at the end of each of the four stages, milliseconds; empty until the race is run. */
    UPROPERTY() TArray<int32> SplitMs;

    RacingMotion::FPlan Plan(int32 Distance) const;
    bool operator==(const FRacingNetRunner& O) const;
};

/** The race in focus: running, just run (for RaceSeconds after its start) or the next one today. */
USTRUCT()
struct FRacingNetRace
{
    GENERATED_BODY()
    /** The rules' race key for the day ("village:0"), empty when no race is left today. */
    UPROPERTY() FString Key;
    UPROPERTY() FString Name;
    UPROPERTY() uint8 Venue = 0;
    /** 0 the venue's main track, 1 Belmonte's sand track. */
    UPROPERTY() uint8 Track = 0;
    UPROPERTY() int32 Distance = 0;
    /** World second of the start (the rules' clock). */
    UPROPERTY() double Start = 0.;
    UPROPERTY() bool bRun = false;
    UPROPERTY() TArray<FRacingNetRunner> Runners;

    bool operator==(const FRacingNetRace& O) const;
};

/** The last finished race's podium. */
USTRUCT()
struct FRacingNetResult
{
    GENERATED_BODY()
    UPROPERTY() FString Key;
    UPROPERTY() FString Race;
    UPROPERTY() uint8 Venue = 0;
    UPROPERTY() int32 Day = 0;
    /** The first three: horse names and times (ms). */
    UPROPERTY() TArray<FString> Top;
    UPROPERTY() TArray<int32> TimeMs;
    UPROPERTY() double Finished = 0.;

    bool operator==(const FRacingNetResult& O) const { return Key == O.Key && Day == O.Day && Top == O.Top && TimeMs == O.TimeMs; }
};

USTRUCT()
struct FRacingNetStanding
{
    GENERATED_BODY()
    UPROPERTY() FString Stable;
    UPROPERTY() FColor Color = FColor::White;
    UPROPERTY() int32 Wins = 0;
    UPROPERTY() int32 Earnings = 0;

    bool operator==(const FRacingNetStanding& O) const { return Stable == O.Stable && Color == O.Color && Wins == O.Wins && Earnings == O.Earnings; }
};

/**
 * What clients need of the racing world: a compact snapshot the host rebuilds when it changes (Serial). The clock anchor
 * maps the server's world time to the rules' world seconds, so every machine places the runners from the same clock.
 */
USTRUCT()
struct FRacingNetState
{
    GENERATED_BODY()
    UPROPERTY() uint32 Serial = 0;
    /** World second AnchorWorld at server time AnchorServer, running at Scale world seconds per second. */
    UPROPERTY() double AnchorServer = 0.;
    UPROPERTY() double AnchorWorld = 0.;
    UPROPERTY() float Scale = 1.f;
    /** The race day, its event and whether it is a Grand Prix. */
    UPROPERTY() int32 Day = 0;
    UPROPERTY() FString Event;
    UPROPERTY() bool bGrandPrix = false;
    UPROPERTY() FRacingNetRace Race;
    UPROPERTY() FRacingNetResult Last;
    UPROPERTY() TArray<FRacingNetStanding> Standings;
    /** World second of the next race day's first race (when no race is left today). */
    UPROPERTY() double NextMeeting = 0.;

    /** The content (not the clock): what changing makes the host publish a new serial. */
    bool SameContent(const FRacingNetState& O) const;
    /** What the snapshot weighs on the wire: its strings as UTF-8 with a length, its numbers at their size. */
    int32 PayloadBytes() const;
};

/**
 * The racing world in Yorimichi (docs/RACING.md): one replicated service actor. The host (a listen server, or the game
 * offline) owns the rules' FHRWorldState (game plugin HorseRacing): it creates or loads it, advances it on the clock
 * and saves it under Saved/racing/. Clients get FRacingNetState and compute the runners' positions from it, as the
 * train is placed from its timetable. Races alternate between the Hidamari hippodrome and the Belmonte racecourse; while
 * a player is near the venue of the race in focus, the field parades, runs and pulls up there.
 *
 * Dev: `racing.Next [lead s]` jumps the clock to just before the next start, `racing.TimeScale` runs the clock faster,
 * `racing.Go hidamari|belmonte` travels to a venue's stand. Launch flags: -racingseed=, -racingsave=, -racingnext.
 */
UCLASS()
class YORIMICHI_API ARacingService : public AActor
{
    GENERATED_BODY()
public:
    ARacingService();
    static ARacingService* Spawn(UWorld* World);
    static ARacingService* Find(const UObject* WorldContext);
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

    // ------------------------------------------------------------------ the rules' world (host)
    /** Saved/racing/world.json, or -racingsave=. */
    static FString DefaultSavePath();
    /** The world as JSON into Path, atomically: a flushed sibling temporary file renamed over it, so a crash leaves the old
     *  world or the new one, never a partial file. False (Error the reason, Path untouched) when it could not be written. */
    static bool SaveWorldFile(const FHRWorldState& S, const FString& Path, FString& Error);
    static bool SaveWorldFile(const FHRWorldState& S, const FString& Path) { FString Error; return SaveWorldFile(S, Path, Error); }
    enum class ELoad : uint8 { Loaded, Missing, Unreadable, Invalid };
    /** A world saved by SaveWorldFile, admitted by HRSave (Out untouched unless Loaded): Missing (no file), Unreadable (the
     *  file exists but could not be read: left alone) or Invalid (not an admissible world of these rules; Error says why). */
    static ELoad LoadWorldFile(const FString& Path, FHRWorldState& Out, FString& Error);
    static bool LoadWorldFile(const FString& Path, FHRWorldState& Out) { FString Error; return LoadWorldFile(Path, Out, Error) == ELoad::Loaded; }
    /**
     * Loads the world at Path or creates one from Seed (saving it there), and anchors the clock if it never was. An invalid
     * file is first kept aside (Path.unreadable-<time>); when it cannot be moved, or cannot be read at all, it is left as
     * it is, no world opens and this returns false (racing stays off, PersistenceError says why). A failed first save keeps
     * the world open in memory, dirty, and is retried.
     */
    bool OpenWorld(const FString& Path, const FString& Seed);
    bool HasWorld() const { return bHasWorld; }
    const FHRWorldState& GetWorldState() const { return State; }
    /** Writes the world now; false (the world kept in memory, still dirty, PersistenceError set) when it could not. */
    bool SaveNow();
    /** The last open or save failure, empty once a save succeeds. */
    const FString& GetPersistenceError() const { return PersistenceError; }

    /** Ordinary race days alternate between the venues; Grand Prix days are at Belmonte (docs/RACING.md, "Venues"). */
    static ERacingVenue VenueForDay(int32 T);
    /** The snapshot of a world at a world second: the race in focus, the last result (Previous kept when the day has none),
     *  the standings. Pure, so tests and every host build the same one. */
    static void BuildSnapshot(const FHRWorldState& S, double WorldSeconds, const FRacingNetResult& Previous, FRacingNetState& Out,
        TMap<FString, FIntVector>* LookCache = nullptr);
    /** English name of a race ("Lantern Sprint · race 2"). */
    static FString RaceName(const FHRRace& Race);

    // ------------------------------------------------------------------ the clock
    /** The rules' world second now on the host (Unix time, the anchor and the dev offset). */
    double HostWorldSeconds() const;
    /** The shared clock every machine presents with: the replicated anchor on the server's world time. */
    double WorldNow() const;
    /** Jumps the clock to Lead seconds before the next start (host only). */
    bool JumpToNextRace(double Lead = 100.);
    /** Travels the local player to a venue's stand; false without a player or the venue. */
    bool GoToVenue(const FString& Venue);

    // ------------------------------------------------------------------ presentation
    const FRacingNetState& GetNetState() const { return Net; }
    /** The venue's course (Track 1: Belmonte's sand), or nullptr when it is not loaded. */
    const FRacingCourse* GetCourse(ERacingVenue Venue, uint8 Track = 0) const;
    /** The English HUD line inside a venue's grounds, empty elsewhere. */
    FString HudLine(const AWandererCharacter* Pawn) const;
    FString StateJson() const;
    int32 NumRunnersShown() const { return Shown.Num(); }
    /** The racing TVs (ARacingBroadcast) film the race on this machine: the field is shown wherever the player is, and its
     *  poses are evaluated though the main view does not draw it. */
    void SetBroadcastAudience(bool bOn) { bBroadcastAudience = bOn; }
    /** A runner's world position and speed (m/s) at world second Time, as every machine computes it. */
    bool RunnerAt(const FRacingNetRace& Race, int32 Index, double Time, FVector& Where, float& Yaw, double& Speed) const;
    /** Loads the Hidamari oval (from the hippodrome actor) and the Belmonte tracks (Data/racing/belmonte_courses.json, round
     *  the Belmonte region's origin). */
    bool LoadCourses();
    /** Belmonte's courses from belmonte_courses.json text, round OriginCm (tests). */
    bool LoadBelmonteCourses(const FString& Json, const FVector& OriginCm, FString& Error);

private:
    UPROPERTY(ReplicatedUsing=OnRep_Net) FRacingNetState Net;
    UFUNCTION() void OnRep_Net();

    void TickHost(float DeltaSeconds);
    void RegisterPlayers();
    void Publish(bool bForce);
    void TickPresentation(float DeltaSeconds);
    void ClearRunners();
    bool SpawnRunners(const FRacingNetRace& Race);
    bool LoadLooks();
    FVector LocalViewer() const;

    // Host
    FHRWorldState State;
    bool bHasWorld = false, bDirty = false;
    FString SavePath, PersistenceError;
    double DevSeconds = 0., LastSave = 0., NextRegister = 0., NextPublish = 0., NextReport = 0.;
    float AppliedScale = 1.f;
    TSet<FString> Registered;
    FRacingNetResult LastResult;
    TMap<FString, FIntVector> LookCache;

    // Courses
    FRacingCourse Hidamari, BelmonteTurf, BelmonteSand;
    bool bCoursesLoaded = false, bCoursesFileFailed = false;

    // Runners on this machine
    struct FLookBreed
    {
        FString Slug;
        TObjectPtr<USkeletalMesh> Mesh, Saddle;
        float MeshYaw = -90.f;
        /** Saddle root forward and seat height (cm) less the reference breed's, and the seat height itself. */
        float SeatForward = 0.f, SeatUp = 0.f, SeatZ = 160.f;
        /** Idle, Walk, Trot, Canter, Gallop, Sprint. */
        TArray<TObjectPtr<UAnimSequence>> Clips;
    };
    struct FShown
    {
        TObjectPtr<USkeletalMeshComponent> Horse, Saddle, Jockey;
        int32 Breed = 0, Gait = -1;
        double Phase = 0.;
        /** The traced ground's height above the course's authored height (cm), valid while bGround. */
        float GroundOffset = 0.f, NextTrace = 0.f;
        bool bGround = false;
    };
    TArray<FLookBreed> LookBreeds;
    TArray<FString> CoatTextures;
    TArray<TObjectPtr<UAnimSequence>> JockeyClips;
    UPROPERTY() TObjectPtr<USkeletalMesh> JockeyMesh;
    FVector JockeyOffset = FVector::ZeroVector;
    float JockeyYaw = -90.f;
    FVector JockeyScale = FVector::OneVector;
    bool bLooksLoaded = false, bLooksTried = false;
    UPROPERTY() TArray<TObjectPtr<UObject>> Held;
    UPROPERTY() TObjectPtr<UMaterialInterface> SilksMaterial;
    TArray<FShown> Shown;
    FString ShownKey, FailedKey;
    double ShownStart = 0.;
    bool bBroadcastAudience = false;
};

/** Live-bridge helpers (atelier live py) for scripted racing checks. */
UCLASS()
class YORIMICHI_API URacingLive : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** The clock, the race in focus with each runner's position, the last result and the runners shown, as JSON. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FString RacingState();
    /** racing.Next: jumps to Lead seconds before the next start. */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool RacingNext(float Lead);
    /** Travels to "hidamari" or "belmonte". */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool RacingGo(const FString& Venue);
    /** A point beside the race in focus to watch from (world cm), and the yaw facing the track. Zero when none. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FVector RacingViewPoint(float Along, float Outwards, float& Yaw);
    /** The racing TVs (ARacingBroadcast::StateJson): the screens, the capture, the shot and the frame times, as JSON. */
    UFUNCTION(BlueprintCallable, Category = "Live") static FString RacingTvState();
    /** racing.Tv: travels to a TV's watch point ("osteria_front", "osteria_back", "salon_paris", "salon_bar"). */
    UFUNCTION(BlueprintCallable, Category = "Live") static bool RacingTvGo(const FString& Spot);
};

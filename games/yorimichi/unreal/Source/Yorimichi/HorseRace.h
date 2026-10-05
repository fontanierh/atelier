#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "HorseRace.generated.h"

class AHippodrome;
class AHippodromeFigure;
class AWandererCharacter;
class ACameraActor;
class UAudioComponent;
class USoundBase;
class UCanvas;
class AHUD;
class SWidget;

/** A cup: its song and chart (charts.json), its distance and how fast and how good the field is. */
struct FRaceCup
{
    const TCHAR* Key; const TCHAR* Name; const TCHAR* Blurb;
    double Laps;          // from the gate (mid back straight) to the post: x.5 laps
    float Base, Range;    // m/s at no rhythm and the extra a perfect rhythm adds
    float Lookahead;      // seconds a note takes down the highway
    float FieldLo, FieldHi;   // the other riders' rhythm (0..1)
};

/** One note of a chart (assets/audio/hippodrome/make.py): song seconds, lane 0-3, hold seconds. */
struct FRaceNote
{
    double T = 0.; int32 Lane = 0; double Hold = 0.;
    // 0 waiting, 1 hit, 2 missed; a hold is Holding until its end, then 1 (kept) or 3 (dropped).
    int32 State = 0; bool bHolding = false; int32 Grade = -1;
    double Auto = 0.;   // autoplay: seconds off the beat it is pressed (a large value lets it pass)
};

/** A horse and rider in the race: where it is on the course and how its rhythm drives it. */
struct FRaceRunner
{
    FString Horse, Rider, Name, HorseName;
    TWeakObjectPtr<AHippodromeFigure> Figure;
    bool bPlayer = false;
    double Progress = 0.;          // centre-line metres from the gate
    float Offset = 0.f, LateralSpeed = 0.f, Speed = 0.f, Meter = .5f, SpurLeft = 0.f, Yaw = 0.f;
    int32 Combo = 0, BestCombo = 0, Pips = 0, Place = 0;
    double FinishTime = -1.;
    bool bBoxed = false;
    // The others: their rhythm, the next chart note they meet, the lane they keep.
    float Skill = .7f, PreferredOffset = -4.5f, PassOffset = 0.f, PassTimer = 0.f, StrideClock = 0.f;
    bool bCelebrated = false;
    int32 NextNote = 0;
    FName GaitRole;
    FLinearColor Colour = FLinearColor::White;
};

/**
 * Horse races at the Hidamari Hippodrome (docs/HIPPODROME.md). Hudson, the race master by the grandstand, offers three
 * cups; the player picks one and a horse and races five BOTW riders on the oval. The riding is a rhythm game: the cup's
 * song plays and its chart scrolls down a four-lane highway (D F J K, or the face buttons); every note met on the beat
 * lifts the horse's stride (Perfect, Great, Good; a miss drops it), a run of 16 earns a spur (Space or RB) for a burst
 * of speed, and the arrows or the left stick steer: the rail is the short way round, and a horse ahead blocks the lane.
 * The others ride the same chart at their own skill, a little better when they trail and worse when they lead.
 */
UCLASS()
class YORIMICHI_API AHorseRace : public AActor
{
    GENERATED_BODY()
public:
    AHorseRace();
    virtual void Tick(float Dt) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    void Bind(AHippodrome* Venue);
    static AHorseRace* Find(const UObject* WorldContext);

    enum class EPhase : uint8 { Idle, Menu, Parade, Countdown, Running, Finished, Results };
    EPhase GetPhase() const { return Phase; }
    bool IsRacing() const { return Phase >= EPhase::Parade; }

    /** The player's Interact: Hudson's menu when the player stands by him; false otherwise. */
    static bool TryInteract(AWandererCharacter* Player);
    bool CanTalk(const AWandererCharacter* Player) const;
    void OpenMenu(AWandererCharacter* Player);
    void CloseMenu();
    bool IsMenuOpen() const { return Menu.IsValid(); }
    /** Start a race: Cup 0 Maiden, 1 Stakes, 2 Cup; Horse a roster coat (HorsePinto...); AutoAccuracy > 0 lets the game
     *  play the player's notes at that skill (films and QA). */
    bool StartRace(AWandererCharacter* Player, int32 Cup, const FString& Horse, float AutoAccuracy = 0.f);
    void EndRace(const FString& Why);
    /** Draws the race HUD; JapanHUD hands over the whole screen while a race runs. */
    void DrawHud(AHUD* Hud, UCanvas* Canvas, int32 ControllerStyle);
    FString Describe() const;

    static const FRaceCup Cups[3];
    static const TArray<FString>& Horses();
    static FString HorseName(const FString& Horse);

private:
    TWeakObjectPtr<AHippodrome> Venue;
    TWeakObjectPtr<AWandererCharacter> Player;
    EPhase Phase = EPhase::Idle;
    int32 CupIndex = 0;
    FString PlayerHorse = TEXT("HorsePinto");
    float AutoAccuracy = 0.f;
    FRandomStream Dice;

    // The chart, unrolled through the song's loop so a slow race never runs out of notes.
    TArray<FRaceNote> Notes;
    double SongStart = 0., LoopFrom = 0., LoopTo = 0., SongLength = 0., Beat = .5;
    TArray<double> CountIn;
    double Clock = 0.;            // song seconds since the music started (the chart's clock)
    double ClockOrigin = 0.;      // platform seconds at song time 0 (live play)
    bool bFixedClock = false;     // films: the clock follows the fixed frame step
    double RaceStartClock = 0.;   // song time the gate opened
    float PhaseTime = 0.f;
    int32 Loops = 0;
    bool bLooping = true;
    int32 FirstLive = 0;
    bool LaneDown[4] = { false, false, false, false };
    double RaceTime() const { return Clock - RaceStartClock; }

    TArray<FRaceRunner> Runners;
    int32 PlayerIndex = 0;
    int32 Finishers = 0;

    // Judgement feedback.
    FString Judgement; float JudgementTime = 0.f; FLinearColor JudgementColour = FLinearColor::White;
    float LaneFlash[4] = { 0, 0, 0, 0 }; float LaneHit[4] = { 0, 0, 0, 0 };
    int32 Counts[4] = { 0, 0, 0, 0 };     // perfect, great, good, miss
    FString Callout; float CalloutTime = 0.f;
    float EscHeld = 0.f, ResultsHeld = 0.f;
    int32 LastLapShown = 0;
    bool bHomeStretch = false;

    // Camera and sound.
    UPROPERTY() TObjectPtr<ACameraActor> Camera;
    UPROPERTY() TObjectPtr<UAudioComponent> Music;
    UPROPERTY() TObjectPtr<UAudioComponent> Crowd;
    UPROPERTY() TMap<FName, TObjectPtr<USoundBase>> Sounds;   // "HR_Hoof_03", "Music_race_cup"
    TMap<FName, int32> Variants;
    FVector CamEye = FVector::ZeroVector; FRotator CamRot = FRotator::ZeroRotator; float CamFov = 70.f;
    bool bCamInit = false;

    TSharedPtr<SWidget> Menu;
    int32 MenuCup = 0; int32 MenuHorse = 0;

    // Saved results: best time and place per cup (Saved/hippodrome.json).
    TMap<FString, double> BestTime; TMap<FString, int32> BestPlace;
    bool bResultsLoaded = false;
    void LoadResults(); void SaveResults();
    bool HasWon() const;

    bool LoadChart(const FRaceCup& Cup);
    void LoadSounds();
    USoundBase* Cue(const TCHAR* Name, int32 Variant = -1);
    void Play(const TCHAR* CueName, const FVector& At, float Volume, bool b2D, float Pitch = 1.f);
    void StartMusic(double At);

    void AdvanceClock(float Dt);
    void AdvanceRhythm();
    void Judge(int32 Lane, double PressTime);
    void Grade(FRaceRunner& R, int32 Grade);
    void AdvanceOthers();
    void AdvanceRunners(float Dt);
    void PlaceRunner(FRaceRunner& R, float Dt);
    void AdvanceCamera(float Dt);
    void Finish(FRaceRunner& R);
    void ShowResults();
    void Say(const FString& Line, float Seconds = 2.f) { Callout = Line; CalloutTime = Seconds; }
    double Distance() const;
    FVector RunnerPoint(const FRaceRunner& R, float* Yaw = nullptr) const;
    int32 PlaceOf(int32 Index) const;
    void ReadInput(float Dt);
    void Restore();

    // -racefilm: a filmed race on a fixed 60 Hz clock, frames and sounds written for tools/mix_race_film.py.
    struct FFilm;
    TSharedPtr<FFilm> Film;
    void AdvanceFilm(float Dt);
    void FinishFilm();
};

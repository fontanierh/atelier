#pragma once
#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "JapanMusic.generated.h"

class AActor;
class AWandererCharacter;
class UMediaPlayer;
class UMediaSoundComponent;

/** One track of the music library (its catalog.json entry). */
struct FJapanMusicTrack
{
    FString Path, Title, Group, Role, Style;
    float Seconds = 0.f;
};

/** What the local player is doing, as the music rules see it. */
enum class EJapanMusicScene : uint8 { Explore, Skate, Ride, Sail, Air, Combat };

/** The rules: which cues fit a moment. Pure, so tests and the live bridge can ask without a world. */
struct FJapanMusicRules
{
    /** The music area of a map zone key (Content/Data/map/map.json), or "wild" away from every zone. */
    static FString AreaForZone(const FString& Zone);
    /** The pool for a scene in an area: a name (for logs and coherence) and its library groups. Zone groups
     *  (the library's per-zone score) take only their calm day and quiet takes unless the pool asks for all. */
    static FString PoolName(EJapanMusicScene Scene, const FString& Area);
    static TArray<FString> PoolGroups(const FString& Pool, const FString& Zone);
    static bool TakesRole(const FString& Pool, const FString& Group, const FString& Role);
    /** How loud a pool plays against the game's sound effects (before the player's music volume). */
    static float Level(const FString& Pool);
};

/** The soundtrack (docs/MUSIC.md, "Runtime"). The library is not packaged: `atelier playtest` clones the verified
 *  music cache into the app's container and passes -music=DIR; development play reads the Atelier cache directly.
 *  Without a library the game is silent as before.
 *
 *  Music is presentation for this client only: nothing is replicated and nothing waits on it. Two media channels
 *  crossfade with an equal-power curve; a track never cuts in or out. Exploration plays a track, rests in silence and
 *  then picks again for wherever the player is; skating rests less. Combat cuts the rest short and crossfades in
 *  quickly, then fades back out a few seconds after the last enemy lets go. */
UCLASS()
class YORIMICHI_API UJapanMusic : public UTickableWorldSubsystem
{
    GENERATED_BODY()
public:
    virtual void OnWorldBeginPlay(UWorld& InWorld) override;
    virtual void Deinitialize() override;
    virtual void Tick(float DeltaTime) override;
    virtual TStatId GetStatId() const override;
    virtual bool IsTickable() const override { return bStarted; }
    // Fades finish under the pause menu (the media sound is a UI sound and keeps playing).
    virtual bool IsTickableWhenPaused() const override { return true; }
    /** The menu's Music toggle and volume (0..1). Turning music off fades it out; on again starts after a short rest. */
    void SetPreferences(bool bEnabled, float Volume);
    bool HasLibrary() const { return Tracks.Num() > 0; }
    const FString& GetLibraryDir() const { return LibraryDir; }
    /** One line for logs and the live bridge: the pool, the playing track and the rest. */
    FString Describe() const;
    /** The library folder this launch uses (-music=DIR, else the development cache), or empty. */
    static FString FindLibrary();
protected:
    virtual bool DoesSupportWorldType(EWorldType::Type Type) const override
    { return Type == EWorldType::Game || Type == EWorldType::PIE; }
private:
    struct FChannel
    {
        int32 Track = INDEX_NONE;
        float Fade = 0.f;          // 0..1 position on the equal-power curve
        float FadeRate = 0.f;      // per second; negative fades out
        float Level = 0.f;         // the pool's level when the track started
        double Started = 0.;
        float PlayFor = 0.f;       // seconds before this track fades out by itself
    };
    bool LoadLibrary(const FString& Dir);
    AWandererCharacter* LocalPawn() const;
    EJapanMusicScene ReadScene(AWandererCharacter* Pawn, FString& Zone) const;
    int32 Choose(const FString& Pool, const FString& Zone);
    bool HasTracks(const FString& Pool, const FString& Zone) const;
    void Start(int32 Track, const FString& Pool, float FadeSeconds);
    void FadeOut(int32 Channel, float Seconds);
    void ApplyGain(int32 Channel);
    bool IsAudible(int32 Channel) const { return Channels[Channel].Track != INDEX_NONE; }
    int32 Active() const;
    void Rest(float Minimum, float Maximum);

    TArray<FJapanMusicTrack> Tracks;
    FString LibraryDir;
    UPROPERTY() TObjectPtr<AActor> Holder;
    UPROPERTY() TArray<TObjectPtr<UMediaPlayer>> Players;
    UPROPERTY() TArray<TObjectPtr<UMediaSoundComponent>> Sounds;
    FChannel Channels[2];
    bool bStarted = false, bEnabled = true;
    float Volume = .6f;
    int32 Failures = 0;
    double Clock = 0., NextDecision = 0., RestUntil = 0., SceneSince = 0., LastCombat = -1000., SilentSince = 0.;
    FString Pool, PendingPool, LastStyle, Zone;
    TArray<int32> Recent;
    FRandomStream Random;
};

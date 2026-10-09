#pragma once
#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "SkateSettings.generated.h"
struct FHitResult;

/** What the board rolls on. Each surface picks one of the native session's authored ground profiles (how fast it
 *  coasts, brakes, grips and wobbles) and its own roll sound (roll_<surface>_01 in SoundFolder, else roll_01). */
UENUM(BlueprintType)
enum class ESkateSurface : uint8
{
    None = 0 UMETA(Hidden),
    /** Smooth: park concrete, plaster, tiles. The default. */
    Concrete = 1,
    /** Smooth, a hollow roll: ramps, decks, planks. */
    Wood,
    /** Smooth, a ringing roll: plates, grates. */
    Metal,
    /** Rough: a little more drag and a grainier roll. */
    Asphalt,
    /** Rough: flagstones, cobbles, rock. */
    Stone,
    /** Slow: packed earth, gravel, mud. Coasting dies within a few metres. */
    Dirt,
    /** Very slow: grass, sand. The board barely rolls. */
    Grass,
    Sand
};

/** What skateboarding needs from the game, set in its DefaultGame.ini under [/Script/AtelierSkate.SkateSettings]. */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Atelier Skate"))
class ATELIERSKATE_API USkateSettings : public UDeveloperSettings
{
    GENERATED_BODY()
public:
    USkateSettings();
    /** Typed motion (USkateMotionData) and runtime data (USkateRuntimeData) the session loads; skating needs both. */
    UPROPERTY(Config, EditAnywhere, Category="Skate") FSoftObjectPath MotionData;
    UPROPERTY(Config, EditAnywhere, Category="Skate") FSoftObjectPath RuntimeData;
    /** Controller preset: easy, normal or hardcore. */
    UPROPERTY(Config, EditAnywhere, Category = "Skate") FString Difficulty = TEXT("normal");
    /** 0 loose / 1 tight; feeds the steering scalar. */
    UPROPERTY(Config, EditAnywhere, Category = "Skate", meta=(ClampMin="0", ClampMax="1")) float TruckTightness = .5f;
    /** Multiplier on the jump-height presets (1 is stock). */
    UPROPERTY(Config, EditAnywhere, Category = "Skate", meta=(ClampMin="0.5", ClampMax="2")) float PopHeightScale = 1.f;
    /** Multiplier on the air-spin target (1 is stock). */
    UPROPERTY(Config, EditAnywhere, Category = "Skate", meta=(ClampMin="0.5", ClampMax="3")) float AirSpinScale = 1.f;
    /** Multipliers on the native animation-timed push target and planted-foot propulsion. */
    UPROPERTY(Config, EditAnywhere, Category = "Skate", meta=(ClampMin="0.5", ClampMax="2")) float PushSpeedScale = 1.f;
    UPROPERTY(Config, EditAnywhere, Category = "Skate", meta=(ClampMin="0.5", ClampMax="3")) float PushPowerScale = 1.f;
    /** How far short of vertical a quarter pipe still sends a straight air back down into it: 0 is stock (vertical
     *  walls only), 1 reaches lips of about 50 degrees. The transfer input always leaves the ramp. */
    UPROPERTY(Config, EditAnywhere, Category = "Skate", meta=(ClampMin="0", ClampMax="1")) float VertAssist = 0.f;
    /** Also read a hardflip or inward heelflip flicked close to straight down then up, as newer skate games do, beside
     *  the authored wide arc. Off is stock. */
    UPROPERTY(Config, EditAnywhere, Category = "Skate") bool bTightFlicks = false;
    /** Read the trick stick at 120 Hz, from a controller thread, instead of once per 60 Hz tick (README, "120 Hz
     *  flicks"). Off is stock. */
    UPROPERTY(Config, EditAnywhere, Category = "Skate") bool bFlick120Hz = false;
    /** The board parts (the board contract in the plugin README: deck top 9.05 cm above the ground, X nose). */
    UPROPERTY(Config, EditAnywhere, Category = "Skate") FSoftObjectPath DeckMesh;
    UPROPERTY(Config, EditAnywhere, Category = "Skate") FSoftObjectPath TruckMesh;
    UPROPERTY(Config, EditAnywhere, Category = "Skate") FSoftObjectPath WheelMesh;
    /** A masked material for the board's parts with a scalar parameter Dissolve (0 whole, 1 gone): the Ride backend
     *  dissolves the board in and out with it (RIDE.md, "Transitions"). Without one the board shows and hides. */
    UPROPERTY(Config, EditAnywhere, Category = "Skate") FSoftObjectPath BoardDissolveMaterial;
    /** Content folder of the board sounds: loops roll_01, grind_01, slide_01, skid_01, scrape_01 and one-shot banks
     *  <cue>_01.. (pop, land, ...). */
    UPROPERTY(Config, EditAnywhere, Category = "Skate") FString SoundFolder;
    /** Body hitting the ground in a bail (the "fall" cue). */
    UPROPERTY(Config, EditAnywhere, Category = "Skate") TArray<FSoftObjectPath> FallSounds;

    /** What each colliding triangle rides like, first match wins: an actor or component tag SkateSurface.<Surface>
     *  (SkateSurface.Wood), the static mesh's name in SurfaceMeshes, the triangle's material in SurfaceMaterials, then
     *  DefaultSurface. Names drop a leading SM_, MI_ or M_ (MI_Road is Road). */
    UPROPERTY(Config, EditAnywhere, Category = "Surfaces") TMap<FString, ESkateSurface> SurfaceMeshes;
    UPROPERTY(Config, EditAnywhere, Category = "Surfaces") TMap<FString, ESkateSurface> SurfaceMaterials;
    UPROPERTY(Config, EditAnywhere, Category = "Surfaces") ESkateSurface DefaultSurface = ESkateSurface::Concrete;
    /** The surface a hit is on, by the same rules (for others on the same ground: Cairo's bike). The material needs a
     *  trace with bTraceComplex and bReturnFaceIndex; without a face only tags, the mesh and DefaultSurface count. */
    static ESkateSurface SurfaceAt(const FHitResult& Hit);
};

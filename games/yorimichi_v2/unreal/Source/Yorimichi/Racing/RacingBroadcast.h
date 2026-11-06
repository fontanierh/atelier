#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RacingMotion.h"
#include "RacingBroadcast.generated.h"

class ARacingService;
class UCanvas;
class UMaterialInstanceDynamic;
class UProceduralMeshComponent;
class USceneCaptureComponent2D;
class UTextureRenderTarget2D;
struct FRacingNetRace;
struct FRacingNetState;
struct FRacingCourse;

/**
 * The racing TVs' pure parts (docs/RACING.md, "TVs"): where the screens hang and what the broadcast camera films. The
 * camera is a function of the replicated race and the shared clock only, so every player sees the same shot at the
 * same moment.
 */
namespace RacingTv
{
    /** A wall screen, from Haras Valley's Data/tv_spots.json. Its pivot is on the wall plane at the screen's centre, in
     *  Belmonte-local Unreal cm (Haras Valley's frame is the region's: world = region origin + pivot); it faces Yaw. */
    struct FSpot
    {
        const TCHAR* Id;
        FVector Pivot;
        float Yaw;
        /** Where a viewer stands to watch it (on the floor), and the yaw facing the screen. */
        FVector Watch;
        float WatchYaw;
        /** The screen's size over Haras Valley's 70-inch one (PictureWidth x PictureHeight). */
        float Scale;
    };
    /** The Salon des Paris (two) and the osteria's taproom (two). */
    YORIMICHI_API TConstArrayView<FSpot> Spots();
    /** Parse the building-derived TV spots from Belmonte's runtime.json ('tv_spots'); false when absent or invalid. */
    YORIMICHI_API bool ParseSpots(const FString& RuntimeJson, TArray<FSpot>& Out, FString* OutError = nullptr);
    /** Load and validate the building-derived TV spots from a runtime.json file path; logs and returns false on error. */
    YORIMICHI_API bool LoadSpots(const FString& Path, TArray<FSpot>& Out, FString* OutError = nullptr);
    YORIMICHI_API int32 FindSpot(const FString& Id, TConstArrayView<FSpot> InSpots = {});
    /** Haras Valley's 70-inch screen: the picture (cm), the frame round it, and how far the picture stands off the wall;
     *  each spot scales it. */
    inline constexpr double PictureWidth = 155., PictureHeight = 87.2, FrameWidth = 159.4, FrameHeight = 91.6, PictureFront = 11.2;
    /** The screen's transform: at the region origin plus the pivot, facing its yaw, at its scale. */
    YORIMICHI_API FTransform SpotTransform(const FSpot& Spot, const FVector& OriginCm);
    YORIMICHI_API FVector ScreenCentre(const FSpot& Spot, const FVector& OriginCm);

    /** The broadcast starts WindowSeconds before the off, when the field already stands lined up at the start
     *  (RacingMotion::LineupSeconds), and ends with the race's focus (HRClock::RaceSeconds after the start). */
    inline constexpr double WindowSeconds = 120.;
    static_assert(WindowSeconds <= RacingMotion::LineupSeconds, "The TVs never show the field walking to the start");

    /** The broadcast's shots. Before the off the director cuts between the whole course from above, the stand, the crowd
     *  in it and the field lined up at the start; then the start, the race from trackside cameras with a view from above
     *  in two of its stages, head-on down the home straight, the line and the field pulling up. */
    enum class EShot : uint8 { None, Course, Stands, Crowd, Lineup, Start, Travelling, Aerial, Face, Line, Finish };
    YORIMICHI_API const TCHAR* ShotName(EShot Shot);
    /** The shot T seconds after the start: LeaderRun metres run by the leader of Distance, FirstHome/LastHome the
     *  winner's and the last runner's finishing times (0 when not run), bStraight whether the leader is on the straight to
     *  the post. */
    YORIMICHI_API EShot ChooseShot(double T, double LeaderRun, double Distance, double FirstHome, double LastHome, bool bStraight);

    /** Where a venue's stand is along its course: its centre at S metres from the post, Out metres outwards, Half its
     *  half-length along the track, Height its top over the track. */
    struct FVenueShots
    {
        double StandS, StandOut, StandHalf, StandHeight;
    };
    YORIMICHI_API const FVenueShots& VenueShots(uint8 Venue);
    /** Which of the three crowd cameras along the stand frames the most players (Players: their pawns' positions, the
     *  same on every machine), the middle one when none is there. */
    YORIMICHI_API int32 CrowdCamera(const FRacingCourse& Course, const FVenueShots& Venue, TConstArrayView<FVector> Players);

    struct FCamera
    {
        EShot Shot = EShot::None;
        FVector Eye = FVector::ZeroVector, Aim = FVector::ZeroVector;
        /** Horizontal field of view, degrees. */
        float Fov = 40.f;
    };
    /** The camera for the race in focus at world second Now, with the players' pawns for the crowd shot; false when the
     *  race or its course is missing. */
    YORIMICHI_API bool Direct(const ARacingService& Service, const FRacingNetRace& Race, double Now, TConstArrayView<FVector> Players, FCamera& Out);
    /** The horizontal field of view that keeps Points within Fraction of the frame (16:9) seen from Eye towards Aim. */
    YORIMICHI_API float FitFov(const FVector& Eye, const FVector& Aim, TConstArrayView<FVector> Points, float Fraction, float MinFov, float MaxFov);
}

/**
 * The racing TVs (docs/RACING.md, "TVs"): four wall screens in Belmonte, two in the osteria's taproom and two in the Salon
 * des Paris, showing the race in focus live and an idle card between races. Presentation only, on every machine that
 * draws (never a dedicated server), from ARacingService's replicated snapshot: nothing of its own is replicated.
 *
 * One scene capture films for every screen into a 480x270 film ten times a second, and only while the
 * local player is near a screen, in front of it and looking at it during a race's window; the film and the race's
 * lower third are drawn into the screens' 640x360 picture. Otherwise nothing is captured: the screens show the idle card, redrawn once a second while someone
 * is near. While the capture runs it asks the service to show the field wherever the race is (Hidamari is far from
 * Belmonte), so the camera always has horses to film.
 *
 * Dev: `racing.Tv [spot]` travels to a screen's watch point, `racing.TvCapture 0` keeps the capture off (to measure it),
 * `racing.TvHz` sets its rate.
 */
UCLASS()
class YORIMICHI_API ARacingBroadcast : public AActor
{
    GENERATED_BODY()
public:
    ARacingBroadcast();
    static ARacingBroadcast* Spawn(UWorld* World);
    static ARacingBroadcast* Find(const UObject* WorldContext);
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;

    /** Travels the local player to a screen's watch point (an id from RacingTv::Spots, default the first). */
    bool GoToScreen(const FString& Id);
    /** Live state for scripted checks: the screens, whether the capture runs, the shot and the frame times. */
    FString StateJson() const;
    bool IsLive() const { return bLive; }

private:
    bool Build();
    void SetLive(bool bOn);
    void Capture(const ARacingService& Service, double Now);
    void DrawIdle(const FRacingNetState& Net, double Now);
    void DrawLowerThird(UCanvas* Canvas, const FRacingNetState& Net, double Now) const;

    UPROPERTY(Transient) TArray<TObjectPtr<UProceduralMeshComponent>> Screens;
    UPROPERTY(Transient) TObjectPtr<USceneCaptureComponent2D> Camera;
    /** What the screens show (640x360: the film and the graphics over it), and the camera's film (480x270). */
    UPROPERTY(Transient) TObjectPtr<UTextureRenderTarget2D> Picture;
    UPROPERTY(Transient) TObjectPtr<UTextureRenderTarget2D> Film;
    UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> ScreenMaterial;
    UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> FrameMaterial;
    UPROPERTY() TObjectPtr<UMaterialInterface> PictureBase;
    UPROPERTY() TObjectPtr<UMaterialInterface> FrameBase;
    TArray<FVector> Centres, Normals;
    bool bBuilt = false, bLive = false;
    /** The nearest screen (index) and the local viewer's distance to it, metres. */
    int32 Nearest = INDEX_NONE;
    float NearestM = 1e9f;
    double NextCapture = 0., NextIdle = 0., NextPoll = 0.;
    RacingTv::EShot Shot = RacingTv::EShot::None;
    /** Pictures taken, idle cards drawn, and pictures skipped because no screen near the player was on screen. */
    int32 Captures = 0, IdleDraws = 0, Skipped = 0;
    /** Smoothed game-thread frame and GPU times (ms), for the live check. */
    float FrameMs = 0.f, GpuMs = 0.f;
};

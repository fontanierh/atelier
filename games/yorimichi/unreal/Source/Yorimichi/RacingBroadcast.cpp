#include "RacingBroadcast.h"
#include "AtelierData.h"
#include "BelmonteRegion.h"
#include "HRClock.h"
#include "LiveLibrary.h"
#include "RacingService.h"
#include "WandererCharacter.h"
#include "CanvasItem.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerState.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/KismetRenderingLibrary.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/FileHelper.h"
#include "ProceduralMeshComponent.h"
#include "RenderUtils.h"
#include "RHI.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/ConstructorHelpers.h"

static TAutoConsoleVariable<int32> CVarRacingTvCapture(TEXT("racing.TvCapture"), 1,
    TEXT("1: the racing TVs film the race while a player watches them; 0: never (the idle card only; to measure the capture)."));
static TAutoConsoleVariable<float> CVarRacingTvHz(TEXT("racing.TvHz"), 10.f,
    TEXT("How many pictures a second the racing TVs' capture takes while it runs."));

static FAutoConsoleCommandWithWorldAndArgs RacingTvCommand(TEXT("racing.Tv"),
    TEXT("racing.Tv [osteria_front|osteria_back|salon_paris|salon_bar]: travel to a racing TV's watch point."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
    {
        if (auto* Broadcast = ARacingBroadcast::Find(World)) Broadcast->GoToScreen(Args.Num() ? Args[0] : FString());
    }));

// ------------------------------------------------------------------------------------------------------------ pure parts

namespace RacingTv
{
    // Haras Valley's Data/tv_spots.json (Belmonte-local cm): the Salon's two screens 2.40 and 2.75 m over the hall floor,
    // the taproom's front (door) wall and back wall screens 2.30 m over its floor. Haras Valley's frame is the region's:
    // the osteria's watch point (-3040, -160) is the map stop at plan (-30.4, 1.6) metres.
    // Haras Valley's 70-inch screens were too small to read across a room: 1.4 times as large (2.17 m of picture), on the
    // same walls. The Salon's bar screen is 1.3 times and 15 cm higher, so its bottom stays over the mirror's brass frame
    // (2.21 m); the taproom's front screen still clears the door's reveal and the window's.
    const TCHAR* const SpotIds[] = {
        TEXT("osteria_front"), TEXT("osteria_back"), TEXT("salon_paris"), TEXT("salon_bar")
    };

    bool ParseSpots(const FString& RuntimeJson, TArray<FSpot>& Out, FString* OutError)
    {
        Out.Reset();
        auto Fail = [&](const FString& Why) { if (OutError) *OutError = Why; return false; };
        TSharedPtr<FJsonObject> Root;
        const TArray<TSharedPtr<FJsonValue>>* Rows = nullptr;
        if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(RuntimeJson), Root) || !Root)
            return Fail(TEXT("invalid JSON"));
        if (!Root->TryGetArrayField(TEXT("tv_spots"), Rows) || !Rows || Rows->Num() != UE_ARRAY_COUNT(SpotIds))
            return Fail(TEXT("missing or incomplete tv_spots"));
        auto Vec3 = [](const TSharedPtr<FJsonObject>& Obj, const TCHAR* Key, FVector& V)
        {
            const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
            if (!Obj->TryGetArrayField(Key, Arr) || Arr->Num() != 3) return false;
            V = FVector((*Arr)[0]->AsNumber(), (*Arr)[1]->AsNumber(), (*Arr)[2]->AsNumber());
            return V.ContainsNaN() == false;
        };
        TArray<FSpot> Parsed;
        for (int32 I = 0; I < UE_ARRAY_COUNT(SpotIds); ++I)
        {
            const TSharedPtr<FJsonObject>* Item = nullptr;
            FString Id;
            double Yaw = 0., WatchYaw = 0., Scale = 0.;
            FSpot S{SpotIds[I], FVector::ZeroVector, 0.f, FVector::ZeroVector, 0.f, 1.f};
            if (!(*Rows)[I]->TryGetObject(Item) || !(*Item)->TryGetStringField(TEXT("id"), Id) || Id != S.Id ||
                !Vec3(*Item, TEXT("pivot_cm"), S.Pivot) || !Vec3(*Item, TEXT("watch_cm"), S.Watch) ||
                !(*Item)->TryGetNumberField(TEXT("yaw"), Yaw) || !(*Item)->TryGetNumberField(TEXT("watch_yaw"), WatchYaw) ||
                !(*Item)->TryGetNumberField(TEXT("scale"), Scale) || !FMath::IsFinite(Yaw) || !FMath::IsFinite(WatchYaw) ||
                !FMath::IsFinite(Scale) || Scale <= 0.)
                return Fail(FString::Printf(TEXT("invalid spot %s"), S.Id));
            S.Yaw = float(Yaw);
            S.WatchYaw = float(WatchYaw);
            S.Scale = float(Scale);
            Parsed.Add(S);
        }
        Out = MoveTemp(Parsed);
        return true;
    }

    bool LoadSpots(const FString& Path, TArray<FSpot>& Out, FString* OutError)
    {
        Out.Reset();
        FString Json;
        if (!FFileHelper::LoadFileToString(Json, *Path))
        {
            const FString Why = FString::Printf(TEXT("cannot read %s"), *Path);
            if (OutError) *OutError = Why;
            UE_LOG(LogTemp, Warning, TEXT("RACING TV placements unavailable: %s"), *Why);
            return false;
        }
        FString Why;
        if (!ParseSpots(Json, Out, &Why))
        {
            if (OutError) *OutError = Why;
            UE_LOG(LogTemp, Warning, TEXT("RACING TV placements invalid in %s: %s"), *Path, *Why);
            return false;
        }
        return true;
    }

    TConstArrayView<FSpot> Spots()
    {
        static TArray<FSpot> Loaded;
        static bool bTried = false;
        if (!bTried)
        {
            bTried = true;
            LoadSpots(AtelierDataPath(TEXT("belmonte/runtime.json")), Loaded);
        }
        return TConstArrayView<FSpot>(Loaded);
    }

    int32 FindSpot(const FString& Id, TConstArrayView<FSpot> InSpots)
    {
        const TConstArrayView<FSpot> All = InSpots.IsEmpty() ? Spots() : InSpots;
        for (int32 I = 0; I < All.Num(); ++I) if (Id == All[I].Id) return I;
        return INDEX_NONE;
    }

    FTransform SpotTransform(const FSpot& Spot, const FVector& OriginCm)
    {
        return FTransform(FRotator(0.f, Spot.Yaw, 0.f), OriginCm + Spot.Pivot, FVector(Spot.Scale));
    }

    FVector ScreenCentre(const FSpot& Spot, const FVector& OriginCm)
    {
        return SpotTransform(Spot, OriginCm).TransformPosition(FVector(PictureFront, 0., 0.));
    }

    const TCHAR* ShotName(EShot Shot)
    {
        switch (Shot)
        {
        case EShot::Course: return TEXT("course");
        case EShot::Stands: return TEXT("stands");
        case EShot::Crowd: return TEXT("crowd");
        case EShot::Lineup: return TEXT("lineup");
        case EShot::Start: return TEXT("start");
        case EShot::Travelling: return TEXT("travelling");
        case EShot::Aerial: return TEXT("aerial");
        case EShot::Face: return TEXT("face");
        case EShot::Line: return TEXT("line");
        case EShot::Finish: return TEXT("finish");
        default: return TEXT("none");
        }
    }

    EShot ChooseShot(double T, double LeaderRun, double Distance, double FirstHome, double LastHome, bool bStraight)
    {
        // Until 15 s before the off, ten seconds a shot: the whole course from above, the stand, the crowd in it, the field
        // lined up at the start.
        if (T < -15.)
        {
            const EShot Cycle[] = {EShot::Course, EShot::Stands, EShot::Crowd, EShot::Lineup};
            const int32 Index = FMath::Max(0, FMath::FloorToInt((T + RacingTv::WindowSeconds) / 10.));
            return Cycle[Index % UE_ARRAY_COUNT(Cycle)];
        }
        // Side-on at the start for the off.
        if (T < 6.) return EShot::Start;
        // All home: wide over the field pulling up, under the results.
        if (LastHome > 0. && T >= LastHome + 4.) return EShot::Finish;
        // The last 70 m and the finish: side-on at the line, held until the last runner is home.
        const double ToGo = Distance - LeaderRun;
        if (ToGo <= 70. || (FirstHome > 0. && T >= FirstHome)) return EShot::Line;
        // The home straight: head-on, a long lens past the post.
        if (bStraight && ToGo <= 400.) return EShot::Face;
        // From above once in the second stage and once in the third: the whole field and the course's shape.
        const double Share = Distance > 0. ? LeaderRun / Distance : 0.;
        if ((Share >= .20 && Share < .30) || (Share >= .52 && Share < .60)) return EShot::Aerial;
        return EShot::Travelling;
    }

    const FVenueShots& VenueShots(uint8 Venue)
    {
        // Hidamari (world/regions/hippodrome/layout.py): the 56 m grandstand 22 m outside the post, 15 m high. Belmonte
        // (Haras Valley's hippodrome): the 150 m stand 30 m before the post, its front 14 m out, its seats rising to 45 m.
        static const FVenueShots Shots[] = {{0., 22., 28., 15.}, {-30., 30., 75., 16.}};
        return Shots[FMath::Clamp(int32(Venue), 0, int32(UE_ARRAY_COUNT(Shots)) - 1)];
    }

    int32 CrowdCamera(const FRacingCourse& Course, const FVenueShots& Venue, TConstArrayView<FVector> Players)
    {
        // Three cameras along the stand; each player counts for the nearest within 45 m (ties: the middle, then the first).
        int32 Count[3] = {0, 0, 0};
        for (const FVector& P : Players)
        {
            int32 Best = INDEX_NONE;
            double BestD = 4500.;
            for (int32 K = 0; K < 3; ++K)
            {
                const double D = FVector::Dist2D(P, Course.At(Venue.StandS + (K - 1) * Venue.StandHalf * .6, Venue.StandOut));
                if (D < BestD) { BestD = D; Best = K; }
            }
            if (Best != INDEX_NONE) ++Count[Best];
        }
        int32 Pick = 1;
        for (const int32 K : {0, 2}) if (Count[K] > Count[Pick]) Pick = K;
        return Pick;
    }

    float FitFov(const FVector& Eye, const FVector& Aim, TConstArrayView<FVector> Points, float Fraction, float MinFov, float MaxFov)
    {
        const FRotator Rot = (Aim - Eye).Rotation();
        double Tan = 0.;
        for (const FVector& P : Points)
        {
            const FVector L = Rot.UnrotateVector(P - Eye);
            if (L.X < 100.) continue;
            // The vertical extent counts at the frame's 16:9 aspect.
            Tan = FMath::Max(Tan, FMath::Max(FMath::Abs(L.Y), FMath::Abs(L.Z) * 16. / 9.) / L.X);
        }
        const double Fov = FMath::RadiansToDegrees(2. * FMath::Atan(Tan / FMath::Max(Fraction, .1f)));
        return FMath::Clamp(float(Fov), MinFov, MaxFov);
    }

    bool Direct(const ARacingService& Service, const FRacingNetRace& Race, double Now, TConstArrayView<FVector> Players, FCamera& Out)
    {
        const FRacingCourse* Course = Service.GetCourse(ERacingVenue(Race.Venue), Race.Track);
        const int32 Count = Race.Runners.Num();
        if (!Course || !Count || Race.Key.IsEmpty() || Race.Distance <= 0) return false;
        const double T = Now - Race.Start;
        TArray<double> Run;
        TArray<FVector> At;
        double Lead = -1e9, FirstHome = 0., LastHome = 0.;
        for (int32 I = 0; I < Count; ++I)
        {
            const RacingMotion::FPlan Plan = Race.Runners[I].Plan(Race.Distance);
            Run.Add(RacingMotion::Distance(Plan, T));
            FVector Where;
            float Yaw = 0.f;
            double Speed = 0.;
            Service.RunnerAt(Race, I, Now, Where, Yaw, Speed);
            At.Add(Where);
            Lead = FMath::Max(Lead, Run.Last());
            if (Plan.IsRun())
            {
                FirstHome = FirstHome > 0. ? FMath::Min(FirstHome, Plan.FinishTime()) : Plan.FinishTime();
                LastHome = FMath::Max(LastHome, Plan.FinishTime());
            }
        }
        const double ToGo = Race.Distance - Lead;
        // On the straight to the post: the running heading every 20 m from the leader to the post stays within 8 degrees
        // of the post's. Once true it stays true, as what is left only shortens.
        bool bStraight = ToGo > 0. && ToGo <= 400.;
        if (bStraight)
        {
            float PostYaw = 0.f, Yaw = 0.f;
            Course->At(0., 0., &PostYaw);
            for (double S = -ToGo; S < 0. && bStraight; S += 20.)
            {
                Course->At(S, 0., &Yaw);
                bStraight = FMath::Abs(FMath::FindDeltaAngleDegrees(Yaw, PostYaw)) < 8.f;
            }
        }
        const FVenueShots& Venue = VenueShots(Race.Venue);
        Out.Shot = ChooseShot(T, Lead, Race.Distance, FirstHome, LastHome, bStraight);
        // The group the camera keeps in frame: the runners within 25 m of the leader (all of them before the start).
        const FVector Body(0., 0., 130.), Head(0., 0., 260.);
        TArray<FVector> Frame;
        FVector Mid = FVector::ZeroVector;
        double MidRun = 0.;
        int32 InGroup = 0;
        for (int32 I = 0; I < Count; ++I)
        {
            if (T >= 0. && Lead - Run[I] > 25.) continue;
            Mid += At[I] + Body;
            MidRun += Run[I];
            ++InGroup;
            Frame.Add(At[I]);
            Frame.Add(At[I] + Head);
        }
        Mid /= FMath::Max(InGroup, 1);
        MidRun /= FMath::Max(InGroup, 1);
        // S is metres from the post; lanes are metres outwards, the infield (negative) is clear of the stands.
        const double MidS = MidRun - Race.Distance, Inner = Course->InnerLane, Centre = (Course->InnerLane + Course->OuterLane) * .5;
        const FVector Up(0., 0., 100.);
        Out.Aim = Mid;
        switch (Out.Shot)
        {
        case EShot::Stands:
        {
            // Across the track from the infield, a little past the stand's middle (clear of the post), the whole stand in frame.
            Out.Eye = Course->At(Venue.StandS + 15., Inner - 8.) + Up * 3.;
            Out.Aim = Course->At(Venue.StandS, Venue.StandOut) + Up * Venue.StandHeight * .45;
            const FVector Ends[] = {Course->At(Venue.StandS - Venue.StandHalf, Venue.StandOut), Course->At(Venue.StandS + Venue.StandHalf, Venue.StandOut),
                Course->At(Venue.StandS, Venue.StandOut) + Up * Venue.StandHeight};
            Out.Fov = FitFov(Out.Eye, Out.Aim, Ends, .95f, 30.f, 80.f);
            break;
        }
        case EShot::Crowd:
        {
            // A tighter look at the part of the stand where players stand.
            const double S = Venue.StandS + (CrowdCamera(*Course, Venue, Players) - 1) * Venue.StandHalf * .6;
            Out.Eye = Course->At(S + 12., Inner - 4.) + Up * 2.5;
            Out.Aim = Course->At(S, Venue.StandOut) + Up * Venue.StandHeight * .3;
            Out.Fov = 30.f;
            break;
        }
        case EShot::Course:
        {
            // High (80 to 150 m) over the infield's far side, looking back at the start and the post: the whole course
            // and the field lined up. It drifts slowly on the race clock, the same on every machine.
            const FVector Middle = Course->Centre(), Start = Course->At(-Race.Distance, 0.);
            const FVector Away = (Middle - Course->At(0., 0.)).GetSafeNormal2D(), Side = FVector::CrossProduct(Away, FVector::UpVector);
            const double High = FMath::Clamp(Course->Lap() * .12, 80., 150.);
            Out.Eye = Middle + Away * (High * 60.) + Side * ((T + WindowSeconds) * 120.) + Up * High;
            Out.Aim = FMath::Lerp(Middle, Start, .35);
            TArray<FVector> Track;
            for (double S = 0.; S < Course->Lap(); S += 25.) Track.Add(Course->At(S, 0.));
            Track.Add(Start);
            Out.Fov = FitFov(Out.Eye, Out.Aim, Track, .95f, 50.f, 90.f);
            break;
        }
        case EShot::Aerial:
            // High and wide over the field: behind it, over the infield, 55 m up, following the leading group.
            Out.Eye = Course->At(MidS - 45., Inner - 30.) + Up * 55.;
            Out.Fov = 42.f;
            break;
        case EShot::Lineup:
            // Head-on, 30 m ahead of the field standing at the start.
            Out.Eye = Course->At(-Race.Distance + 30., Centre) + Up * 2.5;
            Out.Fov = FitFov(Out.Eye, Out.Aim, Frame, .85f, 18.f, 60.f);
            break;
        case EShot::Start:
            Out.Eye = Course->At(-Race.Distance + 6., Inner - 22.) + Up * 4.5;
            Out.Fov = FitFov(Out.Eye, Out.Aim, Frame, .8f, 18.f, 55.f);
            break;
        case EShot::Face:
            Out.Eye = Course->At(35., Centre) + Up * 6.;
            Out.Fov = FitFov(Out.Eye, Out.Aim, Frame, .9f, 4.f, 40.f);
            break;
        case EShot::Line:
            // From the infield 25 m past the post, looking back along the line.
            Out.Eye = Course->At(25., Inner - 12.) + Up * 3.5;
            Out.Aim = Course->At(-4., Centre) + Up * 1.2;
            Out.Fov = 34.f;
            break;
        case EShot::Finish:
            Out.Eye = Course->At(MidS + 40., Inner - 30.) + Up * 10.;
            Out.Fov = FitFov(Out.Eye, Out.Aim, Frame, .7f, 20.f, 60.f);
            break;
        default:
        {
            // Trackside cameras every 120 m on the infield: the field gallops towards one from 100 m, past it, and 20 m
            // on the next one takes over. A camera that kept pace with the field would show it standing still against a
            // sliding ground.
            const double Post = FMath::CeilToDouble((MidS - 20.) / 120.) * 120.;
            Out.Eye = Course->At(Post, Inner - 14.) + Up * 4.5;
            // A long lens on the leading group (20 to 30 degrees), so the horses fill the picture.
            Out.Fov = FitFov(Out.Eye, Out.Aim, Frame, .85f, 20.f, 30.f);
            break;
        }
        }
        return true;
    }
}

// ------------------------------------------------------------------------------------------------------------ drawing

// A named namespace: in a unity build an anonymous one would leak into later files.
namespace RacingTvDraw
{
    constexpr float Width = 640.f, Height = 360.f;
    // High contrast for a screen read from across a room: white and gold on near-black panels.
    const FLinearColor Ink(1.f, 1.f, 1.f), Gold(1.f, .78f, .3f), Dim(.72f, .76f, .72f), Panel(.004f, .008f, .006f, .97f), Live(.75f, .03f, .02f);

    void Box(UCanvas* Canvas, float X, float Y, float W, float H, const FLinearColor& Colour)
    {
        FCanvasTileItem Tile(FVector2D(X, Y), GWhiteTexture, FVector2D(W, H), Colour);
        Tile.BlendMode = Colour.A < 1.f ? SE_BLEND_Translucent : SE_BLEND_Opaque;
        Canvas->DrawItem(Tile);
    }

    UFont* Font() { return GEngine->GetLargeFont(); }

    /** The scale that draws the font Px picture pixels tall (cap to descender). */
    float ScaleFor(UCanvas* Canvas, float Px)
    {
        float W = 0.f, H = 0.f;
        Canvas->StrLen(Font(), TEXT("Ag"), W, H);
        return Px / FMath::Max(H, 1.f);
    }

    /** Text Px pixels tall at (X, Y); Align 0 left, 1 centred, 2 right-aligned on X. Returns its width. */
    float Text(UCanvas* Canvas, const FString& S, float X, float Y, float Px, const FLinearColor& Colour, int32 Align = 0)
    {
        const float Scale = ScaleFor(Canvas, Px);
        float W = 0.f, H = 0.f;
        Canvas->StrLen(Font(), S, W, H);
        W *= Scale;
        if (Align) X -= W * (Align == 1 ? .5f : 1.f);
        FCanvasTextItem Item(FVector2D(X, Y), FText::FromString(S), Font(), Colour);
        Item.Scale = FVector2D(Scale);
        Item.EnableShadow(FLinearColor(0.f, 0.f, 0.f, .9f), FVector2D(1.5f, 1.5f));
        Canvas->DrawItem(Item);
        return W;
    }

    /** A saddle-cloth square in the stable's colour. */
    void Silks(UCanvas* Canvas, float X, float Y, float Size, const FColor& Colour)
    {
        Box(Canvas, X - 2.f, Y - 2.f, Size + 4.f, Size + 4.f, FLinearColor(1.f, 1.f, 1.f, .9f));
        Box(Canvas, X, Y, Size, Size, FLinearColor(Colour));
    }

    /** The event's name without the round ("Cedar Bend · race 2" -> "Cedar Bend"). */
    FString Short(const FString& Name)
    {
        FString Left, Right;
        return Name.Split(TEXT(" · "), &Left, &Right) ? Left : Name;
    }

    FString Countdown(double Seconds)
    {
        Seconds = FMath::Max(0., Seconds);
        if (Seconds < 60.) return FString::Printf(TEXT("%d s"), FMath::CeilToInt(Seconds));
        if (Seconds < 3600.) return FString::Printf(TEXT("%d min"), FMath::CeilToInt(Seconds / 60.));
        return FString::Printf(TEXT("%d h %02d"), int32(Seconds / 3600.), int32(FMath::Fmod(Seconds, 3600.) / 60.));
    }

    const TCHAR* VenueName(uint8 Venue) { return ERacingVenue(Venue) == ERacingVenue::Belmonte ? TEXT("Belmonte") : TEXT("Hidamari"); }
}

// ------------------------------------------------------------------------------------------------------------ actor

ARacingBroadcast::ARacingBroadcast()
{
    PrimaryActorTick.bCanEverTick = true;
    // After the service has moved the runners and their poses are evaluated.
    PrimaryActorTick.TickGroup = TG_PostUpdateWork;
    bReplicates = false;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    // The frame: the basic shape material in near black (cooked engine content). The picture's material is the game's
    // (unreal.racing_tv), loaded when the screens are built.
    static ConstructorHelpers::FObjectFinder<UMaterialInterface> Basic(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
    FrameBase = Basic.Object;
}

ARacingBroadcast* ARacingBroadcast::Spawn(UWorld* World)
{
    if (!World || World->GetNetMode() == NM_DedicatedServer) return nullptr;
    if (ARacingBroadcast* Existing = Find(World)) return Existing;
    return World->SpawnActor<ARacingBroadcast>();
}

ARacingBroadcast* ARacingBroadcast::Find(const UObject* WorldContext)
{
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World) return nullptr;
    TActorIterator<ARacingBroadcast> It(World);
    return It ? *It : nullptr;
}

void ARacingBroadcast::BeginPlay()
{
    Super::BeginPlay();
    Build();
}

void ARacingBroadcast::EndPlay(const EEndPlayReason::Type Reason)
{
    if (ARacingService* Service = ARacingService::Find(this)) Service->SetBroadcastAudience(false);
    Super::EndPlay(Reason);
}

bool ARacingBroadcast::Build()
{
    if (bBuilt) return true;
    TActorIterator<ABelmonteRegion> It(GetWorld());
    const ABelmonteRegion* Region = It ? *It : nullptr;
    if (!Region || !FrameBase) return false;
    if (!PictureBase) PictureBase = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Racing/M_RacingTv.M_RacingTv"));
    if (!PictureBase)
    {
        UE_LOG(LogTemp, Warning, TEXT("RACING TV no picture material /Game/Racing/M_RacingTv (build unreal.belmonte): no screens"));
        bBuilt = true;
        return true;
    }
    const TConstArrayView<RacingTv::FSpot> LoadedSpots = RacingTv::Spots();
    if (LoadedSpots.IsEmpty())
    {
        UE_LOG(LogTemp, Warning, TEXT("RACING TV no valid tv_spots in belmonte/runtime.json (run world.belmonte + data.stage): no screens"));
        bBuilt = true;
        return true;
    }
    const FVector Origin = Region->GetActorLocation();

    Picture = NewObject<UTextureRenderTarget2D>(this, TEXT("RacingTvPicture"));
    Picture->ClearColor = FLinearColor::Black;
    Picture->InitCustomFormat(int32(RacingTvDraw::Width), int32(RacingTvDraw::Height), PF_B8G8R8A8, false);
    Picture->UpdateResourceImmediate(true);
    // The camera films at 480x270; the graphics are drawn at the picture's 640x360, so the text stays sharp.
    Film = NewObject<UTextureRenderTarget2D>(this, TEXT("RacingTvFilm"));
    Film->ClearColor = FLinearColor::Black;
    Film->InitCustomFormat(480, 270, PF_B8G8R8A8, false);
    Film->UpdateResourceImmediate(true);
    ScreenMaterial = UMaterialInstanceDynamic::Create(PictureBase, this);
    ScreenMaterial->SetTextureParameterValue(TEXT("Picture"), Picture);
    FrameMaterial = UMaterialInstanceDynamic::Create(FrameBase, this);
    FrameMaterial->SetVectorParameterValue(TEXT("Color"), FLinearColor(.012f, .012f, .014f));

    // The screen in its own frame (cm): the wall plane at X 0, the front +X; the frame a box, the picture just in front.
    TArray<FVector> FV, PV;
    TArray<int32> FT, PT;
    TArray<FVector> FN, PN;
    TArray<FVector2D> FU, PU;
    auto Quad = [](TArray<FVector>& V, TArray<int32>& T, TArray<FVector>& N, TArray<FVector2D>& U, const FVector (&P)[4], const FVector& Normal)
    {
        const int32 B = V.Num();
        const FVector2D UV[4] = {{0., 0.}, {1., 0.}, {1., 1.}, {0., 1.}};
        for (int32 I = 0; I < 4; ++I) { V.Add(P[I]); N.Add(Normal); U.Add(UV[I]); }
        // The corners go clockwise seen from the front; a procedural mesh shows the side they turn anticlockwise from.
        T.Append({B, B + 2, B + 1, B, B + 3, B + 2});
    };
    const double X0 = .6, X1 = 11., FY = RacingTv::FrameWidth * .5, FZ = RacingTv::FrameHeight * .5;
    const double PX = RacingTv::PictureFront, PY = RacingTv::PictureWidth * .5, PZ = RacingTv::PictureHeight * .5;
    Quad(FV, FT, FN, FU, {{X1, FY, FZ}, {X1, -FY, FZ}, {X1, -FY, -FZ}, {X1, FY, -FZ}}, FVector::ForwardVector);
    Quad(FV, FT, FN, FU, {{X0, FY, FZ}, {X1, FY, FZ}, {X1, FY, -FZ}, {X0, FY, -FZ}}, FVector::RightVector);
    Quad(FV, FT, FN, FU, {{X1, -FY, FZ}, {X0, -FY, FZ}, {X0, -FY, -FZ}, {X1, -FY, -FZ}}, -FVector::RightVector);
    Quad(FV, FT, FN, FU, {{X0, FY, FZ}, {X0, -FY, FZ}, {X1, -FY, FZ}, {X1, FY, FZ}}, FVector::UpVector);
    Quad(FV, FT, FN, FU, {{X1, FY, -FZ}, {X1, -FY, -FZ}, {X0, -FY, -FZ}, {X0, FY, -FZ}}, -FVector::UpVector);
    // Seen from the front (looking along -X) the viewer's right is -Y: u runs from +Y to -Y, v from the top down.
    Quad(PV, PT, PN, PU, {{PX, PY, PZ}, {PX, -PY, PZ}, {PX, -PY, -PZ}, {PX, PY, -PZ}}, FVector::ForwardVector);

    for (const RacingTv::FSpot& Spot : LoadedSpots)
    {
        auto* Mesh = NewObject<UProceduralMeshComponent>(this, MakeUniqueObjectName(this, UProceduralMeshComponent::StaticClass(),
            *FString::Printf(TEXT("RacingTv_%s"), Spot.Id)));
        Mesh->SetupAttachment(RootComponent);
        Mesh->SetUsingAbsoluteLocation(true);
        Mesh->SetUsingAbsoluteRotation(true);
        Mesh->SetUsingAbsoluteScale(true);
        Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Mesh->SetCanEverAffectNavigation(false);
        Mesh->SetCastShadow(false);
        Mesh->bUseAsyncCooking = true;
        Mesh->CreateMeshSection(0, FV, FT, FN, FU, {}, {}, false);
        Mesh->CreateMeshSection(1, PV, PT, PN, PU, {}, {}, false);
        Mesh->SetMaterial(0, FrameMaterial);
        Mesh->SetMaterial(1, ScreenMaterial);
        Mesh->RegisterComponent();
        Mesh->SetWorldTransform(RacingTv::SpotTransform(Spot, Origin));
        Screens.Add(Mesh);
        Centres.Add(RacingTv::ScreenCentre(Spot, Origin));
        Normals.Add(FRotator(0.f, Spot.Yaw, 0.f).Vector());
    }

    // One capture for every screen, a 640x360 picture of a bar TV: no Lumen, shadows, reflections, AO, volumetrics, clouds,
    // grass, motion blur or temporal AA (its history would smear at a few pictures a second).
    Camera = NewObject<USceneCaptureComponent2D>(this, TEXT("RacingTvCamera"));
    Camera->SetupAttachment(RootComponent);
    Camera->SetUsingAbsoluteLocation(true);
    Camera->SetUsingAbsoluteRotation(true);
    Camera->bCaptureEveryFrame = false;
    Camera->bCaptureOnMovement = false;
    Camera->bAlwaysPersistRenderingState = true;
    Camera->CaptureSource = ESceneCaptureSource::SCS_FinalColorLDR;
    Camera->TextureTarget = Film;
    // Coarser LODs: the picture is small. The view distance follows the shot (Capture).
    Camera->LODDistanceFactor = 3.f;
    // No Lumen for this view (the show flags alone leave its scene work running): the sky light and the sun light it.
    FPostProcessSettings& Post = Camera->PostProcessSettings;
    Post.bOverride_DynamicGlobalIlluminationMethod = true;
    Post.DynamicGlobalIlluminationMethod = EDynamicGlobalIlluminationMethod::None;
    Post.bOverride_ReflectionMethod = true;
    Post.ReflectionMethod = EReflectionMethod::None;
    // A broadcast look: a little more contrast and colour than the eye's view, so the small picture reads across a room.
    Post.bOverride_ColorContrast = true;
    Post.ColorContrast = FVector4(1.18, 1.18, 1.18, 1.);
    Post.bOverride_ColorSaturation = true;
    Post.ColorSaturation = FVector4(1.12, 1.12, 1.12, 1.);
    Camera->PostProcessBlendWeight = 1.f;
    FEngineShowFlags& F = Camera->ShowFlags;
    F.SetLumenGlobalIllumination(false);
    F.SetLumenReflections(false);
    F.SetDynamicShadows(false);
    F.SetContactShadows(false);
    F.SetCapsuleShadows(false);
    F.SetAmbientOcclusion(false);
    F.SetDistanceFieldAO(false);
    F.SetScreenSpaceReflections(false);
    F.SetVolumetricFog(false);
    F.SetMotionBlur(false);
    F.SetBloom(false);
    F.SetLensFlares(false);
    F.SetLightShafts(false);
    F.SetDepthOfField(false);
    F.SetTemporalAA(false);
    F.SetDecals(false);
    F.SetParticles(false);
    F.SetTranslucency(false);
    F.SetCloud(false);
    // No height fog: across a few hundred metres it greys the small picture (the sky still has its atmosphere).
    F.SetFog(false);
    F.SetInstancedGrass(false);
    Camera->RegisterComponent();
    for (UProceduralMeshComponent* Mesh : Screens) Camera->HideComponent(Mesh);

    bBuilt = true;
    UE_LOG(LogTemp, Display, TEXT("RACING TV %d screens round Belmonte's origin (%.0f, %.0f, %.0f)"), Screens.Num(), Origin.X, Origin.Y, Origin.Z);
    // The card until the first race is filmed.
    if (const ARacingService* Service = ARacingService::Find(this)) DrawIdle(Service->GetNetState(), Service->WorldNow());
    return true;
}

void ARacingBroadcast::SetLive(bool bOn)
{
    if (bOn == bLive) return;
    bLive = bOn;
    if (bOn) Camera->bCameraCutThisFrame = true;
    Shot = RacingTv::EShot::None;
    NextIdle = 0.;
    const TConstArrayView<RacingTv::FSpot> All = RacingTv::Spots();
    UE_LOG(LogTemp, Display, TEXT("RACING TV %s (nearest %s at %.1f m)"), bOn ? TEXT("live") : TEXT("idle card"),
        All.IsValidIndex(Nearest) ? All[Nearest].Id : TEXT("none"), NearestM);
}

void ARacingBroadcast::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    FrameMs = FMath::Lerp(FrameMs, DeltaSeconds * 1000.f, .05f);
    GpuMs = FMath::Lerp(GpuMs, float(FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles())), .05f);
    if (!bBuilt && !Build()) { SetActorTickInterval(1.f); return; }
    ARacingService* Service = ARacingService::Find(this);
    if (!Service) { SetActorTickInterval(1.f); return; }

    // The local viewer: the pawn, else the camera.
    const APlayerController* PC = GetWorld()->GetFirstPlayerController();
    FVector Viewer(TNumericLimits<float>::Max());
    if (PC && PC->IsLocalController())
        Viewer = PC->GetPawn() ? PC->GetPawn()->GetActorLocation() : (PC->PlayerCameraManager ? PC->PlayerCameraManager->GetCameraLocation() : Viewer);
    Nearest = INDEX_NONE;
    NearestM = 1e9f;
    bool bInFront = false;
    for (int32 I = 0; I < Centres.Num(); ++I)
    {
        const float M = float(FVector::Dist(Viewer, Centres[I]) / 100.);
        if (M >= NearestM) continue;
        Nearest = I;
        NearestM = M;
        bInFront = FVector::DotProduct(Viewer - Centres[I], Normals[I]) > 0.;
    }

    const FRacingNetState& Net = Service->GetNetState();
    const double Now = Service->WorldNow();
    const double T = Now - Net.Race.Start;
    const bool bWindow = Net.Serial && !Net.Race.Key.IsEmpty() && !Net.Race.Runners.IsEmpty() &&
        T >= -RacingTv::WindowSeconds && T <= HRClock::RaceSeconds;
    // Filmed only while someone here watches: turns on within 25 m in front of a screen and stays on up to 30 m.
    const float MaxDist = bLive ? 30.f : 25.f;
    const bool bWant = bWindow && NearestM <= MaxDist && bInFront && CVarRacingTvCapture.GetValueOnGameThread() != 0;
    SetLive(bWant);
    Service->SetBroadcastAudience(bWant);
    // Far from every screen nothing needs a frame-accurate tick.
    SetActorTickInterval(NearestM > 60.f ? .5f : 0.f);
    const double Real = FPlatformTime::Seconds();
    if (bLive)
    {
        // Nothing to film for while no screen near the player is on screen (looking away): the picture waits.
        bool bSeen = false;
        for (int32 I = 0; I < Screens.Num() && !bSeen; ++I)
            bSeen = Screens[I] && FVector::Dist(Viewer, Centres[I]) <= 2500. && Screens[I]->WasRecentlyRendered(.3f);
        if (!bSeen) { if (Real >= NextCapture) { ++Skipped; NextCapture = Real + .1; } }
        else if (Real >= NextCapture)
        {
            NextCapture = Real + 1. / FMath::Clamp(CVarRacingTvHz.GetValueOnGameThread(), 1.f, 60.f);
            Capture(*Service, Now);
        }
    }
    else if (NearestM <= 40.f && Real >= NextIdle)
    {
        NextIdle = Real + 1.;
        DrawIdle(Net, Now);
    }
}

void ARacingBroadcast::Capture(const ARacingService& Service, double Now)
{
    const FRacingNetState& Net = Service.GetNetState();
    // The players' pawns (replicated: the same on every machine) for the crowd shot.
    TArray<FVector> Players;
    if (const AGameStateBase* GS = GetWorld()->GetGameState())
        for (const APlayerState* PS : GS->PlayerArray)
            if (const APawn* Pawn = PS ? PS->GetPawn() : nullptr) Players.Add(Pawn->GetActorLocation());
    RacingTv::FCamera Cam;
    if (!RacingTv::Direct(Service, Net.Race, Now, Players, Cam)) return;
    // The course data is flat; keep the eye a little over the real ground (a bank in the infield).
    FHitResult Hit;
    FCollisionQueryParams Query(SCENE_QUERY_STAT(RacingTvGround), false, this);
    if (GetWorld()->LineTraceSingleByObjectType(Hit, Cam.Eye + FVector(0., 0., 3000.), Cam.Eye - FVector(0., 0., 1000.),
        FCollisionObjectQueryParams(ECC_WorldStatic), Query) && Hit.ImpactPoint.Z > Cam.Eye.Z - 200.)
        Cam.Eye.Z = Hit.ImpactPoint.Z + 300.;
    // Every camera must see what it films: a wall, a pole or a bank of the static world between them moves the eye just in
    // front of the obstacle nearest the subject (a trace back from the subject; the static world is the same everywhere).
    const FVector Toward = (Cam.Aim - Cam.Eye).GetSafeNormal();
    const double Reach = FVector::Dist(Cam.Eye, Cam.Aim);
    FHitResult Block;
    FCollisionQueryParams Sight(SCENE_QUERY_STAT(RacingTvSight), false, this);
    if (Reach > 500. && GetWorld()->LineTraceSingleByObjectType(Block, Cam.Aim - Toward * FMath::Min(Reach * .2, 1500.), Cam.Eye,
        FCollisionObjectQueryParams(ECC_WorldStatic), Sight) && !Block.bStartPenetrating)
        Cam.Eye = Block.ImpactPoint + Toward * 500.;
    // A new shot, or the next trackside camera: a cut, not a pan.
    if (Cam.Shot != Shot || FVector::Dist(Cam.Eye, Camera->GetComponentLocation()) > 2000.)
    {
        Camera->bCameraCutThisFrame = true;
        UE_LOG(LogTemp, Display, TEXT("RACING TV shot %s (t=%.1f)"), RacingTv::ShotName(Cam.Shot), Now - Net.Race.Start);
        Shot = Cam.Shot;
    }
    // The views from above see the whole course; the others nothing beyond 400 m.
    Camera->MaxViewDistanceOverride = (Cam.Shot == RacingTv::EShot::Course || Cam.Shot == RacingTv::EShot::Aerial) ? 300000.f : 40000.f;
    Camera->SetWorldLocationAndRotation(Cam.Eye, (Cam.Aim - Cam.Eye).Rotation());
    Camera->FOVAngle = Cam.Fov;
    // CaptureScene renders now (queued before the canvases below), so the picture gets the new film, then the graphics.
    Camera->CaptureScene();
    UCanvas* Canvas = nullptr;
    FVector2D Size;
    FDrawToRenderTargetContext Context;
    // The film as it is (gamma 1: it is already display-encoded), stretched over the picture.
    Picture->TargetGamma = 1.f;
    UKismetRenderingLibrary::BeginDrawCanvasToRenderTarget(this, Picture, Canvas, Size, Context);
    if (Canvas)
    {
        FCanvasTileItem Tile(FVector2D::ZeroVector, Film->GetResource(), FVector2D(RacingTvDraw::Width, RacingTvDraw::Height), FLinearColor::White);
        Tile.BlendMode = SE_BLEND_Opaque;
        Canvas->DrawItem(Tile);
    }
    UKismetRenderingLibrary::EndDrawCanvasToRenderTarget(this, Context);
    // The graphics, at the canvas's own gamma like the idle card.
    Picture->TargetGamma = 0.f;
    UKismetRenderingLibrary::BeginDrawCanvasToRenderTarget(this, Picture, Canvas, Size, Context);
    if (Canvas) DrawLowerThird(Canvas, Net, Now);
    UKismetRenderingLibrary::EndDrawCanvasToRenderTarget(this, Context);
    ++Captures;
}

void ARacingBroadcast::DrawLowerThird(UCanvas* Canvas, const FRacingNetState& Net, double Now) const
{
    using namespace RacingTvDraw;
    const FRacingNetRace& Race = Net.Race;
    const double T = Now - Race.Start;
    // The live tag, once they are off.
    if (T >= 0. && Shot != RacingTv::EShot::Finish)
    {
        Box(Canvas, 16.f, 14.f, 96.f, 34.f, Live);
        Text(Canvas, TEXT("DIRECT"), 64.f, 18.f, 24.f, Ink, 1);
    }

    // The order now: by distance run, the places once home.
    TArray<int32> Order;
    TArray<double> Run;
    for (int32 I = 0; I < Race.Runners.Num(); ++I)
    {
        Order.Add(I);
        Run.Add(RacingMotion::Distance(Race.Runners[I].Plan(Race.Distance), T));
    }
    auto Home = [&](const FRacingNetRunner& R) { return R.Place && R.SplitMs.Num() == 4 && T >= R.SplitMs[3] / 1000.; };
    Order.Sort([&](int32 A, int32 B)
    {
        const FRacingNetRunner &RA = Race.Runners[A], &RB = Race.Runners[B];
        if (Home(RA) != Home(RB)) return Home(RA);
        if (Home(RA)) return RA.Place < RB.Place;
        return Run[A] > Run[B];
    });
    const bool bArrived = !Race.Runners.IsEmpty() && Home(Race.Runners[Order[0]]);

    // The band: one big line of what matters now, then the first three behind their saddle cloths.
    const float Y = 252.f;
    Box(Canvas, 0.f, Y, Width, Height - Y, Panel);
    Box(Canvas, 0.f, Y, Width, 4.f, Gold);
    FString Head;
    if (T < 0.) Head = FString::Printf(TEXT("DÉPART  %s"), *Countdown(-T));
    else if (!bArrived) Head = FString::Printf(TEXT("RESTE  %d m"), FMath::Max(0, FMath::CeilToInt(Race.Distance - (Run.IsEmpty() ? 0. : FMath::Max(Run)))));
    else Head = TEXT("ARRIVÉE");
    Text(Canvas, Short(Race.Name), 18.f, Y + 12.f, 30.f, Ink);
    Text(Canvas, Head, Width - 18.f, Y + 12.f, 30.f, Gold, 2);
    // Three columns: number and name, the type shrunk to fit its column.
    const float Column = (Width - 36.f) / 3.f;
    for (int32 K = 0; K < FMath::Min(3, Order.Num()); ++K)
    {
        const FRacingNetRunner& R = Race.Runners[Order[K]];
        const float X = 18.f + K * Column;
        const FString Label = FString::Printf(TEXT("%d %s"), K + 1, *R.Horse);
        float W = 0.f, H = 0.f;
        Canvas->StrLen(Font(), Label, W, H);
        const float Px = FMath::Min(26.f, 26.f * (Column - 40.f) / FMath::Max(W * ScaleFor(Canvas, 26.f), 1.f));
        Silks(Canvas, X, Y + 62.f, 22.f, R.Silks);
        Text(Canvas, Label, X + 30.f, Y + 58.f + (26.f - Px) * .5f, Px, Ink);
    }
}

void ARacingBroadcast::DrawIdle(const FRacingNetState& Net, double Now)
{
    using namespace RacingTvDraw;
    if (!Picture) return;
    UCanvas* Canvas = nullptr;
    FVector2D Size;
    FDrawToRenderTargetContext Context;
    UKismetRenderingLibrary::BeginDrawCanvasToRenderTarget(this, Picture, Canvas, Size, Context);
    if (!Canvas) { UKismetRenderingLibrary::EndDrawCanvasToRenderTarget(this, Context); return; }
    Box(Canvas, 0.f, 0.f, Width, Height, FLinearColor(.004f, .02f, .012f));
    Box(Canvas, 0.f, 0.f, Width, 6.f, Gold);

    const FRacingNetRace& Race = Net.Race;
    if (!Net.Serial)
        Text(Canvas, TEXT("COURSES"), Width * .5f, 150.f, 48.f, Ink, 1);
    else if (Race.Key.IsEmpty())
    {
        Text(Canvas, TEXT("PROCHAINE RÉUNION"), 24.f, 40.f, 30.f, Gold);
        Text(Canvas, Countdown(Net.NextMeeting - Now), 24.f, 90.f, 64.f, Ink);
    }
    else
    {
        // The next race: where, the countdown, and the three favourites with their odds.
        const double T = Now - Race.Start;
        Text(Canvas, FString::Printf(TEXT("%s  ·  %d m"), *FString(VenueName(Race.Venue)).ToUpper(), Race.Distance), 24.f, 22.f, 28.f, Gold);
        Text(Canvas, Short(Race.Name), 24.f, 62.f, 40.f, Ink);
        Text(Canvas, T < 0. ? Countdown(-T) : FString(TEXT("EN COURS")), Width - 24.f, 22.f, 52.f, Gold, 2);
        TArray<const FRacingNetRunner*> Favourites;
        for (const FRacingNetRunner& R : Race.Runners) if (R.OddsTenths > 0) Favourites.Add(&R);
        Favourites.Sort([](const FRacingNetRunner& A, const FRacingNetRunner& B) { return A.OddsTenths < B.OddsTenths; });
        float Y = 128.f;
        for (int32 I = 0; I < FMath::Min(3, Favourites.Num()); ++I, Y += 50.f)
        {
            const FRacingNetRunner& R = *Favourites[I];
            Box(Canvas, 16.f, Y, Width - 32.f, 44.f, FLinearColor(1.f, 1.f, 1.f, .08f));
            Silks(Canvas, 30.f, Y + 9.f, 26.f, R.Silks);
            Text(Canvas, R.Horse, 72.f, Y + 6.f, 30.f, Ink);
            Text(Canvas, FString::Printf(TEXT("%.1f"), R.OddsTenths / 10.), Width - 30.f, Y + 6.f, 30.f, Gold, 2);
        }
    }
    // The last winner.
    if (!Net.Last.Top.IsEmpty())
    {
        Box(Canvas, 0.f, Height - 52.f, Width, 52.f, Panel);
        const float W = Text(Canvas, TEXT("GAGNANT"), 24.f, Height - 42.f, 26.f, Gold);
        Text(Canvas, Net.Last.Top[0], 24.f + W + 18.f, Height - 42.f, 26.f, Ink);
    }
    UKismetRenderingLibrary::EndDrawCanvasToRenderTarget(this, Context);
    ++IdleDraws;
}

bool ARacingBroadcast::GoToScreen(const FString& Id)
{
    TActorIterator<ABelmonteRegion> It(GetWorld());
    const ABelmonteRegion* Region = It ? *It : nullptr;
    const TConstArrayView<RacingTv::FSpot> All = RacingTv::Spots();
    const int32 Index = Id.IsEmpty() ? (All.IsEmpty() ? INDEX_NONE : 0) : RacingTv::FindSpot(Id, All);
    APlayerController* PC = GetWorld()->GetFirstPlayerController();
    auto* Player = PC ? Cast<AWandererCharacter>(PC->GetPawn()) : nullptr;
    if (!Region || !All.IsValidIndex(Index) || !Player) return false;
    const RacingTv::FSpot& Spot = All[Index];
    // Indoors: the landing trace starts just over the floor, under the ceiling.
    return Player->TravelTo(Region->GetActorLocation() + Spot.Watch, Spot.WatchYaw, TEXT("racing tv"), 150.f);
}

FString ARacingBroadcast::StateJson() const
{
    const ARacingService* Service = ARacingService::Find(this);
    const TConstArrayView<RacingTv::FSpot> All = RacingTv::Spots();
    FString Rows;
    for (int32 I = 0; I < Centres.Num() && All.IsValidIndex(I); ++I)
        Rows += FString::Printf(TEXT("%s{\"id\":\"%s\",\"centre\":[%.1f,%.1f,%.1f],\"yaw\":%.1f}"), I ? TEXT(",") : TEXT(""), All[I].Id,
            Centres[I].X, Centres[I].Y, Centres[I].Z, All[I].Yaw);
    return FString::Printf(TEXT("{\"built\":%s,\"live\":%s,\"shot\":\"%s\",\"nearest\":\"%s\",\"distance_m\":%.1f,\"captures\":%d,\"skipped\":%d,\"idle_draws\":%d,"
        "\"frame_ms\":%.2f,\"gpu_ms\":%.2f,\"runners_shown\":%d,\"camera\":[%.0f,%.0f,%.0f],\"fov\":%.1f,\"screens\":[%s]}"),
        bBuilt ? TEXT("true") : TEXT("false"), bLive ? TEXT("true") : TEXT("false"), RacingTv::ShotName(Shot),
        All.IsValidIndex(Nearest) ? All[Nearest].Id : TEXT(""), NearestM, Captures, Skipped, IdleDraws, FrameMs, GpuMs,
        Service ? Service->NumRunnersShown() : 0, Camera ? Camera->GetComponentLocation().X : 0., Camera ? Camera->GetComponentLocation().Y : 0.,
        Camera ? Camera->GetComponentLocation().Z : 0., Camera ? Camera->FOVAngle : 0.f, *Rows);
}

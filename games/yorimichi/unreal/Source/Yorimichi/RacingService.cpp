#include "RacingService.h"
#include "AtelierData.h"
#include "BelmonteRegion.h"
#include "Hippodrome.h"
#include "HorseComponent.h"
#include "HRBreeds.h"
#include "HRClock.h"
#include "HRContent.h"
#include "HRRules.h"
#include "HRSave.h"
#include "HRVisualGenome.h"
#include "JapanNetwork.h"
#include "JapanSession.h"
#include "LiveLibrary.h"
#include "MoverCharacter.h"
#include "PlayableCharacter.h"
#include "RacingBroadcast.h"
#include "WandererDefinition.h"
#include "WandererCharacter.h"
#include "Animation/AnimSequence.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/SkeletalMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerState.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformFileManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Guid.h"
#include "Misc/Parse.h"
#include "Net/UnrealNetwork.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/ConstructorHelpers.h"

static TAutoConsoleVariable<float> CVarRacingTimeScale(TEXT("racing.TimeScale"), 1.f,
    TEXT("Racing world clock speed (1 = real time; dev only, set on the host)."));

static FAutoConsoleCommandWithWorldAndArgs RacingNextCommand(TEXT("racing.Next"),
    TEXT("racing.Next [lead seconds, default 100]: jump the racing clock to just before the next race's start (host)."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
    {
        if (auto* Service = ARacingService::Find(World)) Service->JumpToNextRace(Args.Num() ? FCString::Atod(*Args[0]) : 100.);
    }));

static FAutoConsoleCommandWithWorldAndArgs RacingGoCommand(TEXT("racing.Go"),
    TEXT("racing.Go [hidamari|belmonte]: travel to a racecourse's stand (default: the venue of the race in focus)."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
    {
        if (auto* Service = ARacingService::Find(World)) Service->GoToVenue(Args.Num() ? Args[0] : FString());
    }));

static FAutoConsoleCommandWithWorldAndArgs RacingSaveCommand(TEXT("racing.Save"),
    TEXT("racing.Save: write the racing world to its save file now (host)."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
    {
        if (auto* Service = ARacingService::Find(World)) Service->SaveNow();
    }));

// Looks and venue constants. A named namespace: in a unity build an anonymous one would leak into later files.
namespace RacingLooks
{
    /** The rules' breeds (HRBreeds: Standard, Giant, Bone, Spirit) as roster breeds. */
    const TCHAR* const Breeds[] = {TEXT("thoroughbred"), TEXT("friesian"), TEXT("andalusian"), TEXT("arabian")};
    constexpr int32 BreedCount = UE_ARRAY_COUNT(Breeds);
    /** Coat 0 is the breed's own; the others are roster coat variant ids. */
    const TCHAR* const Coats[] = {TEXT(""), TEXT("kestrel-bay"), TEXT("kestrel-seal-brown"), TEXT("kestrel-black"), TEXT("kestrel-chestnut"),
        TEXT("kestrel-sorrel"), TEXT("kestrel-palomino"), TEXT("kestrel-buckskin"), TEXT("kestrel-perlino"), TEXT("kestrel-blue-roan"),
        TEXT("kestrel-red-roan"), TEXT("kestrel-dapple-grey"), TEXT("kestrel-silver-dun"), TEXT("kestrel-bay-tobiano"),
        TEXT("kestrel-chestnut-overo"), TEXT("kestrel-leopard"), TEXT("kestrel-blanket")};
    constexpr int32 CoatCount = UE_ARRAY_COUNT(Coats);
    int32 CoatIndex(const TCHAR* Id)
    {
        for (int32 I = 0; I < CoatCount; ++I) if (FCString::Strcmp(Coats[I], Id) == 0) return I;
        return 0;
    }
    /** Roster clips per gait, slowest first, and each gait's speed band (cm/s) and play rates (HorseComponent's). */
    const TCHAR* const HorseClips[] = {TEXT("Idle"), TEXT("Walk"), TEXT("Trot"), TEXT("Canter"), TEXT("Gallop"), TEXT("Sprint")};
    const TCHAR* const RiderClips[] = {TEXT("HorseIdle"), TEXT("HorseWalk"), TEXT("HorseTrot"), TEXT("HorseCanter"), TEXT("HorseGallop"), TEXT("HorseSprint")};
    constexpr int32 GaitCount = UE_ARRAY_COUNT(HorseClips);
    static_assert(GaitCount == UHorseComponent::GaitCount, "Racing gaits must match UHorseComponent::GaitCount");
    int32 GaitFor(float SpeedCm) { return UHorseComponent::GaitForSpeed(SpeedCm); }
    float RateFor(int32 Gait, float SpeedCm) { return UHorseComponent::PlayRateForGait(Gait, SpeedCm, true); }

    /** The look of a horse: (breed index, coat index, scale percent) from its visual genome on day T. */
    FIntVector Look(const FHRHorse& H, int32 T)
    {
        const FHRPhenotype P = HRVisual::ResolvePhenotypeAt(H, T);
        // One roster breed per rules breed, in allele order: no breed falls back to another.
        static_assert(BreedCount == HRBreeds::AlleleCount, "every rules breed needs its roster breed");
        const FString Breed = HRBreeds::Express(H.Genome);
        int32 B = 0;
        for (int32 I = 0; I < HRBreeds::AlleleCount; ++I) if (Breed == HRBreeds::AlleleName(I)) B = I;
        const TCHAR* Coat = TEXT("kestrel-bay");
        const bool bRed = P.Foundation == TEXT("chestnut"), bBlack = P.Foundation == TEXT("black");
        if (P.bGray) Coat = TEXT("kestrel-dapple-grey");
        else if (P.bRoan) Coat = bRed ? TEXT("kestrel-red-roan") : TEXT("kestrel-blue-roan");
        else if (P.Cream >= 2) Coat = TEXT("kestrel-perlino");
        else if (P.Cream == 1) Coat = bRed ? TEXT("kestrel-palomino") : bBlack ? TEXT("kestrel-black") : TEXT("kestrel-buckskin");
        else if (P.bDun) Coat = TEXT("kestrel-silver-dun");
        else if (P.Pattern == TEXT("patch")) Coat = bRed ? TEXT("kestrel-chestnut-overo") : TEXT("kestrel-bay-tobiano");
        else if (P.Pattern == TEXT("spot")) Coat = P.PatternExtent >= 3 ? TEXT("kestrel-leopard") : TEXT("kestrel-blanket");
        else if (bRed) Coat = P.bFlaxen ? TEXT("kestrel-sorrel") : TEXT("kestrel-chestnut");
        else if (bBlack) Coat = TEXT("kestrel-black");
        else Coat = (HRVisual::AppearanceHash(H.Id) & 3) == 0 ? TEXT("kestrel-seal-brown") : TEXT("kestrel-bay");
        // Racing horses keep within 8 % of the breed's size, so the jockey's seat still fits.
        const float Scale = FMath::Clamp(HRBreeds::IndividualScale(P), .92f, 1.08f);
        return FIntVector(B, CoatIndex(Coat), FMath::RoundToInt(Scale * 100.f));
    }

    const TCHAR* VenueName(ERacingVenue V) { return V == ERacingVenue::Belmonte ? TEXT("Belmonte") : TEXT("Hidamari"); }

    FString Countdown(double Seconds)
    {
        Seconds = FMath::Max(0., Seconds);
        if (Seconds < 60.) return FString::Printf(TEXT("%d s"), FMath::CeilToInt(Seconds));
        if (Seconds < 3600.) return FString::Printf(TEXT("%d min"), FMath::CeilToInt(Seconds / 60.));
        return FString::Printf(TEXT("%d h %02d"), int32(Seconds / 3600.), int32(FMath::Fmod(Seconds, 3600.) / 60.));
    }

    double UnixNow() { return double((FDateTime::UtcNow() - FDateTime(1970, 1, 1)).GetTicks()) / double(ETimespan::TicksPerSecond); }

    /** The id this machine's own player keeps across sessions (Saved/racing/player-id.txt). */
    FString LocalPlayerId()
    {
        static FString Cached;
        if (!Cached.IsEmpty()) return Cached;
        const FString Path = FPaths::GetPath(ARacingService::DefaultSavePath()) / TEXT("player-id.txt");
        FString Text;
        if (FFileHelper::LoadFileToString(Text, *Path) && !Text.TrimStartAndEnd().IsEmpty()) Cached = Text.TrimStartAndEnd();
        else
        {
            Cached = TEXT("local:") + FGuid::NewGuid().ToString(EGuidFormats::Digits);
            FFileHelper::SaveStringToFile(Cached, *Path);
        }
        return Cached;
    }
}

// ------------------------------------------------------------------------------------------------------------ snapshot

RacingMotion::FPlan FRacingNetRunner::Plan(int32 Distance) const
{
    RacingMotion::FPlan P;
    P.Distance = Distance;
    if (SplitMs.Num() == 4)
        for (int32 I = 0; I < 4; ++I) P.Splits[I] = SplitMs[I] / 1000.;
    return P;
}

bool FRacingNetRunner::operator==(const FRacingNetRunner& O) const
{
    return Horse == O.Horse && Stable == O.Stable && Jockey == O.Jockey && Silks == O.Silks && OddsTenths == O.OddsTenths &&
        Breed == O.Breed && Coat == O.Coat && Scale == O.Scale && Place == O.Place && SplitMs == O.SplitMs;
}

bool FRacingNetRace::operator==(const FRacingNetRace& O) const
{
    return Key == O.Key && Name == O.Name && Venue == O.Venue && Track == O.Track && Distance == O.Distance && Start == O.Start &&
        bRun == O.bRun && Runners == O.Runners;
}

bool FRacingNetState::SameContent(const FRacingNetState& O) const
{
    return Day == O.Day && Event == O.Event && bGrandPrix == O.bGrandPrix && Race == O.Race && Last == O.Last &&
        Standings == O.Standings && NextMeeting == O.NextMeeting;
}

int32 FRacingNetState::PayloadBytes() const
{
    auto Text = [](const FString& S) { return 4 + FTCHARToUTF8(*S).Length(); };
    int32 Bytes = 4 + 8 + 8 + 4 + 4 + Text(Event) + 1 + 8;
    Bytes += Text(Race.Key) + Text(Race.Name) + 1 + 1 + 4 + 8 + 1 + 4;
    for (const FRacingNetRunner& R : Race.Runners)
        Bytes += Text(R.Horse) + Text(R.Stable) + Text(R.Jockey) + 4 + 4 + 4 + 4 + 4 * R.SplitMs.Num();
    Bytes += Text(Last.Key) + Text(Last.Race) + 1 + 4 + 8 + 4 + 4 + 4 * Last.TimeMs.Num();
    for (const FString& Name : Last.Top) Bytes += Text(Name);
    Bytes += 4;
    for (const FRacingNetStanding& Row : Standings) Bytes += Text(Row.Stable) + 4 + 4 + 4;
    return Bytes;
}

ERacingVenue ARacingService::VenueForDay(int32 T)
{
    if (HRClock::IsGrandPrixDay(T)) return ERacingVenue::Belmonte;
    // Ordinary days, counted within the season (every third day is a Grand Prix): Hidamari, Belmonte, Hidamari...
    const int32 Day = HRClock::DayOfSeason(T);
    const int32 Ordinary = Day - Day / 3;
    return (Ordinary % 2 == 0) ? ERacingVenue::Hidamari : ERacingVenue::Belmonte;
}

FString ARacingService::RaceName(const FHRRace& Race)
{
    const HRContent::FEvent* E = HRContent::FindEvent(Race.EventId);
    const FString Event = E ? FString(E->Name) : Race.EventId;
    FString Round;
    if (Race.Round == TEXT("final")) Round = TEXT("final");
    else if (Race.Round == TEXT("semi")) Round = FString::Printf(TEXT("semi-final %d"), Race.Group + 1);
    else if (Race.Round == TEXT("qualif")) Round = FString::Printf(TEXT("qualifying sprint %d"), Race.Group + 1);
    else if (Race.Round == TEXT("barrage")) Round = Race.Group == 0 ? FString(TEXT("play-off")) : FString::Printf(TEXT("play-off %d"), Race.Group + 1);
    else Round = FString::Printf(TEXT("race %d"), Race.Group + 1);
    return Event + TEXT(" · ") + Round;
}

void ARacingService::BuildSnapshot(const FHRWorldState& S, double Now, const FRacingNetResult& Previous, FRacingNetState& Out,
    TMap<FString, FIntVector>* LookCache)
{
    const HRContent::FEvent& Event = HRContent::EventForT(S.T);
    const ERacingVenue Venue = VenueForDay(S.T);
    Out.Day = S.T;
    Out.Event = Event.Name;
    Out.bGrandPrix = Event.bGrandPrix;
    Out.NextMeeting = HRClock::DayStart(S.T + 1) + HRClock::FirstRaceSecond;
    // The race in focus: the last one started that is still being shown, else the next one to start.
    const FHRRace* Focus = nullptr;
    double FocusStart = 0.;
    const FHRRace* Last = nullptr;
    double LastFinish = -1.;
    for (const FHRRace& R : S.Meeting.Races)
    {
        const double Start = HRRules::RaceStartSeconds(S, R.Key);
        if (Start < 0.) continue;
        const bool bRun = R.Status == TEXT("run");
        if (R.IsRun() && !bRun) continue;   // uncontested or a bye: nothing to watch
        if (bRun && !R.Finishes.IsEmpty())
        {
            const double Finish = Start + R.Finishes[0].TimeUs / 1e6;
            if (Finish <= Now && Finish > LastFinish) { Last = &R; LastFinish = Finish; }
        }
        if (Start <= Now && Now < Start + HRClock::RaceSeconds)
        {
            if (!Focus || Start > FocusStart) { Focus = &R; FocusStart = Start; }
        }
    }
    if (!Focus)
        for (const FHRRace& R : S.Meeting.Races)
        {
            const double Start = HRRules::RaceStartSeconds(S, R.Key);
            if (R.IsRun() || Start <= Now) continue;
            if (!Focus || Start < FocusStart) { Focus = &R; FocusStart = Start; }
        }
    Out.Race = FRacingNetRace();
    if (Focus)
    {
        FRacingNetRace& N = Out.Race;
        N.Key = Focus->Key;
        N.Name = RaceName(*Focus);
        N.Venue = uint8(Venue);
        N.Track = (Venue == ERacingVenue::Belmonte && Event.Surface == 2) ? 1 : 0;
        N.Distance = Focus->Distance;
        N.Start = FocusStart;
        N.bRun = Focus->Status == TEXT("run");
        for (const FHRRunner& Entry : Focus->Entries)
        {
            const FHRHorse* H = S.Horses.Find(Entry.HorseId);
            const FHRStable* St = HRRules::FindStable(S, Entry.StableId);
            if (!H || !St)
            {
                // An admitted world always has its entrants (HRSave): no field rather than a made-up runner.
                UE_LOG(LogTemp, Error, TEXT("RACING %s enters %s of %s, which the world does not have: the race is not shown"),
                    *Focus->Key, *Entry.HorseId, *Entry.StableId);
                N.Runners.Reset();
                break;
            }
            FRacingNetRunner& R = N.Runners.AddDefaulted_GetRef();
            R.Horse = H->Name;
            R.Stable = St->Name;
            R.Silks = FColor::FromHex(St->Color);
            R.OddsTenths = FMath::Clamp(FMath::RoundToInt(HRRules::Rapport(S, *Focus, Entry.HorseId) * 10.), 0, 9999);
            if (!Entry.RiderPlayerId.IsEmpty())
            {
                const FHRPlayer* P = HRRules::FindPlayer(S, Entry.RiderPlayerId);
                R.Jockey = P && !P->Name.IsEmpty() ? P->Name : Entry.RiderPlayerId;
            }
            else if (const FHRRider* Rider = HRRules::RiderOf(S, Entry.HorseId)) R.Jockey = Rider->FullName();
            {
                FIntVector Look;
                if (const FIntVector* Cached = LookCache ? LookCache->Find(H->Id) : nullptr) Look = *Cached;
                else
                {
                    Look = RacingLooks::Look(*H, S.T);
                    if (LookCache) LookCache->Add(H->Id, Look);
                }
                R.Breed = uint8(Look.X); R.Coat = uint8(Look.Y); R.Scale = uint8(Look.Z);
            }
            if (N.bRun)
                if (const FHRFinish* F = Focus->Finishes.FindByPredicate([&](const FHRFinish& X) { return X.HorseId == Entry.HorseId; }))
                {
                    R.Place = uint8(F->Place);
                    for (const FHRSegment& Seg : F->Segments) R.SplitMs.Add(int32(Seg.CumulativeUs / 1000));
                    if (R.SplitMs.Num() != 4) R.SplitMs.Reset();
                    if (!F->RiderName.IsEmpty()) R.Jockey = F->RiderName;
                }
        }
    }
    Out.Last = Previous;
    if (Last)
    {
        FRacingNetResult& L = Out.Last;
        L = FRacingNetResult();
        L.Key = Last->Key;
        L.Race = RaceName(*Last);
        L.Venue = uint8(Venue);
        L.Day = S.T;
        L.Finished = LastFinish;
        for (int32 I = 0; I < FMath::Min(3, Last->Finishes.Num()); ++I)
        {
            L.Top.Add(Last->Finishes[I].HorseName);
            L.TimeMs.Add(int32(Last->Finishes[I].TimeUs / 1000));
        }
    }
    TArray<const FHRStable*> Order;
    for (const FHRStable& St : S.Stables) if (!St.bForSale) Order.Add(&St);
    Order.Sort([](const FHRStable& A, const FHRStable& B)
    {
        if (A.EventWins != B.EventWins) return A.EventWins > B.EventWins;
        if (A.TotalEarnings != B.TotalEarnings) return A.TotalEarnings > B.TotalEarnings;
        return A.Id < B.Id;
    });
    Out.Standings.Reset();
    for (int32 I = 0; I < FMath::Min(6, Order.Num()); ++I)
    {
        FRacingNetStanding& Row = Out.Standings.AddDefaulted_GetRef();
        Row.Stable = Order[I]->Name;
        Row.Color = FColor::FromHex(Order[I]->Color);
        Row.Wins = Order[I]->EventWins;
        Row.Earnings = Order[I]->TotalEarnings;
    }
}

// ------------------------------------------------------------------------------------------------------------ actor

ARacingService::ARacingService()
{
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.TickGroup = TG_PrePhysics;
    bReplicates = true;
    bAlwaysRelevant = true;
    SetNetUpdateFrequency(2.f);
    SetMinNetUpdateFrequency(1.f);
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    RootComponent->SetMobility(EComponentMobility::Static);
    // The saddles take the stable's colour (a cooked engine material, as the sword's).
    static ConstructorHelpers::FObjectFinder<UMaterialInterface> Basic(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
    SilksMaterial = Basic.Object;
}

void ARacingService::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(ARacingService, Net);
}

ARacingService* ARacingService::Spawn(UWorld* World)
{
    if (!World) return nullptr;
    if (ARacingService* Existing = Find(World)) return Existing;
    return World->SpawnActor<ARacingService>();
}

ARacingService* ARacingService::Find(const UObject* WorldContext)
{
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World) return nullptr;
    TActorIterator<ARacingService> It(World);
    return It ? *It : nullptr;
}

void ARacingService::BeginPlay()
{
    Super::BeginPlay();
    LoadCourses();
    if (HasAuthority())
    {
        FString Seed = TEXT("yorimichi-") + FGuid::NewGuid().ToString(EGuidFormats::Digits);
        FParse::Value(FCommandLine::Get(), TEXT("racingseed="), Seed);
        OpenWorld(DefaultSavePath(), Seed);
        if (FParse::Param(FCommandLine::Get(), TEXT("racingnext"))) JumpToNextRace(100.);
        Publish(true);
    }
}

void ARacingService::EndPlay(const EEndPlayReason::Type Reason)
{
    if (HasAuthority() && bHasWorld) SaveNow();
    ClearRunners();
    Super::EndPlay(Reason);
}

FString ARacingService::DefaultSavePath()
{
    FString Path;
    if (FParse::Value(FCommandLine::Get(), TEXT("racingsave="), Path) && !Path.IsEmpty()) return FPaths::ConvertRelativePathToFull(Path);
    return FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("racing") / TEXT("world.json"));
}

bool ARacingService::SaveWorldFile(const FHRWorldState& S, const FString& Path, FString& Error)
{
    IPlatformFile& Files = FPlatformFileManager::Get().GetPlatformFile();
    const FString Dir = FPaths::GetPath(Path);
    if (!Files.CreateDirectoryTree(*Dir))
    {
        Error = FString::Printf(TEXT("cannot create %s"), *Dir);
        return false;
    }
    // The whole world into a sibling temporary file, flushed to disk before it replaces the old one.
    const FString Temp = Path + TEXT(".tmp");
    {
        const FTCHARToUTF8 Utf8(*HRSave::ToJson(S));
        TUniquePtr<IFileHandle> File(Files.OpenWrite(*Temp));
        if (!File || !File->Write(reinterpret_cast<const uint8*>(Utf8.Get()), Utf8.Length()) || !File->Flush(true))
        {
            File.Reset();
            Files.DeleteFile(*Temp);
            Error = FString::Printf(TEXT("cannot write %s"), *Temp);
            return false;
        }
    }
    // rename() replaces the old file atomically (macOS, Linux). Where a rename cannot replace (Windows), the old file steps
    // aside first and comes back if the new one cannot take its place; LoadWorldFile reads the aside copy after a crash.
    if (Files.MoveFile(*Path, *Temp)) return true;
    const FString Previous = Path + TEXT(".previous");
    if (Files.FileExists(*Path))
    {
        Files.DeleteFile(*Previous);
        if (Files.MoveFile(*Previous, *Path))
        {
            if (Files.MoveFile(*Path, *Temp))
            {
                Files.DeleteFile(*Previous);
                return true;
            }
            Files.MoveFile(*Path, *Previous);
        }
    }
    Files.DeleteFile(*Temp);
    Error = FString::Printf(TEXT("cannot rename %s over %s"), *Temp, *Path);
    return false;
}

ARacingService::ELoad ARacingService::LoadWorldFile(const FString& Path, FHRWorldState& Out, FString& Error)
{
    IPlatformFile& Files = FPlatformFileManager::Get().GetPlatformFile();
    FString File = Path;
    if (!Files.FileExists(*File))
    {
        // A replacement interrupted after the old world stepped aside (SaveWorldFile on Windows).
        File = Path + TEXT(".previous");
        if (!Files.FileExists(*File)) return ELoad::Missing;
    }
    FString Text;
    if (!FFileHelper::LoadFileToString(Text, *File))
    {
        Error = FString::Printf(TEXT("cannot read %s"), *File);
        return ELoad::Unreadable;
    }
    if (!HRSave::FromJson(Text, Out, Error)) return ELoad::Invalid;
    return ELoad::Loaded;
}

bool ARacingService::OpenWorld(const FString& Path, const FString& Seed)
{
    SavePath = Path;
    bHasWorld = false;
    PersistenceError.Reset();
    FHRWorldState Loaded;
    FString Error;
    const ELoad Load = LoadWorldFile(Path, Loaded, Error);
    if (Load == ELoad::Loaded)
    {
        State = MoveTemp(Loaded);
        UE_LOG(LogTemp, Display, TEXT("RACING world loaded from %s: day %d, %d horses, %d players"), *Path, State.T, State.Horses.Num(), State.Players.Num());
    }
    else
    {
        if (Load == ELoad::Unreadable)
        {
            // Perhaps only for now (permissions, a disk error): never replace a world that may be fine.
            PersistenceError = Error;
            UE_LOG(LogTemp, Error, TEXT("RACING %s: the save is left as it is and racing stays off"), *Error);
            return false;
        }
        if (Load == ELoad::Invalid)
        {
            // Never lose a world that would not load (another rules version, a broken write): keep it aside, and if that
            // fails keep it where it is and open nothing, so no new world is ever written over it.
            IPlatformFile& Files = FPlatformFileManager::Get().GetPlatformFile();
            const FString SourceFile = Files.FileExists(*Path) ? Path : Path + TEXT(".previous");
            const FString Aside = Path + FString::Printf(TEXT(".unreadable-%lld"), int64(RacingLooks::UnixNow()));
            if (!Files.MoveFile(*Aside, *SourceFile))
            {
                PersistenceError = FString::Printf(TEXT("%s is not an admissible world (%s) and could not be kept aside as %s"), *SourceFile, *Error, *Aside);
                UE_LOG(LogTemp, Error, TEXT("RACING %s: the save is left as it is and racing stays off"), *PersistenceError);
                return false;
            }
            UE_LOG(LogTemp, Error, TEXT("RACING %s is not an admissible world (%s); kept as %s and created a new world"), *SourceFile, *Error, *Aside);
        }
        const double Started = FPlatformTime::Seconds();
        State = HRRules::CreateWorld(Seed);
        UE_LOG(LogTemp, Display, TEXT("RACING world created from seed %s in %.2f s: day %d"), *Seed, FPlatformTime::Seconds() - Started, State.T);
    }
    if (State.EpochUnix == 0) HRRules::StartClock(State, int64(RacingLooks::UnixNow()));
    bHasWorld = true;
    Registered.Reset();
    LookCache.Reset();
    bDirty = true;
    SaveNow();
    return true;
}

bool ARacingService::SaveNow()
{
    if (!bHasWorld || SavePath.IsEmpty()) return false;
    // The dev offset's whole seconds go into the saved epoch, so a reload continues from the same world second.
    const double Whole = FMath::FloorToDouble(DevSeconds);
    State.EpochUnix -= int64(Whole);
    DevSeconds -= Whole;
    FString Error;
    const bool bSaved = SaveWorldFile(State, SavePath, Error);
    LastSave = FPlatformTime::Seconds();
    if (bSaved)
    {
        bDirty = false;
        PersistenceError.Reset();
    }
    else
    {
        // The world stays in memory and dirty: the next save (every 15 s, and at the end) tries again.
        PersistenceError = Error;
        UE_LOG(LogTemp, Error, TEXT("RACING could not save the world: %s"), *Error);
    }
    return bSaved;
}

double ARacingService::HostWorldSeconds() const
{
    return bHasWorld ? HRRules::WorldSeconds(State, RacingLooks::UnixNow() + DevSeconds) : 0.;
}

static double ServerTimeOf(const UWorld* World)
{
    const AGameStateBase* GS = World ? World->GetGameState() : nullptr;
    return GS ? GS->GetServerWorldTimeSeconds() : (World ? World->GetTimeSeconds() : 0.);
}

double ARacingService::WorldNow() const
{
    if (!Net.Serial) return HostWorldSeconds();
    return Net.AnchorWorld + (ServerTimeOf(GetWorld()) - Net.AnchorServer) * Net.Scale;
}

void ARacingService::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!bCoursesLoaded) LoadCourses();
    if (HasAuthority() && bHasWorld) TickHost(DeltaSeconds);
    TickPresentation(DeltaSeconds);
    const double Real = FPlatformTime::Seconds();
    if (Real >= NextReport)
    {
        NextReport = Real + 10.;
        const double Now = WorldNow();
        UE_LOG(LogTemp, Display, TEXT("RACING day=%d world=%.0f race=%s venue=%s t=%.1f run=%d shown=%d serial=%u"), Net.Day, Now, *Net.Race.Key,
            RacingLooks::VenueName(ERacingVenue(Net.Race.Venue)), Now - Net.Race.Start, Net.Race.bRun, Shown.Num(), Net.Serial);
    }
}

void ARacingService::TickHost(float DeltaSeconds)
{
    const float Scale = FMath::Clamp(CVarRacingTimeScale.GetValueOnGameThread(), 0.f, 600.f);
    if (Scale != 1.f) DevSeconds += double(DeltaSeconds) * (Scale - 1.);
    double Now = HostWorldSeconds();
    // A host away for longer than the rules' catch-up (one real week) resumes as if the world had paused then: the clock
    // anchor moves forward, so at most that many days are ever simulated.
    if (const int32 Skipped = HRRules::LimitCatchUp(State, Now))
    {
        bDirty = true;
        UE_LOG(LogTemp, Display, TEXT("RACING away for long: %d race days skipped, %d to catch up"), Skipped, HRRules::MaxCatchUpDays);
    }
    const int32 DayBefore = State.T;
    int32 RunBefore = 0;
    for (const FHRRace& R : State.Meeting.Races) RunBefore += R.IsRun() ? 1 : 0;
    // At most one race day per frame: a host back after hours catches up over a few frames, never in one long hitch.
    HRRules::AdvanceTo(State, FMath::Min(Now, HRClock::DayStart(State.T + 1)));
    int32 RunAfter = 0;
    for (const FHRRace& R : State.Meeting.Races) RunAfter += R.IsRun() ? 1 : 0;
    const bool bChanged = State.T != DayBefore || RunAfter != RunBefore;
    if (State.T != DayBefore) LookCache.Reset();
    bDirty |= bChanged;
    const double Real = FPlatformTime::Seconds();
    if (Real >= NextRegister) { NextRegister = Real + 1.; RegisterPlayers(); }
    if (bChanged || Scale != AppliedScale || Real >= NextPublish) Publish(Scale != AppliedScale);
    if (bDirty && Real - LastSave > 15.) SaveNow();
}

void ARacingService::RegisterPlayers()
{
    const AGameStateBase* GS = GetWorld() ? GetWorld()->GetGameState() : nullptr;
    if (!GS) return;
    for (APlayerState* PS : GS->PlayerArray)
    {
        if (!PS) continue;
        const AController* Owner = Cast<AController>(PS->GetOwner());
        // V1 registers the host's own player only (its id is saved beside the world). Remote guests have no persistent
        // identity yet (an online id may be absent, a session id changes every session), so they get no player record,
        // wallet or stable: they watch from the replicated snapshot, which carries none (docs/RACING.md, "Players").
        if (!Owner || !Owner->IsLocalController()) continue;
        const FString Id = RacingLooks::LocalPlayerId();
        if (Id.IsEmpty() || Registered.Contains(Id)) continue;
        Registered.Add(Id);
        if (HRRules::FindPlayer(State, Id)) continue;
        // Not the player name: offline it is the machine's network name.
        const AJapanPlayerState* JPS = Cast<AJapanPlayerState>(PS);
        const FString Name = JPS ? JPS->RiderName : FString();
        HRRules::AddPlayer(State, Id, Name.IsEmpty() ? FString(TEXT("Player")) : Name);
        bDirty = true;
        UE_LOG(LogTemp, Display, TEXT("RACING player registered: %s (%s)"), *Id, *Name);
    }
}

void ARacingService::Publish(bool bForceAnchor)
{
    if (!HasAuthority() || !bHasWorld) return;
    NextPublish = FPlatformTime::Seconds() + 1.;
    const double Now = HostWorldSeconds();
    FRacingNetState Next = Net;
    BuildSnapshot(State, Now, LastResult, Next, &LookCache);
    LastResult = Next.Last;
    const float Scale = FMath::Clamp(CVarRacingTimeScale.GetValueOnGameThread(), 0.f, 600.f);
    bool bChanged = !Next.SameContent(Net) || !Net.Serial;
    // Re-anchor the shared clock when the speed changes or it drifts from the host's.
    if (bForceAnchor || bChanged || Scale != Net.Scale || FMath::Abs(WorldNow() - Now) > .25)
    {
        Next.AnchorServer = ServerTimeOf(GetWorld());
        Next.AnchorWorld = Now;
        Next.Scale = Scale;
        bChanged = true;
    }
    AppliedScale = Scale;
    if (!bChanged) return;
    Next.Serial = Net.Serial + 1;
    Net = MoveTemp(Next);
    ForceNetUpdate();
}

void ARacingService::OnRep_Net()
{
    UE_LOG(LogTemp, Verbose, TEXT("RACING snapshot %u: %s"), Net.Serial, *Net.Race.Key);
}

bool ARacingService::JumpToNextRace(double Lead)
{
    if (!HasAuthority() || !bHasWorld)
    {
        UE_LOG(LogTemp, Warning, TEXT("RACING racing.Next works on the host only"));
        return false;
    }
    const double Now = HostWorldSeconds();
    double Next = -1.;
    for (const FHRRace& R : State.Meeting.Races)
    {
        const double Start = HRRules::RaceStartSeconds(State, R.Key);
        if (!R.IsRun() && Start > Now && (Next < 0. || Start < Next)) Next = Start;
    }
    // A Grand Prix final is declared once its heats are run, in the day's last slot; no race left: the next day's first.
    if (Next < 0.) Next = HRClock::DayStart(State.T + 1) + HRClock::FirstRaceSecond;
    const double Skip = (Next - Lead) - Now;
    if (Skip > 0.) DevSeconds += Skip;
    UE_LOG(LogTemp, Display, TEXT("RACING NEXT skipped %.0f s: start at world %.0f in %.0f s"), FMath::Max(Skip, 0.), Next, Next - HostWorldSeconds());
    TickHost(0.f);
    Publish(true);
    return true;
}

// ------------------------------------------------------------------------------------------------------------ courses

bool ARacingService::LoadBelmonteCourses(const FString& Json, const FVector& OriginCm, FString& Error)
{
    TSharedPtr<FJsonObject> Root;
    const TSharedPtr<FJsonObject>* Tracks = nullptr;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Root) || !Root || !Root->TryGetObjectField(TEXT("tracks"), Tracks))
    {
        Error = TEXT("no tracks");
        return false;
    }
    auto Read = [&](const TCHAR* Name, FRacingCourse& Out)
    {
        const TSharedPtr<FJsonObject>* Track = nullptr;
        Out.Venue = ERacingVenue::Belmonte;
        Out.bOval = false;
        // The points are lane 1, the outermost; lanes step 1.9 m inwards (the rails are 2.5 m out and 12.8 m in).
        Out.InnerLane = -10.;
        Out.OuterLane = -.5;
        return (*Tracks)->TryGetObjectField(Name, Track) && Out.Line.Parse(*Track, OriginCm, Error);
    };
    return Read(TEXT("turf"), BelmonteTurf) && Read(TEXT("sand"), BelmonteSand);
}

bool ARacingService::LoadCourses()
{
    if (bCoursesLoaded) return true;
    if (bCoursesFileFailed) return false;
    const AHippodrome* Hippodrome = AHippodrome::Find(this);
    TActorIterator<ABelmonteRegion> It(GetWorld());
    const ABelmonteRegion* Region = It ? *It : nullptr;
    if (!Hippodrome || !Region) return false;
    Hidamari.Venue = ERacingVenue::Hidamari;
    Hidamari.bOval = true;
    Hidamari.Oval = Hippodrome->Course;
    // The 14 m oval: the field spreads over its middle 11 m.
    Hidamari.InnerLane = -5.;
    Hidamari.OuterLane = 5.;
    FString Text, Error;
    const FString Path = AtelierDataPath(TEXT("racing/belmonte_courses.json"));
    if (!FFileHelper::LoadFileToString(Text, *Path) || !LoadBelmonteCourses(Text, Region->GetActorLocation(), Error))
    {
        bCoursesFileFailed = true;
        UE_LOG(LogTemp, Warning, TEXT("RACING Belmonte courses unavailable (%s): %s"), *Path, *Error);
        return false;
    }
    bCoursesLoaded = true;
    UE_LOG(LogTemp, Display, TEXT("RACING courses: Hidamari lap %.1f m, Belmonte turf %.1f m, sand %.1f m"), Hidamari.Lap(), BelmonteTurf.Lap(), BelmonteSand.Lap());
    return true;
}

const FRacingCourse* ARacingService::GetCourse(ERacingVenue Venue, uint8 Track) const
{
    const FRacingCourse* Course = (Venue == ERacingVenue::Belmonte) ? (Track == 1 ? &BelmonteSand : &BelmonteTurf) : &Hidamari;
    return Course->IsValid() ? Course : nullptr;
}

bool ARacingService::RunnerAt(const FRacingNetRace& Race, int32 Index, double Time, FVector& Where, float& Yaw, double& Speed) const
{
    const FRacingCourse* Course = GetCourse(ERacingVenue(Race.Venue), Race.Track);
    if (!Course || !Race.Runners.IsValidIndex(Index)) return false;
    const double D = RacingMotion::Distance(Race.Runners[Index].Plan(Race.Distance), Time - Race.Start, &Speed);
    // S is metres from the finish post: the start is Distance metres before it.
    Where = Course->At(D - Race.Distance, Course->LaneOffset(Index, Race.Runners.Num()), &Yaw);
    return true;
}

// ------------------------------------------------------------------------------------------------------------ runners

bool ARacingService::LoadLooks()
{
    if (bLooksTried) return bLooksLoaded;
    bLooksTried = true;
    // Every breed, gait, saddle, coat and jockey clip is required: a runner is never shown riderless, in another breed or
    // coat, or with a missing gait. tools/racing_assets.py (data.racing_assets) checks the same list before the cook.
    TArray<FString> Missing;
    const TSharedPtr<FJsonObject> Roster = AtelierReadJson(AtelierDataPath(TEXT("horses/roster.json")));
    const TSharedPtr<FJsonObject>* Breeds = nullptr;
    if (!Roster || !Roster->TryGetObjectField(TEXT("breeds"), Breeds))
    {
        UE_LOG(LogTemp, Error, TEXT("RACING no horse roster (%s): runners are not shown"), *AtelierDataPath(TEXT("horses/roster.json")));
        return false;
    }
    FString Tack;
    const TArray<TSharedPtr<FJsonValue>>* TackSets = nullptr;
    if (Roster->TryGetArrayField(TEXT("tack_sets"), TackSets) && TackSets->Num()) Tack = (*TackSets)[0]->AsString();
    else Missing.Add(TEXT("tack sets"));
    FString ReferenceSlug;
    Roster->TryGetStringField(TEXT("reference_breed"), ReferenceSlug);
    FVector RefSaddle = FVector::ZeroVector;
    double RefSeat = 0.;
    const TSharedPtr<FJsonObject>* RefBreed = nullptr;
    if (!(*Breeds)->TryGetObjectField(ReferenceSlug, RefBreed) || !UHorseComponent::ReadSeatContacts(*RefBreed, RefSaddle, RefSeat))
        Missing.Add(FString::Printf(TEXT("reference breed '%s' contacts"), *ReferenceSlug));
    for (int32 I = 0; I < RacingLooks::BreedCount; ++I)
    {
        FLookBreed Look;
        Look.Slug = RacingLooks::Breeds[I];
        const TSharedPtr<FJsonObject>* Breed = nullptr;
        FString MeshPath;
        if (!(*Breeds)->TryGetObjectField(Look.Slug, Breed) || !(*Breed)->TryGetStringField(TEXT("mesh"), MeshPath) ||
            !(Look.Mesh = LoadObject<USkeletalMesh>(nullptr, *MeshPath)))
        {
            Missing.Add(FString::Printf(TEXT("breed %s mesh"), *Look.Slug));
            LookBreeds.Add(MoveTemp(Look));
            continue;
        }
        double Yaw = -90.;
        (*Breed)->TryGetNumberField(TEXT("mesh_yaw"), Yaw);
        Look.MeshYaw = float(Yaw);
        const TSharedPtr<FJsonObject>* Clips = nullptr;
        (*Breed)->TryGetObjectField(TEXT("clips"), Clips);
        for (int32 G = 0; G < RacingLooks::GaitCount; ++G)
        {
            const TSharedPtr<FJsonObject>* Clip = nullptr;
            FString ClipPath;
            UAnimSequence* Sequence = nullptr;
            if (Clips && (*Clips)->TryGetObjectField(RacingLooks::HorseClips[G], Clip) && (*Clip)->TryGetStringField(TEXT("path"), ClipPath))
                Sequence = LoadObject<UAnimSequence>(nullptr, *ClipPath);
            if (!Sequence) Missing.Add(FString::Printf(TEXT("breed %s clip %s"), *Look.Slug, RacingLooks::HorseClips[G]));
            Look.Clips.Add(Sequence);
            Held.Add(Sequence);
        }
        const TSharedPtr<FJsonObject>* Saddles = nullptr;
        FString SaddlePath;
        if ((*Breed)->TryGetObjectField(TEXT("saddles"), Saddles) && (*Saddles)->TryGetStringField(Tack, SaddlePath))
            Look.Saddle = LoadObject<USkeletalMesh>(nullptr, *SaddlePath);
        if (!Look.Saddle) Missing.Add(FString::Printf(TEXT("breed %s saddle %s"), *Look.Slug, *Tack));
        FVector Saddle;
        double Seat = 0.;
        if (UHorseComponent::ReadSeatContacts(*Breed, Saddle, Seat))
        {
            Look.SeatForward = float(Saddle.X - RefSaddle.X);
            Look.SeatUp = float(Seat - RefSeat);
            Look.SeatZ = float(Seat);
        }
        else Missing.Add(FString::Printf(TEXT("breed %s seat contacts"), *Look.Slug));
        Held.Add(Look.Mesh);
        Held.Add(Look.Saddle);
        LookBreeds.Add(MoveTemp(Look));
    }
    CoatTextures.Init(FString(), RacingLooks::CoatCount);
    const TArray<TSharedPtr<FJsonValue>>* Variants = nullptr;
    if (Roster->TryGetArrayField(TEXT("coat_variants"), Variants))
        for (const TSharedPtr<FJsonValue>& Value : *Variants)
        {
            const TSharedPtr<FJsonObject>* Item = nullptr;
            FString Id, Texture;
            if (Value->TryGetObject(Item) && (*Item)->TryGetStringField(TEXT("id"), Id) && (*Item)->TryGetStringField(TEXT("texture"), Texture))
            {
                const int32 Index = RacingLooks::CoatIndex(*Id);
                if (Index > 0) CoatTextures[Index] = Texture;
            }
        }
    for (int32 C = 1; C < RacingLooks::CoatCount; ++C)
        if (CoatTextures[C].IsEmpty()) Missing.Add(FString::Printf(TEXT("coat %s texture"), RacingLooks::Coats[C]));
    // The jockey: the default character on his horse clips (authored on the reference breed), seated by the breed's offset.
    FString Rig;
    const UClass* Class = FPlayableCharacter::Default().Class();
    const AWandererCharacter* CDO = Class ? Cast<AWandererCharacter>(Class->GetDefaultObject()) : nullptr;
    if (CDO)
    {
        const USkeletalMeshComponent* Body = CDO->GetMesh();
        Rig = CDO->GetBikeRig();
        // A data-defined character gets its body from its definition when it starts playing (AWandererCharacter).
        const AMoverCharacter* Mover = Cast<AMoverCharacter>(CDO);
        const UWandererDefinition* Definition = Mover && !Mover->DefinitionPath.IsEmpty()
            ? LoadObject<UWandererDefinition>(nullptr, *Mover->DefinitionPath) : nullptr;
        JockeyMesh = Definition && Definition->Mesh ? Definition->Mesh.Get() : (Body ? Body->GetSkeletalMeshAsset() : nullptr);
        if (JockeyMesh && Body && !Rig.IsEmpty())
        {
            JockeyYaw = float(Body->GetRelativeRotation().Yaw);
            JockeyScale = Body->GetRelativeScale3D();
            for (int32 G = 0; G < RacingLooks::GaitCount; ++G)
            {
                UAnimSequence* Clip = LoadObject<UAnimSequence>(nullptr, *FString::Printf(TEXT("/Game/%sHorse/A_%s.A_%s"), *Rig,
                    RacingLooks::RiderClips[G], RacingLooks::RiderClips[G]));
                if (Clip && Clip->GetSkeleton() != JockeyMesh->GetSkeleton()) Clip = nullptr;
                if (!Clip) Missing.Add(FString::Printf(TEXT("jockey clip /Game/%sHorse/A_%s"), *Rig, RacingLooks::RiderClips[G]));
                JockeyClips.Add(Clip);
                Held.Add(Clip);
            }
        }
    }
    if (!JockeyMesh || JockeyClips.Num() != RacingLooks::GaitCount)
        Missing.Add(FString::Printf(TEXT("the default character's jockey mesh and rig (rig '%s')"), *Rig));
    bLooksLoaded = Missing.IsEmpty();
    if (!bLooksLoaded)
        UE_LOG(LogTemp, Error, TEXT("RACING runners are not shown: missing %s (run `atelier build yorimichi data.racing_assets`)"),
            *FString::Join(Missing, TEXT(", ")));
    return bLooksLoaded;
}

void ARacingService::ClearRunners()
{
    for (FShown& S : Shown)
    {
        for (USkeletalMeshComponent* C : {S.Jockey.Get(), S.Saddle.Get(), S.Horse.Get()})
            if (C) C->DestroyComponent();
    }
    Shown.Reset();
    ShownKey.Reset();
}

bool ARacingService::SpawnRunners(const FRacingNetRace& Race)
{
    if (!LoadLooks()) return false;
    auto Part = [&](const TCHAR* Prefix, int32 Index)
    {
        auto* C = NewObject<USkeletalMeshComponent>(this, MakeUniqueObjectName(this, USkeletalMeshComponent::StaticClass(), *FString::Printf(TEXT("%s%d"), Prefix, Index)));
        C->SetupAttachment(RootComponent);
        C->SetMobility(EComponentMobility::Movable);
        C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        C->SetCanEverAffectNavigation(false);
        C->SetAnimationMode(EAnimationMode::AnimationSingleNode);
        C->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::OnlyTickPoseWhenRendered;
        C->bEnableUpdateRateOptimizations = true;
        C->SetUsingAbsoluteLocation(true);
        C->SetUsingAbsoluteRotation(true);
        C->SetUsingAbsoluteScale(true);
        return C;
    };
    // Each runner's own breed and coat, or no field at all: never a stand-in (LoadLooks has checked the breeds).
    TArray<UTexture2D*> Coats;
    for (const FRacingNetRunner& R : Race.Runners)
    {
        UTexture2D* Coat = nullptr;
        if (!LookBreeds.IsValidIndex(R.Breed) || !CoatTextures.IsValidIndex(R.Coat) ||
            (R.Coat > 0 && !(Coat = LoadObject<UTexture2D>(nullptr, *CoatTextures[R.Coat]))))
        {
            UE_LOG(LogTemp, Error, TEXT("RACING %s: runner %s has breed %d and coat %d, which this game cannot show: the field is not shown"),
                *Race.Key, *R.Horse, R.Breed, R.Coat);
            return false;
        }
        Coats.Add(Coat);
    }
    for (int32 I = 0; I < Race.Runners.Num(); ++I)
    {
        const FRacingNetRunner& R = Race.Runners[I];
        FShown S;
        S.Breed = R.Breed;
        const FLookBreed& Look = LookBreeds[S.Breed];
        const float Scale = FMath::Clamp(R.Scale / 100.f, .8f, 1.2f);
        S.Horse = Part(TEXT("RaceHorse"), I);
        S.Horse->SetSkeletalMesh(Look.Mesh);
        S.Horse->SetWorldScale3D(FVector(Scale));
        S.Horse->RegisterComponent();
        // The coat: a dynamic instance of each coat slot with the variant's texture (as UHorseComponent's look).
        if (UTexture2D* Texture = Coats[I])
        {
            int32 Painted = 0;
            for (int32 M = 0; M < S.Horse->GetNumMaterials(); ++M)
            {
                UMaterialInterface* Imported = S.Horse->GetMaterial(M);
                const FString BaseName = Imported && Imported->GetBaseMaterial() ? Imported->GetBaseMaterial()->GetName() : FString();
                if (BaseName != TEXT("M_HorseCoat")) continue;
                UMaterialInstanceDynamic* Coat = UMaterialInstanceDynamic::Create(Imported, this);
                Coat->SetTextureParameterValue(TEXT("BaseColorTexture"), Texture);
                S.Horse->SetMaterial(M, Coat);
                ++Painted;
            }
            if (!Painted)
            {
                UE_LOG(LogTemp, Error, TEXT("RACING breed %s has no M_HorseCoat slot for %s's coat: the field is not shown"), *Look.Slug, *R.Horse);
                S.Horse->DestroyComponent();
                ClearRunners();
                return false;
            }
        }
        S.Saddle = Part(TEXT("RaceSaddle"), I);
        // Attached to the horse: the leader pose moves its bones, the attachment its transform.
        S.Saddle->SetUsingAbsoluteLocation(false);
        S.Saddle->SetUsingAbsoluteRotation(false);
        S.Saddle->SetUsingAbsoluteScale(false);
        S.Saddle->SetupAttachment(S.Horse);
        S.Saddle->SetSkeletalMesh(Look.Saddle);
        S.Saddle->RegisterComponent();
        S.Saddle->SetLeaderPoseComponent(S.Horse, true);
        // The stable's colours on the saddle and its cloth.
        if (SilksMaterial)
        {
            UMaterialInstanceDynamic* Silks = UMaterialInstanceDynamic::Create(SilksMaterial, this);
            Silks->SetVectorParameterValue(TEXT("Color"), FLinearColor(R.Silks));
            for (int32 M = 0; M < S.Saddle->GetNumMaterials(); ++M) S.Saddle->SetMaterial(M, Silks);
        }
        S.Jockey = Part(TEXT("RaceJockey"), I);
        S.Jockey->SetSkeletalMesh(JockeyMesh);
        S.Jockey->SetWorldScale3D(JockeyScale);
        S.Jockey->RegisterComponent();
        // Each horse starts its cycle at a different point, so the field does not step in unison.
        S.Phase = FMath::Frac(I * .37);
        Shown.Add(S);
    }
    ShownKey = Race.Key;
    ShownStart = Race.Start;
    UE_LOG(LogTemp, Display, TEXT("RACING runners shown: %d for %s at %s"), Shown.Num(), *Race.Name, RacingLooks::VenueName(ERacingVenue(Race.Venue)));
    return true;
}

FVector ARacingService::LocalViewer() const
{
    const UWorld* World = GetWorld();
    const APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
    if (!PC || !PC->IsLocalController()) return FVector(TNumericLimits<float>::Max());
    if (const APawn* Pawn = PC->GetPawn()) return Pawn->GetActorLocation();
    return PC->PlayerCameraManager ? PC->PlayerCameraManager->GetCameraLocation() : FVector(TNumericLimits<float>::Max());
}

/** Within about 600 m of the course (its centre plus half its span). */
static bool NearCourse(const FRacingCourse& Course, const FVector& Where)
{
    const double Span = Course.bOval ? Course.Oval.Half + Course.Oval.Radius : 380.;
    return FVector::Dist2D(Course.Centre(), Where) < (600. + Span) * 100.;
}

void ARacingService::TickPresentation(float DeltaSeconds)
{
    if (GetNetMode() == NM_DedicatedServer) return;
    const FRacingNetRace& Race = Net.Race;
    const double Now = WorldNow();
    const double T = Now - Race.Start;
    const FRacingCourse* Course = Net.Serial && !Race.Key.IsEmpty() ? GetCourse(ERacingVenue(Race.Venue), Race.Track) : nullptr;
    // Near the venue, or wherever the player watches the race on a TV (the broadcast camera films the field at the venue).
    const bool bWanted = Course && !Race.Runners.IsEmpty() && T >= -RacingMotion::ParadeSeconds && T <= HRClock::RaceSeconds &&
        (bBroadcastAudience || NearCourse(*Course, LocalViewer()));
    if (!bWanted)
    {
        if (!Shown.IsEmpty()) ClearRunners();
        SetActorTickInterval(.25f);
        return;
    }
    if (ShownKey != Race.Key || ShownStart != Race.Start || Shown.Num() != Race.Runners.Num())
    {
        ClearRunners();
        // A field that cannot be shown has said why once (LoadLooks, SpawnRunners): no retry until the next race.
        const FString Attempt = FString::Printf(TEXT("%s@%.0f"), *Race.Key, Race.Start);
        if (FailedKey == Attempt || !SpawnRunners(Race)) { FailedKey = Attempt; SetActorTickInterval(1.f); return; }
    }
    SetActorTickInterval(0.f);
    const UWorld* World = GetWorld();
    for (int32 I = 0; I < Shown.Num(); ++I)
    {
        FShown& S = Shown[I];
        FVector Where;
        float Yaw = 0.f;
        double Speed = 0.;
        if (!S.Horse || !RunnerAt(Race, I, Now, Where, Yaw, Speed)) continue;
        // The course data is coarse; a ground probe now and then follows the real surface under the hooves. Only walkable
        // ground near the authored height counts (RacingGround::Pick); after a miss the runner is back on the authored
        // height, never on a stale trace.
        const double Authored = Where.Z;
        if ((S.NextTrace -= DeltaSeconds) <= 0.f)
        {
            S.NextTrace = .4f;
            TArray<FHitResult> Hits;
            FCollisionObjectQueryParams Objects(ECC_WorldStatic);
            FCollisionQueryParams Query(SCENE_QUERY_STAT(RacingGround), false, this);
            World->LineTraceMultiByObjectType(Hits, Where + FVector(0, 0, RacingGround::Above), Where - FVector(0, 0, RacingGround::Below), Objects, Query);
            TArray<RacingGround::FHit, TInlineAllocator<8>> Candidates;
            for (const FHitResult& Hit : Hits) Candidates.Add({Hit.ImpactPoint.Z, FVector(Hit.ImpactNormal)});
            double Ground = Authored;
            if (RacingGround::Pick(Candidates, Authored, Ground))
            {
                const float Offset = float(Ground - Authored);
                S.GroundOffset = S.bGround ? FMath::Lerp(S.GroundOffset, Offset, .5f) : Offset;
                S.bGround = true;
            }
            else S.bGround = false;
        }
        Where.Z = S.bGround ? Authored + S.GroundOffset : Authored;
        const FLookBreed& Look = LookBreeds[S.Breed];
        S.Horse->SetWorldLocationAndRotation(Where, FRotator(0.f, Yaw + Look.MeshYaw, 0.f));
        const float Scale = S.Horse->GetComponentScale().X;
        if (S.Jockey)
        {
            // Seated as on the reference breed, moved by this breed's (scaled) saddle offset.
            const FVector Seat(Look.SeatForward, 0.f, Look.SeatUp + (Scale - 1.f) * Look.SeatZ);
            S.Jockey->SetWorldLocationAndRotation(Where + FRotator(0.f, Yaw, 0.f).RotateVector(Seat), FRotator(0.f, Yaw + JockeyYaw, 0.f));
        }
        // The gait follows the speed; horse and jockey share one phase through the clip, faster through the gait's band.
        const float SpeedCm = float(Speed * 100.);
        const int32 Gait = RacingLooks::GaitFor(SpeedCm);
        UAnimSequence* Clip = Look.Clips[Gait].Get();
        const float Length = FMath::Max(Clip->GetPlayLength(), .033f);
        S.Phase = FMath::Frac(S.Phase + DeltaSeconds * RacingLooks::RateFor(Gait, SpeedCm) / Length);
        UAnimSequence* Ride = JockeyClips[Gait].Get();
        if (Gait != S.Gait)
        {
            S.Horse->SetAnimation(Clip);
            S.Horse->SetPlayRate(0.f);
            if (S.Jockey && Ride) { S.Jockey->SetAnimation(Ride); S.Jockey->SetPlayRate(0.f); }
            S.Gait = Gait;
        }
        // Off screen the pose waits (OnlyTickPoseWhenRendered); the phase still runs, so it is right when seen again. The TVs'
        // capture draws it too.
        if (!bBroadcastAudience && !S.Horse->WasRecentlyRendered(.25f)) continue;
        S.Horse->SetPosition(FMath::Min(float(S.Phase) * Length, Length - .001f), false);
        if (S.Jockey && Ride)
        {
            const float RideLength = FMath::Max(Ride->GetPlayLength(), .033f);
            S.Jockey->SetPosition(FMath::Min(float(S.Phase) * RideLength, RideLength - .001f), false);
        }
    }
}

// ------------------------------------------------------------------------------------------------------------ HUD, travel, live

FString ARacingService::HudLine(const AWandererCharacter* Pawn) const
{
    if (!Pawn || !Net.Serial || !bCoursesLoaded) return FString();
    const FVector At = Pawn->GetActorLocation();
    ERacingVenue Near = ERacingVenue::Count;
    for (const ERacingVenue V : {ERacingVenue::Hidamari, ERacingVenue::Belmonte})
        if (const FRacingCourse* C = GetCourse(V); C && C->ContainsGrounds(At)) { Near = V; break; }
    if (Near == ERacingVenue::Count) return FString();
    const FString Venue = FString::Printf(TEXT("%s Hippodrome"), RacingLooks::VenueName(Near));
    const double Now = WorldNow();
    const FRacingNetRace& Race = Net.Race;
    const FRacingNetResult& Last = Net.Last;
    FString Result;
    if (!Last.Top.IsEmpty() && ERacingVenue(Last.Venue) == Near && Now - Last.Finished < 300.)
    {
        Result = TEXT("Results: ");
        for (int32 I = 0; I < Last.Top.Num(); ++I) Result += FString::Printf(TEXT("%s%d. %s"), I ? TEXT("   ") : TEXT(""), I + 1, *Last.Top[I]);
    }
    if (Race.Key.IsEmpty())
        return FString::Printf(TEXT("%s   ·   %s%sNext meeting in %s"), *Venue, *Result, Result.IsEmpty() ? TEXT("") : TEXT("   ·   "),
            *RacingLooks::Countdown(Net.NextMeeting - Now));
    const double T = Now - Race.Start;
    if (ERacingVenue(Race.Venue) != Near)
    {
        // The race is at the other venue: its countdown, live there (on the TVs), then where the field arrived.
        const TCHAR* There = RacingLooks::VenueName(ERacingVenue(Race.Venue));
        double Home = 0.;
        for (const FRacingNetRunner& R : Race.Runners) if (R.Place == 1 && R.SplitMs.Num() == 4) Home = R.SplitMs[3] / 1000.;
        if (T < 0.)
            return FString::Printf(TEXT("%s   ·   Today's races at %s: %s in %s"), *Venue, There, *Race.Name, *RacingLooks::Countdown(-T));
        if (!Race.bRun || T < Home) return FString::Printf(TEXT("%s   ·   Live from %s: %s"), *Venue, There, *Race.Name);
        return FString::Printf(TEXT("%s   ·   %s at %s: finished"), *Venue, *Race.Name, There);
    }
    if (T < 0.)
        return FString::Printf(TEXT("%s   ·   %s%sNext race: %s (%d m) — %s"), *Venue, *Result, Result.IsEmpty() ? TEXT("") : TEXT("   ·   "),
            *Race.Name, Race.Distance, *RacingLooks::Countdown(-T));
    double Winner = 0.;
    for (const FRacingNetRunner& R : Race.Runners) if (R.Place == 1 && R.SplitMs.Num() == 4) Winner = R.SplitMs[3] / 1000.;
    if (!Race.bRun || T < Winner) return FString::Printf(TEXT("%s   ·   Race in progress: %s — %d m"), *Venue, *Race.Name, Race.Distance);
    if (!Result.IsEmpty()) return FString::Printf(TEXT("%s   ·   %s   ·   %s"), *Venue, *Race.Name, *Result);
    TArray<const FRacingNetRunner*> Order;
    for (const FRacingNetRunner& R : Race.Runners) if (R.Place > 0) Order.Add(&R);
    Order.Sort([](const FRacingNetRunner& A, const FRacingNetRunner& B) { return A.Place < B.Place; });
    FString Top;
    for (int32 I = 0; I < FMath::Min(3, Order.Num()); ++I) Top += FString::Printf(TEXT("%s%d. %s"), I ? TEXT("   ") : TEXT(""), I + 1, *Order[I]->Horse);
    return FString::Printf(TEXT("%s   ·   %s   ·   Results: %s"), *Venue, *Race.Name, *Top);
}

bool ARacingService::GoToVenue(const FString& Name)
{
    ERacingVenue Venue = ERacingVenue(Net.Race.Venue);
    if (Name.StartsWith(TEXT("hid"))) Venue = ERacingVenue::Hidamari;
    else if (Name.StartsWith(TEXT("bel"))) Venue = ERacingVenue::Belmonte;
    const FRacingCourse* Course = GetCourse(Venue, Venue == ERacingVenue(Net.Race.Venue) ? Net.Race.Track : 0);
    APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
    auto* Player = PC ? Cast<AWandererCharacter>(PC->GetPawn()) : nullptr;
    if (!Course || !Player) return false;
    // Outside the outer rail just past the post, facing across the track.
    float Yaw = 0.f;
    const double Out = Course->OuterLane + 9.;
    const FVector Stand = Course->At(15., Out, &Yaw);
    const FVector Track = Course->At(15., Course->InnerLane, nullptr);
    const float Facing = float(FMath::RadiansToDegrees(FMath::Atan2(Track.Y - Stand.Y, Track.X - Stand.X)));
    const bool bMoved = Player->TravelTo(Stand, Facing, TEXT("racecourse"), 400.f);
    UE_LOG(LogTemp, Display, TEXT("RACING GO %s moved=%d at=(%.0f,%.0f,%.0f)"), RacingLooks::VenueName(Venue), bMoved, Stand.X, Stand.Y, Stand.Z);
    return bMoved;
}

FString ARacingService::StateJson() const
{
    const double Now = WorldNow();
    const FRacingNetRace& Race = Net.Race;
    FString Runners;
    for (int32 I = 0; I < Race.Runners.Num(); ++I)
    {
        FVector Where;
        float Yaw = 0.f;
        double Speed = 0.;
        const bool bPlaced = RunnerAt(Race, I, Now, Where, Yaw, Speed);
        const FRacingNetRunner& R = Race.Runners[I];
        Runners += FString::Printf(TEXT("%s{\"horse\":\"%s\",\"stable\":\"%s\",\"jockey\":\"%s\",\"odds\":%.1f,\"breed\":%d,\"coat\":%d,\"place\":%d,"
            "\"distance\":%.1f,\"speed\":%.2f,\"at\":[%.0f,%.0f,%.0f],\"placed\":%s}"), I ? TEXT(",") : TEXT(""),
            *R.Horse.ReplaceCharWithEscapedChar(), *R.Stable.ReplaceCharWithEscapedChar(), *R.Jockey.ReplaceCharWithEscapedChar(), R.OddsTenths / 10.,
            R.Breed, R.Coat, R.Place, RacingMotion::Distance(R.Plan(Race.Distance), Now - Race.Start), Speed, Where.X, Where.Y, Where.Z,
            bPlaced ? TEXT("true") : TEXT("false"));
    }
    FString Top;
    for (int32 I = 0; I < Net.Last.Top.Num(); ++I) Top += FString::Printf(TEXT("%s\"%s\""), I ? TEXT(",") : TEXT(""), *Net.Last.Top[I].ReplaceCharWithEscapedChar());
    return FString::Printf(TEXT("{\"serial\":%u,\"host\":%s,\"world\":%.2f,\"scale\":%.2f,\"day\":%d,\"event\":\"%s\",\"grand_prix\":%s,"
        "\"race\":{\"key\":\"%s\",\"name\":\"%s\",\"venue\":\"%s\",\"track\":%d,\"distance\":%d,\"start\":%.2f,\"t\":%.2f,\"run\":%s,\"runners\":[%s]},"
        "\"last\":{\"race\":\"%s\",\"top\":[%s]},\"shown\":%d,\"courses\":%s,\"players\":%d,\"save\":\"%s\"}"),
        Net.Serial, HasAuthority() ? TEXT("true") : TEXT("false"), Now, Net.Scale, Net.Day, *Net.Event.ReplaceCharWithEscapedChar(),
        Net.bGrandPrix ? TEXT("true") : TEXT("false"), *Race.Key, *Race.Name.ReplaceCharWithEscapedChar(),
        RacingLooks::VenueName(ERacingVenue(Race.Venue)), Race.Track, Race.Distance, Race.Start, Now - Race.Start, Race.bRun ? TEXT("true") : TEXT("false"),
        *Runners, *Net.Last.Race.ReplaceCharWithEscapedChar(), *Top, Shown.Num(), bCoursesLoaded ? TEXT("true") : TEXT("false"),
        bHasWorld ? State.Players.Num() : -1, *SavePath.ReplaceCharWithEscapedChar());
}

FString URacingLive::RacingState()
{
    const ARacingService* Service = ARacingService::Find(ULiveLibrary::GameWorld());
    return Service ? Service->StateJson() : FString(TEXT("{}"));
}

bool URacingLive::RacingNext(float Lead)
{
    ARacingService* Service = ARacingService::Find(ULiveLibrary::GameWorld());
    return Service && Service->JumpToNextRace(Lead);
}

bool URacingLive::RacingGo(const FString& Venue)
{
    ARacingService* Service = ARacingService::Find(ULiveLibrary::GameWorld());
    return Service && Service->GoToVenue(Venue);
}

FVector URacingLive::RacingViewPoint(float Along, float Outwards, float& Yaw)
{
    Yaw = 0.f;
    const ARacingService* Service = ARacingService::Find(ULiveLibrary::GameWorld());
    const FRacingNetRace* Race = Service ? &Service->GetNetState().Race : nullptr;
    const FRacingCourse* Course = Race ? Service->GetCourse(ERacingVenue(Race->Venue), Race->Track) : nullptr;
    if (!Course) return FVector::ZeroVector;
    const FVector View = Course->At(Along, Outwards, nullptr);
    const FVector Track = Course->At(Along, (Course->InnerLane + Course->OuterLane) * .5, nullptr);
    Yaw = float(FMath::RadiansToDegrees(FMath::Atan2(Track.Y - View.Y, Track.X - View.X)));
    return View;
}

FString URacingLive::RacingTvState()
{
    const ARacingBroadcast* Broadcast = ARacingBroadcast::Find(ULiveLibrary::GameWorld());
    return Broadcast ? Broadcast->StateJson() : FString(TEXT("{}"));
}

bool URacingLive::RacingTvGo(const FString& Spot)
{
    ARacingBroadcast* Broadcast = ARacingBroadcast::Find(ULiveLibrary::GameWorld());
    return Broadcast && Broadcast->GoToScreen(Spot);
}

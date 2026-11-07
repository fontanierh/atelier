#include "JapanMusic.h"
#include "EngineUtils.h"
#include "Engine/Engine.h"
#include "FoxHunter.h"
#include "HorseComponent.h"
#include "BikeComponent.h"
#include "SailboatComponent.h"
#include "JapanMap.h"
#include "MediaPlayer.h"
#include "MediaSoundComponent.h"
#include "SkateComponent.h"
#include "WandererCharacter.h"
#include "Dom/JsonObject.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "HAL/IConsoleManager.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
    // The music sits under the sound effects: footsteps, wheels and blades stay in front. The player's Music volume
    // scales this.
    constexpr float BaseLevel = .42f;
    constexpr double DecideEvery = .5;
    // An engaged enemy this close (cm) is a fight; the fight holds this long after the last one lets go.
    constexpr float CombatRadius = 3000.f;
    constexpr double CombatHold = 6.;
    struct FArea { const TCHAR* Zone; const TCHAR* Area; float RadiusMetres; };
    // Every map zone's music area and how far it reaches. The nearest zone in reach wins; elsewhere is "wild".
    const FArea Areas[] = {
        {TEXT("arrival"), TEXT("town"), 160}, {TEXT("arcade"), TEXT("town"), 160}, {TEXT("plaza"), TEXT("town"), 160},
        {TEXT("hillside"), TEXT("town"), 160}, {TEXT("park"), TEXT("town"), 180}, {TEXT("station"), TEXT("town"), 160},
        {TEXT("zeppelin_city"), TEXT("town"), 120}, {TEXT("communitypark"), TEXT("park"), 120},
        {TEXT("harbor"), TEXT("coast"), 160}, {TEXT("fishing"), TEXT("coast"), 120}, {TEXT("cove"), TEXT("coast"), 120},
        {TEXT("spawn"), TEXT("coast"), 140}, {TEXT("landing"), TEXT("coast"), 160},
        {TEXT("skatepier"), TEXT("pier"), 90}, {TEXT("brinecove_quay"), TEXT("brinecove"), 450},
        {TEXT("craterpark"), TEXT("crater"), 420},
        {TEXT("mega"), TEXT("park"), 110}, {TEXT("megapark"), TEXT("park"), 220}, {TEXT("zeppelin_megapark"), TEXT("park"), 120},
        {TEXT("belmonte"), TEXT("belmonte"), 260}, {TEXT("belmonte_training"), TEXT("belmonte"), 160},
        {TEXT("zeppelin_belmonte"), TEXT("belmonte"), 120}, {TEXT("belmonte_salon"), TEXT("salon"), 70},
        {TEXT("belmonte_course"), TEXT("course"), 260}, {TEXT("hippodrome"), TEXT("course"), 260},
        {TEXT("forest_lake"), TEXT("nature"), 220}, {TEXT("temple"), TEXT("nature"), 160}, {TEXT("hamlet"), TEXT("hamlet"), 160},
        {TEXT("foothills"), TEXT("nature"), 260}, {TEXT("zeppelin_forest"), TEXT("nature"), 120}};
    const FArea* FindArea(const FString& Zone)
    {
        for (const FArea& A : Areas) if (Zone == A.Zone) return &A;
        return nullptr;
    }
    FAutoConsoleCommandWithWorld MusicStatus(TEXT("japan.MusicStatus"), TEXT("Log the soundtrack's pool, track and rest."),
        FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
        {
            // The game's world, whichever world the command arrived with.
            if (GEngine && (!World || !World->IsGameWorld()))
                for (const FWorldContext& Context : GEngine->GetWorldContexts())
                    if (Context.World() && Context.World()->IsGameWorld()) { World = Context.World(); break; }
            const UJapanMusic* Music = World ? World->GetSubsystem<UJapanMusic>() : nullptr;
            UE_LOG(LogTemp, Display, TEXT("MUSIC %s"), Music ? *Music->Describe() : TEXT("music: no game world"));
        }));
    float EqualPower(float X) { return FMath::Sin(FMath::Clamp(X, 0.f, 1.f) * HALF_PI); }
}

FString FJapanMusicRules::AreaForZone(const FString& Zone)
{
    const FArea* A = FindArea(Zone);
    return A ? FString(A->Area) : FString(TEXT("wild"));
}

FString FJapanMusicRules::PoolName(EJapanMusicScene Scene, const FString& Area)
{
    switch (Scene)
    {
    case EJapanMusicScene::Combat: return TEXT("combat");
    case EJapanMusicScene::Skate:
        if (Area == TEXT("crater")) return TEXT("skate_crater");
        if (Area == TEXT("pier")) return TEXT("skate_pier");
        return TEXT("skate");
    case EJapanMusicScene::Sail: return TEXT("sail");
    case EJapanMusicScene::Air: return TEXT("air");
    case EJapanMusicScene::Ride: return Area == TEXT("course") ? TEXT("course") : TEXT("ride");
    default: return Area;
    }
}

TArray<FString> FJapanMusicRules::PoolGroups(const FString& Pool, const FString& Zone)
{
    // Style cues give each pool its colour; the zone's own score joins calm exploration pools so a place keeps
    // its theme among the lofi and jazz. Combat stays on the lighter fight cues: no boss or siege music for a skirmish.
    TArray<FString> Groups;
    const auto Add = [&Groups](std::initializer_list<const TCHAR*> List) { for (const TCHAR* G : List) Groups.Add(G); };
    if (Pool == TEXT("combat")) Add({TEXT("skirmish"), TEXT("ambush"), TEXT("energy_duel"), TEXT("energy_taiko")});
    else if (Pool == TEXT("skate_crater")) Add({TEXT("energy_breakbeat"), TEXT("energy_dnb"), TEXT("energy_festival"), TEXT("energy_race"), TEXT("craterpark")});
    else if (Pool == TEXT("skate_pier")) Add({TEXT("jazz_harbor"), TEXT("jazz_salon"), TEXT("lofi_seaside"), TEXT("lofi_coffee"), TEXT("lofi_rooftop")});
    else if (Pool == TEXT("skate")) Add({TEXT("lofi_rooftop"), TEXT("lofi_market"), TEXT("lofi_train"), TEXT("lofi_dojo"), TEXT("energy_festival")});
    else if (Pool == TEXT("town")) Add({TEXT("lofi_market"), TEXT("lofi_coffee"), TEXT("lofi_study"), TEXT("lofi_rooftop")});
    else if (Pool == TEXT("coast")) Add({TEXT("lofi_seaside"), TEXT("lofi_lighthouse"), TEXT("jazz_harbor")});
    else if (Pool == TEXT("brinecove")) Add({TEXT("jazz_harbor"), TEXT("lofi_lighthouse"), TEXT("lofi_seaside")});
    else if (Pool == TEXT("pier")) Add({TEXT("jazz_harbor"), TEXT("lofi_seaside"), TEXT("lofi_coffee")});
    else if (Pool == TEXT("park")) Add({TEXT("lofi_rooftop"), TEXT("lofi_study"), TEXT("calm_dawn")});
    else if (Pool == TEXT("crater")) Add({TEXT("calm_high"), TEXT("craterpark")});
    else if (Pool == TEXT("belmonte")) Add({TEXT("jazz_salon"), TEXT("jazz_harbor"), TEXT("lofi_coffee")});
    else if (Pool == TEXT("salon")) Add({TEXT("jazz_salon"), TEXT("jazz_harbor")});
    else if (Pool == TEXT("course")) Add({TEXT("energy_festival"), TEXT("world_koto")});
    else if (Pool == TEXT("hamlet")) Add({TEXT("world_koto"), TEXT("lofi_dojo"), TEXT("calm_dawn")});
    else if (Pool == TEXT("sail")) Add({TEXT("lofi_seaside"), TEXT("lofi_lighthouse"), TEXT("jazz_harbor"), TEXT("calm_dawn")});
    else if (Pool == TEXT("air")) Add({TEXT("calm_high"), TEXT("lofi_train")});
    else if (Pool == TEXT("ride")) Add({TEXT("lofi_train"), TEXT("lofi_rooftop"), TEXT("calm_dawn")});
    else Add({TEXT("calm_dawn"), TEXT("calm_high"), TEXT("lofi_study"), TEXT("lofi_dojo")});   // nature, wild
    // The zone's own takes, wherever the player stands in a calm pool.
    if (!Zone.IsEmpty() && Pool != TEXT("combat") && !Pool.StartsWith(TEXT("skate")) && Pool != TEXT("sail") && Pool != TEXT("air"))
        Groups.AddUnique(Zone);
    return Groups;
}

bool FJapanMusicRules::TakesRole(const FString& Pool, const FString& Group, const FString& Role)
{
    // Zone takes come as day, quiet and contrast. Contrast is the loud alternate: only Crater Park's skating uses it.
    if (Role != TEXT("day") && Role != TEXT("quiet") && Role != TEXT("contrast")) return true;
    if (Pool == TEXT("skate_crater")) return true;
    return Role != TEXT("contrast");
}

float FJapanMusicRules::Level(const FString& Pool)
{
    if (Pool == TEXT("combat") || Pool == TEXT("skate_crater")) return 1.1f;
    if (Pool.StartsWith(TEXT("skate"))) return 1.f;
    return .9f;
}

FString UJapanMusic::FindLibrary()
{
    FString Dir;
    if (FParse::Value(FCommandLine::Get(), TEXT("-music="), Dir) && !Dir.IsEmpty())
        return IFileManager::Get().FileExists(*FPaths::Combine(Dir, TEXT("catalog.json"))) ? Dir : FString();
    if (FParse::Param(FCommandLine::Get(), TEXT("nomusic"))) return FString();
    // Development play is not sandboxed: read the verified Atelier cache in place.
    const FString Home = FPlatformMisc::GetEnvironmentVariable(TEXT("HOME"));
    if (Home.IsEmpty()) return FString();
    Dir = FPaths::Combine(Home, TEXT(".cache/atelier/yorimichi/music"));
    return IFileManager::Get().FileExists(*FPaths::Combine(Dir, TEXT("catalog.json"))) ? Dir : FString();
}

bool UJapanMusic::LoadLibrary(const FString& Dir)
{
    FString Text;
    if (!FFileHelper::LoadFileToString(Text, *FPaths::Combine(Dir, TEXT("catalog.json")))) return false;
    TSharedPtr<FJsonObject> Root;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid()) return false;
    const TArray<TSharedPtr<FJsonValue>>* Rows = nullptr;
    if (!Root->TryGetArrayField(TEXT("tracks"), Rows)) return false;
    for (const TSharedPtr<FJsonValue>& Row : *Rows)
    {
        const TSharedPtr<FJsonObject>* O = nullptr;
        if (!Row.IsValid() || !Row->TryGetObject(O)) continue;
        FJapanMusicTrack T;
        FString Relative;
        if (!(*O)->TryGetStringField(TEXT("path"), Relative) || Relative.Contains(TEXT(".."))) continue;
        T.Path = FPaths::Combine(Dir, Relative);
        if (!IFileManager::Get().FileExists(*T.Path)) continue;
        (*O)->TryGetStringField(TEXT("title"), T.Title);
        (*O)->TryGetStringField(TEXT("group"), T.Group);
        (*O)->TryGetStringField(TEXT("role"), T.Role);
        (*O)->TryGetStringField(TEXT("style_family"), T.Style);
        double Seconds = 0.;
        if ((*O)->TryGetNumberField(TEXT("duration_s"), Seconds)) T.Seconds = float(Seconds);
        if (T.Seconds > 30.f) Tracks.Add(MoveTemp(T));
    }
    return Tracks.Num() > 0;
}

void UJapanMusic::OnWorldBeginPlay(UWorld& InWorld)
{
    Super::OnWorldBeginPlay(InWorld);
    if (InWorld.GetNetMode() == NM_DedicatedServer) return;
    LibraryDir = FindLibrary();
    if (LibraryDir.IsEmpty() || !LoadLibrary(LibraryDir))
    {
        UE_LOG(LogTemp, Display, TEXT("MUSIC off: no library%s"), LibraryDir.IsEmpty() ? TEXT("") : *(TEXT(" in ") + LibraryDir));
        return;
    }
    FActorSpawnParameters Spawn;
    Spawn.ObjectFlags |= RF_Transient;
    Holder = InWorld.SpawnActor<AActor>(AActor::StaticClass(), FTransform::Identity, Spawn);
    if (!Holder) return;
    for (int32 I = 0; I < 2; ++I)
    {
        UMediaPlayer* Player = NewObject<UMediaPlayer>(this);
        Player->PlayOnOpen = true;
        // Electra plays the library's MP3s; AvfMedia lists no mp3 extension.
        Player->SetDesiredPlayerName(FName(TEXT("ElectraPlayer")));
        Player->SetLooping(false);
        UMediaSoundComponent* Sound = NewObject<UMediaSoundComponent>(Holder);
        Sound->Channels = EMediaSoundChannels::Stereo;
        Sound->bAllowSpatialization = false;
        Sound->bIsUISound = true;   // keeps playing under the pause menu
        Sound->SetMediaPlayer(Player);
        Sound->SetVolumeMultiplier(0.f);
        Sound->RegisterComponent();
        Players.Add(Player);
        Sounds.Add(Sound);
    }
    Random.Initialize(int32(FDateTime::Now().GetTicks() & 0x7fffffff));
    // A first cue soon after arriving, then the rules take over.
    RestUntil = 8.;
    bStarted = true;
    UE_LOG(LogTemp, Display, TEXT("MUSIC library=%s tracks=%d"), *LibraryDir, Tracks.Num());
}

void UJapanMusic::Deinitialize()
{
    for (UMediaPlayer* Player : Players) if (Player) Player->Close();
    Players.Reset();
    Sounds.Reset();
    Holder = nullptr;
    bStarted = false;
    Super::Deinitialize();
}

TStatId UJapanMusic::GetStatId() const
{
    RETURN_QUICK_DECLARE_CYCLE_STAT(UJapanMusic, STATGROUP_Tickables);
}

void UJapanMusic::SetPreferences(bool bInEnabled, float InVolume)
{
    Volume = FMath::Clamp(InVolume, 0.f, 1.f);
    if (bEnabled && !bInEnabled)
        for (int32 C = 0; C < 2; ++C) if (IsAudible(C)) FadeOut(C, 2.5f);
    if (!bEnabled && bInEnabled) { RestUntil = Clock + 3.; Pool.Reset(); PendingPool.Reset(); }
    bEnabled = bInEnabled;
    for (int32 C = 0; C < 2 && bStarted; ++C) ApplyGain(C);
}

AWandererCharacter* UJapanMusic::LocalPawn() const
{
    const UWorld* World = GetWorld();
    const APlayerController* Controller = World ? World->GetFirstPlayerController() : nullptr;
    return Controller ? Cast<AWandererCharacter>(Controller->GetPawn()) : nullptr;
}

EJapanMusicScene UJapanMusic::ReadScene(AWandererCharacter* Pawn, FString& OutZone) const
{
    const FVector Where = Pawn->GetActorLocation();
    OutZone.Reset();
    if (const UJapanMap* Map = Pawn->GetMap())
    {
        double Best = TNumericLimits<double>::Max();
        for (const FJapanMapZone& Z : Map->GetZones())
            if (const FArea* A = FindArea(Z.Key))
            {
                const double Distance = FVector::Dist2D(Where, Z.Location);
                if (Distance < A->RadiusMetres * 100. && Distance < Best) { Best = Distance; OutZone = Z.Key; }
            }
    }
    for (TActorIterator<AFoxHunter> It(GetWorld()); It; ++It)
        if (It->IsAlive() && It->IsEngaged() && FVector::Dist(It->GetActorLocation(), Where) < CombatRadius)
            return EJapanMusicScene::Combat;
    if (const USkateComponent* Skate = Pawn->GetSkate(); Skate && Skate->IsRiding()) return EJapanMusicScene::Skate;
    if (const USailboatComponent* Boat = Pawn->GetSailboat(); Boat && Boat->IsEquipped()) return EJapanMusicScene::Sail;
    if (Pawn->IsZeppelinPassenger()) return EJapanMusicScene::Air;
    if (const UBikeComponent* Bike = Pawn->GetBike(); Bike && Bike->IsRiding()) return EJapanMusicScene::Ride;
    if (const UHorseComponent* Horse = Pawn->GetHorse(); Horse && Horse->IsRiding()) return EJapanMusicScene::Ride;
    return EJapanMusicScene::Explore;
}

int32 UJapanMusic::Choose(const FString& InPool, const FString& InZone)
{
    // Variety: never one of the last few tracks. Coherence: favour the style family that is already playing, and
    // the zone's own score where there is one.
    const TArray<FString> Groups = FJapanMusicRules::PoolGroups(InPool, InZone);
    TArray<int32> Candidates;
    TArray<float> Weights;
    float Total = 0.f;
    for (int32 I = 0; I < Tracks.Num(); ++I)
    {
        const FJapanMusicTrack& T = Tracks[I];
        if (!Groups.Contains(T.Group) || !FJapanMusicRules::TakesRole(InPool, T.Group, T.Role)) continue;
        float W = Recent.Contains(I) ? 0.f : 1.f;
        if (W > 0.f && !LastStyle.IsEmpty() && T.Style == LastStyle) W *= 2.f;
        if (W > 0.f && T.Group == InZone) W *= 1.5f;
        Candidates.Add(I); Weights.Add(W); Total += W;
    }
    if (Candidates.IsEmpty()) return INDEX_NONE;
    if (Total <= 0.f)
    {
        // Every candidate played recently: the one played longest ago.
        for (const int32 Old : Recent) if (Candidates.Contains(Old)) return Old;
        return Candidates[0];
    }
    float Pick = Random.FRand() * Total;
    for (int32 I = 0; I < Candidates.Num(); ++I) if ((Pick -= Weights[I]) <= 0.f) return Candidates[I];
    return Candidates.Last();
}

bool UJapanMusic::HasTracks(const FString& InPool, const FString& InZone) const
{
    const TArray<FString> Groups = FJapanMusicRules::PoolGroups(InPool, InZone);
    return Tracks.ContainsByPredicate([&](const FJapanMusicTrack& T)
        { return Groups.Contains(T.Group) && FJapanMusicRules::TakesRole(InPool, T.Group, T.Role); });
}

int32 UJapanMusic::Active() const
{
    for (int32 C = 0; C < 2; ++C) if (Channels[C].Track != INDEX_NONE && Channels[C].FadeRate >= 0.f) return C;
    return INDEX_NONE;
}

void UJapanMusic::ApplyGain(int32 C)
{
    if (!Sounds.IsValidIndex(C) || !Sounds[C]) return;
    const float Gain = BaseLevel * Volume * Channels[C].Level * EqualPower(Channels[C].Fade);
    Sounds[C]->SetVolumeMultiplier(Gain);
}

void UJapanMusic::FadeOut(int32 C, float Seconds)
{
    if (Channels[C].Track == INDEX_NONE) return;
    Channels[C].FadeRate = -1.f / FMath::Max(Seconds, .1f);
}

void UJapanMusic::Rest(float Minimum, float Maximum)
{
    RestUntil = Clock + Random.FRandRange(Minimum, Maximum);
}

void UJapanMusic::Start(int32 Track, const FString& InPool, float FadeSeconds)
{
    if (!Tracks.IsValidIndex(Track)) return;
    // The free channel, else the quieter one; the other crossfades out over the same time.
    int32 C = Channels[0].Track == INDEX_NONE ? 0 : Channels[1].Track == INDEX_NONE ? 1 : (Channels[0].Fade <= Channels[1].Fade ? 0 : 1);
    if (Channels[C].Track != INDEX_NONE) Players[C]->Close();
    FadeOut(1 - C, FadeSeconds);
    const FJapanMusicTrack& T = Tracks[Track];
    FChannel& Ch = Channels[C];
    Ch = FChannel();
    Ch.Track = Track;
    Ch.FadeRate = 1.f / FMath::Max(FadeSeconds, .1f);
    Ch.Level = FJapanMusicRules::Level(InPool);
    Ch.Started = Clock;
    // Long takes play a few minutes and fade out on their own; a fight plays its cue to the end.
    const float Cap = InPool == TEXT("combat") ? T.Seconds : Random.FRandRange(150.f, 240.f);
    Ch.PlayFor = FMath::Max(20.f, FMath::Min(T.Seconds - 10.f, Cap));
    ApplyGain(C);
    Players[C]->OpenFile(T.Path);
    Recent.Remove(Track);
    Recent.Add(Track);
    if (Recent.Num() > 10) Recent.RemoveAt(0);
    LastStyle = T.Style;
    UE_LOG(LogTemp, Display, TEXT("MUSIC play pool=%s zone=%s track=\"%s\" group=%s fade=%.1fs for=%.0fs"),
        *InPool, Zone.IsEmpty() ? TEXT("-") : *Zone, *T.Title, *T.Group, FadeSeconds, Ch.PlayFor);
}

void UJapanMusic::Tick(float DeltaTime)
{
    if (!bStarted) return;   // no library: the game is silent as before
    Clock += DeltaTime;
    // Fades, every frame.
    for (int32 C = 0; C < 2; ++C)
    {
        FChannel& Ch = Channels[C];
        if (Ch.Track == INDEX_NONE) continue;
        Ch.Fade = FMath::Clamp(Ch.Fade + Ch.FadeRate * DeltaTime, 0.f, 1.f);
        if (Failures && Players[C]->GetTime().GetTotalSeconds() > 2.) Failures = 0;
        ApplyGain(C);
        if (Ch.FadeRate < 0.f && Ch.Fade <= 0.f)
        {
            Players[C]->Close();
            Ch = FChannel();
            if (Active() == INDEX_NONE) SilentSince = Clock;
        }
    }
    if (Clock < NextDecision) return;
    NextDecision = Clock + DecideEvery;
    if (!bEnabled) return;

    // A track that fails to open or ends early is dropped, quietly.
    for (int32 C = 0; C < 2; ++C)
    {
        FChannel& Ch = Channels[C];
        if (Ch.Track == INDEX_NONE || Clock - Ch.Started < 6.) continue;
        UMediaPlayer* Player = Players[C];
        if (!Player->IsPlaying() && !Player->IsPreparing() && !Player->IsBuffering())
        {
            const bool bFailed = Player->GetTime().GetTotalSeconds() < 1.;
            UE_LOG(LogTemp, Display, TEXT("MUSIC %s track=\"%s\""), bFailed ? TEXT("failed") : TEXT("stopped"), *Tracks[Ch.Track].Title);
            Player->Close();
            Ch = FChannel();
            // A track that never played is not retried at once: rest, and after a few failures give up quietly.
            if (bFailed && ++Failures >= 4)
            {
                UE_LOG(LogTemp, Warning, TEXT("MUSIC off: the media player cannot play this library"));
                // Nothing ticks after this: silence and close both channels now.
                for (int32 Other = 0; Other < 2; ++Other)
                {
                    Players[Other]->Close();
                    Channels[Other] = FChannel();
                    ApplyGain(Other);
                }
                bStarted = false;
                return;
            }
            if (bFailed) Rest(20.f, 40.f);
        }
    }

    AWandererCharacter* Pawn = LocalPawn();
    if (!Pawn) return;
    FString NewZone;
    const EJapanMusicScene Scene = ReadScene(Pawn, NewZone);
    if (Scene == EJapanMusicScene::Combat) LastCombat = Clock;
    const bool bCombat = Clock - LastCombat < CombatHold;
    // A fight's scene beneath it decides where the music goes when it ends.
    const FString Area = FJapanMusicRules::AreaForZone(NewZone);
    const FString Calm = FJapanMusicRules::PoolName(Scene == EJapanMusicScene::Combat ? EJapanMusicScene::Explore : Scene, Area);
    const FString Wanted = bCombat && HasTracks(TEXT("combat"), NewZone) ? FString(TEXT("combat")) : Calm;
    if (Wanted != PendingPool) { PendingPool = Wanted; SceneSince = Clock; }
    // A new scene must hold a moment before the music follows it: no flapping at a zone's edge or between pushes.
    if (Clock - SceneSince < (Wanted == TEXT("combat") ? 1. : 4.)) return;
    if (Pawn->IsCinematic()) return;   // no changes under a cinematic

    const int32 A = Active();
    if (Wanted != Pool)
    {
        const FString Previous = Pool;
        Pool = Wanted;
        Zone = NewZone;
        if (Wanted == TEXT("combat"))
        {
            Start(Choose(Pool, Zone), Pool, A == INDEX_NONE ? 2.f : 2.5f);
            return;
        }
        if (Previous == TEXT("combat"))
        {
            // The fight is over: let it go, then a rest before the calm returns.
            if (A != INDEX_NONE) FadeOut(A, 5.f);
            Rest(15.f, 30.f);
            return;
        }
        if (A != INDEX_NONE)
        {
            // Coherence: a track that suits the new scene keeps playing.
            const FJapanMusicTrack& T = Tracks[Channels[A].Track];
            if ((!FJapanMusicRules::PoolGroups(Pool, Zone).Contains(T.Group) || !FJapanMusicRules::TakesRole(Pool, T.Group, T.Role))
                && HasTracks(Pool, Zone))
                Start(Choose(Pool, Zone), Pool, 8.f);
            return;
        }
        // Arriving somewhere new after a while in silence brings the next cue in sooner.
        if (!Previous.IsEmpty() && Clock - SilentSince > 25. && RestUntil - Clock > 6.) RestUntil = Clock + 6.;
    }
    Zone = NewZone;
    if (A != INDEX_NONE)
    {
        FChannel& Ch = Channels[A];
        if (Clock - Ch.Started >= Ch.PlayFor)
        {
            if (Pool == TEXT("combat")) { Start(Choose(Pool, Zone), Pool, 4.f); return; }
            FadeOut(A, 10.f);
            // Silence between cues: longer exploring, shorter skating.
            if (Pool.StartsWith(TEXT("skate"))) Rest(30.f, 60.f); else Rest(70.f, 160.f);
        }
        return;
    }
    if (Clock >= RestUntil)
    {
        const int32 Track = Choose(Pool, Zone);
        if (Track == INDEX_NONE) { Rest(30.f, 30.f); return; }
        Start(Track, Pool, Pool == TEXT("combat") ? 2.f : 6.f);
    }
}

FString UJapanMusic::Describe() const
{
    if (!bStarted) return TEXT("music: no library");
    const int32 A = Active();
    const FString Playing = A != INDEX_NONE ? FString::Printf(TEXT("\"%s\" at %.1fs/%.0fs fade=%.2f"), *Tracks[Channels[A].Track].Title,
        Players[A]->GetTime().GetTotalSeconds(), Players[A]->GetDuration().GetTotalSeconds(), Channels[A].Fade) : FString(TEXT("(resting)"));
    return FString::Printf(TEXT("music: %s pool=%s zone=%s playing=%s rest=%.0fs volume=%.2f"), bEnabled ? TEXT("on") : TEXT("off"),
        *Pool, Zone.IsEmpty() ? TEXT("-") : *Zone, *Playing, FMath::Max(0., RestUntil - Clock), Volume);
}

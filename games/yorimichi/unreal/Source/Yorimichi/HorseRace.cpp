#include "HorseRace.h"
#include "JapanNetwork.h"
#include "AtelierData.h"
#include "AtelierFX.h"
#include "Hippodrome.h"
#include "HorseRideComponent.h"
#include "WandererCharacter.h"
#include "Animation/AnimSequence.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/AudioComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/HUD.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "ImageUtils.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Sound/SoundBase.h"
#include "UnrealClient.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

static TAutoConsoleVariable<float> CVarRaceLatency(TEXT("hippodrome.LatencyMs"), 0.f,
    TEXT("Horse races: milliseconds the presses are shifted back to meet the music (audio output latency)."));

// Judgement windows (seconds either side of the beat) and what each grade is worth to the stride (0..1).
static constexpr double PerfectWindow = .05, GreatWindow = .10, GoodWindow = .15;
static const float GradeQuality[4] = { 1.f, .8f, .5f, 0.f };
static const TCHAR* GradeName[4] = { TEXT("PERFECT"), TEXT("GREAT"), TEXT("GOOD"), TEXT("MISS") };
static const FLinearColor GradeColour[4] = { FLinearColor(1.f, .86f, .3f), FLinearColor(.45f, .95f, .55f), FLinearColor(.55f, .78f, 1.f), FLinearColor(.95f, .35f, .3f) };
// Lanes: green, red, blue, yellow (the Xbox face buttons' colours, so the pad reads at a glance).
static const FLinearColor LaneColour[4] = { FLinearColor(.32f, .86f, .38f), FLinearColor(.94f, .32f, .28f), FLinearColor(.32f, .56f, .98f), FLinearColor(.98f, .8f, .24f) };
static const FKey LaneKeys[4] = { EKeys::D, EKeys::F, EKeys::J, EKeys::K };
static const FKey LanePads[4] = { EKeys::Gamepad_FaceButton_Bottom, EKeys::Gamepad_FaceButton_Right, EKeys::Gamepad_FaceButton_Left, EKeys::Gamepad_FaceButton_Top };
static constexpr float SpurBoost = 3.f, SpurSeconds = 2.6f, Separation = 2.f, BlockLength = 3.4f;
static constexpr int32 ComboPerPip = 16, MaxPips = 4;

const FRaceCup AHorseRace::Cups[3] = {
    { TEXT("maiden"), TEXT("Maiden Plate"), TEXT("A canter for newcomers: a lap and a half, 132 BPM, single notes."), 1.5, 8.2f, 3.4f, 1.6f, .45f, .70f },
    { TEXT("stakes"), TEXT("Hidamari Stakes"), TEXT("A lap and a half at a brisk 148 BPM, with the first chords."), 1.5, 9.0f, 3.6f, 1.4f, .60f, .82f },
    { TEXT("cup"), TEXT("Hidamari Cup"), TEXT("Two and a half laps at 164 BPM against the best riders in the land."), 2.5, 10.2f, 3.8f, 1.25f, .72f, .92f },
};

// The other riders, strongest first, and their silks.
struct FRival { const TCHAR* Rider; const TCHAR* Name; FLinearColor Silks; };
static const FRival Rivals[5] = {
    { TEXT("RiderUrbosa"), TEXT("Urbosa"), FLinearColor(.95f, .55f, .2f) },
    { TEXT("RiderMipha"), TEXT("Mipha"), FLinearColor(.85f, .25f, .3f) },
    { TEXT("RiderPaya"), TEXT("Paya"), FLinearColor(.75f, .55f, .95f) },
    { TEXT("RiderTali"), TEXT("Tali"), FLinearColor(.35f, .8f, .85f) },
    { TEXT("RiderKohm"), TEXT("Kohm"), FLinearColor(.6f, .85f, .35f) },
};

const TArray<FString>& AHorseRace::Horses()
{
    static const TArray<FString> List = { TEXT("HorsePinto"), TEXT("HorseBlack"), TEXT("HorseRoan"), TEXT("HorseLilac"), TEXT("HorseDun"), TEXT("HorseWhite"), TEXT("Epona") };
    return List;
}

FString AHorseRace::HorseName(const FString& Horse)
{
    static const TMap<FString, FString> Names = {
        { TEXT("HorsePinto"), TEXT("Biscuit (pinto)") }, { TEXT("HorseBlack"), TEXT("Kuro (black)") }, { TEXT("HorseRoan"), TEXT("Momo (roan)") },
        { TEXT("HorseLilac"), TEXT("Fuji (lilac)") }, { TEXT("HorseDun"), TEXT("Kinako (dun)") }, { TEXT("HorseWhite"), TEXT("Shiro (white)") },
        { TEXT("Epona"), TEXT("Epona") } };
    const FString* Name = Names.Find(Horse);
    return Name ? *Name : Horse;
}

static FString Short(const FString& Name) { int32 Paren; return Name.FindChar(TEXT('('), Paren) ? Name.Left(Paren).TrimEnd() : Name; }

static FString ClockText(double Seconds)
{
    Seconds = FMath::Max(0., Seconds);
    const int32 Minutes = int32(Seconds / 60.);
    return FString::Printf(TEXT("%d:%05.2f"), Minutes, Seconds - Minutes * 60.);
}

static const TCHAR* Ordinal(int32 Place)
{
    static const TCHAR* Names[7] = { TEXT("-"), TEXT("1st"), TEXT("2nd"), TEXT("3rd"), TEXT("4th"), TEXT("5th"), TEXT("6th") };
    return Names[FMath::Clamp(Place, 0, 6)];
}

// ------------------------------------------------------------------------------------------------------------ Life

struct AHorseRace::FFilm
{
    FString Dir; int32 Captured = 0, Pending = -1; FDelegateHandle Capture;
    float Warm = 0.f, Elapsed = 0.f; bool bStarted = false, bDone = false;
    int32 Cup = 1; FString Horse = TEXT("Epona"); float Accuracy = .93f;
    FString CameraCsv = TEXT("frame,x,y,z,pitch,yaw,roll,fov,phase\n");
    TArray<FString> Music;   // {"frame":..,"event":"start|seek|fade",...}
};

AHorseRace::AHorseRace()
{
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.TickGroup = TG_PostPhysics;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

void AHorseRace::Bind(AHippodrome* InVenue)
{
    Venue = InVenue;
    Dice.Initialize(int32(FPlatformTime::Cycles() & 0x7fffffff));
    if (FParse::Param(FCommandLine::Get(), TEXT("racefilm")))
    {
        Film = MakeShared<FFilm>();
        FParse::Value(FCommandLine::Get(), TEXT("racecup="), Film->Cup);
        FParse::Value(FCommandLine::Get(), TEXT("racehorse="), Film->Horse);
        FParse::Value(FCommandLine::Get(), TEXT("raceauto="), Film->Accuracy);
        FParse::Value(FCommandLine::Get(), TEXT("reviewdir="), Film->Dir);
        if (Film->Dir.IsEmpty()) Film->Dir = FPaths::ProjectSavedDir() / TEXT("Screenshots/RaceFilm") / FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S"));
        FApp::SetFixedDeltaTime(1. / 60.); FApp::SetUseFixedTimeStep(true);
        Dice.Initialize(7);
        UE_LOG(LogTemp, Display, TEXT("RACE FILM cup %d horse %s autoplay %.2f -> %s"), Film->Cup, *Film->Horse, Film->Accuracy, *Film->Dir);
    }
}

AHorseRace* AHorseRace::Find(const UObject* WorldContext)
{
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World) return nullptr;
    TActorIterator<AHorseRace> It(World);
    return It ? *It : nullptr;
}

void AHorseRace::EndPlay(const EEndPlayReason::Type Reason)
{
    CloseMenu();
    if (Film.IsValid() && Film->Capture.IsValid()) UGameViewportClient::OnScreenshotCaptured().Remove(Film->Capture);
    Super::EndPlay(Reason);
}

// ------------------------------------------------------------------------------------------------------------ Results

void AHorseRace::LoadResults()
{
    if (bResultsLoaded) return;
    bResultsLoaded = true;
    FString Text; TSharedPtr<FJsonObject> Root;
    if (!FFileHelper::LoadFileToString(Text, *(FPaths::ProjectSavedDir() / TEXT("hippodrome.json"))) ||
        !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid()) return;
    for (const FRaceCup& Cup : Cups)
    {
        const TSharedPtr<FJsonObject>* Entry = nullptr;
        if (!Root->TryGetObjectField(Cup.Key, Entry)) continue;
        double Time = 0.; int32 Place = 0;
        if ((*Entry)->TryGetNumberField(TEXT("best_time"), Time)) BestTime.Add(Cup.Key, Time);
        if ((*Entry)->TryGetNumberField(TEXT("best_place"), Place)) BestPlace.Add(Cup.Key, Place);
    }
}

void AHorseRace::SaveResults()
{
    if (Film.IsValid()) return;   // a film never touches the player's records
    TSharedPtr<FJsonObject> Root = MakeShared<FJsonObject>();
    for (const FRaceCup& Cup : Cups)
    {
        if (!BestPlace.Contains(Cup.Key)) continue;
        TSharedPtr<FJsonObject> Entry = MakeShared<FJsonObject>();
        Entry->SetNumberField(TEXT("best_place"), BestPlace[Cup.Key]);
        if (BestTime.Contains(Cup.Key)) Entry->SetNumberField(TEXT("best_time"), BestTime[Cup.Key]);
        Root->SetObjectField(Cup.Key, Entry);
    }
    Root->SetStringField(TEXT("horse"), PlayerHorse);   // also the horse ridden about the world (UHorseRideComponent)
    FString Text; FJsonSerializer::Serialize(Root.ToSharedRef(), TJsonWriterFactory<>::Create(&Text));
    FFileHelper::SaveStringToFile(Text, *(FPaths::ProjectSavedDir() / TEXT("hippodrome.json")));
}

bool AHorseRace::HasWon() const
{
    for (const auto& Pair : BestPlace) if (Pair.Value == 1) return true;
    return false;
}

// ------------------------------------------------------------------------------------------------------------ Sound

void AHorseRace::LoadSounds()
{
    if (Sounds.Num()) return;
    for (const TCHAR* Bank : { TEXT("HR_Fanfare"), TEXT("HR_GateClang"), TEXT("HR_CrowdLoop"), TEXT("HR_CrowdCheer"), TEXT("HR_Hoof"), TEXT("HR_HitPerfect"),
                              TEXT("HR_HitGood"), TEXT("HR_Miss"), TEXT("HR_Spur"), TEXT("HR_Countdown"), TEXT("HR_FinishBell"), TEXT("HR_Win"), TEXT("HR_Lose") })
    {
        int32 Count = 0;
        for (int32 I = 1; I <= 12; ++I)
        {
            const FString Name = FString::Printf(TEXT("%s_%02d"), Bank, I);
            USoundBase* Sound = LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/Audio/Hippodrome/%s.%s"), *Name, *Name));
            if (!Sound) break;
            Sounds.Add(FName(*Name), Sound); ++Count;
        }
        Variants.Add(Bank, Count);
        if (!Count) UE_LOG(LogTemp, Warning, TEXT("Hippodrome: no sound %s (run unreal.hippodrome_audio)"), Bank);
    }
    for (const FRaceCup& Cup : Cups)
    {
        const FString Name = FString::Printf(TEXT("Music_race_%s"), Cup.Key);
        if (USoundBase* Sound = LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/Audio/Hippodrome/%s.%s"), *Name, *Name))) Sounds.Add(FName(*Name), Sound);
    }
}

USoundBase* AHorseRace::Cue(const TCHAR* Name, int32 Variant)
{
    const int32 Count = Variants.FindRef(Name);
    if (Count <= 0) return Sounds.FindRef(Name);
    const int32 Pick = Variant >= 0 ? Variant % Count : Dice.RandRange(0, Count - 1);
    return Sounds.FindRef(FName(*FString::Printf(TEXT("%s_%02d"), Name, Pick + 1)));
}

void AHorseRace::Play(const TCHAR* CueName, const FVector& At, float Volume, bool b2D, float Pitch)
{
    USoundBase* Sound = Cue(CueName);
    if (!Sound) return;
    if (b2D) UGameplayStatics::PlaySound2D(this, Sound, Volume, Pitch);
    else UGameplayStatics::PlaySoundAtLocation(this, Sound, At, Volume, Pitch);
    FAtelierAudioLog::Record(Sound, At, Volume, Pitch, b2D);
}

void AHorseRace::StartMusic(double At)
{
    USoundBase* Song = Sounds.FindRef(FName(*FString::Printf(TEXT("Music_race_%s"), Cups[CupIndex].Key)));
    if (Music) Music->Stop();
    Music = Song ? UGameplayStatics::CreateSound2D(this, Song, 1.f, 1.f, 0.f, nullptr, false, false) : nullptr;
    if (Music) Music->Play(At);
    Clock = At; ClockOrigin = FPlatformTime::Seconds() - At;
    if (Film.IsValid() && Song)
        Film->Music.Add(FString::Printf(TEXT("{\"frame\":%d,\"event\":\"start\",\"sound\":\"%s\",\"at\":%.4f}"), Film->Captured, *Song->GetPathName(), At));
}

// ------------------------------------------------------------------------------------------------------------ Chart

bool AHorseRace::LoadChart(const FRaceCup& Cup)
{
    FString Text; TSharedPtr<FJsonObject> Root;
    if (!FFileHelper::LoadFileToString(Text, *AtelierDataPath(TEXT("hippodrome/charts.json"))) ||
        !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
    { UE_LOG(LogTemp, Warning, TEXT("Hippodrome: no charts.json (run unreal.hippodrome_audio)")); return false; }
    const TSharedPtr<FJsonObject>* Cups_ = nullptr; const TSharedPtr<FJsonObject>* Chart = nullptr;
    if (!Root->TryGetObjectField(TEXT("cups"), Cups_) || !(*Cups_)->TryGetObjectField(Cup.Key, Chart)) return false;
    const TSharedPtr<FJsonObject>& C = *Chart;
    SongStart = C->GetNumberField(TEXT("start")); SongLength = C->GetNumberField(TEXT("length"));
    LoopFrom = C->GetNumberField(TEXT("loop_from")); LoopTo = C->GetNumberField(TEXT("loop_to"));
    Beat = C->GetNumberField(TEXT("beat"));
    CountIn.Reset();
    for (const TSharedPtr<FJsonValue>& V : C->GetArrayField(TEXT("count_in"))) CountIn.Add(V->AsNumber());
    TArray<FRaceNote> Base;
    for (const TSharedPtr<FJsonValue>& V : C->GetArrayField(TEXT("notes")))
    {
        const TSharedPtr<FJsonObject>& N = V->AsObject();
        FRaceNote Note; Note.T = N->GetNumberField(TEXT("t")); Note.Lane = FMath::Clamp(int32(N->GetNumberField(TEXT("lane"))), 0, 3);
        N->TryGetNumberField(TEXT("hold"), Note.Hold);
        if (Note.T < LoopTo) Base.Add(Note);   // the outro's last note is the song's ending, not the race's
    }
    // A slow race keeps riding the last eight bars: their notes repeat once per pass of the loop.
    Notes = Base;
    const double Span = LoopTo - LoopFrom;
    for (int32 Pass = 1; Pass <= 4 && Span > 1.; ++Pass)
        for (const FRaceNote& N : Base) if (N.T >= LoopFrom) { FRaceNote Copy = N; Copy.T += Pass * Span; Notes.Add(Copy); }
    for (FRaceNote& N : Notes)
        N.Auto = Dice.FRand() < AutoAccuracy + .03f ? Dice.FRandRange(-1.f, 1.f) * (.012 + (1. - AutoAccuracy) * .14) : 1e6;
    UE_LOG(LogTemp, Display, TEXT("Hippodrome: %s chart %d notes (%d with loops), gate at %.2f s"), Cup.Key, Base.Num(), Notes.Num(), SongStart);
    return Base.Num() > 0;
}

// ------------------------------------------------------------------------------------------------------------ Menu

bool AHorseRace::CanTalk(const AWandererCharacter* P) const
{
    const AHippodrome* V = Venue.Get();
    const AHippodromeFigure* Master = V ? V->GetMaster() : nullptr;
    return P && Master && Phase == EPhase::Idle && !Menu.IsValid() && !P->OnVehicle()
        && FVector::Dist2D(P->GetActorLocation(), Master->GetActorLocation()) < 380.f;
}

bool AHorseRace::TryInteract(AWandererCharacter* P)
{
    if (!P || !JapanNetwork::Allows(P->GetWorld(), JapanNetwork::EActivity::Race)) return false;
    AHorseRace* Race = Find(P);
    if (!Race || !Race->CanTalk(P)) return false;
    Race->OpenMenu(P);
    return true;
}

void AHorseRace::OpenMenu(AWandererCharacter* P)
{
    if (Menu.IsValid() || !P || !GEngine || !GEngine->GameViewport) return;
    LoadResults();
    Player = P; Phase = EPhase::Menu;
    MenuCup = CupIndex; MenuHorse = FMath::Max(0, Horses().IndexOfByKey(PlayerHorse));
    if (AHippodromeFigure* Master = Venue.IsValid() ? Venue->GetMaster() : nullptr) Master->PlayBody(TEXT("talk"), true);
    TWeakObjectPtr<AHorseRace> Self(this);
    TWeakObjectPtr<AWandererCharacter> Who(P);
    auto Title = [](const TCHAR* Text, int32 Size) { return SNew(STextBlock).Text(FText::FromString(Text)).Font(FCoreStyle::GetDefaultFontStyle("Bold", Size)).ColorAndOpacity(FLinearColor::White); };
    TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 6)[Title(TEXT("Hudson"), 24)];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 16)[SNew(STextBlock).Text(FText::FromString(TEXT("Race master of the Hidamari Hippodrome"))).ColorAndOpacity(FLinearColor(.95f, .78f, .45f))];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 16)[SNew(STextBlock).AutoWrapText(true).ColorAndOpacity(FLinearColor::White)
        .Text(FText::FromString(TEXT("\"A horse runs on rhythm! Ride the beat and she'll fly; lose it and she'll plod. Hug the rail on the turns, and save your spurs for the home straight.\"")))];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 6)[Title(TEXT("Race"), 16)];
    TSharedPtr<SButton> First;
    TSharedRef<SHorizontalBox> CupRow = SNew(SHorizontalBox);
    for (int32 I = 0; I < 3; ++I)
    {
        TSharedRef<SButton> B = SNew(SButton).OnClicked_Lambda([Self, I] { if (Self.IsValid()) Self->MenuCup = I; return FReply::Handled(); })
            [SNew(SVerticalBox)
                + SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Bold", 14))
                    .Text_Lambda([Self, I] { return FText::FromString(FString::Printf(TEXT("%s%s"), Self.IsValid() && Self->MenuCup == I ? TEXT("● ") : TEXT("○ "), Cups[I].Name)); })]
                + SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).AutoWrapText(true).Font(FCoreStyle::GetDefaultFontStyle("Regular", 10)).Text(FText::FromString(Cups[I].Blurb))]
                + SVerticalBox::Slot().AutoHeight().Padding(0, 4, 0, 0)[SNew(STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Regular", 10)).ColorAndOpacity(FLinearColor(1.f, .85f, .5f))
                    .Text_Lambda([Self, I]
                    {
                        if (!Self.IsValid() || !Self->BestPlace.Contains(Cups[I].Key)) return FText::FromString(TEXT("not yet run"));
                        const int32 Place = Self->BestPlace[Cups[I].Key];
                        const TCHAR* Medal = Place == 1 ? TEXT("gold") : Place == 2 ? TEXT("silver") : Place == 3 ? TEXT("bronze") : TEXT("no medal");
                        return FText::FromString(FString::Printf(TEXT("best %s (%s)  %s"), Ordinal(Place), Medal,
                            Self->BestTime.Contains(Cups[I].Key) ? *ClockText(Self->BestTime[Cups[I].Key]) : TEXT("")));
                    })]];
        if (I == MenuCup) First = B;
        CupRow->AddSlot().FillWidth(1.f).Padding(0, 0, 8, 0)[B];
    }
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 14)[CupRow];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 6)[Title(TEXT("Horse"), 16)];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 14)[SNew(SButton)
        .Text_Lambda([Self]
        {
            if (!Self.IsValid()) return FText::GetEmpty();
            return FText::FromString(FString::Printf(TEXT("%s   (click to change)"), *HorseName(Horses()[Self->MenuHorse])));
        })
        .OnClicked_Lambda([Self]
        {
            if (!Self.IsValid()) return FReply::Handled();
            // Epona waits until the player has won a race.
            do Self->MenuHorse = (Self->MenuHorse + 1) % Horses().Num();
            while (Horses()[Self->MenuHorse] == TEXT("Epona") && !Self->HasWon());
            return FReply::Handled();
        })];
    if (!HasWon())
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 12)[SNew(STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Italic", 10)).ColorAndOpacity(FLinearColor(.8f, .8f, .75f))
            .Text(FText::FromString(TEXT("Hudson: \"Win any race and a certain red mare from the far stable will let you ride her.\"")))];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 16)[SNew(STextBlock).AutoWrapText(true).Font(FCoreStyle::GetDefaultFontStyle("Regular", 10)).ColorAndOpacity(FLinearColor(.85f, .9f, .85f))
        .Text(FText::FromString(TEXT("Notes: D F J K (pad: A B X Y) as they reach the line; hold the long ones.  Steer: arrows or left stick.  Spur: Space or RB (earned every 16 in a row).  Hold Esc to retire."))) ];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 8)[SNew(SButton).HAlign(HAlign_Center).Text(FText::FromString(TEXT("To the gate!")))
        .OnClicked_Lambda([Self, Who]
        {
            if (Self.IsValid() && Who.IsValid())
            {
                const int32 Cup = Self->MenuCup; const FString Horse = Horses()[Self->MenuHorse];
                Self->CloseMenu();
                Self->StartRace(Who.Get(), Cup, Horse);
            }
            return FReply::Handled();
        })];
    TSharedRef<SButton> Leave = SNew(SButton).HAlign(HAlign_Center).Text(FText::FromString(TEXT("Not today")))
        .OnClicked_Lambda([Self] { if (Self.IsValid()) Self->CloseMenu(); return FReply::Handled(); });
    Rows->AddSlot().AutoHeight()[Leave];
    if (!First) First = Leave;
    Menu = SNew(SBorder).HAlign(HAlign_Center).VAlign(VAlign_Center).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0, 0, 0, .35f))
        [SNew(SBox).WidthOverride(720)
            [SNew(SBorder).Padding(28).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(.06f, .045f, .03f, .96f))[Rows]]];
    GEngine->GameViewport->AddViewportWidgetContent(Menu.ToSharedRef(), 21);
    P->SetMenuOpen(true);
    GEngine->GameViewport->SetMouseCaptureMode(EMouseCaptureMode::NoCapture);
    FSlateApplication::Get().SetKeyboardFocus(First, EFocusCause::SetDirectly);
}

void AHorseRace::CloseMenu()
{
    if (!Menu.IsValid()) return;
    if (GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(Menu.ToSharedRef());
    Menu.Reset();
    if (AWandererCharacter* P = Player.Get()) P->SetMenuOpen(false);
    if (Phase == EPhase::Menu) Phase = EPhase::Idle;
    if (AHippodromeFigure* Master = Venue.IsValid() ? Venue->GetMaster() : nullptr) Master->PlayBody(TEXT("idle"), true);
}

// ------------------------------------------------------------------------------------------------------------ Race

double AHorseRace::Distance() const { return Venue.IsValid() ? Cups[CupIndex].Laps * Venue->Course.Lap : 1.; }

FVector AHorseRace::RunnerPoint(const FRaceRunner& R, float* Yaw) const
{
    return Venue->Course.At(Venue->Course.GateS + R.Progress, R.Offset, Yaw);
}

bool AHorseRace::StartRace(AWandererCharacter* P, int32 Cup, const FString& Horse, float Auto)
{
    if (!JapanNetwork::Allows(GetWorld(), JapanNetwork::EActivity::Race)) return false;
    AHippodrome* V = Venue.Get();
    if (!V || !P || IsRacing()) return false;
    CloseMenu();
    LoadResults();
    CupIndex = FMath::Clamp(Cup, 0, 2);
    AutoAccuracy = FMath::Clamp(Auto, 0.f, 1.f);
    if (!LoadChart(Cups[CupIndex])) return false;
    LoadSounds();
    Player = P;
    PlayerHorse = Horses().Contains(Horse) ? Horse : FString(TEXT("HorsePinto"));
    const FString Own = UHorseRideComponent::RiderFor(P);
    const FString PlayerRider = Own.IsEmpty() ? FHorseSpec::PlayerRider() : Own;   // Cairo, or Link playing as Link
    for (FRaceRunner& R : Runners) if (R.Figure.IsValid()) R.Figure->Destroy();
    Runners.Reset();
    // Six stalls across the gate; the player draws one of the middle four.
    const FRaceCup& C = Cups[CupIndex];
    TArray<FString> Coats;
    for (const FString& H : Horses()) if (H != PlayerHorse && H != TEXT("Epona")) Coats.Add(H);
    PlayerIndex = Dice.RandRange(1, 4);
    TArray<int32> Order = { 0, 1, 2, 3, 4 };
    for (int32 I = Order.Num() - 1; I > 0; --I) Order.Swap(I, Dice.RandRange(0, I));
    int32 Rival = 0;
    for (int32 Stall = 0; Stall < 6; ++Stall)
    {
        FRaceRunner R;
        R.Offset = -5.f + Stall * 2.f;
        if (Stall == PlayerIndex)
        {
            R.bPlayer = true; R.Horse = PlayerHorse; R.Rider = PlayerRider; R.Name = TEXT("You"); R.Colour = FLinearColor(1.f, .9f, .4f);
        }
        else
        {
            const int32 Which = Order[Rival];
            R.Horse = Coats[Rival % Coats.Num()]; R.Rider = Rivals[Which].Rider; R.Name = Rivals[Which].Name; R.Colour = Rivals[Which].Silks;
            R.Skill = FMath::Lerp(C.FieldHi, C.FieldLo, Which / 4.f) + Dice.FRandRange(-.03f, .03f);
            R.PreferredOffset = -4.6f + Dice.FRandRange(0.f, 2.2f);
            ++Rival;
        }
        R.HorseName = Short(HorseName(R.Horse));
        float Yaw = 0.f; const FVector At = RunnerPoint(R, &Yaw);
        R.Figure = AHippodromeFigure::Spawn(GetWorld(), R.Horse, R.Rider, At, Yaw);
        R.Yaw = Yaw;
        Runners.Add(R);
    }
    Notes.Sort([](const FRaceNote& A, const FRaceNote& B) { return A.T < B.T; });
    FirstLive = 0; Loops = 0; bLooping = true; Finishers = 0; Clock = 0.; RaceStartClock = 1e9;
    for (int32 I = 0; I < 4; ++I) { Counts[I] = 0; LaneFlash[I] = LaneHit[I] = 0.f; LaneDown[I] = false; }
    Judgement.Reset(); Callout.Reset(); EscHeld = ResultsHeld = 0.f; LastLapShown = 0; bHomeStretch = false; bCamInit = false;
    // The player waits by the grandstand, out of sight, with the keys handed to the race.
    P->TravelTo(V->ReturnGround, V->ReturnYaw, TEXT("Hippodrome"));
    P->SetControlsSuspended(true);
    P->SetActorHiddenInGame(true);
    if (!Camera)
    {
        FActorSpawnParameters Params; Params.Owner = this;
        Camera = GetWorld()->SpawnActor<ACameraActor>(Params);
    }
    AdvanceCamera(0.f);
    if (APlayerController* PC = Cast<APlayerController>(P->GetController())) PC->SetViewTargetWithBlend(Camera, Film.IsValid() ? 0.f : 1.f, VTBlend_EaseInOut, 2.f);
    Play(TEXT("HR_Fanfare"), FVector::ZeroVector, .8f, true);
    if (USoundBase* Loop = Cue(TEXT("HR_CrowdLoop"), 0))
    {
        Crowd = UGameplayStatics::CreateSound2D(this, Loop, .32f, 1.f, 0.f, nullptr, false, false);
        if (Crowd) Crowd->Play();
        FAtelierAudioLog::Record(Loop, FVector::ZeroVector, .32f, 1.f, true, true);
    }
    Phase = EPhase::Parade; PhaseTime = 0.f;
    Say(FString::Printf(TEXT("%s  ·  %s"), C.Name, *Short(HorseName(PlayerHorse))), 4.f);
    UE_LOG(LogTemp, Display, TEXT("RACE start %s on %s, stall %d, autoplay %.2f"), C.Key, *PlayerHorse, PlayerIndex + 1, AutoAccuracy);
    return true;
}

void AHorseRace::Restore()
{
    AWandererCharacter* P = Player.Get();
    AHippodrome* V = Venue.Get();
    if (!P) return;
    P->SetActorHiddenInGame(false);
    P->SetControlsSuspended(false);
    if (V) P->TravelTo(V->ReturnGround, V->ReturnYaw, TEXT("Hippodrome"));
    if (APlayerController* PC = Cast<APlayerController>(P->GetController())) PC->SetViewTargetWithBlend(P, .8f, VTBlend_EaseInOut, 2.f);
}

void AHorseRace::EndRace(const FString& Why)
{
    if (!IsRacing()) { CloseMenu(); return; }
    UE_LOG(LogTemp, Display, TEXT("RACE end (%s)"), *Why);
    if (Music) { Music->FadeOut(1.2f, 0.f); Music = nullptr; }
    if (Crowd) { Crowd->FadeOut(1.5f, 0.f); Crowd = nullptr; }
    for (FRaceRunner& R : Runners) if (R.Figure.IsValid()) R.Figure->Destroy();
    Runners.Reset();
    if (Venue.IsValid()) Venue->SetGateOnTrack(true);
    Restore();
    if (AHippodromeFigure* Master = Venue.IsValid() ? Venue->GetMaster() : nullptr) Master->PlayBody(TEXT("idle"), true);
    Phase = EPhase::Idle; PhaseTime = 0.f;
}

// ------------------------------------------------------------------------------------------------------------ Tick

void AHorseRace::Tick(float Dt)
{
    Super::Tick(Dt);
    if (Film.IsValid()) AdvanceFilm(Dt);
    if (!Venue.IsValid() || !IsRacing()) return;
    PhaseTime += Dt;
    // The field runs the back straight again on the last lap: the gate goes once they are away (behind the camera).
    Venue->SetGateOnTrack(Phase < EPhase::Running || RaceTime() < 5.);
    JudgementTime = FMath::Max(0.f, JudgementTime - Dt);
    CalloutTime = FMath::Max(0.f, CalloutTime - Dt);
    for (int32 I = 0; I < 4; ++I) { LaneFlash[I] = FMath::Max(0.f, LaneFlash[I] - Dt); LaneHit[I] = FMath::Max(0.f, LaneHit[I] - Dt); }
    switch (Phase)
    {
    case EPhase::Parade:
        // The fanfare over the gate, then the song's count-in.
        if (PhaseTime > 4.4f) { LoadSounds(); bFixedClock = Film.IsValid(); StartMusic(0.); Phase = EPhase::Countdown; PhaseTime = 0.f; }
        break;
    case EPhase::Countdown:
        AdvanceClock(Dt);
        if (Clock >= SongStart)
        {
            Phase = EPhase::Running; PhaseTime = 0.f; RaceStartClock = SongStart;
            Play(TEXT("HR_GateClang"), Venue->GateCentre, 1.f, false);
            Play(TEXT("HR_CrowdCheer"), FVector::ZeroVector, .55f, true);
            for (FRaceRunner& R : Runners) if (R.Figure.IsValid()) R.Figure->PlayRiderOnce(TEXT("start"));
            Say(TEXT("And they're off!"), 1.6f);
        }
        break;
    default:
        AdvanceClock(Dt);
        break;
    }
    ReadInput(Dt);
    if (Phase >= EPhase::Running)
    {
        AdvanceRhythm();
        AdvanceOthers();
        AdvanceRunners(Dt);
    }
    else for (FRaceRunner& R : Runners) PlaceRunner(R, Dt);
    AdvanceCamera(Dt);
    if (Phase == EPhase::Finished && PhaseTime > 5.5f) ShowResults();
    if (Phase == EPhase::Results && ((ResultsHeld > 0.f && PhaseTime > 1.5f) || PhaseTime > (Film.IsValid() ? 1e9f : 14.f))) EndRace(TEXT("results"));
}

void AHorseRace::AdvanceClock(float Dt)
{
    if (bFixedClock) Clock += Dt; else Clock = FPlatformTime::Seconds() - ClockOrigin;
    // The song's last eight bars carry on while the player is still racing: the audio jumps back and the chart's
    // unrolled copies of those notes keep coming.
    if (!bLooping || LoopTo - LoopFrom < 1.) return;
    const double Song = Clock - Loops * (LoopTo - LoopFrom);
    if (Song >= LoopTo && Loops < 4)
    {
        ++Loops;
        const double Seek = LoopFrom + (Song - LoopTo);
        if (Music) Music->Play(Seek);
        if (Film.IsValid()) Film->Music.Add(FString::Printf(TEXT("{\"frame\":%d,\"event\":\"seek\",\"at\":%.4f}"), Film->Captured, Seek));
    }
}

// ------------------------------------------------------------------------------------------------------------ Rhythm

void AHorseRace::ReadInput(float Dt)
{
    APlayerController* PC = Player.IsValid() ? Cast<APlayerController>(Player->GetController()) : nullptr;
    if (!PC) return;
    const bool bRunning = Phase == EPhase::Running;
    const double Press = Clock - CVarRaceLatency.GetValueOnGameThread() / 1000.;
    for (int32 Lane = 0; Lane < 4; ++Lane)
    {
        LaneDown[Lane] = PC->IsInputKeyDown(LaneKeys[Lane]) || PC->IsInputKeyDown(LanePads[Lane]);
        if (PC->WasInputKeyJustPressed(LaneKeys[Lane]) || PC->WasInputKeyJustPressed(LanePads[Lane]))
        {
            LaneFlash[Lane] = .12f;
            if (bRunning) Judge(Lane, Press);
            if (Phase == EPhase::Results) ResultsHeld = 1.f;
        }
    }
    if (AutoAccuracy > 0.f && bRunning)
    {
        // Autoplay presses each note at its planned slip, and holds the long ones to their end.
        for (int32 I = FirstLive; I < Notes.Num() && Notes[I].T < Clock + .2; ++I)
        {
            FRaceNote& N = Notes[I];
            if (N.State == 0 && N.Auto < 1. && Clock >= N.T + N.Auto) { LaneFlash[N.Lane] = .12f; Judge(N.Lane, Clock); }
            if (N.bHolding) LaneDown[N.Lane] = true;
        }
    }
    if (Phase == EPhase::Results && (PC->WasInputKeyJustPressed(EKeys::Enter) || PC->WasInputKeyJustPressed(EKeys::SpaceBar))) ResultsHeld = 1.f;
    if (!Runners.IsValidIndex(PlayerIndex)) return;
    FRaceRunner& Me = Runners[PlayerIndex];
    if (bRunning && Me.FinishTime < 0.)
    {
        float Steer = PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftX);
        if (FMath::Abs(Steer) < .2f) Steer = 0.f;
        if (PC->IsInputKeyDown(EKeys::Left) || PC->IsInputKeyDown(EKeys::Gamepad_DPad_Left)) Steer -= 1.f;
        if (PC->IsInputKeyDown(EKeys::Right) || PC->IsInputKeyDown(EKeys::Gamepad_DPad_Right)) Steer += 1.f;
        if (AutoAccuracy > 0.f)
        {
            // Autoplay rides the rail and swings out round a horse it is catching.
            float Want = -4.6f;
            for (const FRaceRunner& O : Runners)
                if (&O != &Me && O.Progress - Me.Progress > 0. && O.Progress - Me.Progress < 9. && FMath::Abs(O.Offset - Want) < Separation) Want = O.Offset + Separation + .6f;
            Steer = FMath::Clamp((Want - Me.Offset) * .8f, -1.f, 1.f);
        }
        Me.LateralSpeed = FMath::Clamp(Steer, -1.f, 1.f) * 4.2f;
        const bool bSpur = PC->WasInputKeyJustPressed(EKeys::SpaceBar) || PC->WasInputKeyJustPressed(EKeys::Gamepad_RightShoulder)
            || (AutoAccuracy > 0.f && Me.Pips > 0 && (Distance() - Me.Progress < 280. || Me.Pips >= MaxPips));
        if (bSpur && Me.Pips > 0 && Me.SpurLeft <= 0.f)
        {
            --Me.Pips; Me.SpurLeft = SpurSeconds;
            Play(TEXT("HR_Spur"), FVector::ZeroVector, .7f, true);
            if (Me.Figure.IsValid()) Me.Figure->PlayRiderOnce(TEXT("spur"));
            Say(TEXT("Spur!"), .9f);
        }
    }
    const bool bEsc = PC->IsInputKeyDown(EKeys::Escape) || PC->IsInputKeyDown(EKeys::Gamepad_Special_Right);
    EscHeld = bEsc && Phase != EPhase::Results ? EscHeld + Dt : 0.f;
    if (EscHeld > 1.f) EndRace(TEXT("retired"));
}

void AHorseRace::Judge(int32 Lane, double PressTime)
{
    int32 Best = -1; double BestGap = 1e9;
    for (int32 I = FirstLive; I < Notes.Num() && Notes[I].T < PressTime + GoodWindow + .01; ++I)
    {
        const FRaceNote& N = Notes[I];
        if (N.Lane != Lane || N.State != 0) continue;
        const double Gap = FMath::Abs(N.T - PressTime);
        if (Gap < BestGap) { BestGap = Gap; Best = I; }
    }
    if (!Runners.IsValidIndex(PlayerIndex)) return;
    FRaceRunner& Me = Runners[PlayerIndex];
    if (Best < 0 || BestGap > GoodWindow)
    {
        Me.Meter = FMath::Max(0.f, Me.Meter - .015f);   // a stray press costs a little, never the combo
        return;
    }
    FRaceNote& N = Notes[Best];
    const int32 G = BestGap <= PerfectWindow ? 0 : BestGap <= GreatWindow ? 1 : 2;
    N.Grade = G; N.State = 1; N.bHolding = N.Hold > .05;
    ++Counts[G];
    Grade(Me, G);
    LaneHit[Lane] = .22f;
    Judgement = GradeName[G];
    if (G == 2) Judgement += N.T > PressTime ? TEXT("  early") : TEXT("  late");
    JudgementColour = GradeColour[G]; JudgementTime = .5f;
    Play(G == 0 ? TEXT("HR_HitPerfect") : TEXT("HR_HitGood"), FVector::ZeroVector, G == 0 ? .5f : .38f, true);
}

void AHorseRace::Grade(FRaceRunner& R, int32 G)
{
    // The stride is a running average of how well the beat is kept: the last dozen notes or so.
    R.Meter += (GradeQuality[G] - R.Meter) * .14f;
    if (G < 3)
    {
        ++R.Combo; R.BestCombo = FMath::Max(R.BestCombo, R.Combo);
        if (R.Combo % ComboPerPip == 0 && R.Pips < MaxPips)
        {
            ++R.Pips;
            if (R.bPlayer) Say(TEXT("Spur ready!  Space / RB"), 1.4f);
        }
    }
    else R.Combo = 0;
}

void AHorseRace::AdvanceRhythm()
{
    if (!Runners.IsValidIndex(PlayerIndex)) return;
    FRaceRunner& Me = Runners[PlayerIndex];
    const bool bRacing = Me.FinishTime < 0.;
    for (int32 I = FirstLive; I < Notes.Num() && Notes[I].T <= Clock + .01; ++I)
    {
        FRaceNote& N = Notes[I];
        if (N.State == 0 && Clock > N.T + GoodWindow)
        {
            N.State = 2;
            if (!bRacing) continue;
            ++Counts[3];
            Grade(Me, 3);
            Judgement = GradeName[3]; JudgementColour = GradeColour[3]; JudgementTime = .45f;
            Play(TEXT("HR_Miss"), FVector::ZeroVector, .3f, true);
        }
        if (N.bHolding)
        {
            if (Clock >= N.T + N.Hold) { N.bHolding = false; if (bRacing) { Grade(Me, 0); Judgement = TEXT("HELD!"); JudgementColour = GradeColour[0]; JudgementTime = .45f; } }
            else if (!LaneDown[N.Lane] && Clock < N.T + N.Hold - .08) { N.bHolding = false; N.State = 3; }
            else Me.Meter = FMath::Min(1.f, Me.Meter + .1f * FApp::GetDeltaTime());   // a held note keeps the horse lifting
        }
    }
    while (FirstLive < Notes.Num() && Notes[FirstLive].State != 0 && !Notes[FirstLive].bHolding && Notes[FirstLive].T < Clock) ++FirstLive;
}

void AHorseRace::AdvanceOthers()
{
    // The others meet the same notes, each at its skill: a little sharper behind the player, a little looser ahead.
    const FRaceRunner& Me = Runners[PlayerIndex];
    for (FRaceRunner& R : Runners)
    {
        if (R.bPlayer) continue;
        while (R.NextNote < Notes.Num() && Notes[R.NextNote].T <= Clock)
        {
            ++R.NextNote;
            if (R.FinishTime >= 0.) continue;
            const float Lead = float(R.Progress - Me.Progress);
            const float M = FMath::Clamp(R.Skill - FMath::Clamp(Lead / 40.f, -1.f, 1.f) * .1f, .05f, .98f);
            const float W[4] = { M * M, 2.f * M * (1.f - M) * .6f, 2.f * M * (1.f - M) * .4f, (1.f - M) * (1.f - M) };
            float Roll = Dice.FRand() * (W[0] + W[1] + W[2] + W[3]);
            int32 G = 0;
            while (G < 3 && Roll > W[G]) Roll -= W[G++];
            Grade(R, G);
            const bool bLate = Distance() - R.Progress < 300.;
            if (R.Pips > 0 && R.SpurLeft <= 0.f && (bLate || R.Pips >= MaxPips) && Dice.FRand() < .25f) { --R.Pips; R.SpurLeft = SpurSeconds; if (R.Figure.IsValid()) R.Figure->PlayRiderOnce(TEXT("spur")); }
        }
    }
}

// ------------------------------------------------------------------------------------------------------------ Running

void AHorseRace::AdvanceRunners(float Dt)
{
    const FRaceCup& C = Cups[CupIndex];
    const FHippodromeCourse& Course = Venue->Course;
    const float Edge = float(Course.Width * .5 - .9);
    const double T = RaceTime();
    for (FRaceRunner& R : Runners)
    {
        float Target;
        if (R.FinishTime >= 0.)
        {
            // Past the post: ease to a canter, a trot, then a walk.
            const double Since = T - R.FinishTime;
            Target = Since < 3. ? 7.f : Since < 7. ? 3.8f : Since < 11. ? 1.6f : 0.f;
        }
        else Target = C.Base + C.Range * R.Meter + (R.SpurLeft > 0.f ? SpurBoost : 0.f) + (R.Combo >= 2 * ComboPerPip ? .25f : 0.f);
        const float Accel = R.SpurLeft > 0.f ? 7.f : T < 3. ? 4.2f : Target > R.Speed ? 2.6f : 3.2f;
        R.Speed = FMath::FInterpConstantTo(R.Speed, Target, Dt, Accel);
        R.SpurLeft = FMath::Max(0.f, R.SpurLeft - Dt);
        // A horse right ahead in the same path holds this one to its pace.
        R.bBoxed = false;
        for (const FRaceRunner& O : Runners)
        {
            const double Ahead = O.Progress - R.Progress;
            if (&O == &R || Ahead <= 0. || Ahead > BlockLength || FMath::Abs(O.Offset - R.Offset) > Separation * .95f) continue;
            if (O.Speed < R.Speed) { R.Speed = FMath::Max(O.Speed, 0.f); R.bBoxed = R.FinishTime < 0.; }
        }
        if (!R.bPlayer && R.FinishTime < 0.)
        {
            // The others keep their line by the rail, swing out round a slower horse ahead and drift back once clear,
            // never cutting across one alongside.
            float Want = R.PreferredOffset;
            for (const FRaceRunner& O : Runners)
            {
                const double Ahead = O.Progress - R.Progress;
                if (&O != &R && Ahead > 0. && Ahead < 9. && FMath::Abs(O.Offset - R.Offset) < Separation && O.Speed < R.Speed + .4f)
                { R.PassOffset = FMath::Min(O.Offset + Separation + .6f, Edge); R.PassTimer = 2.2f; }
            }
            if (R.PassTimer > 0.f) { R.PassTimer -= Dt; Want = FMath::Max(Want, R.PassOffset); }
            if (Want < R.Offset)
                for (const FRaceRunner& O : Runners)
                    if (&O != &R && FMath::Abs(O.Progress - R.Progress) < 3.6 && O.Offset < R.Offset && O.Offset > Want - Separation) { Want = R.Offset; break; }
            R.LateralSpeed = FMath::Clamp((Want - R.Offset) * 1.2f, -1.8f, 1.8f);
        }
        else if (R.FinishTime >= 0.) R.LateralSpeed = 0.f;
        R.Offset = FMath::Clamp(R.Offset + R.LateralSpeed * Dt, -Edge, Edge);
    }
    // Two horses never overlap: within a length of each other they keep a body's width apart (a horse is 2.7 m long).
    for (int32 I = 0; I < Runners.Num(); ++I)
        for (int32 J = I + 1; J < Runners.Num(); ++J)
        {
            FRaceRunner& A = Runners[I]; FRaceRunner& B = Runners[J];
            const float Gap = B.Offset - A.Offset;
            if (FMath::Abs(B.Progress - A.Progress) > 3.2 || FMath::Abs(Gap) >= Separation) continue;
            const float Push = (Separation - FMath::Abs(Gap)) * .5f * (Gap >= 0.f ? 1.f : -1.f);
            A.Offset = FMath::Clamp(A.Offset - Push, -Edge, Edge); B.Offset = FMath::Clamp(B.Offset + Push, -Edge, Edge);
        }
    for (FRaceRunner& R : Runners)
    {
        R.Progress += R.Speed * Dt / Course.CurvatureScale(Course.GateS + R.Progress, R.Offset);
        if (R.FinishTime < 0. && R.Progress >= Distance()) Finish(R);
        PlaceRunner(R, Dt);
    }
    if (Phase != EPhase::Running || !Runners.IsValidIndex(PlayerIndex)) return;
    // Laps count at the finish post; the last 400 m are the home stretch.
    const FRaceRunner& Me = Runners[PlayerIndex];
    const int32 Total = FMath::CeilToInt(C.Laps);
    const int32 Lap = FMath::Min(Total, 1 + int32(FMath::Max(0., Me.Progress - (Course.Lap - Course.GateS)) / Course.Lap) + (Me.Progress >= Course.Lap - Course.GateS ? 1 : 0));
    if (Lap != LastLapShown)
    {
        if (LastLapShown > 0) { Say(Lap == Total ? TEXT("Final lap!") : FString::Printf(TEXT("Lap %d"), Lap), 1.6f); Play(TEXT("HR_CrowdCheer"), FVector::ZeroVector, .4f, true); }
        LastLapShown = Lap;
    }
    if (!bHomeStretch && Distance() - Me.Progress < 400.) { bHomeStretch = true; Say(TEXT("The home stretch!"), 1.8f); Play(TEXT("HR_CrowdCheer"), FVector::ZeroVector, .6f, true); }
}

void AHorseRace::PlaceRunner(FRaceRunner& R, float Dt)
{
    AHippodromeFigure* F = R.Figure.Get();
    if (!F) return;
    float Yaw = 0.f;
    const FVector At = RunnerPoint(R, &Yaw);
    // The horse turns its head into a lane change.
    const float Drift = FMath::RadiansToDegrees(FMath::Atan2(R.LateralSpeed, FMath::Max(R.Speed, 2.f)));
    R.Yaw = FMath::FixedTurn(R.Yaw, Yaw + Drift, 220.f * FMath::Max(Dt, .001f));
    if (Dt <= 0.f || Phase < EPhase::Running) R.Yaw = Yaw + Drift;
    F->SetActorLocationAndRotation(At, FRotator(0, R.Yaw, 0));
    const FHorseSpec& H = F->GetBody();
    const float V = R.Speed * 100.f;
    FName Role = TEXT("idle"), RiderRole = TEXT("idle"); float Ref = 0.f;
    if (V > 30.f)
    {
        static const FName Gaits[5] = { TEXT("walk"), TEXT("trot"), TEXT("canter"), TEXT("run"), TEXT("sprint") };
        static const float Limits[5] = { 300.f, 540.f, 740.f, 960.f, 1e9f };
        int32 G = 0; while (V > Limits[G]) ++G;
        Role = Gaits[G]; RiderRole = G == 4 ? FName(TEXT("run")) : Gaits[G];
        Ref = H.SpeedsCm.FindRef(Role);
        if (Venue->Course.InTurn(Venue->Course.GateS + R.Progress) && G >= 3)
        {
            // The turns are all to the left: the horses lean into them.
            Role = G == 4 ? FName(TEXT("Move_Gear_Top_Curve_L_Fast")) : FName(TEXT("Move_Gear_Top_Curve_L"));
            if (F->RiderHas(TEXT("left"))) RiderRole = TEXT("left");
        }
    }
    const float Rate = Ref > 1.f ? FMath::Clamp(V / Ref, .5f, 2.f) : 1.f;
    F->Gait(Role, RiderRole, Rate);
    R.GaitRole = Role;
    // Hooves: two falls a stride for the horses near the camera.
    if (V > 30.f && Ref > 1.f && Camera)
    {
        const float Length = FMath::Max(H.Lengths.FindRef(F->BodyClip()), .1f);
        R.StrideClock += Dt * Rate / Length * 2.f;
        if (R.StrideClock >= 1.f)
        {
            R.StrideClock -= 1.f;
            const float Near = FVector::Dist(At, Camera->GetActorLocation());
            if (Near < 3000.f) Play(TEXT("HR_Hoof"), At, (R.bPlayer ? .55f : .4f) * (1.f - Near / 3000.f), false, Dice.FRandRange(.94f, 1.06f));
        }
    }
    // The winner rears on the way back.
    if (R.FinishTime >= 0. && R.Place == 1 && !R.bCelebrated && RaceTime() - R.FinishTime > 7.5 && R.Speed < 2.f)
    {
        R.bCelebrated = true;
        F->PlayBody(TEXT("rear"), false); F->PlayRiderOnce(TEXT("rear"));
    }
}

void AHorseRace::Finish(FRaceRunner& R)
{
    R.FinishTime = RaceTime();
    R.Place = ++Finishers;
    if (Finishers == 1) Play(TEXT("HR_FinishBell"), FVector::ZeroVector, .7f, true);
    if (!R.bPlayer) return;
    Phase = EPhase::Finished; PhaseTime = 0.f;
    bLooping = false;
    if (Music) Music->AdjustVolume(2.f, .35f);
    if (Film.IsValid()) Film->Music.Add(FString::Printf(TEXT("{\"frame\":%d,\"event\":\"fade\",\"seconds\":2.0,\"level\":0.35}"), Film->Captured));
    Play(R.Place == 1 ? TEXT("HR_Win") : TEXT("HR_Lose"), FVector::ZeroVector, .8f, true);
    Play(TEXT("HR_CrowdCheer"), FVector::ZeroVector, R.Place <= 3 ? .8f : .45f, true);
    Say(R.Place == 1 ? TEXT("1st!  What a ride!") : FString::Printf(TEXT("%s place"), Ordinal(R.Place)), 4.f);
    const FString Key = Cups[CupIndex].Key;
    if (!BestPlace.Contains(Key) || R.Place < BestPlace[Key]) BestPlace.Add(Key, R.Place);
    if (!BestTime.Contains(Key) || R.FinishTime < BestTime[Key]) BestTime.Add(Key, R.FinishTime);
    SaveResults();
    if (AHippodromeFigure* Master = Venue->GetMaster()) Master->PlayBody(R.Place == 1 ? TEXT("dance") : TEXT("point"), true);
    UE_LOG(LogTemp, Display, TEXT("RACE finish %s %s in %.2f s: perfect %d great %d good %d miss %d, best combo %d"),
        Cups[CupIndex].Key, Ordinal(R.Place), R.FinishTime, Counts[0], Counts[1], Counts[2], Counts[3], R.BestCombo);
}

int32 AHorseRace::PlaceOf(int32 Index) const
{
    // Finishers by their place, the rest by how far they have run.
    const FRaceRunner& R = Runners[Index];
    if (R.Place > 0) return R.Place;
    int32 Place = Finishers + 1;
    for (const FRaceRunner& O : Runners) if (O.Place == 0 && &O != &R && O.Progress > R.Progress) ++Place;
    return Place;
}

void AHorseRace::ShowResults()
{
    // Those still running finish at their present pace.
    for (FRaceRunner& R : Runners)
        if (R.Place == 0)
        {
            R.FinishTime = RaceTime() + (Distance() - R.Progress) / FMath::Max(R.Speed, 6.f);
            R.Place = -1;
        }
    TArray<FRaceRunner*> Late;
    for (FRaceRunner& R : Runners) if (R.Place < 0) Late.Add(&R);
    Late.Sort([](const FRaceRunner& A, const FRaceRunner& B) { return A.FinishTime < B.FinishTime; });
    for (FRaceRunner* R : Late) R->Place = ++Finishers;
    Phase = EPhase::Results; PhaseTime = 0.f; ResultsHeld = 0.f;
}

// ------------------------------------------------------------------------------------------------------------ Camera

void AHorseRace::AdvanceCamera(float Dt)
{
    if (!Camera || !Runners.IsValidIndex(PlayerIndex)) return;
    const FRaceRunner& Me = Runners[PlayerIndex];
    float Yaw = 0.f;
    const FVector At = RunnerPoint(Me, &Yaw);
    const FRotator Facing(0, Yaw, 0);
    const FVector Fwd = Facing.Vector(), Right = FRotationMatrix(Facing).GetUnitAxis(EAxis::Y), Up(0, 0, 1);
    // Close behind and above the player's horse (it is the subject), pulled back a little with speed and the spur.
    const float Back = 640.f + Me.Speed * 10.f + (Me.SpurLeft > 0.f ? 120.f : 0.f);
    // A rider close behind in the camera's lane would fill the foreground: the camera cranes up and looks down over it,
    // so every horse stays in view and the player's stays clear.
    bool bCrowded = false;
    for (const FRaceRunner& R : Runners)
    {
        const double Behind = Me.Progress - R.Progress;
        bCrowded |= !R.bPlayer && Phase == EPhase::Running && Behind > .3 && Behind < Back / 100. + 1.5 && FMath::Abs(R.Offset - Me.Offset) < 2.6f;
    }
    CamLift = Dt > 0.f ? FMath::FInterpTo(CamLift, bCrowded ? 1.f : 0.f, Dt, bCrowded ? 3.f : 1.2f) : 0.f;
    FVector Eye = At - Fwd * Back * (1.f - .2f * CamLift) + Up * (300.f + 280.f * CamLift) + Right * 40.f;
    FVector Focus = At + Fwd * (650.f - 250.f * CamLift) + Up * 150.f;
    if (Phase >= EPhase::Finished && Me.FinishTime >= 0.)
    {
        // Past the post the camera swings round to the side of the horse.
        const float Swing = FMath::Min(float(RaceTime() - Me.FinishTime) / 3.f, 1.f) * 75.f;
        const FVector Offset = (Eye - At).RotateAngleAxis(-Swing, Up);
        Eye = At + Offset * .8f; Focus = At + Up * 160.f;
    }
    // Before the off: in front of the gate, looking back at the stalls; the camera comes round behind as they break.
    float GateYaw = 0.f;
    Venue->Course.At(Venue->Course.GateS, 0., &GateYaw);
    const FRotator GateFacing(0, GateYaw, 0);
    const FVector GateEye = Venue->GateCentre + GateFacing.Vector() * 1500.f - FRotationMatrix(GateFacing).GetUnitAxis(EAxis::Y) * 650.f + Up * 420.f;
    const FVector GateFocus = Venue->GateCentre + Up * 170.f;
    const float Blend = Phase < EPhase::Running ? 0.f : FMath::SmoothStep(0.f, 1.f, FMath::Min(float(RaceTime()) / 1.8f, 1.f));
    if (Phase < EPhase::Running)
    {
        // A slow push in through the parade and count-in.
        const float Push = Phase == EPhase::Parade ? PhaseTime / 4.4f * .5f : .5f + float(Clock / FMath::Max(SongStart, .1)) * .5f;
        Eye = FMath::Lerp(GateEye + GateFacing.Vector() * 500.f, GateEye, FMath::Clamp(Push, 0.f, 1.f)); Focus = GateFocus;
    }
    else if (Blend < 1.f)
    {
        // As the gate opens the camera arcs out over the infield and round behind the field, never through it.
        const float Arc = FMath::Sin(Blend * PI);
        Eye = FMath::Lerp(GateEye, Eye, Blend) - FRotationMatrix(GateFacing).GetUnitAxis(EAxis::Y) * 900.f * Arc + Up * 350.f * Arc;
        Focus = FMath::Lerp(GateFocus, Focus, Blend);
    }
    if (!bCamInit || Dt <= 0.f) { CamEye = Eye; CamRot = (Focus - Eye).Rotation(); bCamInit = true; }
    else
    {
        CamEye = FMath::VInterpTo(CamEye, Eye, Dt, Phase < EPhase::Running ? 3.f : 7.f);
        CamRot = FMath::RInterpTo(CamRot, (Focus - CamEye).Rotation(), Dt, 8.f);
    }
    const float Fov = 68.f + FMath::Clamp(Me.Speed - 9.f, 0.f, 8.f) * 1.1f + (Me.SpurLeft > 0.f ? 9.f : 0.f);
    CamFov = Dt > 0.f ? FMath::FInterpTo(CamFov, Fov, Dt, 4.f) : Fov;
    Camera->SetActorLocationAndRotation(CamEye, CamRot);
    Camera->GetCameraComponent()->SetFieldOfView(CamFov);
    Camera->GetCameraComponent()->SetConstraintAspectRatio(false);
}

// ------------------------------------------------------------------------------------------------------------ HUD

namespace
{
    struct FPainter
    {
        AHUD* Hud; UCanvas* Canvas; float S;
        void Rect(float X, float Y, float W, float H, const FLinearColor& C) const { Hud->DrawRect(C, X, Y, W, H); }
        void Text(const FString& T, float X, float Y, const FLinearColor& C, float Scale, UFont* Font, bool bCentre = false, bool bShadow = true) const
        {
            float W = 0.f, H = 0.f; Canvas->StrLen(Font, T, W, H);
            if (bCentre) X -= W * Scale * .5f;
            if (bShadow) Hud->DrawText(T, FLinearColor(0, 0, 0, .6f * C.A), X + 2.f * S, Y + 2.f * S, Font, Scale);
            Hud->DrawText(T, C, X, Y, Font, Scale);
        }
        float Width(const FString& T, float Scale, UFont* Font) const { float W = 0.f, H = 0.f; Canvas->StrLen(Font, T, W, H); return W * Scale; }
        void Disc(float X, float Y, float R, const FLinearColor& C) const
        {
            const int32 Rows = FMath::Max(4, int32(R));
            for (int32 I = 0; I < Rows; ++I)
            {
                const float V = (I + .5f) / Rows * 2.f - 1.f, Half = R * FMath::Sqrt(FMath::Max(0.f, 1.f - V * V));
                Hud->DrawRect(C, X - Half, Y + V * R - R / Rows, Half * 2.f, 2.f * R / Rows + .5f);
            }
        }
        void Ring(float X, float Y, float R, const FLinearColor& C, float Thick, float From = 0.f, float To = 2.f * PI) const
        {
            const int32 Segments = 28;
            for (int32 I = 0; I < Segments; ++I)
            {
                const float A = FMath::Lerp(From, To, float(I) / Segments), B = FMath::Lerp(From, To, float(I + 1) / Segments);
                Hud->DrawLine(X + R * FMath::Cos(A), Y + R * FMath::Sin(A), X + R * FMath::Cos(B), Y + R * FMath::Sin(B), C, Thick);
            }
        }
    };
}

void AHorseRace::DrawHud(AHUD* Hud, UCanvas* Canvas, int32 Style)
{
    if (!Hud || !Canvas || !GEngine || !Venue.IsValid() || !Runners.IsValidIndex(PlayerIndex)) return;
    const FPainter P{ Hud, Canvas, Canvas->SizeY / 1080.f };
    const float S = P.S, SX = Canvas->SizeX, SY = Canvas->SizeY;
    UFont* Small = GEngine->GetSmallFont(); UFont* Medium = GEngine->GetMediumFont(); UFont* Large = GEngine->GetLargeFont();
    const FRaceCup& C = Cups[CupIndex];
    const FRaceRunner& Me = Runners[PlayerIndex];
    // A light touch: text over the scene with soft shadows and thin rules, kept to the sky and the strip under the horse.
    const FLinearColor Ink(1.f, .95f, .84f), Dim(.86f, .84f, .78f, .85f), Gold(1.f, .86f, .45f), Wash(0.f, 0.f, 0.f, .16f);
    const bool bPad = Style != 0;
    static const TCHAR* PadNames[5][4] = { { TEXT("D"), TEXT("F"), TEXT("J"), TEXT("K") }, { TEXT("A"), TEXT("B"), TEXT("X"), TEXT("Y") },
        { TEXT("X"), TEXT("O"), TEXT("[]"), TEXT("/\\") }, { TEXT("B"), TEXT("A"), TEXT("Y"), TEXT("X") }, { TEXT("v"), TEXT(">"), TEXT("<"), TEXT("^") } };
    const TCHAR* const* Keys = PadNames[FMath::Clamp(Style, 0, 4)];
    const bool bRaceView = Phase != EPhase::Results;   // the results card stands alone over the scene

    // ---- Header: the cup and the lap, then the clock, the distance to go and the speed.
    {
        const float X = 36 * S, Y = 28 * S;
        const int32 Total = FMath::CeilToInt(C.Laps);
        const FString LapText = Phase >= EPhase::Finished ? FString(TEXT("Finished")) : LastLapShown >= Total ? FString(TEXT("Final lap")) : FString::Printf(TEXT("Lap %d / %d"), FMath::Max(LastLapShown, 1), Total);
        P.Text(FString::Printf(TEXT("%s  ·  %s"), *FString(C.Name).ToUpper(), *LapText), X, Y, Gold, 1.15f * S, Small);
        const double Time = Phase >= EPhase::Running ? (Me.FinishTime >= 0. ? Me.FinishTime : RaceTime()) : 0.;
        P.Text(ClockText(Time), X, Y + 22 * S, Ink, .95f * S, Medium);
        P.Text(FString::Printf(TEXT("%.0f m to go   %.0f km/h"), FMath::Max(0., Distance() - Me.Progress), Me.Speed * 3.6f), X + 130 * S, Y + 30 * S, Dim, 1.1f * S, Small);
    }
    // ---- Standings: just the riders round you (the one ahead, you, the one behind), with the gaps; the full field
    // waits for the results. Nothing before the off.
    if (bRaceView && Phase >= EPhase::Running)
    {
        TArray<int32> Order; for (int32 I = 0; I < Runners.Num(); ++I) Order.Add(I);
        Order.Sort([this](int32 A, int32 B) { return PlaceOf(A) < PlaceOf(B); });
        const int32 Mine = Order.IndexOfByKey(PlayerIndex);
        const int32 First = FMath::Clamp(Mine - 1, 0, FMath::Max(0, Order.Num() - 3)), Last = FMath::Min(First + 3, Order.Num());
        const float X = 36 * S, RowH = 23 * S; float Y = 92 * S;
        P.Rect(X - 10 * S, Y - 6 * S, 250 * S, (Last - First) * RowH + 10 * S, Wash);
        for (int32 K = First; K < Last; ++K)
        {
            const FRaceRunner& R = Runners[Order[K]];
            const FLinearColor Col = R.bPlayer ? Gold : Ink;
            P.Text(Ordinal(PlaceOf(Order[K])), X, Y, Col, 1.05f * S, Small);
            P.Rect(X + 38 * S, Y + 4 * S, 6 * S, 12 * S, R.Colour);
            P.Text(R.Name, X + 52 * S, Y, Col, 1.05f * S, Small);
            if (R.bPlayer) P.Rect(X + 52 * S, Y + 19 * S, P.Width(R.Name, 1.05f * S, Small), 1.5f * S, Gold);
            // Gaps are to you: + ahead, - behind; a finished rider shows its time.
            const double Gap = R.Progress - Me.Progress;
            const FString Text = R.FinishTime >= 0. && R.Place > 0 ? ClockText(R.FinishTime) : R.bPlayer ? FString() : FString::Printf(TEXT("%+d m"), FMath::RoundToInt(Gap));
            P.Text(Text, X + 232 * S - P.Width(Text, 1.05f * S, Small), Y, Dim, 1.05f * S, Small);
            Y += RowH;
        }
    }
    // ---- Minimap of the oval, top right: just the rails, the post and the dots.
    {
        const FHippodromeCourse& K = Venue->Course;
        const float W = 220 * S, H = 110 * S, X0 = SX - W - 36 * S, Y0 = 32 * S;
        const double SpanX = 2. * (K.Half + K.Radius + K.Width), SpanY = 2. * (K.Radius + K.Width);
        auto Map = [&](const FVector& World) { return FVector2D(X0 + (World.X / 100. - (K.Origin.X - SpanX / 2.)) / SpanX * W, Y0 + (World.Y / 100. + K.Origin.Y + SpanY / 2.) / SpanY * H); };
        for (const float Edge : { -float(K.Width * .5), float(K.Width * .5) })
            for (int32 I = 0; I < 64; ++I)
            {
                const FVector2D A = Map(K.At(K.Lap * I / 64., Edge)), B = Map(K.At(K.Lap * (I + 1) / 64., Edge));
                Hud->DrawLine(A.X, A.Y, B.X, B.Y, FLinearColor(1.f, .95f, .85f, .5f), 1.2f * S);
            }
        const FVector2D In = Map(K.At(0., -K.Width * .5)), Out = Map(K.At(0., K.Width * .5));
        Hud->DrawLine(In.X, In.Y, Out.X, Out.Y, FLinearColor(1.f, .35f, .3f, .9f), 2.f * S);
        for (int32 Pass = 0; Pass < 2; ++Pass)
            for (const FRaceRunner& R : Runners)
                if (R.bPlayer == (Pass == 1))
                {
                    const FVector2D D = Map(RunnerPoint(R));
                    if (R.bPlayer) P.Disc(D.X, D.Y, 6.f * S, FLinearColor(0, 0, 0, .5f));
                    P.Disc(D.X, D.Y, (R.bPlayer ? 4.5f : 3.2f) * S, R.Colour);
                }
    }
    // ---- The note rail, along the bottom under the horse: four thin rows, the notes sliding left into the hit rings.
    // It covers only the dirt behind the horse, so the track ahead, the field and the stands stay clear.
    const float RowH = 22 * S, RailTop = SY - 40 * S - 4 * RowH, RailX0 = 36 * S, RailX1 = SX - 36 * S, HitX = RailX0 + 44 * S;
    auto RowY = [&](int32 Lane) { return RailTop + (Lane + .5f) * RowH; };
    auto AtX = [&](double Ahead) { return HitX + float(Ahead / C.Lookahead) * (RailX1 - HitX); };
    if (bRaceView)
    {
        P.Rect(RailX0, RailTop, RailX1 - RailX0, 4 * RowH, FLinearColor(.04f, .03f, .02f, .16f));
        for (int32 Line = 1; Line < 4; ++Line) P.Rect(HitX, RailTop + Line * RowH, RailX1 - HitX, 1.f, FLinearColor(1.f, .95f, .8f, .07f));
        // Beat lines drift left with the music.
        if (Beat > .05)
            for (double B = FMath::CeilToDouble(Clock / Beat) * Beat; B < Clock + C.Lookahead; B += Beat)
                P.Rect(AtX(B - Clock), RailTop, 1.5f * S, 4 * RowH, FLinearColor(1.f, .95f, .8f, .08f));
        // The hit line, the rings and the keys.
        P.Rect(HitX - 1.25f * S, RailTop - 3 * S, 2.5f * S, 4 * RowH + 6 * S, FLinearColor(1.f, .95f, .82f, .55f));
        for (int32 Lane = 0; Lane < 4; ++Lane)
        {
            const float LY = RowY(Lane);
            const FLinearColor Col = LaneColour[Lane];
            if (LaneDown[Lane] || LaneFlash[Lane] > 0.f) P.Disc(HitX, LY, 12 * S, FLinearColor(Col.R, Col.G, Col.B, .35f));
            P.Ring(HitX, LY, 9 * S, FLinearColor(Col.R, Col.G, Col.B, .85f), 2.f * S);
            if (LaneHit[Lane] > 0.f) P.Ring(HitX, LY, (9.f + (.22f - LaneHit[Lane]) * 60.f) * S, FLinearColor(1.f, 1.f, .9f, LaneHit[Lane] * 3.f), 2.f * S);
            P.Text(bPad ? Keys[Lane] : PadNames[0][Lane], RailX0 + 12 * S, LY - 8 * S, Dim, 1.f * S, Small, true);
        }
        // Notes, far ones first so the near ones draw over them; a long note trails a bar to its end.
        for (int32 I = Notes.Num() - 1; I >= FirstLive; --I)
        {
            const FRaceNote& N = Notes[I];
            if (N.T - Clock > C.Lookahead || (N.State != 0 && !N.bHolding) || N.T + N.Hold < Clock - .2) continue;
            const FLinearColor Col = LaneColour[N.Lane];
            const float NX = AtX(FMath::Max(N.T - Clock, N.bHolding ? 0. : -.2)), LY = RowY(N.Lane);
            if (N.Hold > .05)
            {
                const float EX = AtX(FMath::Min(N.T + N.Hold - Clock, double(C.Lookahead)));
                P.Rect(NX, LY - 3 * S, FMath::Max(0.f, EX - NX), 6 * S, FLinearColor(Col.R, Col.G, Col.B, N.bHolding ? .95f : .7f));
            }
            P.Disc(NX, LY, 9.5f * S, FLinearColor(0, 0, 0, .3f));
            P.Disc(NX, LY, 8 * S, Col);
            P.Disc(NX - 2 * S, LY - 2.5f * S, 2.8f * S, FLinearColor(1.f, 1.f, 1.f, .45f));
        }
        // Judgement and combo just above the hit rings, where the eye already is.
        if (JudgementTime > 0.f)
        {
            const float A = FMath::Clamp(JudgementTime / .2f, 0.f, 1.f);
            P.Text(Judgement, HitX + 24 * S, RailTop - 34 * S - (1.f - A) * 6 * S, FLinearColor(JudgementColour.R, JudgementColour.G, JudgementColour.B, A), 1.3f * S, Medium);
        }
        if (Me.Combo >= 4) P.Text(FString::Printf(TEXT("%d combo"), Me.Combo), HitX + 190 * S, RailTop - 26 * S, Dim, 1.1f * S, Small);
    }
    // ---- Stride (the rhythm meter) and the spurs, one thin line under the rail.
    if (bRaceView)
    {
        const float X = RailX0, Y = SY - 28 * S, W = 300 * S;
        P.Text(TEXT("STRIDE"), X, Y - 7 * S, Dim, .95f * S, Small);
        const float BarX = X + 64 * S, BarH = 6 * S;
        P.Rect(BarX, Y - BarH * .5f, W, BarH, FLinearColor(1.f, 1.f, 1.f, .14f));
        const FLinearColor Fill = FMath::Lerp(FLinearColor(.9f, .42f, .3f), FLinearColor(.5f, .95f, .55f), Me.Meter);
        P.Rect(BarX, Y - BarH * .5f, W * Me.Meter, BarH, Me.SpurLeft > 0.f ? Gold : Fill);
        for (int32 Mark = 1; Mark < 4; ++Mark) P.Rect(BarX + W * Mark / 4.f, Y - BarH * .5f, 1.5f * S, BarH, FLinearColor(0, 0, 0, .3f));
        const float PipX = BarX + W + 28 * S;
        for (int32 Pip = 0; Pip < MaxPips; ++Pip)
        {
            // A horseshoe: an open ring.
            const bool bOn = Pip < Me.Pips;
            P.Ring(PipX + Pip * 26 * S, Y, 8 * S, bOn ? Gold : FLinearColor(1.f, 1.f, 1.f, .25f), (bOn ? 3.f : 1.5f) * S, -PI * 1.25f, PI * .25f);
        }
        const float Next = float(Me.Combo % ComboPerPip) / ComboPerPip;
        if (Me.Pips < MaxPips) P.Rect(PipX - 8 * S, Y + 11 * S, 26 * S * MaxPips * Next, 1.5f * S, FLinearColor(1.f, .86f, .45f, .6f));
        const FString Hint = bPad ? FString::Printf(TEXT("%s spur"), Style == 2 ? TEXT("R1") : Style == 3 ? TEXT("R") : TEXT("RB")) : FString(TEXT("Space spur"));
        if (Me.Pips > 0) P.Text(Hint, PipX + MaxPips * 26 * S + 4 * S, Y - 7 * S, Gold, .95f * S, Small);
    }
    // ---- Controls: above the rail through the count-in and the first seconds of the race, then it fades away.
    {
        const float Shown = Phase < EPhase::Running ? 1.f : FMath::Clamp(1.f - (float(RaceTime()) - 6.f) / 1.5f, 0.f, 1.f);
        const FString Line = bPad ? FString::Printf(TEXT("%s %s %s %s notes   Left stick / D-pad steer   Hold Menu retire"), Keys[0], Keys[1], Keys[2], Keys[3])
            : FString(TEXT("D F J K notes (hold the long ones)   Left / Right steer   Hold Esc retire"));
        if (Shown > 0.f && bRaceView) P.Text(Line, SX * .5f, RailTop - 30 * S, FLinearColor(.88f, .86f, .8f, .8f * Shown), 1.05f * S, Small, true);
    }
    // ---- Countdown, callouts, being boxed in.
    if (Phase == EPhase::Countdown)
    {
        int32 Beat_ = 0; for (double T : CountIn) if (Clock >= T) ++Beat_;
        const TCHAR* Words[5] = { TEXT(""), TEXT("Ready"), TEXT("3"), TEXT("2"), TEXT("1") };
        if (Beat_ > 0) P.Text(Words[FMath::Min(Beat_, 4)], SX * .5f, SY * .36f, FLinearColor(1.f, .9f, .6f, .9f), 2.4f * S, Large, true);
    }
    if (Phase == EPhase::Running && RaceTime() < .9) P.Text(TEXT("GO!"), SX * .5f, SY * .36f, FLinearColor(1.f, .85f, .35f, 1.f - float(RaceTime()) / .9f), 2.8f * S, Large, true);
    if (CalloutTime > 0.f && !Callout.IsEmpty())
        P.Text(Callout, SX * .5f, SY * .2f, FLinearColor(1.f, .93f, .78f, FMath::Clamp(CalloutTime / .4f, 0.f, 1.f)), 1.5f * S, Medium, true);
    if (Me.bBoxed && Phase == EPhase::Running)
        P.Text(TEXT("Boxed in: steer round!"), SX * .5f, SY * .26f, FLinearColor(1.f, .55f, .4f), 1.1f * S, Medium, true);
    if (EscHeld > .05f) P.Text(FString::Printf(TEXT("Retiring... %.0f%%"), EscHeld * 100.f), SX * .5f, SY * .3f, FLinearColor(1.f, .6f, .5f), 1.2f * S, Medium, true);
    // ---- Results.
    if (Phase == EPhase::Results)
    {
        const float W = 760 * S, H = 400 * S, X = SX * .5f - W * .5f, Y = SY * .5f - H * .5f;
        P.Rect(X, Y, W, H, FLinearColor(.05f, .035f, .025f, .72f));
        P.Rect(X, Y, W, 2 * S, FLinearColor(1.f, .8f, .4f));
        P.Text(FString::Printf(TEXT("%s  ·  RESULT"), C.Name).ToUpper(), X + 32 * S, Y + 24 * S, FLinearColor(1.f, .8f, .42f), 1.1f * S, Medium);
        TArray<int32> Order; for (int32 I = 0; I < Runners.Num(); ++I) Order.Add(I);
        Order.Sort([this](int32 A, int32 B) { return Runners[A].Place < Runners[B].Place; });
        float RY = Y + 70 * S;
        for (int32 Index : Order)
        {
            const FRaceRunner& R = Runners[Index];
            const FLinearColor Col = R.bPlayer ? FLinearColor(1.f, .88f, .45f) : Ink;
            if (R.bPlayer) P.Rect(X + 20 * S, RY - 4 * S, W - 40 * S, 30 * S, FLinearColor(1.f, .85f, .35f, .15f));
            P.Text(Ordinal(R.Place), X + 32 * S, RY, Col, 1.4f * S, Small);
            P.Rect(X + 84 * S, RY + 3 * S, 10 * S, 18 * S, R.Colour);
            P.Text(FString::Printf(TEXT("%s on %s"), *R.Name, *R.HorseName), X + 106 * S, RY, Col, 1.4f * S, Small);
            P.Text(ClockText(R.FinishTime), X + W - 150 * S, RY, Col, 1.4f * S, Small);
            RY += 32 * S;
        }
        const int32 Notes_ = Counts[0] + Counts[1] + Counts[2] + Counts[3];
        const float Accuracy = Notes_ ? (Counts[0] + .8f * Counts[1] + .5f * Counts[2]) / Notes_ * 100.f : 0.f;
        RY += 14 * S;
        P.Text(FString::Printf(TEXT("Rhythm %.0f%%     Perfect %d   Great %d   Good %d   Miss %d     Best combo %d"), Accuracy, Counts[0], Counts[1], Counts[2], Counts[3], Me.BestCombo),
            X + 32 * S, RY, Ink, 1.25f * S, Small);
        RY += 34 * S;
        const FString Key = C.Key;
        if (BestTime.Contains(Key)) P.Text(FString::Printf(TEXT("Best time %s     Best place %s"), *ClockText(BestTime[Key]), Ordinal(BestPlace.FindRef(Key))), X + 32 * S, RY, Dim, 1.25f * S, Small);
        const int32 Place = Me.Place;
        const TCHAR* Medal = Place == 1 ? TEXT("GOLD") : Place == 2 ? TEXT("SILVER") : Place == 3 ? TEXT("BRONZE") : nullptr;
        if (Medal)
        {
            const FLinearColor MC = Place == 1 ? FLinearColor(1.f, .82f, .3f) : Place == 2 ? FLinearColor(.85f, .87f, .9f) : FLinearColor(.85f, .55f, .3f);
            // In the title row, clear of the times.
            P.Disc(X + W - 48 * S, Y + 38 * S, 16 * S, MC);
            P.Text(Medal, X + W - 72 * S - P.Width(Medal, 1.2f * S, Small), Y + 27 * S, MC, 1.2f * S, Small);
        }
        P.Text(bPad ? FString::Printf(TEXT("%s continue"), Keys[0]) : FString(TEXT("Enter continue")), X + W * .5f, Y + H - 40 * S, Dim, 1.2f * S, Small, true);
    }
}

FString AHorseRace::Describe() const
{
    TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
    static const TCHAR* Phases[7] = { TEXT("idle"), TEXT("menu"), TEXT("parade"), TEXT("countdown"), TEXT("running"), TEXT("finished"), TEXT("results") };
    O->SetStringField(TEXT("phase"), Phases[int32(Phase)]);
    O->SetStringField(TEXT("cup"), Cups[CupIndex].Key);
    O->SetNumberField(TEXT("clock"), Clock);
    O->SetNumberField(TEXT("race_time"), Phase >= EPhase::Running ? RaceTime() : 0.);
    O->SetNumberField(TEXT("distance"), Distance());
    O->SetNumberField(TEXT("loops"), Loops);
    TArray<TSharedPtr<FJsonValue>> Counted;
    for (int32 I = 0; I < 4; ++I) Counted.Add(MakeShared<FJsonValueNumber>(Counts[I]));
    O->SetArrayField(TEXT("counts"), Counted);
    TArray<TSharedPtr<FJsonValue>> List;
    for (int32 I = 0; I < Runners.Num(); ++I)
    {
        const FRaceRunner& R = Runners[I];
        TSharedRef<FJsonObject> E = MakeShared<FJsonObject>();
        E->SetStringField(TEXT("name"), R.Name); E->SetStringField(TEXT("horse"), R.Horse); E->SetBoolField(TEXT("player"), R.bPlayer);
        E->SetNumberField(TEXT("progress"), R.Progress); E->SetNumberField(TEXT("offset"), R.Offset); E->SetNumberField(TEXT("speed"), R.Speed);
        E->SetNumberField(TEXT("meter"), R.Meter); E->SetNumberField(TEXT("combo"), R.Combo); E->SetNumberField(TEXT("pips"), R.Pips);
        E->SetNumberField(TEXT("place"), PlaceOf(I)); E->SetNumberField(TEXT("finish"), R.FinishTime);
        E->SetStringField(TEXT("gait"), R.GaitRole.ToString()); E->SetBoolField(TEXT("boxed"), R.bBoxed);
        List.Add(MakeShared<FJsonValueObject>(E));
    }
    O->SetArrayField(TEXT("runners"), List);
    FString Text; FJsonSerializer::Serialize(O, TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text));
    return Text;
}

// ------------------------------------------------------------------------------------------------------------ Film

void AHorseRace::AdvanceFilm(float Dt)
{
    FFilm& F = *Film;
    if (F.bDone) return;
    AWandererCharacter* P = Cast<AWandererCharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
    if (!P || !P->IsReady() || !Venue.IsValid()) return;
    if (!F.bStarted)
    {
        // Stand by the grandstand and let streaming, shaders and the light settle before the first kept frame.
        if (F.Warm == 0.f) P->TravelTo(Venue->ReturnGround, Venue->ReturnYaw, TEXT("Race film"));
        F.Warm += Dt;
        if (F.Warm < 5.f) return;
        F.bStarted = true;
        IFileManager::Get().MakeDirectory(*F.Dir, true);
        FFilm* Self = &F;
        F.Capture = UGameViewportClient::OnScreenshotCaptured().AddLambda([Self](int32 W, int32 H, const TArray<FColor>& Pixels)
        {
            if (Self->Pending < 0) return;
            TArray<FColor> Opaque = Pixels; for (FColor& C : Opaque) C.A = 255;
            FImageUtils::SaveImageByExtension(*(Self->Dir / FString::Printf(TEXT("frame_%05d.jpg"), Self->Pending)), FImageView(Opaque.GetData(), W, H), 92);
            Self->Pending = -1;
        });
        FAtelierAudioLog::Events.Reset(); FAtelierAudioLog::Frame = 0; FAtelierAudioLog::bRecording = true;
        if (!StartRace(P, F.Cup, F.Horse, F.Accuracy)) { UE_LOG(LogTemp, Error, TEXT("RACE FILM could not start the race")); FinishFilm(); return; }
        return;   // the first kept frame is the race camera's
    }
    F.Elapsed += Dt;
    FAtelierAudioLog::Frame = F.Captured;
    if (Camera)
    {
        const FVector E = Camera->GetActorLocation(); const FRotator R = Camera->GetActorRotation();
        F.CameraCsv += FString::Printf(TEXT("%d,%.1f,%.1f,%.1f,%.2f,%.2f,%.2f,%.1f,%d\n"), F.Captured, E.X, E.Y, E.Z, R.Pitch, R.Yaw, R.Roll, CamFov, int32(Phase));
    }
    F.Pending = F.Captured++;
    FScreenshotRequest::RequestScreenshot(true);
    if ((Phase == EPhase::Results && PhaseTime > 5.f) || Phase == EPhase::Idle || F.Elapsed > 240.f) FinishFilm();
}

void AHorseRace::FinishFilm()
{
    FFilm& F = *Film;
    F.bDone = true;
    FString Audio = TEXT("[\n");
    for (int32 I = 0; I < FAtelierAudioLog::Events.Num(); ++I)
    {
        const FAtelierAudioEvent& E = FAtelierAudioLog::Events[I];
        Audio += FString::Printf(TEXT("  {\"frame\":%d,\"sound\":\"%s\",\"source\":\"%s\",\"x\":%.1f,\"y\":%.1f,\"z\":%.1f,\"volume\":%.3f,\"pitch\":%.3f,\"2d\":%s,\"loop\":%s}%s\n"),
            E.Frame, *E.Sound, *E.Source.Replace(TEXT("\\"), TEXT("/")), E.At.X, E.At.Y, E.At.Z, E.Volume, E.Pitch, E.b2D ? TEXT("true") : TEXT("false"),
            E.bLoop ? TEXT("true") : TEXT("false"), I + 1 < FAtelierAudioLog::Events.Num() ? TEXT(",") : TEXT(""));
    }
    Audio += TEXT("]\n");
    FFileHelper::SaveStringToFile(Audio, *(F.Dir / TEXT("audio.json")));
    FFileHelper::SaveStringToFile(F.CameraCsv, *(F.Dir / TEXT("camera.csv")));
    const FString Result = FString::Printf(TEXT("{\"frames\":%d,\"fps\":60,\"cup\":\"%s\",\"horse\":\"%s\",\"autoplay\":%.2f,\"music\":[%s],\"race\":%s}\n"),
        F.Captured, Cups[CupIndex].Key, *PlayerHorse, AutoAccuracy, *FString::Join(F.Music, TEXT(",")), *Describe());
    FFileHelper::SaveStringToFile(Result, *(F.Dir / TEXT("film.json")));
    UE_LOG(LogTemp, Display, TEXT("RACE FILM COMPLETE %s"), *Result);
    FAtelierAudioLog::bRecording = false;
    if (F.Capture.IsValid()) UGameViewportClient::OnScreenshotCaptured().Remove(F.Capture);
    FPlatformMisc::RequestExit(false);
}

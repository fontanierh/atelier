#include "YorimichiLive.h"
#include "LiveLibrary.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "SkateComponent.h"
#include "SkatePark.h"
#include "YorimichiCombatFX.h"
#include "BotwCreature.h"
#include "BotwRider.h"
#include "Components/SkeletalMeshComponent.h"
#include "EngineUtils.h"
#include "Misc/FileHelper.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

// Yorimichi's verbs for the live bridge (the platform's are in ULiveLibrary).

bool UYorimichiLive::Drive(FVector2D Intent, int32 Gait)
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player()); if (!P) return false;
    P->Live_Drive(Intent.GetClampedToMaxSize(1.f), FMath::Clamp(Gait, 0, 2)); return true;
}

bool UYorimichiLive::Press(const FString& Button)
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player()); return P && P->Live_Press(FName(*Button));
}

bool UYorimichiLive::ToggleSword()
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player()); if (!P || !P->GetSword() || !P->GetSword()->IsInstalled()) return false;
    P->GetSword()->ToggleWeapon(); return true;
}

static USkateComponent* PlayerSkate() { AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player()); return P ? P->GetSkate() : nullptr; }
bool UYorimichiLive::SkateToggle() { USkateComponent* S = PlayerSkate(); return S && S->Toggle(); }
bool UYorimichiLive::SkateInput(FVector2D Left, FVector2D Right, bool Push, bool Brake, bool Powerslide, bool GrabLeft, bool GrabRight)
{
    USkateComponent* S = PlayerSkate(); if (!S) return false;
    FSkateInput In; In.Left = Left; In.Right = Right; In.bPush = Push; In.bBrake = Brake; In.bPowerslide = Powerslide; In.bGrabLeft = GrabLeft; In.bGrabRight = GrabRight;
    S->SetScriptedInput(&In); return true;
}
bool UYorimichiLive::SkateRelease() { USkateComponent* S = PlayerSkate(); if (!S) return false; S->SetScriptedInput(nullptr); return true; }
FString UYorimichiLive::SkateState()
{
    USkateComponent* S = PlayerSkate(); if (!S) return TEXT("no skate");
    const FVector P = S->GetOwner()->GetActorLocation();
    return FString::Printf(TEXT("%s | combo=%s | last=%s landed=%d bails=%d grinds=%d score=%d | pos=(%.0f,%.0f,%.0f)"), *S->GetDebug(), *S->GetComboLine(),
        *S->GetLastTrick().ToString(), S->GetLandedCount(), S->GetBailCount(), S->GetGrindCount(), S->GetScore(), P.X, P.Y, P.Z);
}
bool UYorimichiLive::SkateGoofy(bool bGoofy) { USkateComponent* S = PlayerSkate(); if (!S) return false; S->SetGoofy(bGoofy); return true; }
bool UYorimichiLive::SkateLaunch(FVector Velocity) { USkateComponent* S = PlayerSkate(); if (!S) return false; S->Launch(Velocity); return true; }
static bool GFilmHud = false;
void UYorimichiLive::FilmHud(bool bOn) { GFilmHud = bOn; }
bool UYorimichiLive::IsFilmHud() { return GFilmHud; }
int32 UYorimichiLive::AudioLog(const FString& Command, const FString& Path)
{
    if (Command == TEXT("start")) { FAtelierAudioLog::Events.Reset(); FAtelierAudioLog::Frame = 0; FAtelierAudioLog::bRecording = true; return 0; }
    FAtelierAudioLog::bRecording = false;
    if (Command == TEXT("stop") && !Path.IsEmpty())
    {
        TArray<TSharedPtr<FJsonValue>> Rows;
        for (const FAtelierAudioEvent& E : FAtelierAudioLog::Events)
        {
            TSharedPtr<FJsonObject> O = MakeShared<FJsonObject>();
            O->SetNumberField(TEXT("frame"), E.Frame); O->SetStringField(TEXT("sound"), E.Sound); O->SetStringField(TEXT("source"), E.Source);
            O->SetNumberField(TEXT("x"), E.At.X); O->SetNumberField(TEXT("y"), E.At.Y); O->SetNumberField(TEXT("z"), E.At.Z);
            O->SetNumberField(TEXT("volume"), E.Volume); O->SetNumberField(TEXT("pitch"), E.Pitch); O->SetBoolField(TEXT("2d"), E.b2D);
            Rows.Add(MakeShared<FJsonValueObject>(O));
        }
        FString Text; auto Writer = TJsonWriterFactory<>::Create(&Text); FJsonSerializer::Serialize(Rows, Writer);
        FFileHelper::SaveStringToFile(Text, *ULiveLibrary::Resolve(Path));
    }
    return FAtelierAudioLog::Events.Num();
}
void UYorimichiLive::AudioFrame(int32 Frame) { FAtelierAudioLog::Frame = Frame; }
FString UYorimichiLive::SkateLoops() { USkateComponent* S = PlayerSkate(); return S ? S->GetLoopState() : FString(); }
bool UYorimichiLive::HoldCamera(float Seconds) { AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player()); if (!P) return false; P->Live_HoldCamera(Seconds); return true; }
bool UYorimichiLive::SkatePlace(FVector GroundPoint, float Yaw) { USkateComponent* S = PlayerSkate(); return S && S->PlaceAt(GroundPoint, Yaw); }
FTransform UYorimichiLive::SkateParkSpawn()
{
    UWorld* W = ULiveLibrary::GameWorld(); if (!W) return FTransform::Identity;
    for (TActorIterator<ASkatePark> It(W); It; ++It)
        if (It->ActorHasTag(TEXT("skatepier")))
            return FTransform(FRotator(0, It->ParkSpawnYaw, 0), It->ParkSpawn);
    return FTransform::Identity;
}

static bool BotwModeFromText(const FString& Text, EBotwMode& Mode)
{
    static const TMap<FString, EBotwMode> Modes = { { TEXT("idle"), EBotwMode::Idle }, { TEXT("showcase"), EBotwMode::Showcase },
        { TEXT("wander"), EBotwMode::Wander }, { TEXT("camp"), EBotwMode::Camp }, { TEXT("scripted"), EBotwMode::Scripted } };
    const EBotwMode* Found = Modes.Find(Text.ToLower());
    if (Found) Mode = *Found;
    return Found != nullptr;
}

static ABotwCreature* FindBotw(const FString& Name)
{
    UWorld* World = ULiveLibrary::Player() ? ULiveLibrary::Player()->GetWorld() : nullptr;
    if (World) for (TActorIterator<ABotwCreature> It(World); It; ++It) if (It->GetName() == Name) return *It;
    return nullptr;
}

FString UYorimichiLive::BotwRoster()
{
    TArray<TSharedPtr<FJsonValue>> Out;
    for (const auto& Entry : FBotwSpec::All())
    {
        const FBotwSpec& S = Entry.Value;
        TSharedPtr<FJsonObject> O = MakeShared<FJsonObject>();
        O->SetStringField(TEXT("name"), S.Name); O->SetStringField(TEXT("label"), S.Label);
        O->SetNumberField(TEXT("height_cm"), S.HeightCm); O->SetNumberField(TEXT("clips"), S.Clips.Num());
        TSharedPtr<FJsonObject> Roles = MakeShared<FJsonObject>();
        for (const auto& R : S.Roles) Roles->SetStringField(R.Key.ToString(), R.Value.ToString());
        O->SetObjectField(TEXT("roles"), Roles);
        Out.Add(MakeShared<FJsonValueObject>(O));
    }
    FString Text; TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Text);
    FJsonSerializer::Serialize(Out, Writer); return Text;
}

FString UYorimichiLive::BotwSpawn(const FString& Name, FVector Ground, float Yaw, const FString& Mode)
{
    EBotwMode Parsed = EBotwMode::Idle;
    if (!BotwModeFromText(Mode, Parsed) || !ULiveLibrary::Player()) return FString();
    ABotwCreature* Creature = ABotwCreature::SpawnAt(ULiveLibrary::Player()->GetWorld(), Name, Ground, Yaw, Parsed);
    return Creature ? Creature->GetName() : FString();
}

float UYorimichiLive::BotwPlay(const FString& Actor, const FString& Clip, bool bLoop, float Rate)
{
    ABotwCreature* Creature = FindBotw(Actor); return Creature ? Creature->Play(Clip, bLoop, Rate) : 0.f;
}

bool UYorimichiLive::BotwMoveTo(const FString& Actor, FVector Ground, bool bRun)
{
    ABotwCreature* Creature = FindBotw(Actor); if (!Creature) return false;
    Creature->MoveTo(Ground, bRun); return true;
}

bool UYorimichiLive::BotwMode(const FString& Actor, const FString& Mode)
{
    ABotwCreature* Creature = FindBotw(Actor); EBotwMode Parsed;
    if (!Creature || !BotwModeFromText(Mode, Parsed)) return false;
    Creature->SetMode(Parsed); return true;
}

FString UYorimichiLive::BotwList()
{
    TArray<TSharedPtr<FJsonValue>> Out;
    UWorld* World = ULiveLibrary::Player() ? ULiveLibrary::Player()->GetWorld() : nullptr;
    if (World) for (TActorIterator<ABotwCreature> It(World); It; ++It)
    {
        TSharedPtr<FJsonObject> O = MakeShared<FJsonObject>();
        O->SetStringField(TEXT("actor"), It->GetName()); O->SetStringField(TEXT("name"), It->Spec().Name);
        O->SetStringField(TEXT("clip"), It->CurrentClip());
        const FVector L = It->GetActorLocation();
        O->SetArrayField(TEXT("location"), { MakeShared<FJsonValueNumber>(L.X), MakeShared<FJsonValueNumber>(L.Y), MakeShared<FJsonValueNumber>(L.Z) });
        O->SetNumberField(TEXT("yaw"), It->GetActorRotation().Yaw);
        Out.Add(MakeShared<FJsonValueObject>(O));
    }
    FString Text; TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Text);
    FJsonSerializer::Serialize(Out, Writer); return Text;
}

int32 UYorimichiLive::BotwClear()
{
    int32 Removed = 0;
    UWorld* World = ULiveLibrary::Player() ? ULiveLibrary::Player()->GetWorld() : nullptr;
    if (World) for (TActorIterator<ABotwCreature> It(World); It; ++It) { It->Destroy(); ++Removed; }
    return Removed;
}

FString UYorimichiLive::SwitchCharacter(const FString& Name)
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player());
    if (P) if (AWandererCharacter* To = ABotwRider::SwitchPlayer(P, Name)) P = To;
    return P ? ABotwRider::NameOf(P) : FString();
}

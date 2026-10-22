#include "YorimichiLive.h"
#include "LiveLibrary.h"
#include "WandererCharacter.h"
#include "JapanPreferences.h"
#include "JapanWorld.h"
#include "FoliageSystem.h"
#include "YorimichiBuildIdentity.h"
#include "Misc/App.h"
#include "JapanCharacterSelect.h"
#include "WandererSword.h"
#include "SkateComponent.h"
#include "BikeComponent.h"
#include "DrivingComponent.h"
#include "HorseComponent.h"
#include "SkatePark.h"
#include "YorimichiCombatFX.h"
#include "PlayableCharacter.h"
#include "AdventureMoveSet.h"
#include "SwordTrainer.h"
#include "Hippodrome.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "EngineUtils.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Framework/Application/SlateApplication.h"
#include "Input/Events.h"
#include "InputCoreTypes.h"
#include "DevNotes.h"
#include "Engine/GameViewportClient.h"
#include "UnrealClient.h"
#include "GameFramework/PlayerController.h"

// Yorimichi's verbs for the live bridge (the platform's are in ULiveLibrary).

bool UYorimichiLive::Drive(FVector2D Intent, int32 Gait)
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player()); if (!P) return false;
    P->Live_Drive(Intent.GetClampedToMaxSize(1.f), FMath::Clamp(Gait, 0, 2)); return true;
}

bool UYorimichiLive::BikeLean(float Lean)
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player()); if (!P) return false;
    P->Live_BikeLean(Lean); return true;
}

bool UYorimichiLive::Press(const FString& Button)
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player()); return P && P->Live_Press(FName(*Button));
}

bool UYorimichiLive::MenuKey(const FString& Key)
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player());
    const bool bPrefsOpen = P && P->GetPreferences() && P->GetPreferences()->IsMenuOpen();
    const bool bSelectOpen = FJapanCharacterSelect::IsOpen();
    if (!P || (!bPrefsOpen && !bSelectOpen) || !FSlateApplication::IsInitialized()) return false;
    if (bSelectOpen && (Key == TEXT("next") || Key == TEXT("Right") || Key == TEXT("Gamepad_DPad_Right"))) return FJapanCharacterSelect::StepSelection(1);
    if (bSelectOpen && (Key == TEXT("previous") || Key == TEXT("Left") || Key == TEXT("Gamepad_DPad_Left"))) return FJapanCharacterSelect::StepSelection(-1);
    if (bSelectOpen && (Key == TEXT("accept") || Key == TEXT("Enter") || Key == TEXT("Gamepad_FaceButton_Bottom"))) return FJapanCharacterSelect::Choose() != nullptr;
    // accept, next and previous (Enter, Tab and Shift+Tab), or any key by name, such as Gamepad_DPad_Down.
    const bool bNamed = Key == TEXT("accept") || Key == TEXT("next") || Key == TEXT("previous");
    const FKey Named = bNamed ? (Key == TEXT("accept") ? EKeys::Enter : EKeys::Tab) : FKey(*Key);
    if (!Named.IsValid()) return false;
    const FModifierKeysState Modifiers(Key == TEXT("previous"),false,false,false,false,false,false,false,false);
    const FKeyEvent Event(Named,Modifiers,uint32(0),false,0,0);
    auto& Slate = FSlateApplication::Get();
    const bool Down = Slate.ProcessKeyDownEvent(Event);
    const bool Up = Slate.ProcessKeyUpEvent(Event);
    return Down || Up;
}

bool UYorimichiLive::PadInput(const FString& Key, float Value)
{
    const FKey Input(*Key);
    if (!Input.IsValid() || !Input.IsGamepadKey() || !FSlateApplication::IsInitialized()) return false;
    auto& Slate = FSlateApplication::Get();
    if (Input.IsAxis1D()) Slate.ProcessAnalogInputEvent(FAnalogInputEvent(Input,Slate.GetModifierKeys(),uint32(0),false,0,0,Value));
    else if (Value > .5f) Slate.ProcessKeyDownEvent(FKeyEvent(Input,Slate.GetModifierKeys(),uint32(0),false,0,0));
    else Slate.ProcessKeyUpEvent(FKeyEvent(Input,Slate.GetModifierKeys(),uint32(0),false,0,0));
    return true;
}

FString UYorimichiLive::MenuFocus()
{
    if (FJapanCharacterSelect::IsOpen()) return FJapanCharacterSelect::FocusedControl();
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player());
    return P && P->GetPreferences() ? P->GetPreferences()->FocusedControl() : FString();
}

bool UYorimichiLive::SetPreference(const FString& Key, float Value)
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player());
    return P && P->GetPreferences() && P->GetPreferences()->SetValue(Key, Value);
}

FString UYorimichiLive::FoliageReviewState()
{
    const auto O=MakeShared<FJsonObject>();const auto Values=MakeShared<FJsonObject>();
    const auto* Player=Cast<AWandererCharacter>(ULiveLibrary::Player());
    if (Player && Player->GetPreferences())
        for (const auto& Value:Player->GetPreferences()->GetValues()) Values->SetNumberField(Value.Key,Value.Value);
    O->SetObjectField(TEXT("preferences"),Values);
    O->SetStringField(TEXT("code"),UTF8_TO_TCHAR(YORIMICHI_NETWORK_BUILD_ID));
    O->SetBoolField(TEXT("fixed_step"),FApp::UseFixedTimeStep());
    O->SetBoolField(TEXT("fixed_frame_rate"),GEngine && GEngine->bUseFixedFrameRate);
    O->SetBoolField(TEXT("film_hud"),IsFilmHud());
    bool Ready=false;bool Enabled=false;
    if (auto* World=ULiveLibrary::GameWorld())
    {
        for (TActorIterator<AJapanWorld> It(World);It;++It) Ready=It->bGameplayReady && It->BootstrapError.IsEmpty();
        if (const auto* System=World->GetSubsystem<UYorimichiFoliageSubsystem>())
        {
            Enabled=System->IsEnabled();Ready&=!System->IsReloading();O->SetBoolField(TEXT("reloading"),System->IsReloading());
            const FIntPoint Counts=System->LoadedModeCounts();
            O->SetNumberField(TEXT("managed_legacy_meshes_resident"),Counts.X);
            O->SetNumberField(TEXT("managed_prepared_meshes_resident"),Counts.Y);
        }
    }
    O->SetBoolField(TEXT("ready"),Ready);O->SetBoolField(TEXT("enabled"),Enabled);
    FString Out;FJsonSerializer::Serialize(O,TJsonWriterFactory<>::Create(&Out));return Out;
}

bool UYorimichiLive::HippodromeVisit()
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player());
    const AHippodrome* V = AHippodrome::Find(P);
    return P && V && P->TravelTo(V->ReturnGround, V->ReturnYaw, TEXT("hippodrome"));
}

FString UYorimichiLive::TrainerState()
{
    const ASwordTrainer* T = ASwordTrainer::Find(ULiveLibrary::Player());
    return T ? T->Describe() : FString(TEXT("{}"));
}

bool UYorimichiLive::TrainerBout(int32 Level, bool bHerShield, bool bPlayerShield)
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player());
    ASwordTrainer* T = ASwordTrainer::Find(P);
    return T && T->StartBout(P, Level, bHerShield, bPlayerShield);
}

bool UYorimichiLive::TrainerMenu()
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player());
    ASwordTrainer* T = ASwordTrainer::Find(P);
    if (!T) return false;
    if (T->IsMenuOpen()) T->CloseMenu(); else T->OpenMenu(P);
    return true;
}

bool UYorimichiLive::TrainerEnd()
{
    ASwordTrainer* T = ASwordTrainer::Find(ULiveLibrary::Player());
    if (!T) return false;
    T->EndBout(TEXT("")); return true;
}

bool UYorimichiLive::TrainerForce(const FString& Attack, const FString& Defence)
{
    ASwordTrainer* T = ASwordTrainer::Find(ULiveLibrary::Player());
    if (!T) return false;
    T->ForceNext(Attack); T->ForceDefence(Defence); return true;
}

bool UYorimichiLive::TrainerPlace(FVector Ground, float Yaw)
{
    ASwordTrainer* T = ASwordTrainer::Find(ULiveLibrary::Player());
    if (!T) return false;
    T->PlaceAt(Ground, Yaw); return true;
}

FString UYorimichiLive::MoveState()
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player());
    return P && P->GetMoves() ? P->GetMoves()->Describe() : FString(TEXT("{}"));
}

bool UYorimichiLive::Launch(FVector Velocity)
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player()); if (!P) return false;
    P->LaunchCharacter(Velocity, true, true); return true;
}

bool UYorimichiLive::ToggleSword()
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player());
    return P && P->GetMoves() && P->Live_Press(FName(TEXT("weapon")));
}

static USkateComponent* PlayerSkate() { AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player()); return P ? P->GetSkate() : nullptr; }
bool UYorimichiLive::SkateToggle() { USkateComponent* S = PlayerSkate(); return S && S->Toggle(); }
bool UYorimichiLive::SkateInput(FVector2D Left, FVector2D Right, bool Push, bool Brake, bool Powerslide, float GrabLeft, float GrabRight)
{
    USkateComponent* S = PlayerSkate(); if (!S) return false;
    FSkateInput In; In.Left = Left; In.Right = Right; In.bPush = Push; In.bBrake = Brake; In.bPowerslide = Powerslide;
    In.TriggerLeft = FMath::Clamp(GrabLeft, 0.f, 1.f); In.TriggerRight = FMath::Clamp(GrabRight, 0.f, 1.f);
    In.bGrabLeft = In.TriggerLeft > 0; In.bGrabRight = In.TriggerRight > 0;
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
FString UYorimichiLive::BikeState()
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player()); const UBikeComponent* B = P ? P->GetBike() : nullptr;
    if (!B) return TEXT("no bike");
    const FVector A = P->GetActorLocation(); const FTransform T = B->GetBikeTransform(); const FRotator R = T.Rotator(); const FVector2D Gaps = B->GetWheelGaps();
    return FString::Printf(TEXT("state=%d clip=%s t=%.3f speed=%.0f sprint=%d steer=%.2f parked=%d air=%d gaps=(%.1f,%.1f) groundpitch=%.1f drift=%.2f wheelie=%.1f airtime=%.2f slope=%.1f hint=%s pos=(%.0f,%.0f,%.0f) yaw=%.1f bike=(%.0f,%.0f,%.0f) bikerot=(%.1f,%.1f,%.1f)"),
        int32(B->GetState()), *B->GetClip().ToString(), B->GetClipTime(), B->GetSpeed(), B->IsSprinting() ? 1 : 0, B->GetSteering(), B->IsParked() ? 1 : 0, P->GetCharacterMovement()->IsMovingOnGround() ? 0 : 1, Gaps.X, Gaps.Y, B->GetGroundPitch(), B->GetDrift(), B->GetWheelie(), B->GetAirTime(), B->GetSlope(), *B->GetStatus().Replace(TEXT(" "), TEXT("_")),
        A.X, A.Y, A.Z, P->GetActorRotation().Yaw, T.GetLocation().X, T.GetLocation().Y, T.GetLocation().Z, R.Pitch, R.Yaw, R.Roll);
}

FString UYorimichiLive::CarState()
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player()); const UDrivingComponent* C = P ? P->GetCar() : nullptr;
    if (!C) return TEXT("no car");
    const FVector A = P->GetActorLocation(); const FTransform T = C->GetCarTransform(); const FRotator R = T.Rotator();
    return FString::Printf(TEXT("driving=%d speed=%.0f kph=%.1f scale=%.4f hint=%s pos=(%.0f,%.0f,%.0f) yaw=%.1f car=(%.0f,%.0f,%.0f) carrot=(%.1f,%.1f,%.1f)"),
        C->IsEquipped() ? 1 : 0, C->GetSpeed(), C->GetSpeedKph(), C->GetKartScale(), *C->GetStatus().Replace(TEXT(" "), TEXT("_")),
        A.X, A.Y, A.Z, P->GetActorRotation().Yaw, T.GetLocation().X, T.GetLocation().Y, T.GetLocation().Z, R.Pitch, R.Yaw, R.Roll);
}

FString UYorimichiLive::CarLoops()
{
    const AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player()); const UDrivingComponent* C = P ? P->GetCar() : nullptr;
    return C ? C->GetAudioState() : FString();
}

FString UYorimichiLive::CarRide()
{
    const AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player()); const UDrivingComponent* C = P ? P->GetCar() : nullptr;
    return C ? C->GetRideState() : FString(TEXT("no car"));
}
static bool GFilmHud = false;
void UYorimichiLive::FilmHud(bool bOn) { GFilmHud = bOn; }
bool UYorimichiLive::IsFilmHud() { return GFilmHud; }
FString UYorimichiLive::SkateLoops() { USkateComponent* S = PlayerSkate(); return S ? S->GetLoopState() : FString(); }
FString UYorimichiLive::BikeLoops()
{
    const AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player()); const UBikeComponent* B = P ? P->GetBike() : nullptr;
    return B ? B->GetLoopState() : FString();
}
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

FString UYorimichiLive::SwitchCharacter(const FString& Name)
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player());
    if (P) if (AWandererCharacter* To = FPlayableCharacter::SwitchPlayer(P, Name)) P = To;
    return P ? FPlayableCharacter::NameOf(P) : FString();
}

FString UYorimichiLive::CharacterSelectState()
{
    return FJapanCharacterSelect::Describe();
}

bool UYorimichiLive::OpenCharacterSelect()
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player());
    return P && FJapanCharacterSelect::Open(P, false);
}

FString UYorimichiLive::SelectCharacter(const FString& Name)
{
    AWandererCharacter* P = FJapanCharacterSelect::Choose(Name);
    return P ? FPlayableCharacter::NameOf(P) : FString();
}

FString UYorimichiLive::HorseState()
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player()); const UHorseComponent* H = P ? P->GetHorse() : nullptr;
    if (!H) return TEXT("no horse");
    const FVector A = P->GetActorLocation(); const FTransform T = H->GetHorseTransform(); const FRotator R = T.Rotator();
    return FString::Printf(TEXT("state=%d role=%s horse_clip=%s serial=%u t=%.3f speed=%.0f sprint=%d steer=%.2f ground=%d groundpitch=%.1f breed=%s tack=%s coat=%s mask=%s hair=%s pattern=%s tint=%s status=%s pos=(%.0f,%.0f,%.0f) yaw=%.1f horse=(%.0f,%.0f,%.0f) horserot=(%.1f,%.1f,%.1f)"),
        int32(H->GetState()), *H->GetRiderClip().ToString(), *H->GetHorseClip().ToString(), H->GetSerial(), H->GetPoseTime(), H->GetSpeed(), H->IsSprinting() ? 1 : 0, H->GetSteering(),
        P->GetCharacterMovement()->IsMovingOnGround() ? 1 : 0, H->GetGroundPitch(), *H->GetBreedId(), *H->GetTackId(), *H->GetCoatId(), *H->GetMaskId(),
        *H->GetHairColorId(), *H->GetHairPatternId(), *H->GetTintId(), *H->GetStatus().Replace(TEXT(" "), TEXT("_")),
        A.X, A.Y, A.Z, P->GetActorRotation().Yaw, T.GetLocation().X, T.GetLocation().Y, T.GetLocation().Z, R.Pitch, R.Yaw, R.Roll);
}
FString UYorimichiLive::HorseConfigure(const FString& Breed, const FString& Tack, const FString& Coat, const FString& Mask, const FString& HairColor, const FString& HairPattern, const FString& Tint)
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player()); UHorseComponent* H = P ? P->GetHorse() : nullptr;
    return H && H->ConfigureHorse(Breed, Tack, Coat, Mask, HairColor, HairPattern, Tint) ? HorseState() : FString();
}

bool UYorimichiLive::TypeKey(const FString& Key, const FString& Characters)
{
    const FKey Input(*Key);
    if (!Input.IsValid() || !FSlateApplication::IsInitialized()) return false;
    auto& Slate = FSlateApplication::Get();
    const FKeyEvent Event(Input,Slate.GetModifierKeys(),uint32(0),false,0,0);
    bool bHandled = Slate.ProcessKeyDownEvent(Event);
    for (const TCHAR Character : Characters) bHandled |= Slate.ProcessKeyCharEvent(FCharacterEvent(Character,Slate.GetModifierKeys(),uint32(0),false));
    return Slate.ProcessKeyUpEvent(Event) || bHandled;
}

bool UYorimichiLive::DevMode(bool bOn)
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player());
    if (P && DevNotes::IsOn() != bOn) DevNotes::Toggle(P->GetWorld(), P->GetPreferences());
    return DevNotes::IsOn();
}

FString UYorimichiLive::DevModeState()
{
    TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
    O->SetBoolField(TEXT("on"), DevNotes::IsOn());
    O->SetNumberField(TEXT("notes"), DevNotes::Count());
    const TSharedPtr<SWidget> Focus = FSlateApplication::IsInitialized() ? FSlateApplication::Get().GetKeyboardFocusedWidget() : nullptr;
    O->SetStringField(TEXT("focus"), Focus.IsValid() ? Focus->GetTypeAsString() : FString());
    FViewport* Viewport = GEngine && GEngine->GameViewport ? GEngine->GameViewport->Viewport : nullptr;
    O->SetBoolField(TEXT("mouse_capture"), Viewport && Viewport->HasMouseCapture());
    APlayerController* PC = ULiveLibrary::Player() ? Cast<APlayerController>(ULiveLibrary::Player()->GetController()) : nullptr;
    O->SetBoolField(TEXT("cursor"), PC && PC->bShowMouseCursor);
    FString Out; const TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Out); FJsonSerializer::Serialize(O, W);
    return Out;
}

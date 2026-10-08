#include "YorimichiLive.h"
#include "LiveLibrary.h"
#include "WandererCharacter.h"
#include "JapanPreferences.h"
#include "WandererSword.h"
#include "SkateComponent.h"
#include "BikeComponent.h"
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

bool UYorimichiLive::MenuKey(const FString& Key)
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player());
    if (!P || !P->GetPreferences() || !P->GetPreferences()->IsMenuOpen() || !FSlateApplication::IsInitialized()) return false;
    if (Key != TEXT("accept") && Key != TEXT("next") && Key != TEXT("previous")) return false;
    const FModifierKeysState Modifiers(Key == TEXT("previous"),false,false,false,false,false,false,false,false);
    const FKeyEvent Event(Key == TEXT("accept") ? EKeys::Enter : EKeys::Tab,Modifiers,uint32(0),false,0,0);
    auto& Slate = FSlateApplication::Get();
    const bool Down = Slate.ProcessKeyDownEvent(Event);
    const bool Up = Slate.ProcessKeyUpEvent(Event);
    return Down || Up;
}

bool UYorimichiLive::SetPreference(const FString& Key, float Value)
{
    AWandererCharacter* P = Cast<AWandererCharacter>(ULiveLibrary::Player());
    return P && P->GetPreferences() && P->GetPreferences()->SetValue(Key, Value);
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
    return FString::Printf(TEXT("state=%d clip=%s t=%.3f speed=%.0f sprint=%d steer=%.2f parked=%d air=%d gaps=(%.1f,%.1f) groundpitch=%.1f hint=%s pos=(%.0f,%.0f,%.0f) yaw=%.1f bike=(%.0f,%.0f,%.0f) bikerot=(%.1f,%.1f,%.1f)"),
        int32(B->GetState()), *B->GetClip().ToString(), B->GetClipTime(), B->GetSpeed(), B->IsSprinting() ? 1 : 0, B->GetSteering(), B->IsParked() ? 1 : 0, P->GetCharacterMovement()->IsMovingOnGround() ? 0 : 1, Gaps.X, Gaps.Y, B->GetGroundPitch(), *B->GetStatus().Replace(TEXT(" "), TEXT("_")),
        A.X, A.Y, A.Z, P->GetActorRotation().Yaw, T.GetLocation().X, T.GetLocation().Y, T.GetLocation().Z, R.Pitch, R.Yaw, R.Roll);
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

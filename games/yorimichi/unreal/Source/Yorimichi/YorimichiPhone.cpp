#include "YorimichiPhone.h"
#include "AtelierStream.h"
#include "WandererCharacter.h"
#include "SailboatComponent.h"
#include "JapanPreferences.h"
#include "JapanMap.h"
#include "ZeppelinService.h"
#include "Dom/JsonObject.h"
#include "HAL/PlatformTime.h"
#include "GameFramework/CharacterMovementComponent.h"

namespace
{
    // The touch page's buttons (phone/client.js).
    enum : uint32 { Jump = 1, Dash = 2, Use = 4, Sailboat = 8, Wave = 16, Walk = 32, Spawn = 64, Sprint = 128, Roll = 256 };

    TSharedRef<FJsonObject> Object() { return MakeShared<FJsonObject>(); }
    TSharedRef<FJsonValue> Pair(double A, double B)
    {
        return MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{MakeShared<FJsonValueNumber>(A), MakeShared<FJsonValueNumber>(B)});
    }
}

FYorimichiPhone::FYorimichiPhone(AWandererCharacter* InRider) : Rider(InRider), Stream(MakeShared<FAtelierStream>())
{
    Stream->OnAction(TEXT("settings"), [this](const FString& Player, const FJsonObject&) { SendSettings(Player); });
    Stream->OnAction(TEXT("map"), [this](const FString& Player, const FJsonObject&) { SendMap(Player); });
    Stream->OnAction(TEXT("setSetting"), [this](const FString& Player, const FJsonObject& J)
    {
        AWandererCharacter* C = Rider.Get(); FString Key; double Number = 0;
        if (C && C->GetPreferences() && J.TryGetStringField(TEXT("key"), Key) && J.TryGetNumberField(TEXT("value"), Number) && FMath::IsFinite(Number))
        {
            C->GetPreferences()->SetValue(Key, Number);
            SendSettings(Player); // Failure returns the authoritative unchanged values and an error.
        }
    });
    Stream->OnAction(TEXT("teleport"), [this](const FString& Player, const FJsonObject& J)
    {
        AWandererCharacter* C = Rider.Get(); FString Zone; bool bOk = false;
        if (!C) return;
        if (J.TryGetStringField(TEXT("zone"), Zone) && Zone.Len() <= 32 && C->GetMap() && !C->IsCinematic()) bOk = C->GetMap()->TeleportToZone(Zone);
        if (bOk) { Stream->ResetControls(); C->ReleaseJump(FInputActionValue(false)); }
        UE_LOG(LogTemp, Display, TEXT("PHONE STREAM teleport %s: %s"), *Zone, bOk ? TEXT("ok") : TEXT("unknown zone"));
        auto Reply = Object(); Reply->SetStringField(TEXT("zone"), Zone); Reply->SetBoolField(TEXT("ok"), bOk);
        Stream->Send(Player, Reply, TEXT("teleport"));
    });
    Stream->OnAction(TEXT("flightSpeed"), [this](const FString&, const FJsonObject& J)
    {
        AWandererCharacter* C = Rider.Get(); double Delta = 0;
        // Aboard it changes the ride's speed; at the docked ship it chooses the next stop.
        if (C && J.TryGetNumberField(TEXT("delta"), Delta) && FMath::IsFinite(Delta) && Delta != 0)
            C->ZeppelinStep(Delta < 0 ? -1 : 1);
    });
}

bool FYorimichiPhone::IsTouchActive() const { return Stream->IsTouchActive(); }

void FYorimichiPhone::SendSettings(const FString& Player)
{
    AWandererCharacter* C = Rider.Get();
    if (!C || !C->GetPreferences()) return;
    TArray<TSharedPtr<FJsonValue>> Rows;
    for (const auto& V : C->GetPreferences()->GetValues())
    {
        auto Row = Object();
        Row->SetStringField(TEXT("key"), V.Key); Row->SetStringField(TEXT("label"), V.Label);
        Row->SetNumberField(TEXT("value"), V.Value); Row->SetNumberField(TEXT("min"), V.Minimum); Row->SetNumberField(TEXT("max"), V.Maximum);
        if (V.Step > 0.f) Row->SetNumberField(TEXT("step"), V.Step);
        if (V.Key == TEXT("renderer"))
        {
            Row->SetBoolField(TEXT("restart_supported"),UJapanPreferences::CanRestartRenderer());
            Row->SetNumberField(TEXT("running"),UJapanPreferences::CurrentRenderer());
        }
        Rows.Add(MakeShared<FJsonValueObject>(Row));
    }
    auto Json = Object(); Json->SetArrayField(TEXT("values"), Rows);
    if (!C->GetPreferences()->GetGraphicsError().IsEmpty()) Json->SetStringField(TEXT("error"),C->GetPreferences()->GetGraphicsError());
    Stream->Send(Player, Json, TEXT("settings"));
}

void FYorimichiPhone::SendMap(const FString& Player)
{
    AWandererCharacter* C = Rider.Get();
    if (!C || !C->GetMap()) return;
    const UJapanMap* M = C->GetMap();
    auto Json = Object();
    Json->SetBoolField(TEXT("loaded"), M->IsLoaded());
    Json->SetStringField(TEXT("image"), TEXT("/map/map.jpg"));
    const FBox2D& B = M->GetBounds();
    TArray<TSharedPtr<FJsonValue>> Bounds; for (double V : {B.Min.X, B.Min.Y, B.Max.X, B.Max.Y}) Bounds.Add(MakeShared<FJsonValueNumber>(V));
    Json->SetArrayField(TEXT("bounds"), Bounds);
    auto Projection = [&](const TCHAR* Key, const TArray<FVector2D>& Knots)
    {
        TArray<TSharedPtr<FJsonValue>> Rows; for (const auto& K : Knots) Rows.Add(Pair(K.X, K.Y));
        Json->SetArrayField(Key, Rows);
    };
    Projection(TEXT("projection_x"), M->GetProjectionX()); Projection(TEXT("projection_y"), M->GetProjectionY());
    TArray<TSharedPtr<FJsonValue>> Zones;
    for (const auto& Z : M->GetZones())
    {
        auto Row = Object();
        Row->SetStringField(TEXT("key"), Z.Key); Row->SetStringField(TEXT("name"), Z.Name); Row->SetStringField(TEXT("hint"), Z.Hint);
        Row->SetNumberField(TEXT("x"), Z.Location.X / 100.0); Row->SetNumberField(TEXT("y"), -Z.Location.Y / 100.0);   // Blender metres, north up
        Zones.Add(MakeShared<FJsonValueObject>(Row));
    }
    Json->SetArrayField(TEXT("zones"), Zones);
    Stream->Send(Player, Json, TEXT("map"));
}

void FYorimichiPhone::Tick(float Dt)
{
    AWandererCharacter* C = Rider.Get(); if (!C) return;
    const FAtelierTouchControls In = Stream->Tick();
    if (In.bLeaseExpired)
    {
        // On a lost connection, stop rather than drift out of view.
        C->GetCharacterMovement()->StopMovementImmediately(); C->Sailboat->EmergencyStop();
        C->MoveIntent = FVector2D::ZeroVector; C->bJog = C->bSprintHeld = false;
        bBrakeAfterLease = C->Sailboat->IsEquipped();
    }
    if (!In.bActive)
    {
        if (In.Released & Jump) C->ReleaseJump(FInputActionValue(false));
        if (bBrakeAfterLease && C->Sailboat->IsEquipped()) C->MoveIntent = FVector2D(0, -1);
        return;   // no touch page: the game's own input (or the plain player's) is in charge
    }
    bBrakeAfterLease = false;
    if (In.bPaused) C->Sailboat->EmergencyStop();
    FVector2D Move = In.Move, Look = In.Look; uint32 Pressed = In.Pressed, Released = In.Released;
    if (Pressed & Spawn)
    {
        Move = Look = FVector2D::ZeroVector; Pressed = Released = 0;
        Stream->ResetControls(Spawn);
        C->ReturnToSpawn();
    }
    C->MoveIntent = C->bMenuOpen ? FVector2D::ZeroVector : Move;
    C->bJog = (In.Buttons & Walk) != 0;
    C->bSprintHeld = (In.Buttons & Sprint) != 0;
    if (C->Controller && !C->bMenuOpen)
    {
        FRotator R = C->Controller->GetControlRotation();
        if (!Look.IsNearlyZero()) C->LookGrace = 2.f;
        R.Yaw += FMath::Clamp(Look.X * C->MouseSensitivity / .4f, -45., 45.);
        R.Pitch = FMath::Clamp(FRotator::NormalizeAxis(R.Pitch) - Look.Y * C->MouseSensitivity / .4f, -65., 45.);
        C->Controller->SetControlRotation(R);
    }
    const FInputActionValue Press(true);
    if (Pressed & Jump) C->RequestJump(Press);
    if (Pressed & Dash) C->Dash(Press);
    if (Pressed & Roll) C->Dodge(Press);
    if (Pressed & Use) C->Interact(Press);
    if (Pressed & Sailboat)
    {
        C->ToggleSailboat(Press);
        auto Hint = Object(); Hint->SetStringField(TEXT("text"), C->Sailboat->GetStatus());
        Stream->Send(Stream->GetPlayer(), Hint, TEXT("hint"));
    }
    if (Pressed & Wave) C->Wave(Press);
    if (Released & Jump) C->ReleaseJump(FInputActionValue(false));   // after the press: a tap within one frame is a short hop
    const double Now = FPlatformTime::Seconds();
    if (Now - LastStatus > .2 && Stream->SecondsSinceInput() < 2.)
    {
        LastStatus = Now;
        const FVector P = C->GetActorLocation();
        const FString RampHint = C->GetZeppelin() ? C->GetZeppelin()->Hint(C) : FString();
        AZeppelinService* Z = C->GetZeppelin();
        auto S = Object();
        S->SetBoolField(TEXT("ready"), C->IsReady());
        S->SetNumberField(TEXT("speed"), C->Sailboat->IsEquipped() ? C->Sailboat->GetSpeed() : C->GetVelocity().Size());
        S->SetBoolField(TEXT("sailboat"), C->Sailboat->IsEquipped());
        S->SetBoolField(TEXT("falling"), C->GetCharacterMovement()->IsFalling());
        S->SetNumberField(TEXT("x"), P.X); S->SetNumberField(TEXT("y"), P.Y); S->SetNumberField(TEXT("z"), P.Z);
        S->SetNumberField(TEXT("yaw"), C->GetActorRotation().Yaw);
        S->SetNumberField(TEXT("viewYaw"), C->GetControlRotation().Yaw);
        S->SetNumberField(TEXT("viewPitch"), FRotator::NormalizeAxis(C->GetControlRotation().Pitch));
        S->SetBoolField(TEXT("inputActive"), In.bActive);
        S->SetNumberField(TEXT("fps"), 1.f / FMath::Max(Dt, .001f));
        S->SetBoolField(TEXT("showFps"), C->GetPreferences()->ShowFrameRate());
        S->SetStringField(TEXT("rampHint"), RampHint);
        S->SetNumberField(TEXT("zeppelinStage"), Z ? Z->GetStage() : -1);
        S->SetNumberField(TEXT("flightSpeed"), Z ? Z->GetFlightSpeed() : 1.f);
        S->SetNumberField(TEXT("propellerAngle"), Z ? Z->GetPropellerAngle() : 0.f);
        S->SetNumberField(TEXT("zeppelinDock"), Z ? Z->GetDock() : -1);
        S->SetBoolField(TEXT("zeppelinChoose"), Z && Z->CanChooseStop(C));
        S->SetNumberField(TEXT("stamina"), C->Stamina.Units);
        S->SetNumberField(TEXT("staminaRings"), C->Stamina.Capacity);
        S->SetBoolField(TEXT("sprinting"), C->Stamina.Sprinting);
        S->SetBoolField(TEXT("exhausted"), C->Stamina.Exhausted);
        Stream->Send(Stream->GetPlayer(), S);
    }
}

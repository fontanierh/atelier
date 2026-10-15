#include "DevNotes.h"
#include "JapanPreferences.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "Framework/Application/IInputProcessor.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformApplicationMisc.h"
#include "HAL/PlatformProcess.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "UnrealClient.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

namespace
{
constexpr float Slow = 1200.f, Fast = 6000.f;        // cm/s
constexpr float MouseDegrees = .12f, StickDegrees = 120.f;
constexpr float LookReach = 100000.f;                 // cm: the farthest point a note records as looked at

struct FNote
{
    int32 Index = 0;
    FString Time, Text, Shot, Map, Target;
    FVector Eye = FVector::ZeroVector, Look = FVector::ZeroVector, Player = FVector::ZeroVector;
    FRotator Rotation = FRotator::ZeroRotator;
    float Fov = 90.f, Distance = -1.f;
};

class FDevInput;
struct FState
{
    TWeakObjectPtr<UWorld> World;
    TWeakObjectPtr<ACameraActor> Camera;
    TWeakObjectPtr<UJapanPreferences> Menu;
    TSharedPtr<FDevInput> Input;
    TSharedPtr<SWidget> Hud, Editor;
    TSharedPtr<SEditableTextBox> Box;
    FString Folder, Status;
    TArray<FNote> Notes;
    FNote Pending;
    float Yaw = 0.f, Pitch = 0.f;
    FVector2D LeftStick = FVector2D::ZeroVector, RightStick = FVector2D::ZeroVector, Mouse = FVector2D::ZeroVector;
    float LeftTrigger = 0.f, RightTrigger = 0.f;
    TSet<FKey> Held;
    bool bOn = false;
};
FState& S() { static FState State; return State; }

APlayerController* Controller()
{
    UWorld* World = S().World.Get();
    return World ? UGameplayStatics::GetPlayerController(World, 0) : nullptr;
}

// The settings menu or the note box has the input: the free camera holds still and passes every event on.
bool Passive()
{
    const FState& St = S();
    return St.Editor.IsValid() || (St.Menu.IsValid() && St.Menu->IsMenuOpen());
}

float Held(const FKey& Key) { return S().Held.Contains(Key) ? 1.f : 0.f; }

FString Vec(const FVector& V) { return FString::Printf(TEXT("[%.1f, %.1f, %.1f]"), V.X, V.Y, V.Z); }

FString Quote(const FString& Text)
{
    FString Out = Text.Replace(TEXT("\\"), TEXT("\\\\")).Replace(TEXT("\""), TEXT("\\\"")).Replace(TEXT("\n"), TEXT("\\n"));
    return TEXT("\"") + Out + TEXT("\"");
}

FString Markdown()
{
    FString Out = TEXT("# Yorimichi dev notes\n\nPositions are Unreal world centimetres (x, y, z); rotation is pitch, yaw, roll in degrees.\n");
    for (const FNote& N : S().Notes)
    {
        Out += FString::Printf(TEXT("\n## Note %d · %s\n\n%s\n\n- screenshot: `%s`\n- camera: %s, pitch %.1f, yaw %.1f, fov %.0f\n"),
            N.Index, *N.Time, *N.Text, *N.Shot, *Vec(N.Eye), N.Rotation.Pitch, N.Rotation.Yaw, N.Fov);
        if (N.Distance >= 0.f)
            Out += FString::Printf(TEXT("- looking at: %s, %.1f m away (%s)\n"), *Vec(N.Look), N.Distance / 100.f, *N.Target);
        else
            Out += TEXT("- looking at: sky (nothing within 1 km)\n");
        Out += FString::Printf(TEXT("- player: %s · map %s\n"), *Vec(N.Player), *N.Map);
    }
    return Out;
}

FString Json()
{
    TArray<FString> Items;
    for (const FNote& N : S().Notes)
        Items.Add(FString::Printf(TEXT("  {\"index\": %d, \"time\": %s, \"text\": %s, \"screenshot\": %s, \"map\": %s,\n")
            TEXT("   \"camera\": {\"location_cm\": %s, \"pitch\": %.2f, \"yaw\": %.2f, \"roll\": %.2f, \"fov\": %.1f, \"forward\": %s},\n")
            TEXT("   \"look_at\": %s, \"look_distance_m\": %.2f, \"look_target\": %s, \"player_cm\": %s}"),
            N.Index, *Quote(N.Time), *Quote(N.Text), *Quote(N.Shot), *Quote(N.Map), *Vec(N.Eye), N.Rotation.Pitch, N.Rotation.Yaw,
            N.Rotation.Roll, N.Fov, *FString::Printf(TEXT("[%.4f, %.4f, %.4f]"), N.Rotation.Vector().X, N.Rotation.Vector().Y, N.Rotation.Vector().Z),
            N.Distance >= 0.f ? *Vec(N.Look) : TEXT("null"), N.Distance / 100.f, *Quote(N.Target), *Vec(N.Player)));
    return TEXT("{\"units\": \"unreal cm\", \"notes\": [\n") + FString::Join(Items, TEXT(",\n")) + TEXT("\n]}\n");
}

void WriteNotes()
{
    const FState& St = S();
    FFileHelper::SaveStringToFile(Markdown(), *FPaths::Combine(St.Folder, TEXT("notes.md")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
    FFileHelper::SaveStringToFile(Json(), *FPaths::Combine(St.Folder, TEXT("notes.json")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
}

void CloseEditor()
{
    FState& St = S();
    if (St.Editor && GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(St.Editor.ToSharedRef());
    St.Editor.Reset(); St.Box.Reset();
    St.Held.Reset();
    if (GEngine && GEngine->GameViewport) FSlateApplication::Get().SetAllUserFocusToGameViewport();
}

void Save(const FText& Text, ETextCommit::Type How)
{
    FState& St = S();
    if (!St.Editor) return;
    if (How == ETextCommit::OnEnter)
    {
        St.Pending.Text = Text.ToString().TrimStartAndEnd();
        if (St.Pending.Text.IsEmpty()) St.Pending.Text = TEXT("(no text)");
        St.Notes.Add(St.Pending);
        WriteNotes();
        St.Status = FString::Printf(TEXT("Saved note %d."), St.Pending.Index);
        CloseEditor();
    }
    else if (How == ETextCommit::OnCleared)
    {
        IFileManager::Get().Delete(*FPaths::Combine(St.Folder, St.Pending.Shot), false, true, true);
        St.Status = TEXT("Note cancelled.");
        CloseEditor();
    }
}

void BeginNote()
{
    FState& St = S();
    ACameraActor* Camera = St.Camera.Get();
    UWorld* World = St.World.Get();
    if (!Camera || !World || !GEngine || !GEngine->GameViewport || St.Editor) return;
    FNote& N = St.Pending;
    N = FNote();
    N.Index = St.Notes.Num() + 1;
    N.Time = FDateTime::Now().ToString(TEXT("%Y-%m-%d %H:%M:%S"));
    N.Shot = FString::Printf(TEXT("note-%03d.png"), N.Index);
    N.Map = World->GetMapName();
    N.Eye = Camera->GetActorLocation();
    N.Rotation = Camera->GetActorRotation();
    N.Fov = Camera->GetCameraComponent()->FieldOfView;
    if (APlayerController* PC = Controller())
        if (APawn* Pawn = PC->GetPawn()) N.Player = Pawn->GetActorLocation();
    FCollisionQueryParams Params(TEXT("DevNote"), true);
    if (APlayerController* PC = Controller()) if (PC->GetPawn()) Params.AddIgnoredActor(PC->GetPawn());
    FHitResult Hit;
    if (World->LineTraceSingleByChannel(Hit, N.Eye, N.Eye + N.Rotation.Vector() * LookReach, ECC_Visibility, Params))
    {
        N.Look = Hit.ImpactPoint;
        N.Distance = Hit.Distance;
        N.Target = Hit.GetActor() ? Hit.GetActor()->GetName() : FString();
        if (Hit.GetComponent()) N.Target += TEXT(" / ") + Hit.GetComponent()->GetName();
    }
    // The scene alone (no menus or note box), drawn at the end of this frame.
    FScreenshotRequest::RequestScreenshot(FPaths::Combine(St.Folder, N.Shot), false, false);
    TSharedRef<SEditableTextBox> Box = SNew(SEditableTextBox)
        .HintText(FText::FromString(TEXT("What is wrong or right here? Enter saves, Escape cancels.")))
        .RevertTextOnEscape(true).ClearKeyboardFocusOnCommit(false).SelectAllTextWhenFocused(true)
        .Font(FCoreStyle::GetDefaultFontStyle("Regular", 18))
        .OnTextCommitted_Static(&Save);
    St.Box = Box;
    St.Editor = SNew(SBox).HAlign(HAlign_Center).VAlign(VAlign_Bottom).Padding(FMargin(0, 0, 0, 120))
    [
        SNew(SBox).WidthOverride(900.f)
        [
            SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.f, 0.f, 0.f, .78f)).Padding(16)
            [
                SNew(SVerticalBox)
                + SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 8)
                [
                    SNew(STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Bold", 16)).ColorAndOpacity(FLinearColor::White)
                        .Text(FText::FromString(FString::Printf(TEXT("Note %d · type with the keyboard · Enter saves · Escape cancels"), N.Index)))
                ]
                + SVerticalBox::Slot().AutoHeight()[Box]
            ]
        ]
    ];
    St.Held.Reset();
    GEngine->GameViewport->AddViewportWidgetContent(St.Editor.ToSharedRef(), 60);
    FSlateApplication::Get().SetAllUserFocus(Box, EFocusCause::SetDirectly);
}

class FDevInput : public IInputProcessor
{
public:
    void Tick(const float Delta, FSlateApplication&, TSharedRef<ICursor>) override
    {
        FState& St = S();
        ACameraActor* Camera = St.Camera.Get();
        APlayerController* PC = Controller();
        if (!Camera || !PC) return;
        if (PC->GetViewTarget() != Camera) PC->SetViewTarget(Camera);
        if (St.Editor && St.Box && !St.Box->HasKeyboardFocus()) FSlateApplication::Get().SetAllUserFocus(St.Box, EFocusCause::SetDirectly);
        if (Passive()) { St.Mouse = FVector2D::ZeroVector; return; }
        const float Dt = FMath::Min(Delta, .1f);
        auto Dead = [](float V) { return FMath::Abs(V) < .15f ? 0.f : V; };
        St.Yaw += St.Mouse.X * MouseDegrees + Dead(St.RightStick.X) * StickDegrees * Dt;
        St.Pitch = FMath::Clamp(St.Pitch - St.Mouse.Y * MouseDegrees + Dead(St.RightStick.Y) * StickDegrees * .75f * Dt, -89.f, 89.f);
        St.Mouse = FVector2D::ZeroVector;
        const FRotator Rotation(St.Pitch, St.Yaw, 0.f);
        const FRotationMatrix Axes(Rotation);
        const float Forward = Held(EKeys::W) - Held(EKeys::S) + Dead(St.LeftStick.Y);
        const float Side = Held(EKeys::D) - Held(EKeys::A) + Dead(St.LeftStick.X);
        const float Up = Held(EKeys::E) + Held(EKeys::SpaceBar) - Held(EKeys::Q) - Held(EKeys::C) + St.RightTrigger - St.LeftTrigger;
        FVector Move = Axes.GetUnitAxis(EAxis::X) * Forward + Axes.GetUnitAxis(EAxis::Y) * Side + FVector::UpVector * Up;
        Move = Move.GetClampedToMaxSize(1.f);
        const bool bFast = St.Held.Contains(EKeys::LeftShift) || St.Held.Contains(EKeys::Gamepad_LeftShoulder);
        Camera->SetActorLocationAndRotation(Camera->GetActorLocation() + Move * (bFast ? Fast : Slow) * Dt, Rotation);
    }

    bool HandleKeyDownEvent(FSlateApplication&, const FKeyEvent& Event) override
    {
        if (Passive()) return false;
        const FKey Key = Event.GetKey();
        if (Key == EKeys::N || Key == EKeys::Gamepad_FaceButton_Top) { if (!Event.IsRepeat()) BeginNote(); return true; }
        if (Key == EKeys::X || Key == EKeys::Gamepad_Special_Left) { if (!Event.IsRepeat()) DevNotes::Export(); return true; }
        if (!Moves(Key)) return false;
        S().Held.Add(Key);
        return true;
    }

    bool HandleKeyUpEvent(FSlateApplication&, const FKeyEvent& Event) override
    {
        S().Held.Remove(Event.GetKey());
        return !Passive() && (Moves(Event.GetKey()) || Event.GetKey() == EKeys::N || Event.GetKey() == EKeys::X
            || Event.GetKey() == EKeys::Gamepad_FaceButton_Top || Event.GetKey() == EKeys::Gamepad_Special_Left);
    }

    bool HandleAnalogInputEvent(FSlateApplication&, const FAnalogInputEvent& Event) override
    {
        FState& St = S();
        const FKey Key = Event.GetKey();
        const float V = Event.GetAnalogValue();
        if (Key == EKeys::Gamepad_LeftX) St.LeftStick.X = V;
        else if (Key == EKeys::Gamepad_LeftY) St.LeftStick.Y = V;
        else if (Key == EKeys::Gamepad_RightX) St.RightStick.X = V;
        else if (Key == EKeys::Gamepad_RightY) St.RightStick.Y = V;
        else if (Key == EKeys::Gamepad_LeftTriggerAxis) St.LeftTrigger = V;
        else if (Key == EKeys::Gamepad_RightTriggerAxis) St.RightTrigger = V;
        else return false;
        return !Passive();
    }

    bool HandleMouseMoveEvent(FSlateApplication&, const FPointerEvent& Event) override
    {
        if (Passive()) return false;
        S().Mouse += Event.GetCursorDelta();
        return true;
    }

    const TCHAR* GetDebugName() const override { return TEXT("DevNotes"); }

private:
    static bool Moves(const FKey& Key)
    {
        static const TSet<FKey> Keys = {EKeys::W, EKeys::A, EKeys::S, EKeys::D, EKeys::Q, EKeys::E, EKeys::C, EKeys::SpaceBar,
            EKeys::LeftShift, EKeys::Gamepad_LeftShoulder, EKeys::Gamepad_LeftStick_Up, EKeys::Gamepad_LeftStick_Down,
            EKeys::Gamepad_LeftStick_Left, EKeys::Gamepad_LeftStick_Right, EKeys::Gamepad_RightStick_Up, EKeys::Gamepad_RightStick_Down,
            EKeys::Gamepad_RightStick_Left, EKeys::Gamepad_RightStick_Right, EKeys::Gamepad_LeftTrigger, EKeys::Gamepad_RightTrigger};
        return Keys.Contains(Key);
    }
};

FText HudText()
{
    const FState& St = S();
    return FText::FromString(FString::Printf(
        TEXT("DEV MODE · fly: WASD / left stick · look: mouse / right stick · up E Space / RT · down Q C / LT · fast Shift / LB\n")
        TEXT("N or Y: note with screenshot · X or View: export zip (Finder opens it) · notes: %d%s%s"),
        St.Notes.Num(), St.Status.IsEmpty() ? TEXT("") : TEXT("\n"), *St.Status));
}
}

bool DevNotes::IsOn() { return S().bOn; }
int32 DevNotes::Count() { return S().Notes.Num(); }

void DevNotes::Toggle(UWorld* World, UJapanPreferences* Menu)
{
    FState& St = S();
    if (St.bOn)
    {
        CloseEditor();
        if (St.Input) FSlateApplication::Get().UnregisterInputPreProcessor(St.Input);
        St.Input.Reset();
        if (St.Hud && GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(St.Hud.ToSharedRef());
        St.Hud.Reset();
        if (APlayerController* PC = Controller()) if (PC->GetPawn()) PC->SetViewTarget(PC->GetPawn());
        if (ACameraActor* Camera = St.Camera.Get()) Camera->Destroy();
        St.Camera.Reset();
        St.bOn = false;
        return;
    }
    if (!World || !GEngine || !GEngine->GameViewport) return;
    St.World = World;
    St.Menu = Menu;
    APlayerController* PC = Controller();
    if (!PC) return;
    if (St.Folder.IsEmpty() || St.Notes.IsEmpty())
        St.Folder = FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("DevNotes"),
            TEXT("yorimichi-notes-") + FDateTime::Now().ToString(TEXT("%Y%m%d-%H%M%S"))));
    IFileManager::Get().MakeDirectory(*St.Folder, true);
    FVector Eye = PC->PlayerCameraManager ? PC->PlayerCameraManager->GetCameraLocation() : FVector::ZeroVector;
    FRotator Rotation = PC->PlayerCameraManager ? PC->PlayerCameraManager->GetCameraRotation() : FRotator::ZeroRotator;
    ACameraActor* Camera = World->SpawnActor<ACameraActor>(Eye, FRotator(Rotation.Pitch, Rotation.Yaw, 0.f));
    if (!Camera) return;
    Camera->GetCameraComponent()->SetFieldOfView(PC->PlayerCameraManager ? PC->PlayerCameraManager->GetFOVAngle() : 90.f);
    Camera->GetCameraComponent()->bConstrainAspectRatio = false;
    St.Camera = Camera;
    St.Pitch = Rotation.Pitch; St.Yaw = Rotation.Yaw;
    St.Held.Reset(); St.LeftStick = St.RightStick = St.Mouse = FVector2D::ZeroVector; St.LeftTrigger = St.RightTrigger = 0.f;
    PC->SetViewTarget(Camera);
    St.Input = MakeShared<FDevInput>();
    FSlateApplication::Get().RegisterInputPreProcessor(St.Input, 0);
    St.Hud = SNew(SBox).HAlign(HAlign_Left).VAlign(VAlign_Top).Padding(FMargin(16, 12))
    [
        SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0.f, 0.f, 0.f, .55f)).Padding(10)
        [
            SNew(STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Regular", 13)).ColorAndOpacity(FLinearColor::White).Text_Static(&HudText)
        ]
    ];
    GEngine->GameViewport->AddViewportWidgetContent(St.Hud.ToSharedRef(), 50);
    St.Status = FString::Printf(TEXT("Notes folder: %s"), *St.Folder);
    St.bOn = true;
}

FString DevNotes::Export()
{
    FState& St = S();
    if (St.Notes.IsEmpty()) { St.Status = TEXT("No notes to export yet: press N or Y first."); return FString(); }
    WriteNotes();
    FPlatformApplicationMisc::ClipboardCopy(*Markdown());
    FString Zip;
#if PLATFORM_MAC
    // The packaged app is sandboxed: the zip goes beside the notes folder in its container, and Finder shows it.
    Zip = FPaths::Combine(FPaths::GetPath(St.Folder), FPaths::GetCleanFilename(St.Folder) + FDateTime::Now().ToString(TEXT("-export-%H%M%S")) + TEXT(".zip"));
    int32 Code = -1;
    FString Out, Error;
    FPlatformProcess::ExecProcess(TEXT("/usr/bin/ditto"), *FString::Printf(TEXT("-c -k --keepParent \"%s\" \"%s\""), *St.Folder, *Zip), &Code, &Out, &Error);
    if (Code != 0 || !IFileManager::Get().FileExists(*Zip))
    {
        St.Status = FString::Printf(TEXT("Zip failed (%d): the notes are in %s, and copied to the clipboard."), Code, *St.Folder);
        return FString();
    }
    FPlatformProcess::ExploreFolder(*Zip);
#else
    Zip = St.Folder;
#endif
    St.Status = FString::Printf(TEXT("Exported %d notes: %s (notes also copied to the clipboard)"), St.Notes.Num(), *Zip);
    UE_LOG(LogTemp, Display, TEXT("DEV NOTES exported %d to %s"), St.Notes.Num(), *Zip);
    return Zip;
}

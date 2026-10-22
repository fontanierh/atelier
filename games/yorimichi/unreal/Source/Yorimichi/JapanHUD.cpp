#include "JapanHUD.h"
#include "JapanNetwork.h"
#include "JapanSession.h"
#include "AdventureMoveSet.h"
#include "ZeppelinService.h"
#include "WandererCharacter.h"
#include "JapanPreferences.h"
#include "JapanCharacterSelect.h"
#include "SkateComponent.h"
#include "SailboatComponent.h"
#include "BikeComponent.h"
#include "DrivingComponent.h"
#include "HorseComponent.h"
#include "WandererSword.h"
#include "FoxHunter.h"
#include "SwordTrainer.h"
#include "LiveLibrary.h"
#include "BelmonteTrainService.h"
#include "RacingService.h"
#include "YorimichiLive.h"
#include "EngineUtils.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Framework/Application/SlateApplication.h"
#include "GenericPlatform/GenericPlatformInputDeviceMapper.h"
#include "GenericPlatform/InputDeviceRegistry.h"
#include "HAL/IConsoleManager.h"

// Automatic by default; the explicit styles allow visual QA without hardware.
static TAutoConsoleVariable<int32> CVarControllerHUD(TEXT("japan.ControllerHUD"),-1,
    TEXT("HUD labels: -1 connected device, 0 keyboard, 1 Xbox, 2 PlayStation, 3 Nintendo, 4 generic."));

static int32 ConnectedControllerStyle()
{
    if (!FSlateApplication::IsInitialized() || !FSlateApplication::Get().IsGamepadAttached()) return 0;
    TArray<FInputDeviceId> Devices;
    IPlatformInputDeviceMapper::Get().GetAllConnectedInputDevices(Devices);
    for (const FInputDeviceId Device : Devices)
        if (const auto Descriptor=FInputDeviceRegistry::FindDescriptor(Device); Descriptor.IsSet())
        {
            const FString Name=Descriptor->InputDeviceName.ToString();
            if (Name.Contains(TEXT("PS4")) || Name.Contains(TEXT("PS5")) || Name.Contains(TEXT("DualShock")) || Name.Contains(TEXT("DualSense"))) return 2;
            if (Name.Contains(TEXT("Xbox")) || Name.Contains(TEXT("XInput"))) return 1;
            if (Name.Contains(TEXT("Nintendo")) || Name.Contains(TEXT("Switch"))) return 3;
        }
    // Unknown pads get physical button positions, never guessed A/B lettering.
    return 4;
}

struct FControllerLabels
{
    const TCHAR *Jump, *Roll, *Dash, *Skate, *Map, *Menu, *Sprint, *Crouch, *Attack, *Parry, *Weapon, *RightBumper, *LeftBumper;
};

static FControllerLabels ControllerLabels(int32 Style)
{
    switch (Style)
    {
        case 1: return {TEXT("A"),TEXT("B"),TEXT("X"),TEXT("Y"),TEXT("View"),TEXT("Menu"),TEXT("LS click"),TEXT("RS click"),TEXT("RT"),TEXT("LT"),TEXT("D-pad Left"),TEXT("RB"),TEXT("LB")};
        case 2: return {TEXT("Cross"),TEXT("Circle"),TEXT("Square"),TEXT("Triangle"),TEXT("Touchpad"),TEXT("Options"),TEXT("L3"),TEXT("R3"),TEXT("R2"),TEXT("L2"),TEXT("D-pad Left"),TEXT("R1"),TEXT("L1")};
        case 3: return {TEXT("B"),TEXT("A"),TEXT("Y"),TEXT("X"),TEXT("Minus"),TEXT("Plus"),TEXT("LS click"),TEXT("RS click"),TEXT("ZR"),TEXT("ZL"),TEXT("D-pad Left"),TEXT("R"),TEXT("L")};
        default: return {TEXT("Bottom button"),TEXT("Right button"),TEXT("Left button"),TEXT("Top button"),TEXT("View / Select"),TEXT("Menu / Start"),TEXT("LS click"),TEXT("RS click"),TEXT("Right trigger"),TEXT("Left trigger"),TEXT("D-pad Left"),TEXT("Right bumper"),TEXT("Left bumper")};
    }
}

int32 AJapanHUD::CurrentControllerStyle()
{
    const int32 Override=CVarControllerHUD.GetValueOnGameThread();
    return Override<0?ConnectedControllerStyle():FMath::Clamp(Override,0,4);
}

void AJapanHUD::DrawHUD()
{
    Super::DrawHUD();
    const AWandererCharacter* Pawn = Cast<AWandererCharacter>(GetOwningPawn());
    if (!Canvas || !GEngine) return;
    UFont* Font = GEngine->GetSmallFont();
    if (!Pawn)
    {
        if (JapanNetwork::IsOnline(GetWorld()))
        {
            DrawRect(FLinearColor(.04f,.06f,.06f,1),0,0,Canvas->SizeX,Canvas->SizeY);
            DrawText(TEXT("YORIMICHI   /   loading the shared world"),FLinearColor(.93f,.87f,.72f),Canvas->SizeX*.3f,Canvas->SizeY*.45f,Font,1.4f);
            DrawText(TEXT("Checking matching content and collision. F10 opens session controls."),FLinearColor::White,Canvas->SizeX*.3f,Canvas->SizeY*.5f,Font,1.f);
        }
        return;
    }
    if (!Pawn->IsReady())
    {
        DrawRect(FLinearColor(.04f,.06f,.06f,1),0,0,Canvas->SizeX,Canvas->SizeY);
        DrawText(TEXT("YORIMICHI   /   preparing the countryside"),FLinearColor(.93f,.87f,.72f),Canvas->SizeX*.34f,Canvas->SizeY*.5f,Font,1.4f);
        return;
    }
    if (FJapanCharacterSelect::IsOpen()) return;
    if (Pawn->IsCinematic() || Pawn->IsPhoneTouchActive()) return;
    // A line from the live bridge (ULiveLibrary::Say), centred at the top.
    {
        FString Line; float Alpha = 0.f;
        if (ULiveLibrary::CurrentMessage(Line, Alpha))
        {
            float W = 0.f, H = 0.f; Canvas->StrLen(Font, Line, W, H); const float S = 1.3f;
            const float X = Canvas->SizeX * .5f - W * S * .5f, Y = Canvas->SizeY * .12f;
            DrawRect(FLinearColor(0, 0, 0, .45f * Alpha), X - 14, Y - 8, W * S + 28, H * S + 16);
            DrawText(Line, FLinearColor(1.f, .93f, .78f, Alpha), X, Y, Font, S);
        }
    }
    // The skate trick line (docs/SKATE.md).
    auto DrawSkateLine = [&]()
    {
        const USkateComponent* Ride = Pawn->GetSkate();
        if (!Ride || !Ride->IsRiding()) return;
        const FString Line = Ride->GetComboLine();
        const float Alpha = Ride->GetComboAlpha();
        const float Scale = Canvas->SizeY / 1080.f;
        if (!Line.IsEmpty() && Alpha > .02f)
        {
            float W = 0.f, H = 0.f; Canvas->StrLen(Font, Line, W, H); const float S = 2.1f * Scale;
            const float X = Canvas->SizeX * .5f - W * S * .5f, Y = Canvas->SizeY * .84f;
            DrawText(Line, FLinearColor(0, 0, 0, .55f * Alpha), X + 2, Y + 2, Font, S);
            DrawText(Line, FLinearColor(1.f, .93f, .72f, Alpha), X, Y, Font, S);
        }
        if (Ride->GetScore() > 0) DrawText(FString::Printf(TEXT("%d"), Ride->GetScore()), FLinearColor(1.f, .93f, .72f), Canvas->SizeX - 140 * Scale, 54 * Scale, Font, 1.3f * Scale);
    };
    // The sword trainer (ASwordTrainer): the prompt to ask her, and in a bout her bar and her words at the top (kept in
    // filmed frames).
    auto DrawTrainer = [&](bool bController, bool bSailboat)
    {
    if (const ASwordTrainer* Trainer = ASwordTrainer::Find(Pawn); Trainer && !bSailboat && !Pawn->IsZeppelinPassenger())
    {
        const float Scale = Canvas->SizeY / 1080.f;
        if (Trainer->CanTalk(Pawn) && !Trainer->IsMenuOpen())
        {
            const FString Ask = FString::Printf(TEXT("%s   Talk to Kaede (sword training)"), bController ? TEXT("D-pad Down") : TEXT("E"));
            float W = 0.f, H = 0.f; Canvas->StrLen(Font, Ask, W, H); const float S = 1.3f * FMath::Max(Scale, .75f);
            const float X = Canvas->SizeX * .5f - W * S * .5f, Y = Canvas->SizeY * .7f;
            DrawRect(FLinearColor(0, 0, 0, .45f), X - 14, Y - 8, W * S + 28, H * S + 16);
            DrawText(Ask, FLinearColor(1.f, .9f, .74f), X, Y, Font, S);
        }
        const ASwordTrainer::EBout Bout = Trainer->GetBout();
        if (Bout == ASwordTrainer::EBout::Ready || Bout == ASwordTrainer::EBout::Fighting || Bout == ASwordTrainer::EBout::Over)
        {
            const float W = 420 * Scale, X = Canvas->SizeX * .5f - W * .5f, Y = 64 * Scale;
            DrawText(FString::Printf(TEXT("%s  ·  %s%s"), *Trainer->GetDisplayName(), Trainer->GetStyle().Name, Trainer->HasOwnShield() ? TEXT("  ·  sword and shield") : TEXT("")),
                FLinearColor(.97f, .9f, .76f), X, Y - 28 * Scale, Font, 1.4f * Scale);
            DrawRect(FLinearColor(0, 0, 0, .45f), X - 3 * Scale, Y - 3 * Scale, W + 6 * Scale, 16 * Scale);
            DrawRect(FLinearColor(.95f, .45f, .22f), X, Y, W * Trainer->GetHealthFraction(), 10 * Scale);
            if (const auto* Moves = Trainer->GetMoves(); Moves && Moves->GuardPressure() > .01f)
                DrawRect(FLinearColor(.95f, .75f, .35f), X, Y + 12 * Scale, W * Moves->GuardPressure(), 3 * Scale);
            if (!Trainer->IsHostileRonin())
                DrawText(FString::Printf(TEXT("bouts  you %d  ·  Kaede %d"), Trainer->GetLosses(), Trainer->GetWins()), FLinearColor(.85f, .82f, .74f), X, Y + 16 * Scale, Font, 1.f * Scale);
        }
        float Alpha = 0.f;
        const FString Said = Trainer->GetCallout(Alpha);
        if (!Said.IsEmpty())
        {
            float W = 0.f, H = 0.f; Canvas->StrLen(Font, Said, W, H); const float S = 1.6f * FMath::Max(Scale, .75f);
            const float X = Canvas->SizeX * .5f - W * S * .5f, Y = Canvas->SizeY * .22f;
            DrawText(Said, FLinearColor(0, 0, 0, .6f * Alpha), X + 2, Y + 2, Font, S);
            DrawText(Said, FLinearColor(1.f, .94f, .8f, Alpha), X, Y, Font, S);
        }
    }
    };
    // Filming the skating (UYorimichiLive::FilmHud): only the trick line, and the sword trainer's bar and words.
    if (UYorimichiLive::IsFilmHud()) { DrawSkateLine(); DrawTrainer(false, false); return; }
    // Being hit washes the screen red for a moment (AYorimichiCombatFX::PlayerHurt).
    if (Pawn->GetDamageFlash()>0.f) DrawRect(FLinearColor(.75f,.08f,.04f,.13f*Pawn->GetDamageFlash()),0,0,Canvas->SizeX,Canvas->SizeY);
    const double Now = FPlatformTime::Seconds();
    if (Now >= NextControllerCheck)
    {
        const int32 Style=CurrentControllerStyle();
        if (Style!=ControllerStyle)
            UE_LOG(LogTemp,Display,TEXT("CONTROLS HUD style=%d automatic=%d"),Style,CVarControllerHUD.GetValueOnGameThread()<0);
        ControllerStyle=Style;
        NextControllerCheck=Now+.25;
    }
    const bool bController=ControllerStyle!=0;
    const FControllerLabels Pad=ControllerLabels(ControllerStyle);
    if (LastFrameTime > 0.)
    {
        FrameWindowTime += Now-LastFrameTime;
        ++FrameWindowCount;
        if (FrameWindowTime >= .5)
        {
            DisplayedFrameRate = FrameWindowCount/FrameWindowTime;
            FrameWindowTime = 0.; FrameWindowCount = 0;
        }
    }
    LastFrameTime = Now;
    if (Pawn->GetPreferences() && Pawn->GetPreferences()->ShowFrameRate() && DisplayedFrameRate > 0.f)
        DrawText(FString::Printf(TEXT("%.0f fps"),DisplayedFrameRate),FLinearColor(.94f,.92f,.84f),Canvas->SizeX-85,20,Font,1.f);
    const bool bSailboat = Pawn->GetSailboat() && Pawn->GetSailboat()->IsEquipped();
    FString Controls = bSailboat ? FString::Printf(TEXT("K step ashore   A / D steer   W raise sail   S lower sail      %s   %.0f km/h"),*Pawn->GetSailboat()->GetStatus(),Pawn->GetSailboat()->GetSpeed()*.036f) : TEXT("WASD run   Alt / J walk   Shift sprint   Space jump / double jump   F dash   C crouch   Ctrl roll   K sailboat   M map");
    if (bController)
        Controls = bSailboat ? FString::Printf(TEXT("D-pad Up step ashore   Left stick steer / raise or lower sail      %s   %.0f km/h"),*Pawn->GetSailboat()->GetStatus(),Pawn->GetSailboat()->GetSpeed()*.036f)
            : FString::Printf(TEXT("Left stick move   Hold %s sprint   %s jump / double jump   %s dash   %s roll"),Pad.Sprint,Pad.Jump,Pad.Dash,Pad.Roll);
    FString Secondary = bController ? FString::Printf(TEXT("Right stick look   %s crouch   %s interact   %s map (hold: places)   %s settings   D-pad Up sailboat"),Pad.Crouch,TEXT("D-pad Down"),Pad.Map,Pad.Menu)
        : TEXT("Mouse look   M map & travel   Esc settings   Tab release mouse   F12 screenshot");
    const UWandererSwordComponent* Sword=Pawn->GetSword();
    const bool bSwordSet=Sword && Sword->IsInstalled() && !bSailboat && !Pawn->IsZeppelinPassenger() && !(Pawn->GetSkate() && Pawn->GetSkate()->IsRiding());
    if (bSwordSet)
    {
        // Sword hints replace the wave/interact tail so the line stays readable; the weapon line shows the live state.
        Secondary = bController ? FString::Printf(TEXT("%s attack, hold to charge   %s parry   %s draw / sheathe sword   %s crouch   %s interact   %s map (hold: places)   %s settings"),Pad.Attack,Pad.Parry,Pad.Weapon,Pad.Crouch,TEXT("D-pad Down"),Pad.Map,Pad.Menu)
            : TEXT("Left click attack, hold to charge   Right click parry   R draw / sheathe sword   Mouse look   M map   Esc settings   Tab release mouse");
    }
    // The merged move set: jump in the air is the double jump, then the paraglider; the roll button is the dodge (side
    // hop or backflip); the parry button guards with the sword and locks on (jump while guarding
    // parries); the dash button only swims fast.
    if (const UAdventureMoveSet* Moves = Pawn->GetMoves(); Moves && !bSailboat && !Pawn->IsZeppelinPassenger() && !(Pawn->GetSkate() && Pawn->GetSkate()->IsRiding()))
    {
        const TCHAR* Guard = TEXT("sword guard");
        const TCHAR* Jump = TEXT("jump / double jump / paraglider");
        Controls = bController ? FString::Printf(TEXT("Left stick move   Hold %s sprint   %s %s   %s dodge / backflip   %s swim dash   %s crouch"),Pad.Sprint,Pad.Jump,Jump,Pad.Roll,Pad.Dash,Pad.Crouch)
            : FString::Printf(TEXT("WASD run   Alt / J walk   Shift sprint   Space %s   Ctrl dodge / backflip   F swim dash   C crouch   K sailboat   M map"),Jump);
        Secondary = bController ? FString::Printf(TEXT("%s attack, hold to charge   Hold %s %s / lock-on, %s parry   %s draw / sheathe   %s map (hold: places)   %s settings"),Pad.Attack,Pad.Parry,Guard,Pad.Jump,Pad.Weapon,Pad.Map,Pad.Menu)
            : FString::Printf(TEXT("Left click attack, hold to charge   Hold right click %s / lock-on, Space parry   R draw / sheathe   Mouse look   M map   Esc settings"),Guard);
    }
    if (bController && (bSailboat || Pawn->IsZeppelinPassenger()))
    {
        Secondary=FString::Printf(TEXT("Right stick look   %s map (hold: places)   %s settings"),Pad.Map,Pad.Menu);
        if (Pawn->IsZeppelinPassenger())
            Secondary+=FString::Printf(TEXT("   %s flight speed"),ControllerStyle==2?TEXT("L1 / R1"):ControllerStyle==3?TEXT("L / R"):TEXT("LB / RB"));
    }
    if(const AZeppelinService* Zeppelin=Pawn->GetZeppelin())
    {
        const FString Hint=Zeppelin->Hint(Pawn);
        if(!Hint.IsEmpty())Controls=Hint.Replace(TEXT("Use"),bController?TEXT("D-pad Down"):TEXT("E"));
        // The flight speed buttons choose the stop before boarding.
        if(Zeppelin->CanChooseStop(Pawn))
            Controls+=FString::Printf(TEXT("   %s change stop"),!bController?TEXT("[ / ]"):ControllerStyle==2?TEXT("L1 / R1"):ControllerStyle==3?TEXT("L / R"):TEXT("LB / RB"));
    }
    {
        const FString TrainHint=ABelmonteTrainService::Hint(Pawn);
        if(!TrainHint.IsEmpty())Controls=TrainHint.Replace(TEXT("Use"),bController?TEXT("D-pad Down"):TEXT("E"));
    }
    const USkateComponent* Ride=Pawn->GetSkate();
    const bool bRide=Ride && Ride->IsRiding();
    if (Pawn->IsTrainPassenger())
    {
        const TCHAR* View=Pawn->IsTrainFirstPerson()?TEXT("vue à la troisième personne"):TEXT("vue à la première personne");
        Secondary += bController ? FString::Printf(TEXT("   %s %s"),Pad.LeftBumper,View) : FString::Printf(TEXT("   P %s"),View);
    }
    if (!Pawn->IsOnTrain() && !bRide && !bSailboat && !Pawn->IsZeppelinPassenger() && Ride && Ride->IsAvailable())
        Secondary += bController ? FString::Printf(TEXT("   %s skateboard"),Pad.Skate) : TEXT("   B skateboard");
    if(bRide)
    {
        // skate. controls (docs/SKATE.md): Flick-It on the right stick or the mouse with the left button held. Both
        // triggers pump and grab; the left stick pushed up or the left bumper is the transfer; the right bumper handplants.
        const float Kmh=Ride->GetSpeed()*.036f;
        Controls=bController
            ? FString::Printf(TEXT("%s push   %s brake   Left stick steer / spin / down powerslide / up transfer   Right stick tricks / manual   %s / %s pump / grab   %s transfer   %s handplant   %s step off      %s   %.0f km/h"),Pad.Jump,Pad.Roll,Pad.Parry,Pad.Attack,Pad.LeftBumper,Pad.RightBumper,Pad.Skate,*Ride->GetStatus(),Kmh)
            : FString::Printf(TEXT("W push   S brake   A / D steer / spin   C powerslide   hold left mouse + flick: tricks, hold part-way: manual   Space ollie   Q / E pump / grab   Shift transfer   B step off      %s   %.0f km/h"),*Ride->GetStatus(),Kmh);
        // Goofy stance mirrors the gestures, so the kickflip and heelflip sides swap.
        const TCHAR* Kick=Ride->IsGoofy()?TEXT("right"):TEXT("left");
        const TCHAR* Heel=Ride->IsGoofy()?TEXT("left"):TEXT("right");
        Secondary=bController?FString::Printf(TEXT("Flick: down-up ollie   down-up-%s kickflip   down-up-%s heelflip   down-left / down-right shove-its   sweep around for 360s   start from up for nollies"),Kick,Heel)
            :FString::Printf(TEXT("Flick the mouse like the stick: pull back then forward = ollie, forward-%s = kickflip, forward-%s = heelflip, pull back then sideways = shove-it   Mouse look"),Kick,Heel);
        DrawSkateLine();
    }
    const UBikeComponent* Bike=Pawn->GetBike();
    const UHorseComponent* Horse=Pawn->GetHorse();
    if (Bike && Bike->IsEquipped())
    {
        const float Kmh=Bike->GetSpeed()*.036f;
        Controls=bController
            ? FString::Printf(TEXT("%s pedal   %s brake   Left stick steer / lean (back while pedalling: wheelie)   %s pedal hard (on / off)   %s jump   %s skid stop (steering: drift)   %s bell   Hold %s get off (stopped)      %s   %.0f km/h"),Pad.Attack,Pad.Parry,Pad.Sprint,Pad.Jump,Pad.Crouch,Pad.Dash,Pad.Skate,*Bike->GetStatus(),Kmh)
            : FString::Printf(TEXT("W pedal   S brake   A / D steer   Up / Down lean (Down while pedalling: wheelie)   Shift pedal hard (on / off)   Space jump   C skid stop (steering: drift)   Left click bell   Q wave   V get off (stopped)      %s   %.0f km/h"),*Bike->GetStatus(),Kmh);
        Secondary=bController?FString::Printf(TEXT("Right stick look   %s map (hold: places)   %s settings"),Pad.Map,Pad.Menu):TEXT("Mouse look   M map & travel   Esc settings");
    }
    else if (Horse && Horse->IsEquipped())
    {
        const float Kmh=Horse->GetSpeed()*.036f;
        Controls=bController
            ? FString::Printf(TEXT("%s ride   %s rein in   Left stick steer   %s sprint (on / off)   %s jump   %s random horse   D-pad Up breed   D-pad Right tack   D-pad Left coat   Hold %s get off (when stopped)      %s   %.0f km/h"),Pad.Attack,Pad.Parry,Pad.Sprint,Pad.Jump,Pad.Dash,Pad.RightBumper,*Horse->GetStatus(),Kmh)
            : FString::Printf(TEXT("W ride   S rein in   A / D steer   Alt walk   J trot   Shift sprint (on / off)   Space jump   N random horse   U breed   I tack   O coat   H get off (when stopped)      %s   %.0f km/h"),*Horse->GetStatus(),Kmh);
        Secondary=bController?FString::Printf(TEXT("Right stick look   %s map (hold: places)   %s settings"),Pad.Map,Pad.Menu):TEXT("Mouse look   M map & travel   Esc settings");
    }
    else if (const UDrivingComponent* Car = Pawn->GetCar(); Car && Car->IsEquipped())
    {
        Controls = bController
            ? FString::Printf(TEXT("%s throttle   %s brake   Left stick steer   %s handbrake   Tap %s step out (stopped)      %s   %.0f km/h"),Pad.Attack,Pad.Parry,Pad.Roll,Pad.LeftBumper,*Car->GetStatus(),Car->GetSpeedKph())
            : FString::Printf(TEXT("W throttle   S brake   A / D steer   Space handbrake   L step out (stopped)      %s   %.0f km/h"),*Car->GetStatus(),Car->GetSpeedKph());
        Secondary = bController ? FString::Printf(TEXT("Right stick look   %s map (hold: places)   %s settings"),Pad.Map,Pad.Menu)
            : TEXT("Mouse look   M map & travel   Esc settings");
    }

    else if (!Pawn->IsOnTrain() && !bRide && !bSailboat && !Pawn->IsZeppelinPassenger())
    {
        if (Bike && Bike->IsAvailable())
            Secondary += bController ? FString::Printf(TEXT("   Hold %s bike"),Pad.Skate) : TEXT("   V bike");
        if (const UDrivingComponent* ParkedCar = Pawn->GetCar(); ParkedCar && !ParkedCar->IsEquipped())
        {
            Secondary += bController ? FString::Printf(TEXT("   Tap %s kart"),Pad.LeftBumper) : TEXT("   L kart");
            const FString CarHint = ParkedCar->GetStatus();
            if (!CarHint.IsEmpty() && CarHint != TEXT("Parked") && CarHint != TEXT("Driving"))
                Secondary += FString::Printf(TEXT("   %s"), *CarHint);
        }
        // Only to a character with horse clips; a shared game offers it while its host allows vehicles
        // (AWandererCharacter::RequestNetworkHorse).
        const AJapanGameState* Rules = GetWorld()->GetGameState<AJapanGameState>();
        if (Horse && Horse->CanRide() && (!JapanNetwork::IsOnline(GetWorld()) || (Rules && Rules->bPredictedVehicles)))
            Secondary += bController ? FString::Printf(TEXT("   Hold %s horse"),Pad.RightBumper) : TEXT("   H horse   N random horse");
    }

    if(!bSailboat&&!Pawn->IsZeppelinPassenger())
    {
        const auto& Stamina=Pawn->GetStamina();
        const FVector2D Centre(64,Canvas->SizeY-125);
        for(int Ring=0;Ring<int(Stamina.Capacity);++Ring)
        for(int Segment=0;Segment<64;++Segment)
        {
            const float Radius=12+Ring*7,A=2*PI*Segment/64-PI/2,B=2*PI*(Segment+1)/64-PI/2;
            const bool Filled=float(Segment)/64<FMath::Clamp(Stamina.Units-Ring,0.f,1.f);
            const FLinearColor Color=Filled?(Stamina.Exhausted?FLinearColor(.9,.4,.2):FLinearColor(.55,.86,.32)):FLinearColor(.15,.22,.16);
            DrawLine(Centre.X+Radius*FMath::Cos(A),Centre.Y+Radius*FMath::Sin(A),Centre.X+Radius*FMath::Cos(B),Centre.Y+Radius*FMath::Sin(B),Color,4.f);
        }
    }
    if (Sword && !bSailboat && !Pawn->IsZeppelinPassenger())
    {
        // Health next to the stamina rings; the nearest living fox gets a line at the top once it is close.
        const float Health=FMath::Clamp(Sword->GetHealth()/UWandererSwordComponent::MaxHealth,0.f,1.f);
        const float BarX=112,BarY=Canvas->SizeY-130,BarW=170,BarH=9;
        DrawRect(FLinearColor(0,0,0,.45f),BarX-2,BarY-2,BarW+4,BarH+4);
        DrawRect(Health>.3f?FLinearColor(.86f,.32f,.28f):FLinearColor(1.f,.15f,.1f),BarX,BarY,BarW*Health,BarH);
        DrawText(Sword->IsDown()?TEXT("knocked down"):FString::Printf(TEXT("%.0f"),Sword->GetHealth()),FLinearColor(.94f,.92f,.84f),BarX+BarW+8,BarY-4,Font,1.f);
        if (const auto* Moves = Pawn->GetMoves(); Moves && Moves->GuardPressure() > .01f)
            DrawRect(FLinearColor(.95f,.75f,.35f),BarX,BarY+BarH+3,BarW*Moves->GuardPressure(),3.f);
        const AFoxHunter* Nearest=nullptr; float Best=1e9f;
        for (TActorIterator<AFoxHunter> It(GetWorld());It;++It)
        {
            const float D=FVector::Dist2D(It->GetActorLocation(),Pawn->GetActorLocation());
            if (D<Best && (It->IsEngaged() || D<1500.f) && It->IsReady()) { Best=D; Nearest=*It; }
        }
        if (Nearest)
        {
            const float TopX=Canvas->SizeX*.5f-140,TopY=24;
            DrawRect(FLinearColor(0,0,0,.42f),TopX-10,TopY-6,300,40);
            FString Line=FString::Printf(TEXT("Fox hunter   %s"),Nearest->IsAlive()?*Nearest->StateName():TEXT("fallen"));
            if (Nearest->LastEventAge()<1.4f && !Nearest->LastEvent().IsEmpty()) Line+=TEXT("   ")+Nearest->LastEvent();
            DrawText(Line,FLinearColor(.95f,.88f,.72f),TopX,TopY-2,Font,1.f);
            for (int32 Pip=0;Pip<AFoxHunter::MaxHealth;++Pip)
                DrawRect(Pip<Nearest->GetHealth()?FLinearColor(.95f,.55f,.2f):FLinearColor(.25f,.2f,.16f),TopX+Pip*30,TopY+18,26,7);
        }
    }
    if (const UDrivingComponent* CarHud = Pawn->GetCar(); CarHud && CarHud->IsEquipped())
    {
        // A quiet tachometer and speed read-out in the corner, in the game's cream and clay palette.
        const float S = FMath::Min(1.25f, FMath::Max(.8f, Canvas->SizeY / 1080.f));
        const float R = 58.f * S;
        const float CX = Canvas->SizeX - 104.f * S, CY = Canvas->SizeY - 168.f * S;
        const float A0 = 145.f, A1 = 35.f;
        const float Revs = FMath::Clamp(CarHud->GetAudioRevs() / 5600.f, 0.f, 1.f);
        auto Point = [&](float Deg, float Radius)
        {
            const float A = FMath::DegreesToRadians(Deg);
            return FVector2D(CX + Radius * FMath::Cos(A), CY - Radius * FMath::Sin(A));
        };
        auto Arc = [&](float From, float To, float Radius, const FLinearColor& Color, float Thickness)
        {
            const int32 Segments = 40;
            FVector2D Last = Point(From, Radius);
            for (int32 I = 1; I <= Segments; ++I)
            {
                const FVector2D Next = Point(FMath::Lerp(From, To, float(I) / Segments), Radius);
                DrawLine(Last.X, Last.Y, Next.X, Next.Y, Color, Thickness);
                Last = Next;
            }
        };
        DrawRect(FLinearColor(0, 0, 0, .26f), CX - R - 16 * S, CY - R - 30 * S, 2 * R + 32 * S, 2 * R + 74 * S);
        Arc(A0, A1, R, FLinearColor(.18f, .19f, .17f, .55f), 5.f * S);
        if (Revs > .001f)
            Arc(A0, FMath::Lerp(A0, A1, Revs), R,
                Revs > .86f ? FLinearColor(1.f, .58f, .2f) : FLinearColor(.88f, .84f, .64f), 5.f * S);
        for (int32 I = 0; I <= 8; ++I)
        {
            const float Deg = FMath::Lerp(A0, A1, I / 8.f);
            const FVector2D A = Point(Deg, R - 9.f * S), B = Point(Deg, R - 3.f * S);
            DrawLine(A.X, A.Y, B.X, B.Y, FLinearColor(.78f, .75f, .62f, .5f), 1.4f * S);
        }
        float W = 0.f, H = 0.f;
        const FString Speed = FString::Printf(TEXT("%.0f"), CarHud->GetSpeedKph());
        Canvas->StrLen(Font, Speed, W, H);
        DrawText(Speed, FLinearColor(1.f, .95f, .82f), CX - W * .95f, CY - 26.f * S, Font, 1.9f * S);
        const FString Unit = TEXT("km/h");
        Canvas->StrLen(Font, Unit, W, H);
        DrawText(Unit, FLinearColor(.8f, .79f, .68f), CX - W * .4f, CY + 20.f * S, Font, .8f * S);
        const float Slip = CarHud->GetAudioSlip();
        const FString State = Slip > .35f ? FString(TEXT("drift")) : CarHud->GetSpeedKph() < 1.f ? FString(TEXT("idle")) : FString();
        if (!State.IsEmpty())
        {
            Canvas->StrLen(Font, State, W, H);
            DrawText(State, Slip > .35f ? FLinearColor(1.f, .72f, .36f) : FLinearColor(.72f, .72f, .62f),
                     CX - W * .43f, CY + 42.f * S, Font, .85f * S);
        }
    }

    DrawTrainer(bController, bSailboat);
    // Near a racecourse: the next race, the race running or the last podium (docs/RACING.md).
    if (const ARacingService* Racing = ARacingService::Find(GetWorld()))
    {
        const FString Line = Racing->HudLine(Pawn);
        if (!Line.IsEmpty())
        {
            float W = 0.f, H = 0.f; Canvas->StrLen(Font, Line, W, H);
            const float S = FMath::Min(1.15f, (Canvas->SizeX - 60.f) / FMath::Max(1.f, W));
            const float X = Canvas->SizeX * .5f - W * S * .5f, Y = Canvas->SizeY * .065f;
            DrawRect(FLinearColor(0, 0, 0, .42f), X - 12, Y - 6, W * S + 24, H * S + 12);
            DrawText(Line, FLinearColor(1.f, .93f, .78f), X, Y, Font, S);
        }
    }

    if (bSwordSet)
    {
        FString Weapon=Sword->IsArmed()?FString::Printf(TEXT("Sword: %s"),*Sword->StateName()):TEXT("Sword: put away");
        const float Charge=Sword->ChargeFraction();
        if (Charge>=0.f) Weapon+=FString::Printf(TEXT("   charge %d%%%s"),FMath::RoundToInt(Charge*100.f),Charge>=1.f?TEXT("  FULL"):TEXT(""));
        if (Sword->LastFeedbackAge()<1.2f && !Sword->LastFeedback().IsEmpty()) Weapon+=TEXT("   ")+Sword->LastFeedback();
        if (const ASwordDummy* Dummy=Pawn->GetSwordDummy()) Weapon+=FString::Printf(TEXT("   dummy: %d hits, %d parried, %d landed"),Dummy->HitsTaken,Dummy->StrikesParried,Dummy->StrikesLanded);
        DrawText(Weapon,FLinearColor(.95f,.9f,.7f),28,Canvas->SizeY-92,Font,1.f);
    }
    float PrimaryWidth,PrimaryHeight,SecondaryWidth,SecondaryHeight;
    Canvas->StrLen(Font,Controls,PrimaryWidth,PrimaryHeight);
    Canvas->StrLen(Font,Secondary,SecondaryWidth,SecondaryHeight);
    const float TextWidth=FMath::Max(PrimaryWidth,SecondaryWidth);
    const float TextScale=FMath::Min(1.f,(Canvas->SizeX-56.f)/FMath::Max(1.f,TextWidth));
    DrawRect(FLinearColor(0,0,0,.38f),16,Canvas->SizeY-68,FMath::Min(float(Canvas->SizeX-32),TextWidth*TextScale+24),52);
    DrawText(Controls,FLinearColor(.94f,.92f,.84f),28,Canvas->SizeY-58,Font,TextScale);
    DrawText(Secondary,FLinearColor(.78f,.79f,.72f),28,Canvas->SizeY-35,Font,TextScale);
    if (!bController && Pawn->IsMouseReleased()) DrawText(TEXT("Mouse released — Tab to capture"),FLinearColor(1,.84f,.45f),28,20,Font,1.f);
}

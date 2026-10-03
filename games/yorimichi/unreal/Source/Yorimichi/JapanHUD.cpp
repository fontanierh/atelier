#include "JapanHUD.h"
#include "ZeppelinService.h"
#include "WandererCharacter.h"
#include "JapanPreferences.h"
#include "SkateComponent.h"
#include "SailboatComponent.h"
#include "WandererSword.h"
#include "FoxHunter.h"
#include "LiveLibrary.h"
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
    const TCHAR *Jump, *Roll, *Dash, *Skate, *Map, *Menu, *Sprint, *Crouch, *Attack, *Parry, *Weapon;
};

static FControllerLabels ControllerLabels(int32 Style)
{
    switch (Style)
    {
        case 1: return {TEXT("A"),TEXT("B"),TEXT("X"),TEXT("Y"),TEXT("View"),TEXT("Menu"),TEXT("LS click"),TEXT("RS click"),TEXT("RT"),TEXT("LT"),TEXT("D-pad Left")};
        case 2: return {TEXT("Cross"),TEXT("Circle"),TEXT("Square"),TEXT("Triangle"),TEXT("Touchpad"),TEXT("Options"),TEXT("L3"),TEXT("R3"),TEXT("R2"),TEXT("L2"),TEXT("D-pad Left")};
        case 3: return {TEXT("B"),TEXT("A"),TEXT("Y"),TEXT("X"),TEXT("Minus"),TEXT("Plus"),TEXT("LS click"),TEXT("RS click"),TEXT("ZR"),TEXT("ZL"),TEXT("D-pad Left")};
        default: return {TEXT("Bottom button"),TEXT("Right button"),TEXT("Left button"),TEXT("Top button"),TEXT("View / Select"),TEXT("Menu / Start"),TEXT("LS click"),TEXT("RS click"),TEXT("Right trigger"),TEXT("Left trigger"),TEXT("D-pad Left")};
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
    if (!Pawn || !Canvas || !GEngine) return;
    UFont* Font = GEngine->GetSmallFont();
    if (!Pawn->IsReady())
    {
        DrawRect(FLinearColor(.04f,.06f,.06f,1),0,0,Canvas->SizeX,Canvas->SizeY);
        DrawText(TEXT("YORIMICHI   /   preparing the countryside"),FLinearColor(.93f,.87f,.72f),Canvas->SizeX*.34f,Canvas->SizeY*.5f,Font,1.4f);
        return;
    }
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
    // Filming the skating (ULiveLibrary::FilmHud): only the trick line.
    if (UYorimichiLive::IsFilmHud()) { DrawSkateLine(); return; }
    // Being hit washes the screen red for a moment (AYorimichiCombatFX::PlayerHurt).
    if (Pawn->GetDamageFlash()>0.f) DrawRect(FLinearColor(.75f,.08f,.04f,.13f*Pawn->GetDamageFlash()),0,0,Canvas->SizeX,Canvas->SizeY);
    // -fightfilm: the filmed fight keeps only the player's health and the fox's bar.
    const bool bFilm=FParse::Param(FCommandLine::Get(),TEXT("fightfilm"));
    if (bFilm)
    {
        const float Scale=Canvas->SizeY/1080.f;
        if (const UWandererSwordComponent* Sword=Pawn->GetSword())
        {
            const float Health=FMath::Clamp(Sword->GetHealth()/UWandererSwordComponent::MaxHealth,0.f,1.f);
            const float X=48*Scale,Y=Canvas->SizeY-78*Scale,W=300*Scale,H=12*Scale;
            DrawRect(FLinearColor(0,0,0,.4f),X-3*Scale,Y-3*Scale,W+6*Scale,H+6*Scale);
            DrawRect(FLinearColor(.2f,.08f,.06f,.8f),X,Y,W,H);
            DrawRect(Health>.3f?FLinearColor(.86f,.32f,.28f):FLinearColor(1.f,.15f,.1f),X,Y,W*Health,H);
        }
        for (TActorIterator<AFoxHunter> It(GetWorld());It;++It)
        {
            if (!It->IsReady() || (!It->IsEngaged() && It->IsAlive()) || It->IsHidden()) continue;
            const float W=420*Scale,X=Canvas->SizeX*.5f-W*.5f,Y=44*Scale;
            DrawText(TEXT("FOX HUNTER"),FLinearColor(.97f,.9f,.76f),X,Y-26*Scale,Font,1.4f*Scale);
            DrawRect(FLinearColor(0,0,0,.42f),X-3*Scale,Y-3*Scale,W+6*Scale,14*Scale);
            const float Seg=W/AFoxHunter::MaxHealth;
            for (int32 Pip=0;Pip<AFoxHunter::MaxHealth;++Pip)
                DrawRect(Pip<It->GetHealth()?FLinearColor(.95f,.52f,.18f):FLinearColor(.22f,.16f,.12f,.9f),X+Pip*Seg+1.5f*Scale,Y,Seg-3*Scale,8*Scale);
            break;
        }
        return;
    }
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
    FString Secondary = bController ? FString::Printf(TEXT("Right stick look   %s crouch   %s interact   %s map   %s settings   D-pad Up sailboat"),Pad.Crouch,TEXT("D-pad Down"),Pad.Map,Pad.Menu)
        : TEXT("Mouse look   M map & travel   Esc settings   Tab release mouse   F12 screenshot");
    const UWandererSwordComponent* Sword=Pawn->GetSword();
    const bool bSwordSet=Sword && Sword->IsInstalled() && !bSailboat && !Pawn->IsZeppelinPassenger() && !(Pawn->GetSkate() && Pawn->GetSkate()->IsRiding());
    if (bSwordSet)
    {
        // Sword hints replace the wave/interact tail so the line stays readable; the weapon line shows the live state.
        Secondary = bController ? FString::Printf(TEXT("%s attack, hold to charge   %s parry   %s draw / sheathe sword   %s crouch   %s interact   %s map   %s settings"),Pad.Attack,Pad.Parry,Pad.Weapon,Pad.Crouch,TEXT("D-pad Down"),Pad.Map,Pad.Menu)
            : TEXT("Left click attack, hold to charge   Right click parry   R draw / sheathe sword   Mouse look   M map   Esc settings   Tab release mouse");
    }
    // A Breath of the Wild move set: jump in the air opens the paraglider, the roll is the dodge, the parry button
    // guards and locks on (jump while guarding parries) and the dash swims fast.
    if (Pawn->GetMoves() && !bSailboat && !Pawn->IsZeppelinPassenger() && !(Pawn->GetSkate() && Pawn->GetSkate()->IsRiding()))
    {
        Controls = bController ? FString::Printf(TEXT("Left stick move   Hold %s sprint   %s jump / paraglider   %s dodge   %s swim dash   %s crouch"),Pad.Sprint,Pad.Jump,Pad.Roll,Pad.Dash,Pad.Crouch)
            : TEXT("WASD run   Alt / J walk   Shift sprint   Space jump / paraglider   Ctrl dodge   F swim dash   C crouch   K sailboat   M map");
        Secondary = bController ? FString::Printf(TEXT("%s attack, hold to charge   Hold %s guard / lock-on, %s parry   %s draw / sheathe   %s map   %s settings"),Pad.Attack,Pad.Parry,Pad.Jump,Pad.Weapon,Pad.Map,Pad.Menu)
            : TEXT("Left click attack, hold to charge   Hold right click guard / lock-on, Space parry   R draw / sheathe   Mouse look   M map   Esc settings");
    }
    if (bController && (bSailboat || Pawn->IsZeppelinPassenger()))
    {
        Secondary=FString::Printf(TEXT("Right stick look   %s map   %s settings"),Pad.Map,Pad.Menu);
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
    const USkateComponent* Ride=Pawn->GetSkate();
    const bool bRide=Ride && Ride->IsRiding();
    if (!bRide && !bSailboat && !Pawn->IsZeppelinPassenger() && Ride && Ride->IsAvailable())
        Secondary += bController ? FString::Printf(TEXT("   %s skateboard"),Pad.Skate) : TEXT("   B skateboard");
    if(bRide)
    {
        // skate. controls (docs/SKATE.md): Flick-It on the right stick or the mouse with the left button held.
        const float Kmh=Ride->GetSpeed()*.036f;
        Controls=bController
            ? FString::Printf(TEXT("%s push   %s brake   Left stick steer / spin / down-diagonal powerslide / forward transfer   Right stick tricks / manual   %s / %s pump / grab   %s step off      %s   %.0f km/h"),Pad.Jump,Pad.Roll,Pad.Parry,Pad.Attack,Pad.Skate,*Ride->GetStatus(),Kmh)
            : FString::Printf(TEXT("W push   S brake   A / D steer / spin   C powerslide   hold left mouse + flick: tricks, hold part-way: manual   Space ollie   Q / E pump / grab   Shift transfer   B step off      %s   %.0f km/h"),*Ride->GetStatus(),Kmh);
        Secondary=bController?TEXT("Flick: down-up ollie   down-up-left kickflip   down-up-right heelflip   down-left / down-right shove-its   sweep around for 360s   start from up for nollies")
            :TEXT("Flick the mouse like the stick: pull back then forward = ollie, forward-left = kickflip, forward-right = heelflip, pull back then sideways = shove-it   Mouse look");
        DrawSkateLine();
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

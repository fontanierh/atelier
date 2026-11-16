#include "RacingResults.h"
#include "HRContent.h"
#include "HRRules.h"
#include "JapanHUD.h"
#include "MenuStyle.h"
#include "RacingCounter.h"
#include "RacingService.h"
#include "SkateComponent.h"
#include "WandererCharacter.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

// ------------------------------------------------------------------------------------------------------------ the result

namespace RacingResultsBuild
{
    /** A display name for the panel: cut to MaxNameChars, never empty. */
    FString Clean(const FString& Name)
    {
        const FString Trimmed = Name.TrimStartAndEnd().Left(FRacingResultState::MaxNameChars);
        return Trimmed.IsEmpty() ? FString(TEXT("Another player")) : Trimmed;
    }

    /** The race's subtitle name: its event, with the round when it is not an ordinary race. */
    FString RaceTitle(const FHRRace& Race)
    {
        const bool bOrdinary = Race.Round != TEXT("final") && Race.Round != TEXT("semi") && Race.Round != TEXT("qualif") &&
            Race.Round != TEXT("barrage");
        if (!bOrdinary) return ARacingService::RaceName(Race);
        const HRContent::FEvent* E = HRContent::FindEvent(Race.EventId);
        return E ? FString(E->Name) : ARacingService::RaceName(Race);
    }
}

FRacingResultState RacingResults::Build(const FHRWorldState& S, const FString& PlayerId, double Now, const TMap<FString, FString>& Names)
{
    FRacingResultState Out;
    if (PlayerId.IsEmpty() || !FMath::IsFinite(Now)) return Out;
    const auto Today = [&S](const FHRTicket& T, const FString& Key) { return T.T == S.T && T.RaceKey == Key; };

    // The latest race of today the player bet on whose winner is home, and recently: decided at the start, seen at the post.
    const FHRRace* Race = nullptr;
    int32 Number = 0;
    double Home = -1.;
    for (int32 I = 0; I < S.Meeting.Races.Num(); ++I)
    {
        const FHRRace& R = S.Meeting.Races[I];
        if (R.Status != TEXT("run") || R.Finishes.IsEmpty()) continue;
        const double Start = HRRules::RaceStartSeconds(S, R.Key);
        if (Start < 0.) continue;
        const double At = Start + R.Finishes[0].TimeUs / 1e6;
        if (Now < At || Now - At >= FRacingResultState::Window || At <= Home) continue;
        if (!S.Tickets.ContainsByPredicate([&](const FHRTicket& T) { return T.PlayerId == PlayerId && Today(T, R.Key); })) continue;
        Race = &R;
        Number = I + 1;
        Home = At;
    }
    if (!Race) return Out;

    const FHRFinish& First = Race->Finishes[0];
    Out.Key = Race->Key;
    Out.Day = S.T;
    Out.Number = Number;
    Out.Race = RacingResultsBuild::RaceTitle(*Race);
    Out.Distance = Race->Distance;
    Out.Home = Home;
    Out.WinnerNumber = Race->Entries.IndexOfByPredicate([&First](const FHRRunner& E) { return E.HorseId == First.HorseId; }) + 1;
    const FHRHorse* Horse = S.Horses.Find(First.HorseId);
    Out.Winner = Horse ? Horse->Name : First.HorseName;
    const FHRStable* Stable = HRRules::FindStable(S, First.StableId);
    Out.WinnerStable = Stable ? Stable->Name : First.StableName;
    // The odds paid on the winner: a winning ticket's, else the pool's as the race closed.
    double Odds = HRRules::Rapport(S, *Race, First.HorseId);
    for (const FHRTicket& T : S.Tickets)
        if (Today(T, Race->Key) && T.Status == TEXT("won") && T.Rapport > 0.) { Odds = T.Rapport; break; }
    Out.WinnerOddsTenths = FMath::IsFinite(Odds) ? FMath::Clamp(FMath::RoundToInt(Odds * 10.), 0, 9999) : 0;

    // The player's own tickets first, then the others' grouped by player in the order they first bet. Only display names
    // leave the host: a player without one is "Another player", and two players with one name are told apart.
    TArray<const FHRTicket*> Mine;
    TArray<FString> Others;
    TMap<FString, TArray<const FHRTicket*>> ByPlayer;
    for (const FHRTicket& T : S.Tickets)
    {
        if (!Today(T, Race->Key)) continue;
        if (T.PlayerId == PlayerId) { Mine.Add(&T); continue; }
        TArray<const FHRTicket*>* List = ByPlayer.Find(T.PlayerId);
        if (!List)
        {
            Others.Add(T.PlayerId);
            List = &ByPlayer.Add(T.PlayerId);
        }
        List->Add(&T);
    }
    Out.OtherPlayers = Others.Num();
    TSet<FString> Taken;
    const auto Add = [&Out, &S](const FHRTicket& T, bool bMine, const FString& Name)
    {
        if (Out.Tickets.Num() >= FRacingResultState::MaxTickets) { Out.MoreTickets++; return; }
        FRacingResultTicket& V = Out.Tickets.AddDefaulted_GetRef();
        const FHRHorse* H = S.Horses.Find(T.HorseId);
        V.bMine = bMine;
        V.Player = Name;
        V.Horse = H ? H->Name : FString(TEXT("A horse"));
        V.Stake = T.Stake;
        V.Status = T.Status;
        V.Payout = T.Payout;
    };
    for (const FHRTicket* T : Mine) Add(*T, true, FString());
    for (const FString& Id : Others)
    {
        const FString* Shown = Names.Find(Id);
        const FHRPlayer* P = HRRules::FindPlayer(S, Id);
        const FString Base = RacingResultsBuild::Clean(Shown && !Shown->IsEmpty() ? *Shown : P ? P->Name : FString());
        FString Name = Base;
        for (int32 N = 2; Taken.Contains(Name); ++N) Name = FString::Printf(TEXT("%s (%d)"), *Base, N);
        Taken.Add(Name);
        for (const FHRTicket* T : ByPlayer[Id]) Add(*T, false, Name);
    }
    return Out;
}

bool RacingResults::IsFresh(const FRacingResultState& Result, double Now)
{
    // The host only builds a result once the winner is home; a client's clock may trail it by a moment.
    return !Result.IsEmpty() && FMath::IsFinite(Now) && Now - Result.Home < FRacingResultState::Window;
}

bool RacingResults::IsFree(const AWandererCharacter* Pawn)
{
    // On the ground: the panel holds the player still, so it waits out a jump, a fall or a swim.
    const UCharacterMovementComponent* Movement = Pawn ? Pawn->GetCharacterMovement() : nullptr;
    return Pawn && Movement && Movement->IsMovingOnGround() && Pawn->IsLocallyControlled() && Pawn->IsReady() && !Pawn->IsMenuOpen() && !Pawn->AreControlsSuspended() &&
        !RacingCounter::IsOpen() && !IsOpen() && !Pawn->OnVehicle() && !Pawn->IsZeppelinPassenger() && !Pawn->IsOnTrain() &&
        !(Pawn->GetSkate() && Pawn->GetSkate()->IsRiding()) && !Pawn->IsWaitingForTravelGround() && !Pawn->IsCinematic() &&
        !Pawn->IsNetworkActivityPending();
}

// ------------------------------------------------------------------------------------------------------------ the panel

// A named namespace: in a unity build an anonymous one would leak into later files.
namespace RacingResultsUi
{
    struct FOpen
    {
        TSharedPtr<SWidget> Menu;
        TWeakObjectPtr<AWandererCharacter> Player;
        /** Results shown or dropped on this machine ("day:key"): each is offered once. */
        TSet<FString> Done;
    };
    FOpen& Open()
    {
        static FOpen State;
        return State;
    }

    using YorimichiMenu::LitButton;
    using YorimichiMenu::Plain;
    using YorimichiMenu::Text;

    const FLinearColor Accent(.95f, .72f, .5f), Dim(1.f, 1.f, 1.f, .6f), On(.63f, .88f, .76f), Off(.71f, .71f, .71f);

    FString Status(const FRacingResultTicket& T)
    {
        return T.Status == TEXT("won") ? FString::Printf(TEXT("won +%d"), T.Payout)
            : T.Status == TEXT("refunded") ? FString::Printf(TEXT("refunded +%d"), T.Payout)
            : FString(TEXT("lost"));
    }

    /** "Horse · N coins" with its outcome at the right: a win in bold accent, the rest dim. */
    TSharedRef<SWidget> TicketRow(const FRacingResultTicket& T, float Indent)
    {
        const bool bWon = T.Status == TEXT("won");
        return SNew(SHorizontalBox)
            + SHorizontalBox::Slot().FillWidth(1.f).Padding(Indent, 1, 0, 1)[SNew(STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Regular", 14))
                .ColorAndOpacity(FLinearColor::White).OverflowPolicy(ETextOverflowPolicy::Ellipsis)
                .Text(FText::FromString(FString::Printf(TEXT("%s  ·  %d coins"), *T.Horse, T.Stake)))]
            + SHorizontalBox::Slot().AutoWidth().Padding(12, 1, 0, 1)[SNew(STextBlock).Justification(ETextJustify::Right)
                .Font(FCoreStyle::GetDefaultFontStyle(bWon ? "Bold" : "Regular", 14)).ColorAndOpacity(bWon ? Accent : Dim)
                .Text(FText::FromString(Status(T)))];
    }

    /** The panel, in the counter's style: the race and its winner, the player's bets, the toggle showing everyone's bets,
     *  the wallet and the legend. Its one button is the toggle; B (Escape) closes it. */
    TSharedRef<SWidget> Build(const FRacingResultState& R, TWeakObjectPtr<URacingWallet> Wallet, TSharedPtr<SButton>& OutToggle)
    {
        const TSharedRef<bool> bShowAll = MakeShared<bool>(false);
        const TSharedRef<YorimichiMenu::FInputKind> Input = MakeShared<YorimichiMenu::FInputKind>(AJapanHUD::CurrentControllerStyle());
        TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 4)[Text(FText::FromString(FString::Printf(TEXT("Race %d result"), R.Number)), 24, FLinearColor::White, "Bold")];
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 12)[Text(FText::FromString(FString::Printf(TEXT("%s  ·  %s m"), *R.Race,
            *FText::AsNumber(R.Distance).ToString())), 11, Accent)];
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 2)[Text(FText::FromString(FString::Printf(TEXT("%d. %s wins"), R.WinnerNumber, *R.Winner)), 18,
            FLinearColor::White, "Bold")];
        Rows->AddSlot().AutoHeight()[Text(FText::FromString(FString::Printf(TEXT("%s  ·  odds %d.%d"), *R.WinnerStable, R.WinnerOddsTenths / 10,
            R.WinnerOddsTenths % 10)), 13, Dim)];
        Rows->AddSlot().AutoHeight().Padding(0, 10)[YorimichiMenu::Divider()];

        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 4)[Text(FText::FromString(TEXT("Your bets")), 16, FLinearColor::White, "Bold")];
        for (const FRacingResultTicket& T : R.Tickets)
            if (T.bMine) Rows->AddSlot().AutoHeight()[TicketRow(T, 0.f)];
        Rows->AddSlot().AutoHeight().Padding(0, 10)[YorimichiMenu::Divider()];

        // The toggle: Off, a dim count of the others; On, their tickets under each player's name.
        TSharedRef<SButton> Toggle = SNew(SButton).ButtonStyle(Plain()).ContentPadding(FMargin(0, 5))
            .OnClicked_Lambda([bShowAll] { *bShowAll = !*bShowAll; return FReply::Handled(); })
            [SNew(SHorizontalBox)
                + SHorizontalBox::Slot().FillWidth(1.f).VAlign(VAlign_Center)[Text(FText::FromString(TEXT("Show everyone's bets")), 14, FLinearColor::White)]
                + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(12, 0, 0, 0)[SNew(STextBlock)
                    .Font(FCoreStyle::GetDefaultFontStyle("Bold", 14))
                    .Text_Lambda([bShowAll] { return FText::FromString(*bShowAll ? TEXT("On") : TEXT("Off")); })
                    .ColorAndOpacity_Lambda([bShowAll] { return FSlateColor(*bShowAll ? On : Off); })]];
        OutToggle = Toggle;
        Rows->AddSlot().AutoHeight()[LitButton(Toggle)];
        const auto Shown = [bShowAll](bool bWhenOn) { return TAttribute<EVisibility>::CreateLambda([bShowAll, bWhenOn]
            { return *bShowAll == bWhenOn ? EVisibility::Visible : EVisibility::Collapsed; }); };
        TSharedRef<SVerticalBox> Everyone = SNew(SVerticalBox);
        FString Group;
        bool bFirst = true;
        for (const FRacingResultTicket& T : R.Tickets)
        {
            if (T.bMine) continue;
            if (bFirst || T.Player != Group)
            {
                Everyone->AddSlot().AutoHeight().Padding(0, bFirst ? 6 : 8, 0, 2)[Text(FText::FromString(T.Player), 14, Accent, "Bold")];
                Group = T.Player;
                bFirst = false;
            }
            Everyone->AddSlot().AutoHeight()[TicketRow(T, 12.f)];
        }
        if (R.MoreTickets > 0)
            Everyone->AddSlot().AutoHeight().Padding(0, 6, 0, 0)[Text(FText::FromString(FString::Printf(TEXT("+%d more bets"), R.MoreTickets)), 13, Dim)];
        if (R.OtherPlayers == 0)
            Everyone->AddSlot().AutoHeight().Padding(0, 6, 0, 0)[Text(FText::FromString(TEXT("No one else bet on this race.")), 13, Dim)];
        Rows->AddSlot().AutoHeight()[SNew(SBox).Visibility(Shown(true))[Everyone]];
        if (R.OtherPlayers > 0)
            Rows->AddSlot().AutoHeight().Padding(0, 6, 0, 0)[SNew(SBox).Visibility(Shown(false))[Text(FText::FromString(R.OtherPlayers == 1
                ? FString(TEXT("1 other player bet on this race.")) : FString::Printf(TEXT("%d other players bet on this race."), R.OtherPlayers)), 13, Dim)]];
        Rows->AddSlot().AutoHeight().Padding(0, 10)[YorimichiMenu::Divider()];

        Rows->AddSlot().AutoHeight()[SNew(SHorizontalBox)
            + SHorizontalBox::Slot().FillWidth(1.f)[Text(TAttribute<FText>::CreateLambda([Wallet]
            {
                return FText::FromString(FString::Printf(TEXT("Coins: %d"), Wallet.IsValid() ? Wallet->GetWallet().Coins : 0));
            }), 13, FLinearColor::White)]
            + SHorizontalBox::Slot().AutoWidth()[SNew(STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Regular", 13)).ColorAndOpacity(FLinearColor::White)
                .Text_Lambda([Wallet] { return FText::FromString(FString::Printf(TEXT("Staked today: %d"), Wallet.IsValid() ? Wallet->GetWallet().DayStaked : 0)); })]];

        TSharedRef<SVerticalBox> Frame = SNew(SVerticalBox);
        Frame->AddSlot().FillHeight(1.f)[SNew(SScrollBox) + SScrollBox::Slot()[Rows]];
        Frame->AddSlot().AutoHeight().Padding(0, 14, 0, 8)[YorimichiMenu::Divider()];
        Frame->AddSlot().AutoHeight()[SNew(STextBlock).AutoWrapText(true).Justification(ETextJustify::Center)
            .Font(FCoreStyle::GetDefaultFontStyle("Regular", 14)).ColorAndOpacity(YorimichiMenu::LegendColor)
            .Text_Lambda([Input, bShowAll]
            {
                const TCHAR* What = *bShowAll ? TEXT("hide others") : TEXT("show everyone");
                if (!Input->bPad) return FText::FromString(FString::Printf(TEXT("Enter %s  ·  Esc close"), What));
                const YorimichiMenu::FPadNames Pad = Input->Pad();
                return FText::FromString(FString::Printf(TEXT("%s %s  ·  %s close"), Pad.Accept, What, Pad.Cancel));
            })];
        return SNew(YorimichiMenu::SMenuKeys, Input, [] { RacingResults::Close(); })
            [SNew(SBorder).HAlign(HAlign_Center).VAlign(VAlign_Center).BorderImage(YorimichiMenu::White()).BorderBackgroundColor(FLinearColor(0, 0, 0, .35f))
                [SNew(SBox).WidthOverride(640).MaxDesiredHeight(860.f)
                    [SNew(SBorder).Padding(28).BorderImage(YorimichiMenu::White()).BorderBackgroundColor(FLinearColor(.05f, .03f, .025f, .96f))[Frame]]]];
    }
}

void RacingResults::Tick(const ARacingService* Service)
{
    UWorld* World = Service ? Service->GetWorld() : nullptr;
    if (!World || Service->GetNetMode() == NM_DedicatedServer || !GEngine || !GEngine->GameViewport) return;
    APlayerController* PC = GEngine->GetFirstLocalPlayerController(World);
    URacingWallet* Wallet = URacingWallet::Of(PC);
    if (!Wallet || Wallet->GetResult().IsEmpty()) return;
    const FRacingResultState& Result = Wallet->GetResult();
    RacingResultsUi::FOpen& State = RacingResultsUi::Open();
    const FString Id = FString::Printf(TEXT("%d:%s"), Result.Day, *Result.Key);
    if (State.Done.Contains(Id)) return;
    // A result the player was too busy for is dropped once stale, not shown late over a later race.
    if (!IsFresh(Result, Service->WorldNow()))
    {
        State.Done.Add(Id);
        return;
    }
    AWandererCharacter* Pawn = PC ? Cast<AWandererCharacter>(PC->GetPawn()) : nullptr;
    if (!IsFree(Pawn)) return;
    State.Done.Add(Id);
    TSharedPtr<SButton> Toggle;
    State.Menu = RacingResultsUi::Build(Result, Wallet, Toggle);
    State.Player = Pawn;
    GEngine->GameViewport->AddViewportWidgetContent(State.Menu.ToSharedRef(), 21);
    Pawn->SetMenuOpen(true);
    GEngine->GameViewport->SetMouseCaptureMode(EMouseCaptureMode::NoCapture);
    FSlateApplication::Get().SetKeyboardFocus(Toggle, EFocusCause::SetDirectly);
    UE_LOG(LogTemp, Display, TEXT("RACING result shown: %s (%d tickets, %d other players)"), *Id, Result.Tickets.Num(), Result.OtherPlayers);
}

bool RacingResults::IsOpen()
{
    // A panel whose player is gone (a world left with it open) is closed.
    if (RacingResultsUi::Open().Menu.IsValid() && !RacingResultsUi::Open().Player.IsValid()) Close();
    return RacingResultsUi::Open().Menu.IsValid();
}

void RacingResults::Close()
{
    RacingResultsUi::FOpen& State = RacingResultsUi::Open();
    if (!State.Menu.IsValid()) return;
    if (GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(State.Menu.ToSharedRef());
    State.Menu.Reset();
    if (AWandererCharacter* Player = State.Player.Get()) Player->SetMenuOpen(false);
    State.Player.Reset();
}

void RacingResults::Reset()
{
    Close();
    RacingResultsUi::Open().Done.Reset();
}

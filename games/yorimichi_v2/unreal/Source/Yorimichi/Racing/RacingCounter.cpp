#include "RacingCounter.h"
#include "BelmonteRegion.h"
#include "HRRules.h"
#include "JapanHUD.h"
#include "MenuStyle.h"
#include "RacingBroadcast.h"
#include "RacingService.h"
#include "SkateComponent.h"
#include "WandererCharacter.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/Controller.h"
#include "Net/UnrealNetwork.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/Text/STextBlock.h"

// ------------------------------------------------------------------------------------------------------------ wallet

URacingWallet::URacingWallet()
{
    PrimaryComponentTick.bCanEverTick = false;
    SetIsReplicatedByDefault(true);
}

void URacingWallet::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    // A player's coins and tickets are theirs alone.
    DOREPLIFETIME_CONDITION(URacingWallet, Wallet, COND_OwnerOnly);
}

URacingWallet* URacingWallet::Of(const AController* Controller)
{
    return Controller ? Controller->FindComponentByClass<URacingWallet>() : nullptr;
}

void URacingWallet::RequestBet(const FString& RaceKey, int32 Runner, int32 Stake)
{
    const AActor* Owner = GetOwner();
    if (!Owner) return;
    if (Owner->HasAuthority())
    {
        ApplyReply(HostHandle(RaceKey, Runner, Stake));
        return;
    }
    Reply = TEXT("Placing your bet...");
    ServerPlaceBet(RaceKey, Runner, Stake);
}

void URacingWallet::ServerPlaceBet_Implementation(const FString& RaceKey, int32 Runner, int32 Stake)
{
    ClientBetReply(HostHandle(RaceKey, Runner, Stake));
}

void URacingWallet::ClientBetReply_Implementation(const FString& Error)
{
    ApplyReply(Error);
}

FString URacingWallet::HostHandle(const FString& RaceKey, int32 Runner, int32 Stake)
{
    // A client cannot flood the host: at most five requests a second are looked at.
    const double Now = FPlatformTime::Seconds();
    if (RequestWindow < 0. || Now - RequestWindow >= 1.)
    {
        RequestWindow = Now;
        Requests = 0;
    }
    if (++Requests > MaxRequestsPerSecond) return TEXT("Too many bets at once. Try again in a moment.");
    if (RaceKey.IsEmpty() || RaceKey.Len() > MaxRaceKeyChars) return TEXT("This bet is not valid.");
    ARacingService* Service = ARacingService::Find(this);
    if (!Service) return TEXT("The betting counter is closed for now.");
    return Service->PlaceBet(Cast<AController>(GetOwner()), RaceKey, Runner, Stake);
}

void URacingWallet::ApplyReply(const FString& Error)
{
    Reply = Error.IsEmpty() ? FString(TEXT("Bet placed.")) : Error;
}

// ------------------------------------------------------------------------------------------------------------ the window

// A named namespace: in a unity build an anonymous one would leak into later files.
namespace RacingCounterUi
{
    struct FOpen
    {
        TSharedPtr<SWidget> Menu;
        TWeakObjectPtr<AWandererCharacter> Player;
    };
    FOpen& Open()
    {
        static FOpen State;
        return State;
    }

    /** The window's choices: a runner of the race in focus (its index) and the stake, or All (the player's coins, as they
     *  change). */
    struct FChoice
    {
        int32 Runner = 0;
        int32 Stake = 1;
        bool bAll = false;

        /** The stake on offer: never more than the coins. */
        int32 Coins(int32 Wallet) const { return bAll ? Wallet : FMath::Min(Stake, Wallet); }
        void Step(int32 Wallet, int32 Direction)
        {
            Stake = RacingCounter::StepStake(Coins(Wallet), Wallet, Direction);
            bAll = Stake > 0 && Stake == Wallet;
        }
    };

    /** The input in use (a pad, and which, or the keys), for the legend: it follows the last key or click as the settings
     *  menu's does. */
    struct FInputKind
    {
        int32 PadStyle = AJapanHUD::CurrentControllerStyle();
        bool bPad = PadStyle != 0;

        FString Legend() const
        {
            if (!bPad) return TEXT("Arrows choose  ·  Enter select  ·  Q / E stake  ·  Esc close");
            const YorimichiMenu::FPadNames Pad = YorimichiMenu::PadNames(PadStyle);
            return FString::Printf(TEXT("D-pad choose  ·  %s select  ·  %s stake  ·  %s close"), Pad.Accept, Pad.Shoulders, Pad.Cancel);
        }
    };

    /** The window's frame: LB / Q step the stake down and RB / E up from whichever button has focus, and the right face
     *  button (B on an Xbox pad) or Escape closes the window. The keys are taken here, so neither the game (wave, interact,
     *  dodge, the settings menu) nor the window's focus moves on them. */
    class SStakeKeys : public SCompoundWidget
    {
    public:
        SLATE_BEGIN_ARGS(SStakeKeys) {}
            SLATE_DEFAULT_SLOT(FArguments, Content)
        SLATE_END_ARGS()

        void Construct(const FArguments& Args, TFunction<void(int32)> InStep, TSharedRef<FInputKind> InInput)
        {
            Step = MoveTemp(InStep);
            Input = InInput;
            ChildSlot[Args._Content.Widget];
        }
        virtual FReply OnPreviewKeyDown(const FGeometry&, const FKeyEvent& E) override
        {
            Input->bPad = E.GetKey().IsGamepadKey();
            return FReply::Unhandled();
        }
        virtual FReply OnPreviewMouseButtonDown(const FGeometry&, const FPointerEvent&) override
        {
            Input->bPad = false;
            return FReply::Unhandled();
        }
        virtual FReply OnKeyDown(const FGeometry&, const FKeyEvent& E) override
        {
            const FKey K = E.GetKey();
            if (IsClose(K))
            {
                if (!E.IsRepeat()) RacingCounter::Close();
                return FReply::Handled();
            }
            const int32 Direction = K == EKeys::Gamepad_LeftShoulder || K == EKeys::Q ? -1 : K == EKeys::Gamepad_RightShoulder || K == EKeys::E ? 1 : 0;
            if (!Direction) return FReply::Unhandled();
            if (!E.IsRepeat()) Step(Direction);
            return FReply::Handled();
        }
        virtual FReply OnKeyUp(const FGeometry&, const FKeyEvent& E) override
        {
            const FKey K = E.GetKey();
            return IsClose(K) || K == EKeys::Gamepad_LeftShoulder || K == EKeys::Q || K == EKeys::Gamepad_RightShoulder || K == EKeys::E
                ? FReply::Handled() : FReply::Unhandled();
        }
    private:
        static bool IsClose(const FKey& K) { return K == EKeys::Gamepad_FaceButton_Right || K == EKeys::Escape; }
        TFunction<void(int32)> Step;
        TSharedPtr<FInputKind> Input;
    };

    int32 WalletCoins(const TWeakObjectPtr<URacingWallet>& Wallet) { return Wallet.IsValid() ? Wallet->GetWallet().Coins : 0; }

    /** The race in focus while it is still open to bets, else nullptr. */
    const FRacingNetRace* OpenRace(const ARacingService* Service)
    {
        if (!Service) return nullptr;
        const FRacingNetRace& Race = Service->GetNetState().Race;
        return !Race.Key.IsEmpty() && Race.Runners.Num() >= 2 && Service->WorldNow() < Race.Start ? &Race : nullptr;
    }

    FString Odds(int32 Tenths) { return FString::Printf(TEXT("%d.%d"), Tenths / 10, Tenths % 10); }

    /** The wallet's ticket at Index (newest first), else nullptr. */
    const FRacingWalletTicket* TicketAt(const TWeakObjectPtr<URacingWallet>& Wallet, int32 Index)
    {
        return Wallet.IsValid() && Wallet->GetWallet().Tickets.IsValidIndex(Index) ? &Wallet->GetWallet().Tickets[Index] : nullptr;
    }

    /** A ticket's outcome, shown at the right of its line. */
    FString TicketStatus(const FRacingWalletTicket& T)
    {
        return T.Status == TEXT("won") ? FString::Printf(TEXT("won +%d"), T.Payout)
            : T.Status == TEXT("lost") ? FString(TEXT("lost"))
            : T.Status == TEXT("refunded") ? FString::Printf(TEXT("refunded +%d"), T.Payout)
            : FString(TEXT("pending"));
    }

    TSharedRef<STextBlock> Text(TAttribute<FText> Value, int32 Size, const FLinearColor& Color, const char* Weight = "Regular",
        ETextJustify::Type Justify = ETextJustify::Left)
    {
        return SNew(STextBlock).Text(Value).Font(FCoreStyle::GetDefaultFontStyle(Weight, Size)).ColorAndOpacity(Color).AutoWrapText(true)
            .Justification(Justify);
    }

    /** A button drawn as a menu row: no button chrome of its own, the row lit (YorimichiMenu::LitRow) while it has focus. */
    TSharedRef<SWidget> LitButton(const TSharedRef<SButton>& Button)
    {
        const TWeakPtr<SWidget> Weak = Button;
        return YorimichiMenu::LitRow([Weak] { const TSharedPtr<SWidget> W = Weak.Pin(); return W && W->HasAnyUserFocus().IsSet(); }, Button);
    }
    const FButtonStyle* Plain() { return &FCoreStyle::Get().GetWidgetStyle<FButtonStyle>("NoBorder"); }

    /** The window, in the game's menu style: the race in focus with each runner's odds, the stake stepper with its steps and
     *  estimated return, the bet and the host's answer, today's tickets and the wallet, then the legend. Buttons only, so the
     *  D-pad or the stick moves between them and the bottom face button presses them; LB / RB (Q / E) step the stake from
     *  anywhere in it and B (Escape) closes it. */
    TSharedRef<SWidget> Build(TWeakObjectPtr<ARacingService> Service, TWeakObjectPtr<URacingWallet> Wallet, TSharedPtr<SButton>& OutFirst)
    {
        const TSharedRef<FChoice> Choice = MakeShared<FChoice>();
        const TSharedRef<FInputKind> Input = MakeShared<FInputKind>();
        const FLinearColor Accent(.95f, .72f, .5f), Dim(1.f, 1.f, 1.f, .6f), Faint(1.f, 1.f, 1.f, .45f);
        TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 4)[Text(FText::FromString(TEXT("Salon des Paris")), 24, FLinearColor::White, "Bold")];
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 10)[Text(FText::FromString(TEXT("Win bets on the next race")), 11, Accent)];
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 12)[Text(TAttribute<FText>::CreateLambda([Service]
        {
            const ARacingService* S = Service.Get();
            const FRacingNetRace* Race = OpenRace(S);
            if (!Race) return FText::FromString(TEXT("No race is open to bets right now."));
            const int32 Left = FMath::Max(0, FMath::CeilToInt(Race->Start - S->WorldNow()));
            return FText::FromString(FString::Printf(TEXT("%s  ·  %d m  ·  starts in %d:%02d"), *Race->Name, Race->Distance, Left / 60, Left % 60));
        }), 14, FLinearColor::White, "Bold")];

        // Runners: a row each, ● the one chosen, its odds at the right.
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 4)[SNew(SBox).Visibility_Lambda([Service] { return OpenRace(Service.Get()) ? EVisibility::Visible : EVisibility::Collapsed; })
            [Text(FText::FromString(TEXT("Runners")), 16, FLinearColor::White, "Bold")]];
        for (int32 I = 0; I < HRRules::MaxRunners; ++I)
        {
            const auto Runner = [Service, I]() -> const FRacingNetRunner*
            {
                const FRacingNetRace* Race = OpenRace(Service.Get());
                return Race && Race->Runners.IsValidIndex(I) ? &Race->Runners[I] : nullptr;
            };
            TSharedRef<SButton> Row = SNew(SButton).ButtonStyle(Plain()).ContentPadding(FMargin(0, 5))
                .OnClicked_Lambda([Choice, I] { Choice->Runner = I; return FReply::Handled(); })
                [SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0, 0, 8, 0)[SNew(SBox).WidthOverride(16)[SNew(STextBlock)
                        .Font(FCoreStyle::GetDefaultFontStyle("Regular", 14))
                        .Text_Lambda([Choice, I] { return FText::FromString(Choice->Runner == I ? TEXT("●") : TEXT("○")); })
                        .ColorAndOpacity_Lambda([Choice, I, Accent, Dim] { return FSlateColor(Choice->Runner == I ? Accent : Dim); })]]
                    + SHorizontalBox::Slot().FillWidth(1.f).VAlign(VAlign_Center)[SNew(STextBlock).ColorAndOpacity(FLinearColor::White)
                        .OverflowPolicy(ETextOverflowPolicy::Ellipsis)
                        .Font_Lambda([Choice, I] { return FCoreStyle::GetDefaultFontStyle(Choice->Runner == I ? "Bold" : "Regular", 14); })
                        .Text_Lambda([Runner, I]
                        {
                            const FRacingNetRunner* R = Runner();
                            return R ? FText::FromString(FString::Printf(TEXT("%d. %s"), I + 1, *R->Horse)) : FText::GetEmpty();
                        })]
                    + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(12, 0, 0, 0)[SNew(STextBlock).ColorAndOpacity(FLinearColor::White)
                        .Font(FCoreStyle::GetDefaultFontStyle("Regular", 14)).Justification(ETextJustify::Right)
                        .Text_Lambda([Runner] { const FRacingNetRunner* R = Runner(); return R ? FText::FromString(Odds(R->OddsTenths)) : FText::GetEmpty(); })]];
            if (I == 0) OutFirst = Row;
            Rows->AddSlot().AutoHeight()[SNew(SBox).Visibility_Lambda([Runner] { return Runner() ? EVisibility::Visible : EVisibility::Collapsed; })[LitButton(Row)]];
        }
        Rows->AddSlot().AutoHeight().Padding(0, 10)[YorimichiMenu::Divider()];

        // The stake: the stepper, its steps (the current one lit) and the estimated return.
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 6)[Text(FText::FromString(TEXT("Stake")), 16, FLinearColor::White, "Bold")];
        auto StepButton = [Wallet, Choice](const TCHAR* Label, int32 Direction)
        {
            return SNew(SButton).HAlign(HAlign_Center).VAlign(VAlign_Center)
                .OnClicked_Lambda([Wallet, Choice, Direction] { Choice->Step(WalletCoins(Wallet), Direction); return FReply::Handled(); })
                [SNew(STextBlock).Text(FText::FromString(Label)).Font(FCoreStyle::GetDefaultFontStyle("Bold", 13))];
        };
        Rows->AddSlot().AutoHeight()[SNew(SHorizontalBox)
            + SHorizontalBox::Slot().FillWidth(1.f).VAlign(VAlign_Center)[StepButton(TEXT("LB / Q  −"), -1)]
            + SHorizontalBox::Slot().FillWidth(1.4f).VAlign(VAlign_Center)[Text(TAttribute<FText>::CreateLambda([Wallet, Choice]
            {
                const int32 Coins = WalletCoins(Wallet), Stake = Choice->Coins(Coins);
                return FText::FromString(Stake > 0 && Stake == Coins ? FString::Printf(TEXT("All %d"), Stake) : FString::FromInt(Stake));
            }), 28, Accent, "Bold", ETextJustify::Center)]
            + SHorizontalBox::Slot().FillWidth(1.f).VAlign(VAlign_Center)[StepButton(TEXT("RB / E  +"), 1)]];
        TSharedRef<SHorizontalBox> Steps = SNew(SHorizontalBox);
        for (int32 S = 0; S < 7; ++S)   // 1, 5, 10, 25, 50, 100 and All at most (RacingCounter::StakeSteps)
        {
            const auto Current = [Wallet, Choice, S]
            {
                const int32 Coins = WalletCoins(Wallet);
                return RacingCounter::StakeSteps(Coins).IndexOfByKey(Choice->Coins(Coins)) == S;
            };
            Steps->AddSlot().AutoWidth().Padding(S ? 14 : 0, 0, 0, 0)[SNew(STextBlock)
                .Visibility_Lambda([Wallet, S] { return RacingCounter::StakeSteps(WalletCoins(Wallet)).IsValidIndex(S) ? EVisibility::Visible : EVisibility::Collapsed; })
                .Text_Lambda([Wallet, S]
                {
                    const TArray<int32> All = RacingCounter::StakeSteps(WalletCoins(Wallet));
                    return !All.IsValidIndex(S) ? FText::GetEmpty() : S == All.Num() - 1 ? FText::FromString(TEXT("All")) : FText::AsNumber(All[S]);
                })
                .Font_Lambda([Current] { return FCoreStyle::GetDefaultFontStyle(Current() ? "Bold" : "Regular", 12); })
                .ColorAndOpacity_Lambda([Current, Accent, Faint] { return FSlateColor(Current() ? Accent : Faint); })];
        }
        Rows->AddSlot().AutoHeight().HAlign(HAlign_Center).Padding(0, 6, 0, 0)[Steps];
        Rows->AddSlot().AutoHeight().Padding(0, 8, 0, 8)[Text(TAttribute<FText>::CreateLambda([Service, Wallet, Choice]
        {
            const FRacingNetRace* Race = OpenRace(Service.Get());
            const int32 Stake = Choice->Coins(WalletCoins(Wallet));
            if (Stake < HRRules::FBetLimits::MinStake) return FText::FromString(TEXT("You have no coins to bet."));
            if (!Race || !Race->Runners.IsValidIndex(Choice->Runner)) return FText::GetEmpty();
            // The stake joins the pool before the odds are read, as it will when the bet is taken.
            const FRacingNetRunner& R = Race->Runners[Choice->Runner];
            const int32 Returns = HRRules::Payout(Stake, HRRules::RapportOf(Race->Pool, R.Backing, Stake));
            return FText::FromString(FString::Printf(TEXT("Returns about %d coins if %s wins (odds move as others bet)"), Returns, *R.Horse));
        }), 12, FLinearColor::White, "Regular", ETextJustify::Center)];

        // The bet, lit like a runner while focused, and the host's answer under it.
        // A press that cannot bet says why under the button, instead of doing nothing under an older answer.
        const auto Blocker = [Service, Wallet, Choice]
        {
            const ARacingService* S = Service.Get();
            static const FRacingNetRace NoRace;
            return RacingCounter::BetBlocker(S ? S->GetNetState().Race : NoRace, S ? S->WorldNow() : 0., Choice->Runner,
                Choice->Coins(WalletCoins(Wallet)));
        };
        TSharedRef<SButton> Bet = SNew(SButton).ButtonStyle(Plain()).ContentPadding(FMargin(0, 7)).HAlign(HAlign_Center)
            .OnClicked_Lambda([Service, Wallet, Choice, Blocker]
            {
                if (!Wallet.IsValid()) return FReply::Handled();
                const FString Why = Blocker();
                const FRacingNetRace* Race = OpenRace(Service.Get());
                if (!Why.IsEmpty() || !Race) Wallet->SetLocalReply(Why.IsEmpty() ? FString(TEXT("No race is open to bets right now.")) : Why);
                else Wallet->RequestBet(Race->Key, Choice->Runner, Choice->Coins(WalletCoins(Wallet)));
                return FReply::Handled();
            })
            [Text(TAttribute<FText>::CreateLambda([Service, Wallet, Choice]
            {
                const FRacingNetRace* Race = OpenRace(Service.Get());
                if (!Race || !Race->Runners.IsValidIndex(Choice->Runner)) return FText::FromString(TEXT("Place the bet"));
                return FText::FromString(FString::Printf(TEXT("Bet %d coins on %s"), Choice->Coins(WalletCoins(Wallet)), *Race->Runners[Choice->Runner].Horse));
            }), 14, FLinearColor::White, "Bold", ETextJustify::Center)];
        Rows->AddSlot().AutoHeight()[LitButton(Bet)];
        // The answer belongs to the race it was about: a new race in focus clears it.
        const TSharedRef<FString> ReplyRace = MakeShared<FString>(Service.IsValid() ? Service->GetNetState().Race.Key : FString());
        Rows->AddSlot().AutoHeight().Padding(0, 6, 0, 0)[Text(TAttribute<FText>::CreateLambda([Service, Wallet, ReplyRace]
        {
            if (!Wallet.IsValid()) return FText::GetEmpty();
            const FString Key = Service.IsValid() ? Service->GetNetState().Race.Key : FString();
            if (Key != *ReplyRace)
            {
                *ReplyRace = Key;
                Wallet->ClearReply();
            }
            return FText::FromString(Wallet->GetReply());
        }), 13, Accent, "Regular", ETextJustify::Center)];
        Rows->AddSlot().AutoHeight().Padding(0, 10)[YorimichiMenu::Divider()];

        // Today's tickets, newest first, each with its outcome at the right; then the wallet.
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 4)[Text(FText::FromString(TEXT("Your tickets")), 16, FLinearColor::White, "Bold")];
        Rows->AddSlot().AutoHeight()[SNew(SBox).Visibility_Lambda([Wallet] { return TicketAt(Wallet, 0) ? EVisibility::Collapsed : EVisibility::Visible; })
            [Text(FText::FromString(TEXT("No tickets today.")), 13, Dim)]];
        for (int32 I = 0; I < FRacingWalletState::MaxTickets; ++I)
        {
            Rows->AddSlot().AutoHeight().Padding(0, 1)[SNew(SHorizontalBox)
                .Visibility_Lambda([Wallet, I] { return TicketAt(Wallet, I) ? EVisibility::Visible : EVisibility::Collapsed; })
                + SHorizontalBox::Slot().FillWidth(1.f)[SNew(STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Regular", 13)).ColorAndOpacity(FLinearColor::White)
                    .OverflowPolicy(ETextOverflowPolicy::Ellipsis)
                    .Text_Lambda([Wallet, I]
                    {
                        const FRacingWalletTicket* T = TicketAt(Wallet, I);
                        return T ? FText::FromString(FString::Printf(TEXT("%s  ·  %d coins"), *T->Horse, T->Stake)) : FText::GetEmpty();
                    })]
                + SHorizontalBox::Slot().AutoWidth().Padding(12, 0, 0, 0)[SNew(STextBlock).Justification(ETextJustify::Right)
                    .Text_Lambda([Wallet, I] { const FRacingWalletTicket* T = TicketAt(Wallet, I); return T ? FText::FromString(TicketStatus(*T)) : FText::GetEmpty(); })
                    .Font_Lambda([Wallet, I] { const FRacingWalletTicket* T = TicketAt(Wallet, I); return FCoreStyle::GetDefaultFontStyle(T && T->Status == TEXT("won") ? "Bold" : "Regular", 13); })
                    .ColorAndOpacity_Lambda([Wallet, I, Accent, Dim] { const FRacingWalletTicket* T = TicketAt(Wallet, I); return FSlateColor(T && T->Status == TEXT("won") ? Accent : Dim); })]];
        }
        Rows->AddSlot().AutoHeight()[SNew(SBox).Visibility_Lambda([Wallet] { return Wallet.IsValid() && Wallet->GetWallet().EarlierTickets > 0 ? EVisibility::Visible : EVisibility::Collapsed; })
            [Text(TAttribute<FText>::CreateLambda([Wallet]
            {
                return FText::FromString(FString::Printf(TEXT("+%d earlier tickets"), Wallet.IsValid() ? Wallet->GetWallet().EarlierTickets : 0));
            }), 13, Dim)]];
        Rows->AddSlot().AutoHeight().Padding(0, 8, 0, 0)[SNew(SHorizontalBox)
            + SHorizontalBox::Slot().FillWidth(1.f)[Text(TAttribute<FText>::CreateLambda([Wallet]
            {
                return FText::FromString(FString::Printf(TEXT("Coins: %d"), WalletCoins(Wallet)));
            }), 13, FLinearColor::White)]
            + SHorizontalBox::Slot().AutoWidth()[SNew(STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Regular", 13)).ColorAndOpacity(FLinearColor::White)
                .Text_Lambda([Wallet] { return FText::FromString(FString::Printf(TEXT("Staked today: %d"), Wallet.IsValid() ? Wallet->GetWallet().DayStaked : 0)); })]];
        TSharedRef<SButton> Leave = SNew(SButton).ButtonStyle(Plain()).ContentPadding(FMargin(0, 5)).HAlign(HAlign_Center)
            .OnClicked_Lambda([] { RacingCounter::Close(); return FReply::Handled(); })
            [Text(FText::FromString(TEXT("Leave the counter")), 13, FLinearColor::White, "Regular", ETextJustify::Center)];
        Rows->AddSlot().AutoHeight().Padding(0, 8, 0, 0)[LitButton(Leave)];
        if (!OpenRace(Service.Get())) OutFirst = Leave;

        // The page scrolls to follow focus when today's tickets make it taller than the screen allows; the legend stays.
        TSharedRef<SVerticalBox> Frame = SNew(SVerticalBox);
        Frame->AddSlot().FillHeight(1.f)[SNew(SScrollBox).NavigationScrollPadding(96.f).ScrollWhenFocusChanges(EScrollWhenFocusChanges::AnimatedScroll)
            + SScrollBox::Slot()[Rows]];
        Frame->AddSlot().AutoHeight().Padding(0, 14, 0, 8)[YorimichiMenu::Divider()];
        Frame->AddSlot().AutoHeight()[SNew(STextBlock).AutoWrapText(true).Justification(ETextJustify::Center)
            .Font(FCoreStyle::GetDefaultFontStyle("Regular", 14)).ColorAndOpacity(YorimichiMenu::LegendColor)
            .Text_Lambda([Input] { return FText::FromString(Input->Legend()); })];
        return SNew(SStakeKeys, [Wallet, Choice](int32 Direction) { Choice->Step(WalletCoins(Wallet), Direction); }, Input)
            [SNew(SBorder).HAlign(HAlign_Center).VAlign(VAlign_Center).BorderImage(YorimichiMenu::White()).BorderBackgroundColor(FLinearColor(0, 0, 0, .35f))
                [SNew(SBox).WidthOverride(640).MaxDesiredHeight(860.f)
                    [SNew(SBorder).Padding(28).BorderImage(YorimichiMenu::White()).BorderBackgroundColor(FLinearColor(.05f, .03f, .025f, .96f))[Frame]]]];
    }
}

// ------------------------------------------------------------------------------------------------------------ the counter

bool RacingCounter::Parse(TConstArrayView<RacingTv::FSpot> Spots, FCounter& Out)
{
    // FindSpot reads the staged spots when given none: no spots here is no counter.
    const int32 Paris = Spots.IsEmpty() ? INDEX_NONE : RacingTv::FindSpot(TEXT("salon_paris"), Spots);
    if (!Spots.IsValidIndex(Paris)) return false;
    // V1's central window (hall-local (-1760, 300), facing the hall's yaw + 180) seen from the Paris screen's watch point
    // (hall-local (-500, -50), facing the hall's yaw - 90).
    const RacingTv::FSpot& Screen = Spots[Paris];
    Out.Spot = Screen.Watch + FRotator(0.f, Screen.WatchYaw, 0.f).RotateVector(FVector(-350., -1260., 0.));
    Out.Yaw = float(FRotator::NormalizeAxis(double(Screen.WatchYaw) - 90.));
    return true;
}

bool RacingCounter::InReach(const FVector& Location, const FVector& OriginCm, const FCounter& Counter)
{
    // In the counter's frame: +X towards the windows, +Y along the counter.
    const FVector L = FRotator(0.f, Counter.Yaw, 0.f).UnrotateVector(Location - OriginCm - Counter.Spot);
    return L.X >= -Reach && L.X <= Behind && FMath::Abs(L.Y) <= HalfLength && L.Z >= -Below && L.Z <= Above;
}

bool RacingCounter::IsAt(const AActor* Actor)
{
    static TWeakObjectPtr<const ABelmonteRegion> Region;
    UWorld* World = Actor ? Actor->GetWorld() : nullptr;
    FCounter Counter;
    if (!World || !Parse(RacingTv::Spots(), Counter)) return false;
    if (!Region.IsValid() || Region->GetWorld() != World)
    {
        TActorIterator<ABelmonteRegion> It(World);
        Region = It ? *It : nullptr;
    }
    return Region.IsValid() && InReach(Actor->GetActorLocation(), Region->GetActorLocation(), Counter);
}

bool RacingCounter::CanUse(const AWandererCharacter* Pawn)
{
    return Pawn && Pawn->IsLocallyControlled() && Pawn->IsReady() && !IsOpen() && !Pawn->OnVehicle() && !Pawn->IsZeppelinPassenger() &&
        !(Pawn->GetSkate() && Pawn->GetSkate()->IsRiding()) && URacingWallet::Of(Pawn->GetController()) && IsAt(Pawn);
}

bool RacingCounter::TryOpen(AWandererCharacter* Pawn)
{
    if (!CanUse(Pawn) || !GEngine || !GEngine->GameViewport) return false;
    RacingCounterUi::FOpen& State = RacingCounterUi::Open();
    TSharedPtr<SButton> First;
    URacingWallet* Wallet = URacingWallet::Of(Pawn->GetController());
    // A fresh window shows no answer from an earlier visit.
    Wallet->ClearReply();
    State.Menu = RacingCounterUi::Build(ARacingService::Find(Pawn), Wallet, First);
    State.Player = Pawn;
    GEngine->GameViewport->AddViewportWidgetContent(State.Menu.ToSharedRef(), 21);
    Pawn->SetMenuOpen(true);
    GEngine->GameViewport->SetMouseCaptureMode(EMouseCaptureMode::NoCapture);
    FSlateApplication::Get().SetKeyboardFocus(First, EFocusCause::SetDirectly);
    return true;
}

FString RacingCounter::Hint(const AWandererCharacter* Pawn)
{
    return CanUse(Pawn) ? FString(TEXT("Place a win bet")) : FString();
}

bool RacingCounter::IsOpen()
{
    // A window whose player is gone (a world left with it open) is closed, so the counter opens again.
    if (RacingCounterUi::Open().Menu.IsValid() && !RacingCounterUi::Open().Player.IsValid()) Close();
    return RacingCounterUi::Open().Menu.IsValid();
}

TArray<int32> RacingCounter::StakeSteps(int32 Coins)
{
    TArray<int32> Steps;
    for (const int32 Step : {1, 5, 10, 25, 50, 100})
        if (Step < Coins) Steps.Add(Step);
    if (Coins >= HRRules::FBetLimits::MinStake) Steps.Add(Coins);
    return Steps;
}

int32 RacingCounter::StepStake(int32 Stake, int32 Coins, int32 Direction)
{
    const TArray<int32> Steps = StakeSteps(Coins);
    if (Steps.IsEmpty()) return 0;
    if (Direction < 0)
    {
        for (int32 I = Steps.Num() - 1; I >= 0; --I)
            if (Steps[I] < Stake) return Steps[I];
        return Steps[0];
    }
    for (const int32 Step : Steps)
        if (Step > Stake) return Step;
    return Steps.Last();
}

FString RacingCounter::BetBlocker(const FRacingNetRace& Race, double Now, int32 Runner, int32 Stake)
{
    if (Race.Key.IsEmpty() || Race.Runners.Num() < 2) return TEXT("No race is open to bets right now.");
    if (!FMath::IsFinite(Now) || Now >= Race.Start) return TEXT("Betting on this race has closed.");
    if (Stake < HRRules::FBetLimits::MinStake) return TEXT("You have no coins to bet.");
    if (!Race.Runners.IsValidIndex(Runner)) return TEXT("This horse is not running in this race.");
    return FString();
}

void RacingCounter::Close()
{
    RacingCounterUi::FOpen& State = RacingCounterUi::Open();
    if (!State.Menu.IsValid()) return;
    if (GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(State.Menu.ToSharedRef());
    State.Menu.Reset();
    if (AWandererCharacter* Player = State.Player.Get()) Player->SetMenuOpen(false);
    State.Player.Reset();
}

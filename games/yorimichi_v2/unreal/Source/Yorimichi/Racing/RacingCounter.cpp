#include "RacingCounter.h"
#include "BelmonteRegion.h"
#include "HRRules.h"
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
#include "Widgets/SBoxPanel.h"
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

    /** The window's choices: a runner of the race in focus (its index) and the stake. */
    struct FChoice
    {
        int32 Runner = 0;
        int32 Stake = 1;
    };

    /** The race in focus while it is still open to bets, else nullptr. */
    const FRacingNetRace* OpenRace(const ARacingService* Service)
    {
        if (!Service) return nullptr;
        const FRacingNetRace& Race = Service->GetNetState().Race;
        return !Race.Key.IsEmpty() && Race.Runners.Num() >= 2 && Service->WorldNow() < Race.Start ? &Race : nullptr;
    }

    FString Odds(int32 Tenths) { return FString::Printf(TEXT("%d.%d"), Tenths / 10, Tenths % 10); }

    FString Ticket(const FRacingWalletTicket& T)
    {
        const FString Result = T.Status == TEXT("won") ? FString::Printf(TEXT("won %d coins"), T.Payout)
            : T.Status == TEXT("lost") ? FString(TEXT("lost"))
            : T.Status == TEXT("refunded") ? FString::Printf(TEXT("refunded %d coins"), T.Payout)
            : FString(TEXT("running"));
        return FString::Printf(TEXT("%s  ·  %s  ·  %d coins  ·  %s"), *T.Horse, *T.Race, T.Stake, *Result);
    }

    TSharedRef<STextBlock> Text(TAttribute<FText> Value, int32 Size, const FLinearColor& Color, const char* Weight = "Regular")
    {
        return SNew(STextBlock).Text(Value).Font(FCoreStyle::GetDefaultFontStyle(Weight, Size)).ColorAndOpacity(Color).AutoWrapText(true);
    }

    /** The window: the race in focus with each runner's odds, the stake (1 to 10), the bet, the wallet and the host's
     *  answer. Buttons only, so the D-pad or the stick moves between them and the bottom face button presses them. */
    TSharedRef<SWidget> Build(TWeakObjectPtr<ARacingService> Service, TWeakObjectPtr<URacingWallet> Wallet, TSharedPtr<SButton>& OutFirst)
    {
        const TSharedRef<FChoice> Choice = MakeShared<FChoice>();
        const FLinearColor Accent(.95f, .72f, .5f);
        TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 6)[Text(FText::FromString(TEXT("Salon des Paris")), 24, FLinearColor::White, "Bold")];
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 12)[Text(FText::FromString(TEXT("Win bets on the next race")), 11, Accent)];
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 10)[Text(TAttribute<FText>::CreateLambda([Service]
        {
            const ARacingService* S = Service.Get();
            const FRacingNetRace* Race = OpenRace(S);
            if (!Race) return FText::FromString(TEXT("No race is open to bets right now."));
            const int32 Left = FMath::Max(0, FMath::CeilToInt(Race->Start - S->WorldNow()));
            return FText::FromString(FString::Printf(TEXT("%s  ·  %d m  ·  starts in %d:%02d"), *Race->Name, Race->Distance, Left / 60, Left % 60));
        }), 14, FLinearColor::White, "Bold")];
        for (int32 I = 0; I < HRRules::MaxRunners; ++I)
        {
            TSharedRef<SButton> Runner = SNew(SButton)
                .Visibility_Lambda([Service, I] { const FRacingNetRace* Race = OpenRace(Service.Get()); return Race && Race->Runners.IsValidIndex(I) ? EVisibility::Visible : EVisibility::Collapsed; })
                .OnClicked_Lambda([Choice, I] { Choice->Runner = I; return FReply::Handled(); })
                [Text(TAttribute<FText>::CreateLambda([Service, Choice, I]
                {
                    const FRacingNetRace* Race = OpenRace(Service.Get());
                    if (!Race || !Race->Runners.IsValidIndex(I)) return FText::GetEmpty();
                    const FRacingNetRunner& R = Race->Runners[I];
                    return FText::FromString(FString::Printf(TEXT("%s %s  ·  %s  ·  odds %s"), Choice->Runner == I ? TEXT("●") : TEXT("○"), *R.Horse, *R.Stable, *Odds(R.OddsTenths)));
                }), 13, FLinearColor::White)];
            if (I == 0) OutFirst = Runner;
            Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 4)[Runner];
        }
        Rows->AddSlot().AutoHeight().Padding(0, 10, 0, 6)[Text(FText::FromString(TEXT("Stake")), 16, FLinearColor::White, "Bold")];
        TSharedRef<SHorizontalBox> Stakes = SNew(SHorizontalBox);
        for (int32 Coins = HRRules::FBetLimits::MinStake; Coins <= HRRules::FBetLimits::MaxStake; ++Coins)
            Stakes->AddSlot().FillWidth(1.f).Padding(0, 0, 4, 0)[SNew(SButton).HAlign(HAlign_Center)
                .OnClicked_Lambda([Choice, Coins] { Choice->Stake = Coins; return FReply::Handled(); })
                [Text(TAttribute<FText>::CreateLambda([Choice, Coins]
                {
                    return FText::FromString(Choice->Stake == Coins ? FString::Printf(TEXT("[%d]"), Coins) : FString::FromInt(Coins));
                }), 13, FLinearColor::White, "Bold")]];
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 10)[Stakes];
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 10)[SNew(SButton).HAlign(HAlign_Center)
            .IsEnabled_Lambda([Service, Choice] { const FRacingNetRace* Race = OpenRace(Service.Get()); return Race && Race->Runners.IsValidIndex(Choice->Runner); })
            .OnClicked_Lambda([Service, Wallet, Choice]
            {
                const FRacingNetRace* Race = OpenRace(Service.Get());
                if (Race && Wallet.IsValid()) Wallet->RequestBet(Race->Key, Choice->Runner, Choice->Stake);
                return FReply::Handled();
            })
            [Text(TAttribute<FText>::CreateLambda([Service, Choice]
            {
                const FRacingNetRace* Race = OpenRace(Service.Get());
                if (!Race || !Race->Runners.IsValidIndex(Choice->Runner)) return FText::FromString(TEXT("Place the bet"));
                return FText::FromString(FString::Printf(TEXT("Bet %d coins on %s"), Choice->Stake, *Race->Runners[Choice->Runner].Horse));
            }), 14, FLinearColor::White, "Bold")]];
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 6)[Text(TAttribute<FText>::CreateLambda([Wallet]
        {
            if (!Wallet.IsValid()) return FText::GetEmpty();
            const FRacingWalletState& W = Wallet->GetWallet();
            return FText::FromString(FString::Printf(TEXT("Coins: %d   ·   Staked today: %d of %d"), W.Coins, W.DayStaked, HRRules::FBetLimits::PerDay));
        }), 13, Accent, "Bold")];
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 10)[Text(TAttribute<FText>::CreateLambda([Wallet]
        {
            if (!Wallet.IsValid() || Wallet->GetWallet().Tickets.IsEmpty()) return FText::FromString(TEXT("No tickets today."));
            TArray<FString> Lines;
            for (const FRacingWalletTicket& T : Wallet->GetWallet().Tickets) Lines.Add(Ticket(T));
            return FText::FromString(FString::Join(Lines, TEXT("\n")));
        }), 11, FLinearColor::White)];
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 12)[Text(TAttribute<FText>::CreateLambda([Wallet]
        {
            return Wallet.IsValid() ? FText::FromString(Wallet->GetReply()) : FText::GetEmpty();
        }), 13, Accent)];
        TSharedRef<SButton> Leave = SNew(SButton).HAlign(HAlign_Center).Text(FText::FromString(TEXT("Leave the counter")))
            .OnClicked_Lambda([] { RacingCounter::Close(); return FReply::Handled(); });
        Rows->AddSlot().AutoHeight()[Leave];
        if (!OpenRace(Service.Get())) OutFirst = Leave;
        return SNew(SBorder).HAlign(HAlign_Center).VAlign(VAlign_Center).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0, 0, 0, .35f))
            [SNew(SBox).WidthOverride(640)
                [SNew(SBorder).Padding(28).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(.05f, .03f, .025f, .96f))[Rows]]];
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
    State.Menu = RacingCounterUi::Build(ARacingService::Find(Pawn), URacingWallet::Of(Pawn->GetController()), First);
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

void RacingCounter::Close()
{
    RacingCounterUi::FOpen& State = RacingCounterUi::Open();
    if (!State.Menu.IsValid()) return;
    if (GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(State.Menu.ToSharedRef());
    State.Menu.Reset();
    if (AWandererCharacter* Player = State.Player.Get()) Player->SetMenuOpen(false);
    State.Player.Reset();
}

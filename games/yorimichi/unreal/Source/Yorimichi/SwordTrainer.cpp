#include "SwordTrainer.h"
#include "AtelierData.h"
#include "BotwMoveSet.h"
#include "JapanGameMode.h"
#include "JapanPreferences.h"
#include "JapanWorld.h"
#include "WandererDefinition.h"
#include "WandererSword.h"
#include "YorimichiCombatFX.h"
#include "SkateComponent.h"
#include "SailboatComponent.h"
#include "AIController.h"
#include "GameFramework/PlayerController.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Misc/Parse.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Animation/AnimSequence.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

namespace
{
    // Her own body (unreal.sword_trainer) and move record; until it is built, Cairo's merged-move-set body stands in.
    const TCHAR* OwnDefinition = TEXT("/Game/SwordTrainer/DA_SwordTrainer.DA_SwordTrainer");
    const TCHAR* StandInDefinition = TEXT("/Game/CairoBotw/DA_CairoBotw.DA_CairoBotw");
    bool HasOwnBody() { return FPackageName::DoesPackageExist(FPackageName::ObjectPathToPackageName(FString(OwnDefinition))); }

    TSharedPtr<FJsonObject> Record(const TCHAR* Relative)
    {
        TSharedPtr<FJsonObject> Out;
        FString Text;
        if (FFileHelper::LoadFileToString(Text, *AtelierDataPath(Relative))) FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Out);
        return Out;
    }

    // The levels (docs/SWORD_TRAINER.md). Gentle telegraphs single cuts and stands open after them; Steady reads and
    // answers about half of the player's blows; Master parries, times perfect dodges into the flurry rush and uses
    // every opening of the set.
    const FTrainerStyle Styles[3] = {
        //  name       react parry dodge guard perfect aggr combo recov charge dash  jump  double feint damage strafe guard up
        { TEXT("Gentle"), .45f, 0.f,  .15f, .3f,   0.f,   .35f, 2,    1.1f,  .08f,  .06f, .06f, 0.f,   0.f,  .6f,  0.f,   .3f },
        { TEXT("Steady"), .25f, .25f, .25f, .25f,  .35f,  .65f, 3,    .6f,   .15f,  .14f, .12f, .08f,  .06f, .85f, .5f,   .55f },
        { TEXT("Master"), .12f, .45f, .3f,  .15f,  .75f,  1.05f, 4,   .3f,   .2f,   .16f, .14f, .14f,  .12f, 1.f,  1.f,   .7f },
    };
    // The training ground: the open apron in front of the tea house, in the hamlet's authored metres (before
    // `village_point`'s offset), and the way she faces when she waits there (toward the lane).
    const FVector2D TrainingGround(90.f, 4.f);
    constexpr float GroundYaw = -60.f;
    constexpr float TalkReach = 340.f, LeaveReach = 3000.f;
}

ASwordTrainer::ASwordTrainer(const FObjectInitializer& ObjectInitializer) : Super(ObjectInitializer)
{
    DefinitionAssetPath = OwnDefinition;
    AIControllerClass = AAIController::StaticClass();
    AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;
    // Cairo's frame until BeginPlay knows which body she has (the imported Tripo skeleton faces +X).
    GetCapsuleComponent()->InitCapsuleSize(22.f, 74.f);
    GetMesh()->SetRelativeLocation(FVector(0, 0, -74.65f));
    GetMesh()->SetRelativeRotation(FRotator::ZeroRotator);
    GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
}

void ASwordTrainer::BeginPlay()
{
    const bool bOwn = HasOwnBody();
    if (!bOwn)
    {
        DefinitionAssetPath = StandInDefinition;
        UE_LOG(LogTemp, Warning, TEXT("Sword trainer: her body is not built (unreal.sword_trainer); Cairo stands in"));
    }
    else
    {
        // 168 cm: the capsule's half height and the floor 0.65 cm under the soles, as the player's export puts it.
        GetCapsuleComponent()->SetCapsuleSize(24.f, 84.f);
        GetMesh()->SetRelativeLocation(FVector(0, 0, -84.65f));
        GetCharacterMovement()->SetCrouchedHalfHeight(72.f);
    }
    Super::BeginPlay();
    UBotwMoveSet* Set = NewObject<UBotwMoveSet>(this, TEXT("TrainerMoves"));
    if (Set->Initialize(this, Record(bOwn ? TEXT("sword-trainer/botw.json") : TEXT("cairo/botw.json")))) Moves = Set;
    else UE_LOG(LogTemp, Error, TEXT("Sword trainer: no move set (build unreal.cairo_botw or unreal.sword_trainer)"));
    if (Moves) Moves->SetShield(false);
    if (Moves) Moves->SetLegacy(false);
    Home = GetActorLocation(); HomeYaw = GetActorRotation().Yaw;
    Dice.Initialize(FParse::Param(FCommandLine::Get(), TEXT("trainerqa")) ? 7 : int32(FPlatformTime::Cycles() & 0x7fffffff));
}

void ASwordTrainer::EndPlay(const EEndPlayReason::Type Reason)
{
    CloseMenu();
    Super::EndPlay(Reason);
}

ASwordTrainer* ASwordTrainer::SpawnInVillage(AJapanWorld* World, const TSharedPtr<FJsonObject>& Village)
{
    const TCHAR* Line = FCommandLine::Get();
    if (!World || !Village.IsValid() || FParse::Param(Line, TEXT("notrainer"))) return nullptr;
    if (AJapanGameMode::IsScriptedSession() && !FParse::Param(Line, TEXT("trainer")) && !FParse::Param(Line, TEXT("trainerqa"))) return nullptr;
    FVector Offset = FVector::ZeroVector;
    const TArray<TSharedPtr<FJsonValue>>* O = nullptr;
    if (Village->TryGetArrayField(TEXT("offset"), O) && O->Num() == 3) Offset = FVector((*O)[0]->AsNumber(), (*O)[1]->AsNumber(), (*O)[2]->AsNumber());
    FVector Where = AJapanWorld::ToUE(TrainingGround.X + Offset.X, TrainingGround.Y + Offset.Y, 200.);
    FHitResult Hit;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(TrainerSpawn), false);
    if (!World->GetWorld()->LineTraceSingleByChannel(Hit, Where, Where - FVector(0, 0, 40000.), ECC_Visibility, Params))
    {
        UE_LOG(LogTemp, Warning, TEXT("Sword trainer: no ground at %s"), *Where.ToString());
        return nullptr;
    }
    Where = Hit.ImpactPoint + FVector(0, 0, 90.f);
    FActorSpawnParameters Spawn; Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
    ASwordTrainer* Trainer = World->GetWorld()->SpawnActor<ASwordTrainer>(Where, FRotator(0, -GroundYaw, 0), Spawn);
    if (Trainer) Trainer->EnterWorld(World);
    UE_LOG(LogTemp, Display, TEXT("Sword trainer %s at %s"), Trainer ? TEXT("spawned") : TEXT("NOT spawned"), *Where.ToString());
    return Trainer;
}

ASwordTrainer* ASwordTrainer::Find(const UObject* WorldContext)
{
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World) return nullptr;
    TActorIterator<ASwordTrainer> It(World);
    return It ? *It : nullptr;
}

bool ASwordTrainer::TryInteract(AWandererCharacter* Player)
{
    ASwordTrainer* Trainer = Find(Player);
    if (!Trainer || !Trainer->CanTalk(Player)) return false;
    Trainer->OpenMenu(Player);
    return true;
}

void ASwordTrainer::PlaceAt(const FVector& Ground, float Yaw)
{
    EndBout(TEXT(""));
    Home = Ground + FVector(0, 0, GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 2.f);
    HomeYaw = Yaw;
    SetActorLocationAndRotation(Home, FRotator(0, Yaw, 0), false, nullptr, ETeleportType::TeleportPhysics);
    GetCharacterMovement()->Velocity = FVector::ZeroVector;
    if (Moves) Moves->Reset();
    Bout = EBout::Home; SetIntent(TEXT("home"));
}

bool ASwordTrainer::CanTalk(const AWandererCharacter* Player) const
{
    return Player && Player != this && IsReady() && Bout == EBout::Home && !Menu.IsValid() &&
        FVector::Dist2D(Player->GetActorLocation(), GetActorLocation()) < TalkReach &&
        FMath::Abs(Player->GetActorLocation().Z - GetActorLocation().Z) < 200.f;
}

bool ASwordTrainer::IsSparringWith(const AActor* Other) const
{
    // From the stance (so each side's lock-on finds the other) to the end of the bout.
    return Other && Other == Opponent.Get() && (Bout == EBout::Ready || Bout == EBout::Fighting);
}

float ASwordTrainer::SparringDamage(int32 Power) const
{
    return Super::SparringDamage(Power) * GetStyle().Damage;
}

const FTrainerStyle& ASwordTrainer::GetStyle() const { return Styles[FMath::Clamp(Level, 0, 2)]; }

float ASwordTrainer::GetHealthFraction() const
{
    const UWandererSwordComponent* S = GetSword();
    return S ? FMath::Clamp(S->GetHealth() / UWandererSwordComponent::MaxHealth, 0.f, 1.f) : 1.f;
}

FString ASwordTrainer::GetCallout(float& Alpha) const
{
    Alpha = FMath::Clamp(CalloutTime / .4f, 0.f, 1.f);
    return CalloutTime > 0.f ? Callout : FString();
}

FString ASwordTrainer::BoutName() const
{
    switch (Bout)
    {
    case EBout::Talking: return TEXT("talking");
    case EBout::Ready: return TEXT("ready");
    case EBout::Fighting: return TEXT("fighting");
    case EBout::Over: return TEXT("over");
    case EBout::Return: return TEXT("return");
    default: return TEXT("home");
    }
}

// ------------------------------------------------------------------------------------------------------------ Menu

void ASwordTrainer::OpenMenu(AWandererCharacter* Player)
{
    if (Menu.IsValid() || !Player || !GEngine || !GEngine->GameViewport) return;
    Opponent = Player;
    Bout = EBout::Talking;
    MenuLevel = Level;
    bMenuOwnShield = bOwnShield;
    TWeakObjectPtr<ASwordTrainer> Self(this);
    const bool bCanSpar = Player->GetMoves() != nullptr;
    auto Title = [](const TCHAR* Text, int32 Size) { return SNew(STextBlock).Text(FText::FromString(Text)).Font(FCoreStyle::GetDefaultFontStyle("Bold", Size)).ColorAndOpacity(FLinearColor::White); };
    TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 6)[Title(TEXT("Kaede"), 24)];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 16)[SNew(STextBlock).Text(FText::FromString(TEXT("Sword teacher of Momiji Hamlet"))).ColorAndOpacity(FLinearColor(.95f, .72f, .5f))];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 16)[SNew(STextBlock).AutoWrapText(true).ColorAndOpacity(FLinearColor::White)
        .Text(FText::FromString(bCanSpar
            ? TEXT("\"Nothing in these woods waits for you to be ready. Let's see your blade. Pick how hard I push; a bout ends when one of us is down.\"")
            : TEXT("\"Your feet aren't ready for my lessons yet. Come back with the merged move set (Esc, Move set).\"")))];
    TSharedPtr<SButton> First;
    if (bCanSpar)
    {
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 6)[Title(TEXT("Level"), 16)];
        TSharedRef<SHorizontalBox> Levels = SNew(SHorizontalBox);
        const TCHAR* Notes[3] = { TEXT("single cuts, slow to answer"), TEXT("combos, guards and dodges"), TEXT("parries, perfect dodges, everything") };
        for (int32 I = 0; I < 3; ++I)
        {
            TSharedRef<SButton> B = SNew(SButton).OnClicked_Lambda([Self, I] { if (Self.IsValid()) Self->MenuLevel = I; return FReply::Handled(); })
                [SNew(SVerticalBox)
                    + SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Bold", 14))
                        .Text_Lambda([Self, I] { return FText::FromString(FString::Printf(TEXT("%s%s"), Self.IsValid() && Self->MenuLevel == I ? TEXT("● ") : TEXT("○ "), Styles[I].Name)); })]
                    + SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).Text(FText::FromString(Notes[I])).Font(FCoreStyle::GetDefaultFontStyle("Regular", 10))]];
            if (I == MenuLevel) First = B;
            Levels->AddSlot().FillWidth(1.f).Padding(0, 0, 8, 0)[B];
        }
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 16)[Levels];
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 8)[SNew(SButton)
            .Text_Lambda([Self] { return FText::FromString(Self.IsValid() && Self->bMenuOwnShield ? TEXT("Kaede: sword and shield") : TEXT("Kaede: sword only")); })
            .OnClicked_Lambda([Self] { if (Self.IsValid()) Self->bMenuOwnShield = !Self->bMenuOwnShield; return FReply::Handled(); })];
        TWeakObjectPtr<AWandererCharacter> Who(Player);
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 18)[SNew(SButton)
            .Text_Lambda([Who] { return FText::FromString(Who.IsValid() && Who->GetMoves() && Who->GetMoves()->HasShield() ? TEXT("You: sword and shield") : TEXT("You: sword only")); })
            .OnClicked_Lambda([Who]
            {
                // The player's own "Shield" setting, saved like every setting (the Esc menu shows the same choice).
                if (Who.IsValid() && Who->GetPreferences() && Who->GetMoves()) Who->GetPreferences()->SetValue(TEXT("shield"), Who->GetMoves()->HasShield() ? 0.f : 1.f);
                return FReply::Handled();
            })];
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 8)[SNew(SButton).HAlign(HAlign_Center)
            .Text(FText::FromString(TEXT("Begin the bout")))
            .OnClicked_Lambda([Self, Who]
            {
                if (Self.IsValid() && Who.IsValid())
                {
                    const int32 L = Self->MenuLevel; const bool bShield = Self->bMenuOwnShield;
                    const bool bTheirs = Who->GetMoves() && Who->GetMoves()->HasShield();
                    Self->CloseMenu();
                    Self->StartBout(Who.Get(), L, bShield, bTheirs);
                }
                return FReply::Handled();
            })];
    }
    TSharedRef<SButton> Leave = SNew(SButton).HAlign(HAlign_Center).Text(FText::FromString(TEXT("Not today")))
        .OnClicked_Lambda([Self] { if (Self.IsValid()) { Self->CloseMenu(); Self->Say(TEXT("Kaede: \"The woods will still be here.\"")); } return FReply::Handled(); });
    Rows->AddSlot().AutoHeight()[Leave];
    if (!First) First = Leave;
    Menu = SNew(SBorder).HAlign(HAlign_Center).VAlign(VAlign_Center).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0, 0, 0, .35f))
        [SNew(SBox).WidthOverride(640)
            [SNew(SBorder).Padding(28).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(.05f, .03f, .025f, .96f))[Rows]]];
    GEngine->GameViewport->AddViewportWidgetContent(Menu.ToSharedRef(), 21);
    Player->SetMenuOpen(true);
    GEngine->GameViewport->SetMouseCaptureMode(EMouseCaptureMode::NoCapture);
    FSlateApplication::Get().SetKeyboardFocus(First, EFocusCause::SetDirectly);
    if (GetDefinition() && GetDefinition()->FindAction(TEXT("Talk"))) PlayGesture(TEXT("Talk"));
}

void ASwordTrainer::CloseMenu()
{
    if (!Menu.IsValid()) return;
    if (GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(Menu.ToSharedRef());
    Menu.Reset();
    if (AWandererCharacter* Player = Opponent.Get()) Player->SetMenuOpen(false);
    if (Bout == EBout::Talking) Bout = EBout::Home;
}

// ------------------------------------------------------------------------------------------------------------ Bout

void ASwordTrainer::Restore(AWandererCharacter* Who)
{
    if (UWandererSwordComponent* S = Who ? Who->GetSword() : nullptr) S->RestoreHealth();
}

bool ASwordTrainer::StartBout(AWandererCharacter* Player, int32 NewLevel, bool bShield, bool bPlayerShield)
{
    if (!Player || !Player->GetMoves() || !Moves || Bout == EBout::Fighting) return false;
    CloseMenu();
    Opponent = Player;
    Level = FMath::Clamp(NewLevel, 0, 2);
    bOwnShield = bShield;
    Moves->SetShield(bOwnShield);
    if (Player->GetMoves()->HasShield() != bPlayerShield)
    {
        if (Player->GetPreferences()) Player->GetPreferences()->SetValue(TEXT("shield"), bPlayerShield ? 1.f : 0.f);
        else Player->GetMoves()->SetShield(bPlayerShield);
    }
    Restore(this); Restore(Player);
    Counts.Reset();
    ReleaseAll();
    Bout = EBout::Ready; BoutTime = 0.f;
    SetIntent(TEXT("ready"));
    Say(FString::Printf(TEXT("Kaede · %s: \"Take your stance.\""), GetStyle().Name), 1.6f);
    UE_LOG(LogTemp, Display, TEXT("SWORD TRAINER bout: level %s, her shield %d, player's shield %d"), GetStyle().Name, bOwnShield, bPlayerShield);
    return true;
}

void ASwordTrainer::EndBout(const FString& Why)
{
    if (Bout == EBout::Home || Bout == EBout::Return) return;
    CloseMenu();
    ReleaseAll();
    Bout = EBout::Return; BoutTime = 0.f;
    SetIntent(TEXT("return"));
    if (!Why.IsEmpty()) Say(Why);
    Restore(this);
    if (AWandererCharacter* Player = Opponent.Get()) Restore(Player);
    UE_LOG(LogTemp, Display, TEXT("SWORD TRAINER bout ended: %s"), *Why);
}

// ---------------------------------------------------------------------------------------------------------- Hands

void ASwordTrainer::Hold(FName Button, bool bDown)
{
    bool& Held = Button == TEXT("guard") ? bGuardDown : bAttackDown;
    if (Held == bDown) return;
    Held = bDown;
    Live_Press(bDown ? Button : FName(*(Button.ToString() + TEXT("_release"))));
}

void ASwordTrainer::Press(FName Button) { Live_Press(Button); }

void ASwordTrainer::Drive(const FVector2D& Stick, int32 Gait) { Live_Drive(Stick, Gait); }

void ASwordTrainer::ReleaseAll()
{
    Hold(TEXT("guard"), false); Hold(TEXT("attack"), false);
    Drive(FVector2D::ZeroVector, 1);
    CombosLeft = 0; HoldFor = 0.f; bAirStep = false; Answer.Reset(); bAnswered = false;
}

/** The stick's frame is her view: aim it at Where, so forward on the stick goes toward it. */
void ASwordTrainer::FaceToward(const FVector& Where, float Dt)
{
    const FVector To = (Where - GetActorLocation()) * FVector(1, 1, 0);
    if (To.SizeSquared() < 1.f || !Controller) return;
    Controller->SetControlRotation(FRotator(0, To.Rotation().Yaw, 0));
}

// ----------------------------------------------------------------------------------------------------------- Brain

void ASwordTrainer::Tick(float Dt)
{
    CalloutTime = FMath::Max(0.f, CalloutTime - Dt);
    IntentTime += Dt; BoutTime += Dt;
    // A gesture (a bow, a word) ends with its clip.
    if (const UWandererDefinition* D = GetDefinition(); D && (GetAnimationAction() == TEXT("Bow") || GetAnimationAction() == TEXT("Talk")))
        if (const UAnimSequence* Clip = D->FindAction(GetAnimationAction()); Clip && (GetActionTime() >= Clip->GetPlayLength() - .05f || HasMovementIntent()))
            StopGesture();
    if (IsReady() && Moves)
        switch (Bout)
        {
        case EBout::Home: AdvanceHome(Dt); break;
        case EBout::Talking: if (AWandererCharacter* P = Opponent.Get()) FaceToward(P->GetActorLocation(), Dt); Drive(FVector2D::ZeroVector, 0); break;
        case EBout::Ready: AdvanceReady(Dt); break;
        case EBout::Fighting: AdvanceFight(Dt); break;
        case EBout::Over: AdvanceOver(Dt); break;
        case EBout::Return: AdvanceReturn(Dt); break;
        }
    Super::Tick(Dt);
}

void ASwordTrainer::AdvanceHome(float Dt)
{
    Drive(FVector2D::ZeroVector, 0);
    // She turns to watch the player when they come close, and back to the lane when they leave.
    APawn* Player = GetWorld()->GetFirstPlayerController() ? GetWorld()->GetFirstPlayerController()->GetPawn() : nullptr;
    const bool bNear = Player && FVector::Dist2D(Player->GetActorLocation(), GetActorLocation()) < 800.f;
    const float Want = bNear ? float((Player->GetActorLocation() - GetActorLocation()).Rotation().Yaw) : HomeYaw;
    if (!Moves->IsBusy() && GetCharacterMovement()->IsMovingOnGround())
        SetActorRotation(FRotator(0, FMath::FixedTurn(float(GetActorRotation().Yaw), Want, 120.f * Dt), 0));
    if (Moves->IsArmed() && !Moves->IsBusy()) Press(TEXT("weapon"));
}

void ASwordTrainer::AdvanceReady(float Dt)
{
    AWandererCharacter* P = Opponent.Get();
    if (!P) { EndBout(TEXT("")); return; }
    FaceToward(P->GetActorLocation(), Dt);
    const float D = FVector::Dist2D(P->GetActorLocation(), GetActorLocation());
    // Sword out, then a step back to a fair distance, guard up.
    if (!Moves->IsArmed() && !Moves->IsBusy()) Press(TEXT("weapon"));
    Hold(TEXT("guard"), true);
    Drive(FVector2D(0.f, D < 380.f ? -1.f : D > 520.f ? .6f : 0.f), 0);
    if (BoutTime > 1.6f && BoutTime - Dt <= 1.6f) Say(TEXT("Ready..."), 1.f);
    if (BoutTime > 2.6f)
    {
        Bout = EBout::Fighting; BoutTime = 0.f; Cooldown = .8f;
        Say(TEXT("Begin!"), 1.2f);
        if (AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(this)) FX->Play(TEXT("charge_ready"), GetActorLocation(), .7f, .02f);
        SetIntent(TEXT("circle"));
    }
}

void ASwordTrainer::AdvanceOver(float Dt)
{
    Drive(FVector2D::ZeroVector, 0);
    Hold(TEXT("guard"), false); Hold(TEXT("attack"), false);
    if (AWandererCharacter* P = Opponent.Get()) if (!Moves->IsDown()) FaceToward(P->GetActorLocation(), Dt);
    if (!Moves->IsDown() && Moves->IsArmed() && !Moves->IsBusy() && BoutTime > 1.8f) Press(TEXT("weapon"));
    if (BoutTime > 2.2f && BoutTime - Dt <= 2.2f && !Moves->IsDown() && GetDefinition() && GetDefinition()->FindAction(TEXT("Bow"))) PlayGesture(TEXT("Bow"));
    if (BoutTime > 5.f) { Bout = EBout::Return; BoutTime = 0.f; SetIntent(TEXT("return")); Restore(this); if (AWandererCharacter* P = Opponent.Get()) Restore(P); }
}

void ASwordTrainer::AdvanceReturn(float Dt)
{
    ReleaseAll();
    if (Moves->IsArmed() && !Moves->IsBusy()) Press(TEXT("weapon"));
    const float D = FVector::Dist2D(Home, GetActorLocation());
    if (D > 60.f && BoutTime < 12.f) { FaceToward(Home, Dt); Drive(FVector2D(0.f, 1.f), 0); return; }
    Drive(FVector2D::ZeroVector, 0);
    Bout = EBout::Home; SetIntent(TEXT("home"));
}

void ASwordTrainer::AdvanceFight(float Dt)
{
    AWandererCharacter* P = Opponent.Get();
    UBotwMoveSet* Theirs = P ? P->GetMoves() : nullptr;
    if (!P || !Theirs || P->GetSkate()->IsRiding() || P->OnVehicle()) { EndBout(TEXT("Kaede: \"Another time, then.\"")); return; }
    if (FVector::Dist2D(P->GetActorLocation(), Home) > LeaveReach) { EndBout(TEXT("Kaede: \"Running is a lesson too.\"")); return; }
    // Someone is down at no health: the bout is over.
    const float Mine = GetSword() ? GetSword()->GetHealth() : 1.f, Their = P->GetSword() ? P->GetSword()->GetHealth() : 1.f;
    if (Mine <= 0.f || Their <= 0.f)
    {
        ReleaseAll();
        Bout = EBout::Over; BoutTime = 0.f; SetIntent(TEXT("over"));
        if (Their <= 0.f) { ++Wins; Say(Level == 2 ? TEXT("Kaede: \"Again. Watch my shoulders, not my blade.\"") : TEXT("Kaede: \"Up you get. Guard, then strike.\""), 4.f); }
        else { ++Losses; Say(Level == 2 ? TEXT("Kaede: \"...Well struck. You've nothing left to learn from me.\"") : TEXT("Kaede: \"Well struck! Try a harder level.\""), 4.f); }
        UE_LOG(LogTemp, Display, TEXT("SWORD TRAINER bout over: %s won at level %s"), Their <= 0.f ? TEXT("Kaede") : TEXT("the player"), GetStyle().Name);
        return;
    }
    const FTrainerStyle& S = GetStyle();
    const FVector Here = GetActorLocation(), There = P->GetActorLocation();
    const float Distance = FVector::Dist2D(Here, There);
    FaceToward(There, Dt);
    Cooldown = FMath::Max(0.f, Cooldown - Dt);
    PressGap = FMath::Max(0.f, PressGap - Dt);
    // The flurry rush after her perfect dodge: blow after blow.
    if (Moves->InFlurry())
    {
        SetIntent(TEXT("flurry")); Hold(TEXT("guard"), false); Drive(FVector2D::ZeroVector, 1);
        if (PressGap <= 0.f) { Press(TEXT("attack")); Press(TEXT("attack_release")); PressGap = .1f; }
        return;
    }
    if (Moves->IsDown()) { ReleaseAll(); SetIntent(TEXT("down")); return; }
    // The player is down: she steps back and waits for them to stand.
    if (Theirs->IsDown())
    {
        ReleaseAll(); SetIntent(TEXT("wait"));
        Hold(TEXT("guard"), true);
        Drive(FVector2D(0.f, Distance < 400.f ? -1.f : 0.f), 0);
        Cooldown = FMath::Max(Cooldown, .8f);
        return;
    }
    if (Defend(Dt, Distance)) return;
    if (!Forced.IsEmpty() && Cooldown <= 0.f && !Intent.StartsWith(TEXT("attack"))) Open(Distance);
    if (Intent.StartsWith(TEXT("attack")) && Press_Attack(Dt, Distance)) return;
    // Circling at a fair distance, guard up (strafing on the lock-on), waiting for an opening.
    SetIntent(TEXT("circle"));
    StrafeSwitch -= Dt;
    if (StrafeSwitch <= 0.f) { StrafeSign = Dice.FRand() < .5f ? -1.f : 1.f; StrafeSwitch = Dice.FRandRange(1.2f, 3.2f); }
    const float Want = Level == 0 ? 340.f : 300.f;
    const float Radial = Distance > Want + 50.f ? 1.f : Distance < Want - 60.f ? -1.f : 0.f;
    // The player winding up a charged spin: she backs off (or, at the top level, cuts in before it is ready).
    if (Theirs->IsCharging() && Level > 0)
    {
        if (Level == 2 && Distance < 260.f && Cooldown <= 0.f && !Theirs->IsFullyCharged()) { Forced = TEXT("combo"); Open(Distance); return; }
        Hold(TEXT("guard"), true); Drive(FVector2D(StrafeSign * .5f, -1.f), 1); SetIntent(TEXT("evade charge"));
        return;
    }
    // Her guard is up for a share of the time (the level's), down for the rest: then she steps in or out, facing.
    GuardSwitch -= Dt;
    if (GuardSwitch <= 0.f) { bGuardUp = Dice.FRand() < S.GuardUp; GuardSwitch = Dice.FRandRange(.8f, 2.2f); }
    Hold(TEXT("guard"), bGuardUp);
    if (bGuardUp) Drive(FVector2D(StrafeSign * .8f, Radial), S.Strafe > .5f && Distance > Want + 120.f ? 1 : 0);
    else
    {
        Drive(FVector2D(0.f, Radial), 0);
        if (!Moves->IsBusy() && Radial == 0.f)
            SetActorRotation(FRotator(0, FMath::FixedTurn(float(GetActorRotation().Yaw), float((There - Here).Rotation().Yaw), 360.f * Dt), 0));
    }
    if (Cooldown <= 0.f && !Moves->IsBusy() && Dice.FRand() < S.Aggression * Dt) Open(Distance);
}

bool ASwordTrainer::Defend(float Dt, float Distance)
{
    AWandererCharacter* P = Opponent.Get();
    UBotwMoveSet* Theirs = P ? P->GetMoves() : nullptr;
    if (!Theirs) return false;
    const FTrainerStyle& S = GetStyle();
    // The blow she can still answer: the playing blow's next window (a charged spin, a dash or jump attack wind up
    // first), or in a combo the next cut, which can come from the cut's input point (the cuts strike from their first
    // frame, so the one swinging is already decided: only a raised guard meets it).
    const FName Action = Theirs->GetActionName();
    const bool bBlow = Theirs->IsAttacking() && !Theirs->IsCharging();
    const float Own = bBlow ? Theirs->NextBlowIn() : -1.f, Next = bBlow ? Theirs->NextCutIn() : -1.f;
    const float In = Own > 0.f ? Own : Next;
    const FName Key = In < 0.f ? NAME_None : FName(*(Action.ToString() + (Own > 0.f ? TEXT("") : TEXT(">"))));
    if (Key != SeenAction) { SeenAction = Key; SeenFor = 0.f; bAnswered = false; Answer.Reset(); }
    if (Key.IsNone())
    {
        if (Intent == TEXT("parry") || Intent == TEXT("dodge")) SetIntent(TEXT("circle"));
        return false;
    }
    SeenFor += Dt;
    if (SeenFor < S.Reaction || Distance > 330.f) return Answer.EndsWith(TEXT("!"));
    if (!bAnswered)
    {
        bAnswered = true;
        Counts.FindOrAdd(TEXT("blows_seen"))++;
        if (!ForcedDefence.IsEmpty()) { Answer = ForcedDefence; ForcedDefence.Reset(); }
        else
        {
            const float R = Dice.FRand();
            Answer = R < S.Parry ? TEXT("parry") : R < S.Parry + S.Dodge ? (Dice.FRand() < S.PerfectDodge ? TEXT("perfect") : TEXT("dodge"))
                : R < S.Parry + S.Dodge + S.Guard ? TEXT("guard") : TEXT("take");
        }
        // In the middle of her own blow she can only take it.
        if (Answer != TEXT("take") && (Moves->IsAttacking() || Moves->IsBusy())) Answer = TEXT("take");
        Counts.FindOrAdd(TEXT("answer_") + Answer)++;
    }
    if (Answer == TEXT("take")) return false;
    CombosLeft = 0; Hold(TEXT("attack"), false);
    if (Intent.StartsWith(TEXT("attack"))) SetIntent(TEXT("circle"));
    if (Answer == TEXT("guard"))
    {
        Hold(TEXT("guard"), true); Drive(FVector2D::ZeroVector, 0);
        return true;
    }
    if (Answer.StartsWith(TEXT("parry")))
    {
        SetIntent(TEXT("parry")); Hold(TEXT("guard"), true); Drive(FVector2D::ZeroVector, 0);
        // The parry's window opens a moment into its clip: pressed so that it is open when the blow can land.
        const FBotwMove* Parry = Moves->Find(Moves->HasShield() ? FName(TEXT("Parry")) : FName(TEXT("SwordParry")));
        const float Opens = Parry && Parry->Guard.Num() ? (Parry->Guard[0].X - Parry->Start) / Parry->Rate : .05f;
        // Only once the guard is up (a press without it would be a jump).
        if (Answer == TEXT("parry") && In <= Opens + .05f && Moves->IsGuarding() && !Moves->IsBusy()) { Press(TEXT("jump")); Answer = TEXT("parry!"); }
        return true;
    }
    // A hop: to the side (or the backflip), early enough to clear the blow, or just as it can come for a perfect dodge.
    SetIntent(TEXT("dodge"));
    if (Answer == TEXT("dodge") || Answer == TEXT("perfect"))
    {
        if (In <= (Answer == TEXT("perfect") ? .08f : .3f))
        {
            Hold(TEXT("guard"), true);   // locked on, so the stick's side is her side
            const float Side = Dice.FRand() < .5f ? -1.f : 1.f;
            Drive(Dice.FRand() < .3f ? FVector2D(0.f, -1.f) : FVector2D(Side, 0.f), 1);
            Press(TEXT("dodge"));
            Answer += TEXT("!");
        }
        return true;
    }
    return Moves->IsHopping();
}

void ASwordTrainer::Open(float Distance)
{
    const FTrainerStyle& S = GetStyle();
    FString Pick = Forced;
    Forced.Reset();
    if (Pick.IsEmpty())
    {
        // Shares of her openings, by what the distance allows; the rest is a combo.
        struct FOption { const TCHAR* Name; float Share; };
        TArray<FOption> Options = { { TEXT("charge"), S.Charge }, { TEXT("jump"), S.JumpCut }, { TEXT("double"), S.DoubleJump }, { TEXT("feint"), S.Feint } };
        if (Distance > 380.f) Options.Add({ TEXT("dash"), S.DashCut * 2.f });
        float R = Dice.FRand();
        for (const FOption& O : Options) { if (R < O.Share) { Pick = O.Name; break; } R -= O.Share; }
        if (Pick.IsEmpty()) Pick = TEXT("combo");
    }
    CombosLeft = Pick == TEXT("combo") ? Dice.RandRange(1, S.MaxCombo) : 0;
    HoldFor = 0.f; bAirStep = false;
    SetIntent(TEXT("attack ") + Pick);
    Counts.FindOrAdd(TEXT("open_") + Pick)++;
}

bool ASwordTrainer::Press_Attack(float Dt, float Distance)
{
    const FTrainerStyle& S = GetStyle();
    const FString Kind = Intent.Mid(7);
    auto Done = [&]()
    {
        Hold(TEXT("attack"), false);
        Cooldown = S.Recovery + Dice.FRandRange(0.f, .6f);
        SetIntent(TEXT("recover"));
        return false;
    };
    if (IntentTime > 4.5f) return Done();
    const UWandererSwordComponent* Sword = GetSword();
    (void)Sword;
    if (Kind == TEXT("combo") || Kind == TEXT("charge"))
    {
        // Close in (guard down, running), then cut; the move set homes the cut the last steps.
        if (Distance > 175.f && !Moves->IsAttacking() && !bAirStep)
        {
            Hold(TEXT("guard"), false); Drive(FVector2D(0.f, 1.f), 1);
            return true;
        }
        Drive(FVector2D::ZeroVector, 1);
        bAirStep = true;   // in range: the attack has begun
        if (Kind == TEXT("charge"))
        {
            // Held through the first cut into the charge, released when full (Gentle lets go early).
            if (!bAttackDown && HoldFor == 0.f) { Hold(TEXT("attack"), true); }
            HoldFor += Dt;
            const float Full = Moves->GetParam(TEXT("FullCharge"), .9f) + Moves->GetParam(TEXT("ChargeHold"), .35f) + .15f;
            if (bAttackDown && (HoldFor > (Level == 0 ? Full * .7f : Full) || Moves->IsFullyCharged())) Hold(TEXT("attack"), false);
            if (!bAttackDown && HoldFor > .3f && !Moves->IsAttacking() && !Moves->IsCharging()) return Done();
            return true;
        }
        // Each cut takes the next press from its input point; pressing every few tenths keeps the combo going.
        if (CombosLeft > 0 && PressGap <= 0.f)
        {
            Press(TEXT("attack")); Press(TEXT("attack_release"));
            --CombosLeft; PressGap = Level == 0 ? .55f : .32f;
            return true;
        }
        if (CombosLeft <= 0 && !Moves->IsAttacking() && PressGap <= 0.f) return Done();
        return true;
    }
    if (Kind == TEXT("dash"))
    {
        // Sprint in, and the press becomes the dash attack.
        Hold(TEXT("guard"), false);
        if (!bAirStep)
        {
            Drive(FVector2D(0.f, 1.f), 2);
            if (GetStamina().Sprinting && Distance < 330.f) { Press(TEXT("attack")); Press(TEXT("attack_release")); bAirStep = true; }
            return true;
        }
        Drive(FVector2D::ZeroVector, 1);
        return Moves->IsAttacking() || IntentTime < .3f ? true : Done();
    }
    if (Kind == TEXT("jump") || Kind == TEXT("double"))
    {
        Hold(TEXT("guard"), false);
        const bool bDouble = Kind == TEXT("double");
        const float Launch = bDouble ? 330.f : 250.f;
        if (!bAirStep)
        {
            if (Distance > Launch) { Drive(FVector2D(0.f, 1.f), 1); return true; }
            Drive(FVector2D(0.f, 1.f), 1);
            Press(TEXT("jump")); bAirStep = true; HoldFor = 0.f;
            return true;
        }
        HoldFor += Dt;
        Drive(FVector2D(0.f, Distance > 130.f ? 1.f : 0.f), 1);
        if (bDouble && HoldFor > .3f && HoldFor - Dt <= .3f) Press(TEXT("jump"));   // the double jump, toward the player
        const float Cut = bDouble ? .62f : .2f;
        if (HoldFor > Cut && HoldFor - Dt <= Cut) { Press(TEXT("attack")); Press(TEXT("attack_release")); }
        if (HoldFor > Cut + .2f && GetCharacterMovement()->IsMovingOnGround() && !Moves->IsBusy()) return Done();
        return true;
    }
    if (Kind == TEXT("feint"))
    {
        // Rush in as if to cut, then backflip out of reach.
        Hold(TEXT("guard"), Distance < 230.f);
        if (!bAirStep)
        {
            if (Distance > 210.f) { Drive(FVector2D(0.f, 1.f), 1); return true; }
            Drive(FVector2D(0.f, -1.f), 1); Press(TEXT("dodge")); bAirStep = true;
            return true;
        }
        Drive(FVector2D::ZeroVector, 0);
        return Moves->IsHopping() || IntentTime < .4f ? true : Done();
    }
    return Done();
}

FString ASwordTrainer::Describe() const
{
    TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
    O->SetStringField(TEXT("bout"), BoutName());
    O->SetStringField(TEXT("level"), GetStyle().Name);
    O->SetStringField(TEXT("intent"), Intent);
    O->SetBoolField(TEXT("own_body"), HasOwnBody());
    O->SetBoolField(TEXT("shield"), bOwnShield);
    O->SetNumberField(TEXT("health"), GetSword() ? GetSword()->GetHealth() : -1.f);
    O->SetNumberField(TEXT("wins"), Wins);
    O->SetNumberField(TEXT("losses"), Losses);
    O->SetNumberField(TEXT("bout_time"), BoutTime);
    if (const AWandererCharacter* P = Opponent.Get())
    {
        O->SetNumberField(TEXT("distance"), FVector::Dist2D(P->GetActorLocation(), GetActorLocation()));
        O->SetNumberField(TEXT("player_health"), P->GetSword() ? P->GetSword()->GetHealth() : -1.f);
    }
    O->SetStringField(TEXT("action"), GetAnimationAction().ToString());
    O->SetStringField(TEXT("moves"), Moves ? Moves->Describe() : FString());
    TSharedRef<FJsonObject> C = MakeShared<FJsonObject>();
    for (const auto& Pair : Counts) C->SetNumberField(Pair.Key, Pair.Value);
    O->SetObjectField(TEXT("counts"), C);
    const TArray<double> Where = { GetActorLocation().X, GetActorLocation().Y, GetActorLocation().Z };
    TArray<TSharedPtr<FJsonValue>> L; for (double V : Where) L.Add(MakeShared<FJsonValueNumber>(V));
    O->SetArrayField(TEXT("location"), L);
    FString Out;
    FJsonSerializer::Serialize(O, TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out));
    return Out;
}

#include "SwordTrainer.h"
#include "RoninProjectile.h"
#include "JapanCombat.h"
#include "AtelierData.h"
#include "AdventureMoveSet.h"
#include "JapanGameMode.h"
#include "JapanPreferences.h"
#include "JapanWorld.h"
#include "WandererDefinition.h"
#include "WandererSword.h"
#include "JapanEncounters.h"
#include "YorimichiCombatFX.h"
#include "SkateComponent.h"
#include "SailboatComponent.h"
#include "AIController.h"
#include "GameFramework/PlayerController.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/Texture.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Materials/MaterialInstanceDynamic.h"
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
    const TCHAR* StandInDefinition = TEXT("/Game/CairoAdventure/DA_CairoAdventure.DA_CairoAdventure");
    bool HasOwnBody() { return FPackageName::DoesPackageExist(FPackageName::ObjectPathToPackageName(FString(OwnDefinition))); }

    TSharedPtr<FJsonObject> Record(const TCHAR* Relative)
    {
        return AtelierReadJson(AtelierDataPath(Relative));
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
    // Distinct OpenGothic / BotW combat personalities for the three Kasa Ronin roles (Scout skirmisher, Guard counter-vanguard, Captain warlord).
    const FTrainerStyle RoninStyles[3] = {
        //  name          react parry dodge guard perfect aggr  combo recov charge dash  jump  double feint damage strafe guard up
        { TEXT("Scout"),    .18f, .22f, .40f, .22f,  .45f,  1.05f, 3,    .36f,  .08f,  .28f, .22f, .10f,  .14f, .80f,  1.f,   .58f },
        { TEXT("Vanguard"), .15f, .42f, .20f, .30f,  .52f,   .92f, 3,    .40f,  .18f,  .14f, .12f, .06f,  .06f, .90f,   .65f, .84f },
        { TEXT("Warlord"),  .11f, .48f, .28f, .18f,  .78f,  1.35f, 4,    .24f,  .24f,  .18f, .16f, .16f,  .10f, 1.f,   1.f,   .76f },
    };
    // The training ground: the lawn beside the tea house, between the lane and the trees (8 m clear of every bed,
    // bush, tree and building), in the hamlet's authored metres (before `village_point`'s offset), and the way she
    // faces when she waits there (toward the tea house and the lane).
    const FVector2D TrainingGround(86.5f, -6.f);
    constexpr float GroundYaw = 120.f;
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
    UAdventureMoveSet* Set = NewObject<UAdventureMoveSet>(this, TEXT("TrainerMoves"));
    if (Set->Initialize(this, Record(bOwn ? TEXT("sword-trainer/adventure.json") : TEXT("cairo/adventure.json")))) Moves = Set;
    else UE_LOG(LogTemp, Error, TEXT("Sword trainer: no move set (build unreal.cairo_adventure or unreal.sword_trainer)"));
    if (Moves) Moves->SetShield(false);
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
    const AWandererCharacter* Viewer = Cast<AWandererCharacter>(WorldContext);
    if (!Viewer && World->GetFirstPlayerController())
        Viewer = Cast<AWandererCharacter>(World->GetFirstPlayerController()->GetPawn());
    // Prefer an actively fighting opponent (or the player's current lock-on target), otherwise the peaceful village trainer.
    if (Viewer && Viewer->GetMoves())
        if (ASwordTrainer* Locked = Cast<ASwordTrainer>(Viewer->GetMoves()->GetTarget()))
            return Locked;
    ASwordTrainer* BestActive = nullptr;
    float BestDist = 3500.f;
    ASwordTrainer* VillageTrainer = nullptr;
    for (TActorIterator<ASwordTrainer> It(World); It; ++It)
    {
        if (!It->IsHostileRonin()) VillageTrainer = *It;
        const float D = Viewer ? FVector::Dist2D(Viewer->GetActorLocation(), It->GetActorLocation()) : 0.f;
        if ((It->Bout == EBout::Ready || It->Bout == EBout::Fighting || It->CalloutTime > 0.f) && D < BestDist)
        {
            BestDist = D;
            BestActive = *It;
        }
    }
    if (BestActive) return BestActive;
    if (VillageTrainer) return VillageTrainer;
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
    return !bHostileRonin && Player && Player != this && IsReady() && Bout == EBout::Home && !Menu.IsValid() &&
        FVector::Dist2D(Player->GetActorLocation(), GetActorLocation()) < TalkReach &&
        FMath::Abs(Player->GetActorLocation().Z - GetActorLocation().Z) < 200.f;
}

bool ASwordTrainer::IsSparringWith(const AActor* Other) const
{
    if (bHostileRonin)
    {
        const AWandererCharacter* Player = Cast<AWandererCharacter>(Other);
        return Player && Player != this && !Player->IsNpc() && !bDefeated && DefeatCooldown <= 0.f && Bout != EBout::Over && Bout != EBout::Return &&
            (!GetSword() || GetSword()->GetHealth() > 0.f);
    }
    // From the stance (so each side's lock-on finds the other) to the end of the bout.
    return Other && Other == Opponent.Get() && (Bout == EBout::Ready || Bout == EBout::Fighting);
}

FString ASwordTrainer::GetDisplayName() const
{
    if (!bHostileRonin) return TEXT("KAEDE");
    switch (RoninRole)
    {
    case 0: return TEXT("KASA RONIN · SCOUT");
    case 1: return TEXT("KASA RONIN · GUARD");
    default: return TEXT("KASA RONIN · CAPTAIN");
    }
}

void ASwordTrainer::SetupRonin(int32 InRole, const FVector& InCampOrigin, const FVector& InMakiwaraTarget)
{
    bHostileRonin = true;
    RoninRole = FMath::Clamp(InRole, 0, 2);
    Level = RoninRole == 2 ? 2 : 1;
    RoleScale = RoninRole == 0 ? .94f : (RoninRole == 1 ? 1.03f : 1.12f);
    CampOrigin = InCampOrigin;
    MakiwaraTarget = InMakiwaraTarget;
    SetActorScale3D(FVector(RoleScale));
    SetActorLocation(GetActorLocation() + FVector(0.f, 0.f, (RoleScale - 1.f) * 84.f), false, nullptr, ETeleportType::TeleportPhysics);
    Home = GetActorLocation();
    HomeYaw = GetActorRotation().Yaw;

    if (USkeletalMeshComponent* Body = GetMesh())
    {
        UMaterialInterface* BodyMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/SwordCamp/Materials/M_RoninBody.M_RoninBody"), nullptr, LOAD_NoWarn | LOAD_Quiet);
        UTexture* CharTex = LoadObject<UTexture>(nullptr, TEXT("/Game/SwordTrainer/Textures/T_tripo_mat_ee5a1a4b.T_tripo_mat_ee5a1a4b"), nullptr, LOAD_NoWarn | LOAD_Quiet);
        if (BodyMat && CharTex)
        {
            UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(BodyMat, this);
            MID->SetTextureParameterValue(TEXT("BaseTex"), CharTex);
            const FLinearColor CoatTint = RoninRole == 0
                ? FLinearColor(.14f, .28f, .62f, 1.f)
                : (RoninRole == 1 ? FLinearColor(.16f, .42f, .24f, 1.f) : FLinearColor(.68f, .10f, .13f, 1.f));
            MID->SetVectorParameterValue(TEXT("CoatTint"), CoatTint);
            Body->SetMaterial(0, MID);
        }
        else
        {
            UE_LOG(LogTemp, Warning, TEXT("Kasa Ronin: missing M_RoninBody or T_tripo_mat_ee5a1a4b; keeping default body material"));
        }
    }

    auto MakeAttachment = [this](const TCHAR* CompName, const TCHAR* AssetPath) -> UStaticMeshComponent*
    {
        UStaticMesh* MeshAsset = LoadObject<UStaticMesh>(nullptr, AssetPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
        if (!MeshAsset) return nullptr;
        UStaticMeshComponent* Comp = NewObject<UStaticMeshComponent>(this, CompName);
        Comp->SetStaticMesh(MeshAsset);
        Comp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Comp->SetCastShadow(true);
        Comp->SetRenderCustomDepth(true);
        Comp->SetCustomDepthStencilValue(1);
        Comp->RegisterComponent();
        Comp->AttachToComponent(GetRootComponent(), FAttachmentTransformRules::KeepRelativeTransform);
        return Comp;
    };

    const TCHAR* HatAsset = RoninRole == 0
        ? TEXT("/Game/SwordCamp/Assets/SM_RoninKasa.SM_RoninKasa")
        : (RoninRole == 1 ? TEXT("/Game/SwordCamp/Assets/SM_GuardJingasa.SM_GuardJingasa")
                          : TEXT("/Game/SwordCamp/Assets/SM_CaptainKabuto.SM_CaptainKabuto"));
    RoninKasa = MakeAttachment(TEXT("RoninKasa"), HatAsset);
    if (RoninRole >= 1)
    {
        RoninMenpo = MakeAttachment(TEXT("RoninMenpo"), TEXT("/Game/SwordCamp/Assets/SM_RoninMenpo.SM_RoninMenpo"));
        RoninDo = MakeAttachment(TEXT("RoninDo"), TEXT("/Game/SwordCamp/Assets/SM_RoninDo.SM_RoninDo"));
        RoninSodeL = MakeAttachment(TEXT("RoninSodeL"), TEXT("/Game/SwordCamp/Assets/SM_RoninSode.SM_RoninSode"));
        RoninSodeR = MakeAttachment(TEXT("RoninSodeR"), TEXT("/Game/SwordCamp/Assets/SM_RoninSode.SM_RoninSode"));
    }
    else
    {
        RoninSubWeapon = MakeAttachment(TEXT("RoninSubWeapon"), TEXT("/Game/SwordCamp/Assets/SM_RoninWakizashi.SM_RoninWakizashi"));
    }
    if (RoninRole == 2)
        RoninSashimono = MakeAttachment(TEXT("RoninSashimono"), TEXT("/Game/SwordCamp/Assets/SM_RoninSashimono.SM_RoninSashimono"));
    RoninWeapon = MakeAttachment(
        TEXT("RoninWeapon"),
        RoninRole == 2
            ? TEXT("/Game/SwordCamp/Assets/SM_RoninNodachi.SM_RoninNodachi")
            : TEXT("/Game/SwordCamp/Assets/SM_RoninKatana.SM_RoninKatana"));

    if (Moves)
        Moves->UseProceduralBlade(RoninRole == 2 ? 104.f : (RoninRole == 1 ? 76.f : 68.f));
    UpdateRoninAttachments();
}

void ASwordTrainer::UpdateRoninAttachments()
{
    if (!bHostileRonin || !GetMesh()) return;
    const USkeletalMeshComponent* Body = GetMesh();
    const FQuat ActorQuat = GetActorQuat();
    const FQuat HeadFlinch = Moves ? Moves->FlinchRotation(3) : FQuat::Identity;
    const FQuat ChestFlinch = Moves ? Moves->FlinchRotation(1) : FQuat::Identity;

    const FName HeadBone = GetSkateBone(TEXT("head"));
    const FName ChestBone = GetSkateBone(TEXT("chest"));
    const FName ArmLBone = GetSkateBone(TEXT("upperarm_L"));
    const FName ArmRBone = GetSkateBone(TEXT("upperarm_R"));

    auto GetAnimatedWorldQuat = [&](FName BoneName, const FQuat& Flinch) -> FQuat
    {
        const USkeletalMesh* SkelAsset = Body->GetSkeletalMeshAsset();
        const int32 BoneIdx = Body->GetBoneIndex(BoneName);
        if (!SkelAsset || BoneIdx == INDEX_NONE) return ActorQuat * Flinch;
        const FReferenceSkeleton& RefSkel = SkelAsset->GetRefSkeleton();
        FTransform RefComp = FTransform::Identity;
        for (int32 Cur = BoneIdx; Cur != INDEX_NONE; Cur = RefSkel.GetParentIndex(Cur))
            RefComp = RefComp * RefSkel.GetRefBonePose()[Cur];
        const FQuat CurComp = Body->GetSocketTransform(BoneName, RTS_Component).GetRotation();
        const FQuat AnimDelta = CurComp * RefComp.GetRotation().Inverse();
        return Body->GetComponentQuat() * AnimDelta;
    };

    const FQuat HeadRot = GetAnimatedWorldQuat(HeadBone, HeadFlinch);
    const FQuat ChestRot = GetAnimatedWorldQuat(ChestBone, ChestFlinch);
    const FVector ScaleVec(RoleScale);

    const FVector HeadPos = Body->GetBoneIndex(HeadBone) != INDEX_NONE ? Body->GetBoneLocation(HeadBone) : GetActorLocation() + FVector(0, 0, 62.f * RoleScale);
    const FVector ChestPos = Body->GetBoneIndex(ChestBone) != INDEX_NONE ? Body->GetBoneLocation(ChestBone) : GetActorLocation() + FVector(0, 0, 26.f * RoleScale);
    const FVector ArmLPos = Body->GetBoneIndex(ArmLBone) != INDEX_NONE ? Body->GetBoneLocation(ArmLBone) : ChestPos + ChestRot.RotateVector(FVector(0, -18.f, 10.f) * RoleScale);
    const FVector ArmRPos = Body->GetBoneIndex(ArmRBone) != INDEX_NONE ? Body->GetBoneLocation(ArmRBone) : ChestPos + ChestRot.RotateVector(FVector(0, 18.f, 10.f) * RoleScale);

    if (RoninKasa)
    {
        RoninKasa->SetWorldScale3D(ScaleVec);
        RoninKasa->SetWorldLocationAndRotation(HeadPos + HeadRot.RotateVector(FVector(-4.0f, 0.f, 24.8f) * RoleScale), HeadRot);
    }
    if (RoninMenpo)
    {
        RoninMenpo->SetWorldScale3D(ScaleVec);
        RoninMenpo->SetWorldLocationAndRotation(HeadPos + HeadRot.RotateVector(FVector(6.5f, 0.f, 9.5f) * RoleScale), HeadRot);
    }
    if (RoninDo)
    {
        RoninDo->SetWorldScale3D(ScaleVec);
        RoninDo->SetWorldLocationAndRotation(ChestPos + ChestRot.RotateVector(FVector(-0.4f, 0.f, -5.0f) * RoleScale), ChestRot);
    }
    if (RoninSodeL)
    {
        RoninSodeL->SetWorldScale3D(ScaleVec);
        RoninSodeL->SetWorldLocationAndRotation(
            ArmLPos + ChestRot.RotateVector(FVector(0.f, -9.5f, -5.5f) * RoleScale),
            ChestRot * FRotator(0.f, -90.f, 0.f).Quaternion() * FRotator(16.f, 0.f, 0.f).Quaternion());
    }
    if (RoninSodeR)
    {
        RoninSodeR->SetWorldScale3D(ScaleVec);
        RoninSodeR->SetWorldLocationAndRotation(
            ArmRPos + ChestRot.RotateVector(FVector(0.f, 9.5f, -5.5f) * RoleScale),
            ChestRot * FRotator(0.f, 90.f, 0.f).Quaternion() * FRotator(16.f, 0.f, 0.f).Quaternion());
    }
    if (RoninSubWeapon)
    {
        RoninSubWeapon->SetWorldScale3D(ScaleVec);
        RoninSubWeapon->SetWorldLocationAndRotation(
            ChestPos + ChestRot.RotateVector(FVector(-4.0f, -20.0f, -22.0f) * RoleScale),
            ChestRot * FRotator(-65.f, -12.f, 0.f).Quaternion());
    }
    if (RoninSashimono)
    {
        RoninSashimono->SetWorldScale3D(ScaleVec);
        RoninSashimono->SetWorldLocationAndRotation(ChestPos + ChestRot.RotateVector(FVector(-17.5f, 0.f, -10.f) * RoleScale), ChestRot);
    }
    if (RoninWeapon && Moves)
    {
        FVector Base, Tip, Major;
        if (Moves->GetBladePose(Base, Tip, Major))
        {
            const FVector BladeDir = (Tip - Base).GetSafeNormal();
            const FVector EdgeDir = Major.IsNearlyZero() ? GetActorForwardVector() : Major;
            const FQuat WeaponRot = FRotationMatrix::MakeFromZX(BladeDir, EdgeDir).ToQuat();
            RoninWeapon->SetWorldScale3D(ScaleVec);
            RoninWeapon->SetWorldLocationAndRotation(Base, WeaponRot);
        }
    }
}

void ASwordTrainer::AlertCamp(AWandererCharacter* Player)
{
    if (!bHostileRonin || !Player || bDefeated || DefeatCooldown > 0.f || Bout == EBout::Fighting || Bout == EBout::Over) return;
    for (TActorIterator<ASwordTrainer> It(GetWorld()); It; ++It)
    {
        ASwordTrainer* Member = *It;
        if (!Member || !Member->IsHostileRonin() || Member->bDefeated || Member->DefeatCooldown > 0.f ||
            Member->Bout == EBout::Fighting || Member->Bout == EBout::Over) continue;
        if (FVector::Dist2D(Member->CampOrigin, CampOrigin) > 2500.f) continue;
        Member->Opponent = Player;
        Member->ReleaseAll();
        if (Member->Moves) Member->Moves->SetCombatTarget(Player);
        if (Member->Moves && !Member->Moves->IsArmed() && !Member->Moves->IsBusy()) Member->Press(TEXT("weapon"));
        if (UJapanEncounters* Encounters = GetWorld()->GetSubsystem<UJapanEncounters>())
            Encounters->Engage(Member, 3200.f, 100);
        Member->Bout = EBout::Fighting;
        Member->BoutTime = 0.f;
        Member->Cooldown = Member->RoninRole == 2 ? .35f : .65f;
        Member->SetIntent(TEXT("circle"));
        if (Member == this)
        {
            const TCHAR* Line = RoninRole == 2
                ? TEXT("Kasa Ronin · Captain: \"To arms! Hold the coastal bluff!\"")
                : (RoninRole == 1 ? TEXT("Kasa Ronin · Guard: \"An intruder! Draw your steel!\"")
                                  : TEXT("Kasa Ronin · Scout: \"Blades out! Don't let them pass!\""));
            Member->Say(Line, 2.8f);
        }
    }
}

void ASwordTrainer::SpawnRoninCamp(AJapanWorld* World)
{
    const TCHAR* Line = FCommandLine::Get();
    if (!World || !World->bLoaded || FParse::Param(Line, TEXT("noronincamp"))) return;
    if (AJapanGameMode::IsScriptedSession() && !FParse::Param(Line, TEXT("ronincamp"))) return;
    UWorld* U = World->GetWorld();
    if (!U) return;

    // Site A: Coastal Bluff Overlook (-54.0, -94.0) facing the main coastal road bend (s=243 at (-55.0, -71.0)).
    const FVector2D CampCenter(-54.0, -94.0);
    const FVector2D RoadPoint(-55.0, -71.0);
    const FVector2D Fwd2D = (RoadPoint - CampCenter).GetSafeNormal();
    const FVector2D Left2D(-Fwd2D.Y, Fwd2D.X);
    const float BaseYawBlender = FMath::RadiansToDegrees(FMath::Atan2(Fwd2D.Y, Fwd2D.X));
    const FVector CampCenterUE = AJapanWorld::ToUE(CampCenter.X, CampCenter.Y, 8.1);

    // Clear instanced trees, bushes and rocks within 15.5 m of the camp center so the arena and sightlines to the road are open.
    TArray<UInstancedStaticMeshComponent*> InstancedComps;
    World->GetComponents<UInstancedStaticMeshComponent>(InstancedComps);
    for (UInstancedStaticMeshComponent* Comp : InstancedComps)
    {
        if (!Comp) continue;
        for (int32 Idx = Comp->GetInstanceCount() - 1; Idx >= 0; --Idx)
        {
            FTransform InstXf;
            if (!Comp->GetInstanceTransform(Idx, InstXf, true)) continue;
            const FVector Loc = InstXf.GetLocation();
            if (FVector::DistSquared2D(Loc, CampCenterUE) < FMath::Square(1550.f))
                Comp->RemoveInstance(Idx);
        }
    }

    auto GroundAt = [&](double Bx, double By, float ExtraZ = 0.f) -> FVector
    {
        const FVector Probe = AJapanWorld::ToUE(Bx, By, 28.0);
        FHitResult Hit;
        FCollisionQueryParams Params(SCENE_QUERY_STAT(RoninCampSpawn), false);
        if (U->LineTraceSingleByChannel(Hit, Probe, Probe - FVector(0, 0, 4000.f), ECC_Visibility, Params))
            return Hit.ImpactPoint + FVector(0, 0, ExtraZ);
        return AJapanWorld::ToUE(Bx, By, 8.1) + FVector(0, 0, ExtraZ);
    };

    auto SpawnProp = [&](const TCHAR* AssetPath, double ForwardM, double LeftM, float LocalYawDeg) -> FVector
    {
        const FVector2D Pos = CampCenter + Fwd2D * ForwardM + Left2D * LeftM;
        const FVector Loc = GroundAt(Pos.X, Pos.Y, -2.f);
        UStaticMesh* MeshAsset = LoadObject<UStaticMesh>(nullptr, AssetPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
        if (!MeshAsset) return Loc;
        FActorSpawnParameters Spawn;
        Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
        if (AStaticMeshActor* Prop = U->SpawnActor<AStaticMeshActor>(Loc, FRotator(0, -(BaseYawBlender + LocalYawDeg), 0), Spawn))
        {
            Prop->SetMobility(EComponentMobility::Stationary);
            if (UStaticMeshComponent* Comp = Prop->GetStaticMeshComponent())
            {
                Comp->SetStaticMesh(MeshAsset);
                Comp->SetCollisionProfileName(TEXT("BlockAll"));
                Comp->SetCastShadow(true);
            }
        }
        return Loc;
    };

    const FVector FireLoc = SpawnProp(TEXT("/Game/SwordCamp/Assets/SM_CampFirePit.SM_CampFirePit"), 0.0, 0.0, 0.f);
    SpawnProp(TEXT("/Game/SwordCamp/Assets/SM_CampJinmaku.SM_CampJinmaku"), -6.2, 0.0, 90.f);
    const FVector RackLoc = SpawnProp(TEXT("/Game/SwordCamp/Assets/SM_CampWeaponRack.SM_CampWeaponRack"), -2.4, 4.4, -35.f);
    SpawnProp(TEXT("/Game/SwordCamp/Assets/SM_CampBales.SM_CampBales"), -2.6, -4.4, 30.f);

    struct FRoninSpawn { int32 Role; double ForwardM; double LeftM; float YawOffset; };
    const FRoninSpawn Squad[3] = {
        { 0,  5.8,  1.6,   0.f },   // Lookout Scout watching the road approach
        { 1, -1.2,  3.2, -55.f },   // Guard practicing before the Makiwara post
        { 2, -2.8, -1.2,  15.f },   // Camp Captain by the fire and Jinmaku curtain
    };
    for (const FRoninSpawn& S : Squad)
    {
        const FVector2D Pos = CampCenter + Fwd2D * S.ForwardM + Left2D * S.LeftM;
        const FVector Where = GroundAt(Pos.X, Pos.Y, 90.f);
        FActorSpawnParameters Spawn;
        Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
        if (ASwordTrainer* Ronin = U->SpawnActor<ASwordTrainer>(Where, FRotator(0, -(BaseYawBlender + S.YawOffset), 0), Spawn))
        {
            Ronin->EnterWorld(World);
            Ronin->SetupRonin(S.Role, FireLoc, RackLoc);
        }
    }
    UE_LOG(LogTemp, Display, TEXT("Kasa Ronin mini-camp spawned at %s (3 Kasa Ronin + 4 procedural camp props)"), *FireLoc.ToString());
}

float ASwordTrainer::SparringDamage(int32 Power) const
{
    return Super::SparringDamage(Power) * GetStyle().Damage;
}

const FTrainerStyle& ASwordTrainer::GetStyle() const
{
    return bHostileRonin ? RoninStyles[FMath::Clamp(RoninRole, 0, 2)] : Styles[FMath::Clamp(Level, 0, 2)];
}

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
    TWeakObjectPtr<ASwordTrainer> Self(this);
    const bool bCanSpar = Player->GetMoves() != nullptr;
    auto Title = [](const TCHAR* Text, int32 Size) { return SNew(STextBlock).Text(FText::FromString(Text)).Font(FCoreStyle::GetDefaultFontStyle("Bold", Size)).ColorAndOpacity(FLinearColor::White); };
    TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 6)[Title(TEXT("Kaede"), 24)];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 16)[SNew(STextBlock).Text(FText::FromString(TEXT("Sword teacher of Momiji Hamlet"))).ColorAndOpacity(FLinearColor(.95f, .72f, .5f))];
    Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 16)[SNew(STextBlock).AutoWrapText(true).ColorAndOpacity(FLinearColor::White)
        .Text(FText::FromString(bCanSpar
            ? TEXT("\"Nothing in these woods waits for you to be ready. Let's see your blade. Pick how hard I push; a bout ends when one of us is down.\"")
            : TEXT("\"Your feet aren't ready for my lessons yet. Come back when you're ready to train.\"")))];
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
        TWeakObjectPtr<AWandererCharacter> Who(Player);
        Rows->AddSlot().AutoHeight().Padding(0, 0, 0, 8)[SNew(SButton).HAlign(HAlign_Center)
            .Text(FText::FromString(TEXT("Begin the bout")))
            .OnClicked_Lambda([Self, Who]
            {
                if (Self.IsValid() && Who.IsValid())
                {
                    const int32 L = Self->MenuLevel;
                    Self->CloseMenu();
                    Self->StartBout(Who.Get(), L, false, false);
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
    if (bShield || bPlayerShield || !Player || !Player->GetMoves() || !Moves || Bout == EBout::Fighting) return false;
    CloseMenu();
    Opponent = Player;
    Level = FMath::Clamp(NewLevel, 0, 2);
    bOwnShield = false;
    Moves->SetShield(bOwnShield);

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
    if (Moves) Moves->SetCombatTarget(nullptr);
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
    const float TargetYaw = float(To.Rotation().Yaw);
    Controller->SetControlRotation(FRotator(0, TargetYaw, 0));
    // OpenGothic Npc::turnToEnemy: hostile Ronin pivot toward the target when not knocked down or committed to a swing.
    if (bHostileRonin && (!Moves || (!Moves->IsDown() && !Moves->IsAttacking())))
        SetActorRotation(FRotator(0, FMath::FixedTurn(float(GetActorRotation().Yaw), TargetYaw, 720.f * Dt), 0));
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
    UpdateRoninAttachments();
}

void ASwordTrainer::AdvanceHome(float Dt)
{
    Drive(FVector2D::ZeroVector, 0);
    if (Moves) Moves->SetCombatTarget(nullptr);
    if (bHostileRonin)
    {
        DefeatCooldown = FMath::Max(0.f, DefeatCooldown - Dt);
        if (bDefeated || DefeatCooldown > 0.f) return;
        AWandererCharacter* Player = Cast<AWandererCharacter>(GetWorld()->GetFirstPlayerController() ? GetWorld()->GetFirstPlayerController()->GetPawn() : nullptr);
        if (GetHealthFraction() < .999f && Player)
        {
            AlertCamp(Player);
            return;
        }
        if (Player && !Player->IsNpc() && Player->IsReady() && !Player->OnVehicle() && !Player->IsZeppelinPassenger() &&
            (!Player->GetSkate() || !Player->GetSkate()->IsRiding()) && (!Player->GetSword() || !Player->GetSword()->IsDown()))
        {
            const bool bSneakstriking = Player->GetMoves() && Player->GetMoves()->GetActionName() == TEXT("Sneakstrike");
            if (!bSneakstriking)
            {
                const FVector ToPlayer = Player->GetActorLocation() - GetActorLocation();
                if (FMath::Abs(ToPlayer.Z) < 350.f)
                {
                    const float Dist = ToPlayer.Size2D();
                    const float CosAngle = FVector::DotProduct(GetActorForwardVector(), ToPlayer.GetSafeNormal2D());
                    const float BackSense = Player->bIsCrouched ? 190.f : 560.f;
                    if ((Dist < 1400.f && CosAngle > -.2f) || Dist < BackSense)
                    {
                        AlertCamp(Player);
                        return;
                    }
                }
            }
        }
        // Camp idle routines: Guard practices cuts against the Makiwara post; Scout scans the road; Captain watches by the fire.
        if (RoninRole == 1)
        {
            if (!Moves->IsArmed() && !Moves->IsBusy()) Press(TEXT("weapon"));
            PracticeTimer -= Dt;
            if (PracticeTimer <= 0.f && !Moves->IsBusy())
            {
                Press(TEXT("attack")); Press(TEXT("attack_release"));
                PracticeTimer = Dice.FRandRange(2.6f, 4.2f);
            }
        }
        else if (RoninRole == 0)
        {
            const float ScanYaw = HomeYaw + 28.f * FMath::Sin(BoutTime * .85f);
            if (!Moves->IsBusy() && GetCharacterMovement()->IsMovingOnGround())
                SetActorRotation(FRotator(0, FMath::FixedTurn(float(GetActorRotation().Yaw), ScanYaw, 90.f * Dt), 0));
        }
        return;
    }
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
    if (bHostileRonin && Moves) Moves->SetCombatTarget(P);
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
    if (Moves) Moves->SetCombatTarget(nullptr);
    if (bHostileRonin)
    {
        if (UJapanEncounters* Encounters = GetWorld()->GetSubsystem<UJapanEncounters>()) Encounters->End(this);
        if (bDefeated)
        {
            // Defeated Ronin stays out of the fight until the player leaves the camp (> 4200 cm) or after 45 s respite.
            const AWandererCharacter* P = Opponent.Get();
            const bool bPlayerLeft = !P || FVector::Dist2D(P->GetActorLocation(), CampOrigin) > 4200.f;
            if (bPlayerLeft || BoutTime > 45.f)
            {
                bDefeated = false;
                DefeatCooldown = 6.f;
                Bout = EBout::Return; BoutTime = 0.f; SetIntent(TEXT("return")); Restore(this);
            }
            return;
        }
        if (BoutTime > 4.f) { DefeatCooldown = 4.f; Bout = EBout::Return; BoutTime = 0.f; SetIntent(TEXT("return")); Restore(this); }
        return;
    }
    if (AWandererCharacter* P = Opponent.Get()) if (!Moves->IsDown()) FaceToward(P->GetActorLocation(), Dt);
    if (!Moves->IsDown() && Moves->IsArmed() && !Moves->IsBusy() && BoutTime > 1.8f) Press(TEXT("weapon"));
    if (BoutTime > 2.2f && BoutTime - Dt <= 2.2f && !Moves->IsDown() && GetDefinition() && GetDefinition()->FindAction(TEXT("Bow"))) PlayGesture(TEXT("Bow"));
    if (BoutTime > 5.f) { Bout = EBout::Return; BoutTime = 0.f; SetIntent(TEXT("return")); Restore(this); if (AWandererCharacter* P = Opponent.Get()) Restore(P); }
}

void ASwordTrainer::AdvanceReturn(float Dt)
{
    ReleaseAll();
    if (Moves) Moves->SetCombatTarget(nullptr);
    if (Moves->IsArmed() && !Moves->IsBusy()) Press(TEXT("weapon"));
    const float D = FVector::Dist2D(Home, GetActorLocation());
    if (D > 60.f && BoutTime < 12.f) { FaceToward(Home, Dt); Drive(FVector2D(0.f, 1.f), 0); return; }
    Drive(FVector2D::ZeroVector, 0);
    Bout = EBout::Home; SetIntent(TEXT("home"));
}

void ASwordTrainer::AdvanceFight(float Dt)
{
    AWandererCharacter* P = Opponent.Get();
    UAdventureMoveSet* Theirs = P ? P->GetMoves() : nullptr;
    if (!P || !Theirs || (!bHostileRonin && (P->GetSkate()->IsRiding() || P->OnVehicle()))) { EndBout(bHostileRonin ? TEXT("") : TEXT("Kaede: \"Another time, then.\"")); return; }
    if (FVector::Dist2D(P->GetActorLocation(), Home) > (bHostileRonin ? 3800.f : LeaveReach))
    {
        if (bHostileRonin)
        {
            if (UJapanEncounters* Encounters = GetWorld()->GetSubsystem<UJapanEncounters>()) Encounters->End(this);
            if (Moves) Moves->SetCombatTarget(nullptr);
            ReleaseAll(); Bout = EBout::Return; BoutTime = 0.f; SetIntent(TEXT("return")); Restore(this);
            return;
        }
        EndBout(TEXT("Kaede: \"Running is a lesson too.\"")); return;
    }
    // Someone is down at no health: the bout is over.
    const float Mine = GetSword() ? GetSword()->GetHealth() : 1.f, Their = P->GetSword() ? P->GetSword()->GetHealth() : 1.f;
    if (Mine <= 0.f || Their <= 0.f)
    {
        ReleaseAll();
        if (Moves) Moves->SetCombatTarget(nullptr);
        if (UJapanEncounters* Encounters = GetWorld()->GetSubsystem<UJapanEncounters>()) Encounters->End(this);
        Bout = EBout::Over; BoutTime = 0.f; SetIntent(TEXT("over"));
        if (bHostileRonin)
        {
            if (Mine <= 0.f) { bDefeated = true; ++Losses; Say(FString::Printf(TEXT("%s: \"A clean cut...\""), *GetDisplayName()), 3.f); }
            else { ++Wins; Say(FString::Printf(TEXT("%s: \"Stay down, traveler.\""), *GetDisplayName()), 3.f); }
        }
        else
        {
            if (Their <= 0.f) { ++Wins; Say(Level == 2 ? TEXT("Kaede: \"Again. Watch my shoulders, not my blade.\"") : TEXT("Kaede: \"Up you get. Guard, then strike.\""), 4.f); }
            else { ++Losses; Say(Level == 2 ? TEXT("Kaede: \"...Well struck. You've nothing left to learn from me.\"") : TEXT("Kaede: \"Well struck! Try a harder level.\""), 4.f); }
        }
        UE_LOG(LogTemp, Display, TEXT("SWORD TRAINER bout over: %s won at level %s"), Their <= 0.f ? TEXT("Kaede") : TEXT("the player"), GetStyle().Name);
        return;
    }
    const FTrainerStyle& S = GetStyle();
    const FVector Here = GetActorLocation(), There = P->GetActorLocation();
    const float Distance = FVector::Dist2D(Here, There);
    if (bHostileRonin && Moves) Moves->SetCombatTarget(P);
    FaceToward(There, Dt);
    Cooldown = FMath::Max(0.f, Cooldown - Dt);
    ProjectileCooldown = FMath::Max(0.f, ProjectileCooldown - Dt);
    PressGap = FMath::Max(0.f, PressGap - Dt);
    OpponentGuardTime = Theirs->IsGuarding() && !Theirs->IsAttacking() ? OpponentGuardTime + Dt : 0.f;
    if (!Moves->IsArmed() && !Moves->IsBusy()) { Press(TEXT("weapon")); return; }
    // The flurry rush after her perfect dodge: blow after blow.
    if (Moves->InFlurry())
    {
        SetIntent(TEXT("flurry")); Hold(TEXT("guard"), false); Drive(FVector2D::ZeroVector, 1);
        if (PressGap <= 0.f) { Press(TEXT("attack")); Press(TEXT("attack_release")); PressGap = .1f; }
        return;
    }
    if (Moves->IsDown()) { ReleaseAll(); SetIntent(TEXT("down")); return; }
    const FString Reaction = Moves->GetActionName().ToString();
    if (Moves->IsBusy() && (Reaction.StartsWith(TEXT("Hit")) || Reaction.Contains(TEXT("GuardBreak"))))
    {
        ReleaseAll(); Drive(FVector2D::ZeroVector, 0);
        CombosLeft = 0; Cooldown = FMath::Max(Cooldown, .55f); SetIntent(TEXT("staggered"));
        return;
    }
    // Group encounter ticket check for the hostile Kasa Ronin camp: up to 2 Ronin attack at once while the 3rd flanks.
    bool bCanTakeTicket = true;
    if (bHostileRonin)
    {
        if (UJapanEncounters* Encounters = GetWorld()->GetSubsystem<UJapanEncounters>())
            Encounters->Refresh(this, 3200.f);
        int32 OtherAttackers = 0;
        for (TActorIterator<ASwordTrainer> It(GetWorld()); It; ++It)
            if (*It != this && It->IsHostileRonin() && !It->bDefeated && It->Bout == EBout::Fighting && It->Intent.StartsWith(TEXT("attack")))
                ++OtherAttackers;
        if (OtherAttackers >= 2) bCanTakeTicket = false;
    }
    // Instant riposte after landing a parry or absorbing a blow on guard (OpenGothic / BotW counter-slash).
    const FName MyAction = Moves->GetActionName();
    if (bHostileRonin && bCanTakeTicket && (MyAction == TEXT("SwordParry") || MyAction == TEXT("Parry") || MyAction == TEXT("SwordGuardHit") || MyAction == TEXT("GuardHit")) &&
        Level > 0 && Distance < 290.f && Moves->GetActionClipTime() >= .12f && !Intent.StartsWith(TEXT("attack")))
    {
        Cooldown = 0.f; Forced = TEXT("combo"); Open(Distance);
        return;
    }
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
    // OpenGothic whiff punishment: if the opponent swings beyond lunge reach (280..440 cm), step back out of the arc and punish recovery.
    if (bHostileRonin && bCanTakeTicket && Level > 0 && !Intent.StartsWith(TEXT("attack")) && !Moves->IsBusy())
    {
        const bool bOpponentSwinging = Theirs->IsAttacking() && !Theirs->IsCharging();
        if (bOpponentSwinging && Distance > 280.f && Distance < 440.f && Theirs->NextBlowIn() >= 0.f)
        {
            bWhiffWatching = true;
            Hold(TEXT("guard"), true);
            Drive(FVector2D(StrafeSign * .4f, -1.f), 1);
            SetIntent(TEXT("whiff_space"));
            return;
        }
        if (bWhiffWatching && (!bOpponentSwinging || Theirs->NextBlowIn() < 0.f) && Distance < 440.f)
        {
            bWhiffWatching = false;
            Cooldown = 0.f;
            Forced = Distance > 275.f ? TEXT("dash") : TEXT("combo");
            Open(Distance);
            return;
        }
        if (!bOpponentSwinging) bWhiffWatching = false;
    }
    if (bCanTakeTicket && !Forced.IsEmpty() && Cooldown <= 0.f && !Intent.StartsWith(TEXT("attack"))) Open(Distance);
    if (Intent.StartsWith(TEXT("attack")) && Press_Attack(Dt, Distance)) return;
    // Circling at a fair distance, guard up (strafing on the lock-on), waiting for an opening.
    SetIntent(TEXT("circle"));
    StrafeSwitch -= Dt;
    if (StrafeSwitch <= 0.f) { StrafeSign = Dice.FRand() < .5f ? -1.f : 1.f; StrafeSwitch = Dice.FRandRange(1.2f, 3.2f); }
    const float Want = !bCanTakeTicket ? 390.f : (Level == 0 ? 340.f : (bHostileRonin ? 285.f : 300.f));
    const float Radial = Distance > Want + 50.f ? 1.f : Distance < Want - 60.f ? -1.f : 0.f;
    // The player winding up a charged spin: she backs off (or, at the top level, cuts in before it is ready).
    if (Theirs->IsCharging() && Level > 0)
    {
        if (bCanTakeTicket && Level == 2 && Distance < 260.f && Cooldown <= 0.f && !Theirs->IsFullyCharged()) { Forced = TEXT("combo"); Open(Distance); return; }
        Hold(TEXT("guard"), true); Drive(FVector2D(StrafeSign * .5f, -1.f), 1); SetIntent(TEXT("evade charge"));
        return;
    }
    // Anti-turtle guard-break mixup: if the opponent holds guard continuously, pressure with a guard-breaking heavy/charge opening.
    if (bHostileRonin && bCanTakeTicket && OpponentGuardTime > .4f && Level > 0 && Cooldown <= .2f && Distance < 350.f && !Moves->IsBusy())
    {
        Cooldown = 0.f;
        Forced = Dice.FRand() < .6f ? TEXT("charge") : TEXT("jump");
        Open(Distance);
        return;
    }
    if (bHostileRonin)
    {
        // Zelda BotW / OpenGothic 3-man crescent surround formation with peer separation so foes flank from distinct angles.
        FVector PeerRepulse = FVector::ZeroVector;
        for (TActorIterator<ASwordTrainer> It(GetWorld()); It; ++It)
        {
            if (*It == this || !It->IsHostileRonin() || It->bDefeated || It->Bout != EBout::Fighting) continue;
            const FVector Away = (Here - It->GetActorLocation()) * FVector(1, 1, 0);
            const float PeerDist = Away.Size2D();
            if (PeerDist > 1.f && PeerDist < 220.f)
                PeerRepulse += Away.GetSafeNormal2D() * ((220.f - PeerDist) / 220.f);
        }
        const float RoleWant = !bCanTakeTicket ? 345.f :
            (RoninRole == 0 ? (ProjectileCooldown <= 0.f ? 580.f : 245.f) : (RoninRole == 1 ? 265.f : 285.f));
        const float RoleRadial = Distance > RoleWant + 35.f ? 1.f : (Distance < RoleWant - 45.f ? -.85f : 0.f);
        const FVector ToPlayerDir = (There - Here).GetSafeNormal2D();
        const FVector RightOfView = FVector(-ToPlayerDir.Y, ToPlayerDir.X, 0.f);
        const FVector AnchorAxis = (CampOrigin - There).SizeSquared2D() > 25.f
            ? (CampOrigin - There).GetSafeNormal2D() : FVector(1.f, 0.f, 0.f);
        const float DesiredSlotRad = FMath::DegreesToRadians(RoninRole == 0 ? -48.f : (RoninRole == 1 ? 48.f : 0.f));
        const FVector SlotDir = AnchorAxis.RotateAngleAxis(FMath::RadiansToDegrees(DesiredSlotRad), FVector::UpVector);
        const FVector CurDir = (Here - There).GetSafeNormal2D();
        const float CrossZ = CurDir.X * SlotDir.Y - CurDir.Y * SlotDir.X;
        const float FlankBias = FMath::Abs(CrossZ) > .18f ? FMath::Clamp(-CrossZ * 2.2f, -1.f, 1.f) : StrafeSign * .28f;
        const bool bApproachSprint = Distance > RoleWant + 85.f;
        const float Lateral = bApproachSprint ? 0.f : FMath::Clamp(FlankBias * .75f + FVector::DotProduct(PeerRepulse, RightOfView) * 1.35f, -1.f, 1.f);
        const float Forward = FMath::Clamp(RoleRadial + FVector::DotProduct(PeerRepulse, ToPlayerDir) * .75f, -1.f, 1.f);
        GuardSwitch -= Dt;
        if (GuardSwitch <= 0.f) { bGuardUp = Dice.FRand() < S.GuardUp; GuardSwitch = Dice.FRandRange(.7f, 1.8f); }
        Hold(TEXT("guard"), !bApproachSprint && (bGuardUp || (!bCanTakeTicket && Distance < 340.f)));
        Drive(FVector2D(Lateral, Forward), bApproachSprint ? 1 : 0);
        if (bCanTakeTicket && Cooldown <= 0.f && !Moves->IsBusy() && Dice.FRand() < S.Aggression * Dt) Open(Distance);
        return;
    }
    // Her guard is up for a share of the time (the level's), down for the rest: then she steps in or out, facing.
    GuardSwitch -= Dt;
    if (GuardSwitch <= 0.f) { bGuardUp = Dice.FRand() < S.GuardUp; GuardSwitch = Dice.FRandRange(.8f, 2.2f); }
    Hold(TEXT("guard"), bGuardUp || !bCanTakeTicket);
    if (bGuardUp) Drive(FVector2D(StrafeSign * .8f, Radial), S.Strafe > .5f && Distance > Want + 120.f ? 1 : 0);
    else
    {
        Drive(FVector2D(0.f, Radial), 0);
        if (!Moves->IsBusy() && Radial == 0.f)
            SetActorRotation(FRotator(0, FMath::FixedTurn(float(GetActorRotation().Yaw), float((There - Here).Rotation().Yaw), 360.f * Dt), 0));
    }
    if (bCanTakeTicket && Cooldown <= 0.f && !Moves->IsBusy() && Dice.FRand() < S.Aggression * Dt) Open(Distance);
}

bool ASwordTrainer::Defend(float Dt, float Distance)
{
    AWandererCharacter* P = Opponent.Get();
    UAdventureMoveSet* Theirs = P ? P->GetMoves() : nullptr;
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
        const FAdventureMove* Parry = Moves->Find(Moves->HasShield() ? FName(TEXT("Parry")) : FName(TEXT("SwordParry")));
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
        if (bHostileRonin && RoninRole == 0 && ProjectileCooldown <= 0.f && Distance >= 450.f && Distance <= 1100.f)
            Options.Insert({ TEXT("throw"), .65f }, 0);
        if (Distance > 380.f) Options.Add({ TEXT("dash"), S.DashCut * 2.f });
        float R = Dice.FRand();
        for (const FOption& O : Options) { if (R < O.Share) { Pick = O.Name; break; } R -= O.Share; }
        if (Pick.IsEmpty()) Pick = TEXT("combo");
    }
    CombosLeft = Pick == TEXT("combo") ? Dice.RandRange(1, S.MaxCombo) : 0;
    HoldFor = 0.f; bAirStep = false;
    OpeningElapsed = 0.f; bOpeningTell = bThrowReleased = false;
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
    if (Kind == TEXT("throw"))
    {
        // A sleeve blade accompanies a quick slash. The scout commits its aim at release.
        if (!bHostileRonin || RoninRole != 0 || Distance < 320.f || Distance > 1250.f) return Done();
        Drive(FVector2D::ZeroVector, 0);
        Hold(TEXT("guard"), !bAirStep);
        OpeningElapsed += Dt;
        if (!bOpeningTell && OpeningElapsed >= .44f) { AttackTell(); bOpeningTell = true; }
        if (!bAirStep && OpeningElapsed >= .60f)
        {
            Hold(TEXT("guard"), false);
            Press(TEXT("attack")); Press(TEXT("attack_release")); bAirStep = true;
        }
        if (bAirStep && !bThrowReleased && Moves->IsAttacking())
        {
            if (ARoninProjectile::Throw(this, Opponent.Get())) Counts.FindOrAdd(TEXT("projectiles"))++;
            bThrowReleased = true; ProjectileCooldown = 4.8f;
        }
        return bThrowReleased && !Moves->IsAttacking() ? Done() : true;
    }
    const UWandererSwordComponent* Sword = GetSword();
    (void)Sword;
    if (Kind == TEXT("combo") || Kind == TEXT("charge"))
    {
        // Close in (guard down, running), then cut; the move set homes the cut the last steps.
        const float StrikeReach = bHostileRonin ? (RoninRole == 2 ? 235.f : 195.f) : 175.f;
        if (Distance > StrikeReach && !Moves->IsAttacking() && !bAirStep)
        {
            Hold(TEXT("guard"), bHostileRonin); Drive(FVector2D(0.f, 1.f), 1);
            return true;
        }
        if (bHostileRonin)
        {
            Hold(TEXT("guard"), false);
            if (!Moves->IsAttacking())
            {
                if (const AWandererCharacter* P = Opponent.Get())
                {
                    const FVector To = (P->GetActorLocation() - GetActorLocation()) * FVector(1, 1, 0);
                    if (To.SizeSquared() > 1.f) SetActorRotation(FRotator(0, To.Rotation().Yaw, 0));
                }
            }
        }
        Drive(FVector2D::ZeroVector, 1);
        if (Kind == TEXT("combo") && !bAirStep)
        {
            const float Windup = bHostileRonin ? (RoninRole == 0 ? .30f : RoninRole == 1 ? .42f : .56f) : .38f;
            OpeningElapsed += Dt;
            Hold(TEXT("guard"), true);
            if (!bOpeningTell && OpeningElapsed >= Windup - .16f) { AttackTell(); bOpeningTell = true; }
            if (OpeningElapsed < Windup) return true;
            Hold(TEXT("guard"), false);
        }
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
        if (CombosLeft > 0 && PressGap > 0.f && PressGap <= .16f && !bOpeningTell)
        { AttackTell(); bOpeningTell = true; }
        if (CombosLeft > 0 && PressGap <= 0.f)
        {
            Press(TEXT("attack")); Press(TEXT("attack_release"));
            --CombosLeft;
            PressGap = bHostileRonin ? (RoninRole == 0 ? .42f : RoninRole == 1 ? .54f : .66f) : (Level == 0 ? .55f : .32f);
            bOpeningTell = false;
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

void ASwordTrainer::AttackTell()
{
    FVector Base, Tip, Major;
    const FVector At = Moves && Moves->GetBladePose(Base, Tip, Major) ? Tip : GetActorLocation() + FVector(0, 0, 40.f);
    if (!JapanCombat::Publish(this, EJapanCombatCue::AttackTell, At, FVector::ZeroVector, 0.f, this))
        if (auto* FX = AYorimichiCombatFX::Get(this)) FX->AttackTell(At);
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

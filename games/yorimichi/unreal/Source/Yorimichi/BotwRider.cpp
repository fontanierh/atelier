#include "BotwRider.h"
#include "BotwCreature.h"
#include "BotwMoveSet.h"
#include "CairoCharacter.h"
#include "ModoriCharacter.h"
#include "JapanWorld.h"
#include "WandererDefinition.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Components/SkeletalMeshComponent.h"
#include "Misc/CommandLine.h"
#include "Misc/PackageName.h"
#include "Misc/Parse.h"

static FString DefinitionPath(const FString& Name) { return FString::Printf(TEXT("/Game/Botw/%s/DA_%sRider.DA_%sRider"), *Name, *Name, *Name); }
/** The rider's definition was imported. Checked on disk, never loaded: a definition holds its character's mesh, clips
 *  and textures, about 1 GiB over the whole roster. */
static bool HasDefinition(const FString& Name) { return FPackageName::DoesPackageExist(FPackageName::ObjectPathToPackageName(DefinitionPath(Name))); }

FString ABotwRider::Requested()
{
    FString Name;
    if (!FParse::Value(FCommandLine::Get(), TEXT("rider="), Name) || Name.IsEmpty()) return FString();
    if (Name == ACairoCharacter::BotwName())
    {
        if (ACairoCharacter::HasBotw()) return Name;
        UE_LOG(LogTemp, Warning, TEXT("BOTW rider %s: not imported (build unreal.cairo_botw)"), *Name);
        return FString();
    }
    if (Name == AModoriCharacter::Name())
    {
        if (AModoriCharacter::IsBuilt()) return Name;
        UE_LOG(LogTemp, Warning, TEXT("%s: not imported (build unreal.modori_botw)"), *Name);
        return FString();
    }
    if (!FBotwSpec::Find(Name) || !LoadObject<UWandererDefinition>(nullptr, *DefinitionPath(Name), nullptr, LOAD_NoWarn | LOAD_Quiet))
    {
        UE_LOG(LogTemp, Warning, TEXT("BOTW rider %s: no %s (build unreal.botw)"), *Name, *DefinitionPath(Name));
        return FString();
    }
    return Name;
}

UClass* ABotwRider::PawnOverride()
{
    const FString Name = Requested();
    if (Name.IsEmpty()) return nullptr;
    if (Name == AModoriCharacter::Name()) return AModoriCharacter::StaticClass();
    return Name == ACairoCharacter::BotwName() ? ACairoCharacter::StaticClass() : ABotwRider::StaticClass();
}

ABotwRider::ABotwRider(const FObjectInitializer& ObjectInitializer) : Super(ObjectInitializer)
{
    FString Name;
    if (FParse::Value(FCommandLine::Get(), TEXT("rider="), Name) && !Name.IsEmpty()) { RiderName = Name; DefinitionAssetPath = DefinitionPath(Name); }
    GetCapsuleComponent()->InitCapsuleSize(30.f, 82.f);
}

void ABotwRider::Fit()
{
    if (const FBotwSpec* Spec = FBotwSpec::Find(RiderName))
    {
        const float HalfHeight = FMath::Max(Spec->HeightCm * .5f, 40.f);
        GetCapsuleComponent()->SetCapsuleSize(FMath::Clamp(Spec->RadiusCm, 20.f, 60.f), HalfHeight);
        GetMesh()->SetRelativeLocationAndRotation(FVector(0, 0, -HalfHeight), FRotator(0, Spec->MeshYaw, 0));
        GetMesh()->SetRelativeScale3D(FVector(Spec->Scale));
        CacheInitialMeshOffset(GetMesh()->GetRelativeLocation(), GetMesh()->GetRelativeRotation());
        FitMeshZ = -HalfHeight;
        GetCharacterMovement()->SetCrouchedHalfHeight(FMath::Max(HalfHeight * .7f, 35.f));
    }
}

void ABotwRider::OnStartCrouch(float HalfHeightAdjust, float ScaledHalfHeightAdjust)
{
    Super::OnStartCrouch(HalfHeightAdjust, ScaledHalfHeightAdjust);
    if (FitMeshZ == 0.f) return;
    GetMesh()->SetRelativeLocation(FVector(0, 0, FitMeshZ + HalfHeightAdjust));
    BaseTranslationOffset.Z = FitMeshZ + HalfHeightAdjust;
}

void ABotwRider::OnEndCrouch(float HalfHeightAdjust, float ScaledHalfHeightAdjust)
{
    Super::OnEndCrouch(HalfHeightAdjust, ScaledHalfHeightAdjust);
    if (FitMeshZ == 0.f) return;
    GetMesh()->SetRelativeLocation(FVector(0, 0, FitMeshZ));
    BaseTranslationOffset.Z = FitMeshZ;
}

void ABotwRider::BeginPlay()
{
    // Size the capsule and stand the mesh in it before the character reads its definition and the board saves the
    // mesh's walking transform.
    Fit();
    if (const FBotwSpec* Spec = FBotwSpec::Find(RiderName))
        UE_LOG(LogTemp, Display, TEXT("BOTW rider: %s (%s), %.0f cm"), *Spec->Name, *Spec->Label, Spec->HeightCm);
    Super::BeginPlay();
    if (const FBotwSpec* Spec = FBotwSpec::Find(RiderName); Spec && Spec->Moves.IsValid())
    {
        UBotwMoveSet* Set = NewObject<UBotwMoveSet>(this, TEXT("BotwMoves"));
        if (Set->Initialize(this, Spec->Moves)) Moves = Set;
    }
}

TArray<FString> ABotwRider::Available()
{
    // Modori first when he is built, then the riders with a move set (Link); -rider=<Name> still starts any of them.
    TArray<FString> Names;
    if (AModoriCharacter::IsBuilt()) Names.Add(AModoriCharacter::Name());
    for (const auto& Pair : FBotwSpec::All())
        if (Pair.Value.Moves.IsValid() && HasDefinition(Pair.Key)) Names.Add(Pair.Key);
    return Names;
}

FString ABotwRider::NameOf(const AWandererCharacter* Character)
{
    if (const ABotwRider* Rider = Cast<ABotwRider>(Character)) return Rider->RiderName;
    if (Cast<AModoriCharacter>(Character)) return AModoriCharacter::Name();
    const ACairoCharacter* Cairo = Cast<ACairoCharacter>(Character);
    return Cairo && Cairo->IsBotw() ? ACairoCharacter::BotwName() : FString(TEXT("Cairo"));
}

FString ABotwRider::Label(const FString& Name)
{
    const FBotwSpec* Spec = FBotwSpec::Find(Name);
    return Spec && !Spec->Label.IsEmpty() ? Spec->Label : Name;
}

AWandererCharacter* ABotwRider::SwitchPlayer(AWandererCharacter* From, const FString& Name)
{
    APlayerController* PC = From ? Cast<APlayerController>(From->GetController()) : nullptr;
    UWorld* World = From ? From->GetWorld() : nullptr;
    const bool bCairo = Name == TEXT("Cairo") || (Name == ACairoCharacter::BotwName() && ACairoCharacter::HasBotw());
    if (!PC || !World || !From->IsReady() || From->IsZeppelinPassenger() || Name == NameOf(From) || (!bCairo && !Available().Contains(Name)))
    {
        UE_LOG(LogTemp, Warning, TEXT("Character switch to %s refused"), *Name);
        return nullptr;
    }
    // Stand the new character's feet where the old one's are, facing its way; the camera keeps its rotation.
    const FRotator Look = PC->GetControlRotation();
    const FVector Feet = From->GetActorLocation() - FVector(0, 0, From->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
    const FRotator Facing(0, From->GetActorRotation().Yaw, 0);
    From->Leave();
    From->SetActorEnableCollision(false);
    const bool bModori = Name == AModoriCharacter::Name();
    UClass* Class = bCairo ? ACairoCharacter::StaticClass() : bModori ? AModoriCharacter::StaticClass() : ABotwRider::StaticClass();
    AWandererCharacter* To = World->SpawnActorDeferred<AWandererCharacter>(Class, FTransform(Facing, Feet), nullptr, nullptr, ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn);
    if (!To) { From->SetActorEnableCollision(true); return nullptr; }
    if (ABotwRider* Rider = Cast<ABotwRider>(To)) { Rider->RiderName = Name; Rider->DefinitionAssetPath = DefinitionPath(Name); Rider->Fit(); }
    if (ACairoCharacter* Cairo = Cast<ACairoCharacter>(To)) Cairo->SetBotw(Name == ACairoCharacter::BotwName());
    To->bSwitchedIn = true;
    To->EnterWorld(From->GetLandscape());   // before BeginPlay, as at the start: the sailboat takes the camera preferences
    To->FinishSpawning(FTransform(Facing, Feet + FVector(0, 0, To->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 2.f)));
    PC->UnPossess();
    PC->Possess(To);
    PC->SetControlRotation(Look);
    From->Destroy();
    UE_LOG(LogTemp, Display, TEXT("Character switch: now playing %s"), *Name);
    return To;
}

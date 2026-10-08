#include "BotwRider.h"
#include "JapanNetwork.h"
#include "BotwCreature.h"
#include "BotwMoveSet.h"
#include "PlayableCharacter.h"
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
    if (const FPlayableCharacter* Character = FPlayableCharacter::Find(Name); Character && Character->IsRequestable())
    {
        if (Character->Built()) return Name;
        UE_LOG(LogTemp, Warning, TEXT("%s: not imported (build %s)"), *Name, *Character->BuildStep);
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
    const FPlayableCharacter* Character = FPlayableCharacter::Find(Name);
    return Character ? Character->Class() : ABotwRider::StaticClass();
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

void ABotwRider::ConfigureNetworkRider(const FString& Name, bool bShield)
{
    Super::ConfigureNetworkRider(Name, bShield);
    RiderName = Name;
    DefinitionAssetPath = DefinitionPath(Name);
    Fit();
}
void ABotwRider::BeginPlay()
{
    if (!GetNetworkRiderName().IsEmpty())
    {
        RiderName = GetNetworkRiderName();
        DefinitionAssetPath = DefinitionPath(RiderName);
    }
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
    // The other playable characters first when they are built (Modori), then the riders with a move set (Link);
    // -rider=<Name> still starts any of them.
    TArray<FString> Names;
    const FPlayableCharacter& Default = FPlayableCharacter::Default();
    for (const FPlayableCharacter& Character : FPlayableCharacter::All())
        if (!Character.bDefault && Character.Name != Default.MoveSet && Character.Built()) Names.Add(Character.Name);
    for (const auto& Pair : FBotwSpec::All())
        if (Pair.Value.Moves.IsValid() && HasDefinition(Pair.Key)) Names.Add(Pair.Key);
    return Names;
}

FString ABotwRider::NameOf(const AWandererCharacter* Character)
{
    if (const ABotwRider* Rider = Cast<ABotwRider>(Character)) return Rider->RiderName;
    const FString Name = Character ? Character->GetPlayableName() : FString();
    return Name.IsEmpty() ? FPlayableCharacter::Default().Name : Name;
}

FString ABotwRider::Label(const FString& Name)
{
    const FBotwSpec* Spec = FBotwSpec::Find(Name);
    return Spec && !Spec->Label.IsEmpty() ? Spec->Label : Name;
}

AWandererCharacter* ABotwRider::SwitchPlayer(AWandererCharacter* From, const FString& Name)
{
    if (From && JapanNetwork::IsOnline(From->GetWorld())) return nullptr; // Network character switching is server-owned.
    APlayerController* PC = From ? Cast<APlayerController>(From->GetController()) : nullptr;
    UWorld* World = From ? From->GetWorld() : nullptr;
    const FPlayableCharacter* Character = FPlayableCharacter::Find(Name);
    const bool bOffered = Character ? Character->Built() : Available().Contains(Name);
    if (!PC || !World || !From->IsReady() || From->IsZeppelinPassenger() || Name == NameOf(From) || !bOffered)
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
    UClass* Class = Character ? Character->Class() : ABotwRider::StaticClass();
    AWandererCharacter* To = World->SpawnActorDeferred<AWandererCharacter>(Class, FTransform(Facing, Feet), nullptr, nullptr, ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn);
    if (!To) { From->SetActorEnableCollision(true); return nullptr; }
    if (ABotwRider* Rider = Cast<ABotwRider>(To)) { Rider->RiderName = Name; Rider->DefinitionAssetPath = DefinitionPath(Name); Rider->Fit(); }
    if (Character && Character->Prepare) Character->Prepare(To, Name);
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

#include "BotwRider.h"
#include "BotwCreature.h"
#include "CairoCharacter.h"
#include "JapanWorld.h"
#include "WandererDefinition.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Components/SkeletalMeshComponent.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

static FString DefinitionPath(const FString& Name) { return FString::Printf(TEXT("/Game/Botw/%s/DA_%sRider.DA_%sRider"), *Name, *Name, *Name); }

FString ABotwRider::Requested()
{
    FString Name;
    if (!FParse::Value(FCommandLine::Get(), TEXT("rider="), Name) || Name.IsEmpty()) return FString();
    if (!FBotwSpec::Find(Name) || !LoadObject<UWandererDefinition>(nullptr, *DefinitionPath(Name), nullptr, LOAD_NoWarn | LOAD_Quiet))
    {
        UE_LOG(LogTemp, Warning, TEXT("BOTW rider %s: no %s (build unreal.botw)"), *Name, *DefinitionPath(Name));
        return FString();
    }
    return Name;
}

UClass* ABotwRider::PawnOverride() { return Requested().IsEmpty() ? nullptr : ABotwRider::StaticClass(); }

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
    }
}

void ABotwRider::BeginPlay()
{
    // Size the capsule and stand the mesh in it before the character reads its definition and the board saves the
    // mesh's walking transform.
    Fit();
    if (const FBotwSpec* Spec = FBotwSpec::Find(RiderName))
        UE_LOG(LogTemp, Display, TEXT("BOTW rider: %s (%s), %.0f cm"), *Spec->Name, *Spec->Label, Spec->HeightCm);
    Super::BeginPlay();
}

TArray<FString> ABotwRider::Available()
{
    TArray<FString> Names;
    for (const auto& Pair : FBotwSpec::All())
        if (LoadObject<UWandererDefinition>(nullptr, *DefinitionPath(Pair.Key), nullptr, LOAD_NoWarn | LOAD_Quiet)) Names.Add(Pair.Key);
    return Names;
}

FString ABotwRider::NameOf(const AWandererCharacter* Character)
{
    const ABotwRider* Rider = Cast<ABotwRider>(Character);
    return Rider ? Rider->RiderName : FString(TEXT("Cairo"));
}

AWandererCharacter* ABotwRider::SwitchPlayer(AWandererCharacter* From, const FString& Name)
{
    APlayerController* PC = From ? Cast<APlayerController>(From->GetController()) : nullptr;
    UWorld* World = From ? From->GetWorld() : nullptr;
    const bool bCairo = Name == TEXT("Cairo");
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
    UClass* Class = bCairo ? ACairoCharacter::StaticClass() : ABotwRider::StaticClass();
    AWandererCharacter* To = World->SpawnActorDeferred<AWandererCharacter>(Class, FTransform(Facing, Feet), nullptr, nullptr, ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn);
    if (!To) { From->SetActorEnableCollision(true); return nullptr; }
    if (ABotwRider* Rider = Cast<ABotwRider>(To)) { Rider->RiderName = Name; Rider->DefinitionAssetPath = DefinitionPath(Name); Rider->Fit(); }
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

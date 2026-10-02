#include "BotwRider.h"
#include "BotwCreature.h"
#include "WandererDefinition.h"
#include "Components/CapsuleComponent.h"
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
    if (FParse::Value(FCommandLine::Get(), TEXT("rider="), Name) && !Name.IsEmpty()) DefinitionAssetPath = DefinitionPath(Name);
    GetCapsuleComponent()->InitCapsuleSize(30.f, 82.f);
}

void ABotwRider::BeginPlay()
{
    // Size the capsule and stand the mesh in it before the character reads its definition and the board saves the
    // mesh's walking transform.
    if (const FBotwSpec* Spec = FBotwSpec::Find(Requested()))
    {
        const float HalfHeight = FMath::Max(Spec->HeightCm * .5f, 40.f);
        GetCapsuleComponent()->SetCapsuleSize(FMath::Clamp(Spec->RadiusCm, 20.f, 60.f), HalfHeight);
        GetMesh()->SetRelativeLocationAndRotation(FVector(0, 0, -HalfHeight), FRotator(0, Spec->MeshYaw, 0));
        GetMesh()->SetRelativeScale3D(FVector(Spec->Scale));
        UE_LOG(LogTemp, Display, TEXT("BOTW rider: %s (%s), %.0f cm"), *Spec->Name, *Spec->Label, Spec->HeightCm);
    }
    Super::BeginPlay();
}

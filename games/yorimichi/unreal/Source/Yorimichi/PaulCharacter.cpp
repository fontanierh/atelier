#include "PaulCharacter.h"
#include "AtelierData.h"
#include "AdventureMoveSet.h"
#include "PlayableCharacter.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Misc/PackageName.h"

namespace
{
    const TCHAR* Definition = TEXT("/Game/Paul/DA_Paul.DA_Paul");
    TSharedPtr<FJsonObject> Record()
    {
        static const TSharedPtr<FJsonObject> Value = AtelierReadJson(AtelierDataPath(TEXT("paul/adventure.json")));
        return Value;
    }
}

static const FPlayableCharacter::FRegister RegisterPaul({APaulCharacter::Name(), &APaulCharacter::StaticClass,
                                                          &APaulCharacter::IsBuilt, TEXT("unreal.paul_adventure")});

APaulCharacter::APaulCharacter()
{
    DefinitionAssetPath = Definition;
    SprintSpeedMultiplier = 1.f;
    GetCapsuleComponent()->InitCapsuleSize(24.f, 83.f);
    GetCharacterMovement()->SetCrouchedHalfHeight(73.f);
    GetMesh()->SetRelativeLocation(FVector(0, 0, -83.65f));
    GetMesh()->SetRelativeRotation(FRotator::ZeroRotator);
}

bool APaulCharacter::IsBuilt()
{
    return Record().IsValid() && FPackageName::DoesPackageExist(FPackageName::ObjectPathToPackageName(FString(Definition)));
}

void APaulCharacter::BeginPlay()
{
    Super::BeginPlay();
    UAdventureMoveSet* Set = NewObject<UAdventureMoveSet>(this, TEXT("AdventureMoves"));
    if (Set->Initialize(this, Record())) Moves = Set;
    else
    {
        DisablePlayerMovement();
        UE_LOG(LogTemp, Error, TEXT("Paul: missing move set (build unreal.paul_adventure)"));
    }
}

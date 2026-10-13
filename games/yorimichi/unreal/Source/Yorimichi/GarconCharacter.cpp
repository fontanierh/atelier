#include "GarconCharacter.h"
#include "AtelierData.h"
#include "AdventureMoveSet.h"
#include "PlayableCharacter.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Misc/PackageName.h"

namespace
{
    const TCHAR* Definition = TEXT("/Game/Garcon/DA_Garcon.DA_Garcon");
    TSharedPtr<FJsonObject> Record()
    {
        static const TSharedPtr<FJsonObject> Value = AtelierReadJson(AtelierDataPath(TEXT("garcon/adventure.json")));
        return Value;
    }
}

static const FPlayableCharacter::FRegister RegisterGarcon({AGarconCharacter::Name(), &AGarconCharacter::StaticClass,
                                                          &AGarconCharacter::IsBuilt, TEXT("unreal.garcon_adventure")});

AGarconCharacter::AGarconCharacter()
{
    DefinitionAssetPath = Definition;
    SprintSpeedMultiplier = 1.f;
    GetCapsuleComponent()->InitCapsuleSize(24.f, 83.f);
    GetCharacterMovement()->SetCrouchedHalfHeight(73.f);
    GetMesh()->SetRelativeLocation(FVector(0, 0, -83.65f));
    GetMesh()->SetRelativeRotation(FRotator::ZeroRotator);
}

bool AGarconCharacter::IsBuilt()
{
    return Record().IsValid() && FPackageName::DoesPackageExist(FPackageName::ObjectPathToPackageName(FString(Definition)));
}

void AGarconCharacter::BeginPlay()
{
    Super::BeginPlay();
    UAdventureMoveSet* Set = NewObject<UAdventureMoveSet>(this, TEXT("AdventureMoves"));
    if (Set->Initialize(this, Record())) Moves = Set;
    else
    {
        DisablePlayerMovement();
        UE_LOG(LogTemp, Error, TEXT("Garcon: missing move set (build unreal.garcon_adventure)"));
    }
}

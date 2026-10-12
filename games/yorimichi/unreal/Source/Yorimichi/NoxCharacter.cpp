#include "NoxCharacter.h"
#include "AtelierData.h"
#include "AdventureMoveSet.h"
#include "PlayableCharacter.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
    const TCHAR* NoxDefinition = TEXT("/Game/Nox/DA_Nox.DA_Nox");

    /** His move record, read once; null when it has not been built. */
    TSharedPtr<FJsonObject> NoxRecord()
    {
        static TSharedPtr<FJsonObject> Record;
        static bool bLoaded = false;
        if (!bLoaded)
        {
            bLoaded = true;
            Record = AtelierReadJson(AtelierDataPath(TEXT("nox/adventure.json")));
        }
        return Record;
    }
}

static const FPlayableCharacter::FRegister RegisterNox({ANoxCharacter::Name(), &ANoxCharacter::StaticClass, &ANoxCharacter::IsBuilt,
                                                           TEXT("unreal.nox_adventure")});

ANoxCharacter::ANoxCharacter()
{
    DefinitionAssetPath = NoxDefinition;
    SprintSpeedMultiplier = 1.f;   // the reference rig's sprint: the dash clip's own stride speed
    // 1.78 m: the capsule's half height to the crown, the soles 0.65 cm under its bottom as Cairo's (export_unreal.py).
    GetCapsuleComponent()->InitCapsuleSize(24.f, 89.f);
    GetCharacterMovement()->SetCrouchedHalfHeight(77.f);
    GetMesh()->SetRelativeLocation(FVector(0, 0, -89.65f));
    // His export turns Tripo's -Y to +X, the way the game's characters face.
    GetMesh()->SetRelativeRotation(FRotator::ZeroRotator);
}

bool ANoxCharacter::IsBuilt()
{
    return NoxRecord().IsValid() && FPackageName::DoesPackageExist(FPackageName::ObjectPathToPackageName(FString(NoxDefinition)));
}

void ANoxCharacter::BeginPlay()
{
    Super::BeginPlay();
    UAdventureMoveSet* Set = NewObject<UAdventureMoveSet>(this, TEXT("AdventureMoves"));
    if (Set->Initialize(this, NoxRecord())) Moves = Set;
    else
    {
        DisablePlayerMovement();
        UE_LOG(LogTemp, Error, TEXT("Nox: no merged move set (build unreal.nox_adventure)"));
    }
}

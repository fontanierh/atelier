#include "ModoriCharacter.h"
#include "AtelierData.h"
#include "BotwMoveSet.h"
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
    const TCHAR* ModoriDefinition = TEXT("/Game/Modori/DA_Modori.DA_Modori");

    /** His move record, read once; null when it has not been built. */
    TSharedPtr<FJsonObject> ModoriRecord()
    {
        static TSharedPtr<FJsonObject> Record;
        static bool bLoaded = false;
        if (!bLoaded)
        {
            bLoaded = true;
            FString Text;
            if (FFileHelper::LoadFileToString(Text, *AtelierDataPath(TEXT("modori/botw.json"))))
                FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Record);
        }
        return Record;
    }
}

AModoriCharacter::AModoriCharacter()
{
    DefinitionAssetPath = ModoriDefinition;
    SprintSpeedMultiplier = 1.f;   // Link's sprint: the dash clip's own stride speed
    // 1.75 m: the capsule's half height to the crown, the soles 0.65 cm under its bottom as Cairo's (export_unreal.py).
    GetCapsuleComponent()->InitCapsuleSize(24.f, 88.f);
    GetCharacterMovement()->SetCrouchedHalfHeight(77.f);
    GetMesh()->SetRelativeLocation(FVector(0, 0, -88.65f));
    // His export turns Tripo's -Y to +X, the way the game's characters face.
    GetMesh()->SetRelativeRotation(FRotator::ZeroRotator);
    // His coat's cloth restarts from the skinned pose after a jump (a respawn, a board mount, a switch) rather than
    // whipping through the body to catch up.
    GetMesh()->SetTeleportDistanceThreshold(150.f);
    GetMesh()->SetTeleportRotationThreshold(60.f);
}

bool AModoriCharacter::IsBuilt()
{
    return ModoriRecord().IsValid() && FPackageName::DoesPackageExist(FPackageName::ObjectPathToPackageName(FString(ModoriDefinition)));
}

void AModoriCharacter::BeginPlay()
{
    Super::BeginPlay();
    UBotwMoveSet* Set = NewObject<UBotwMoveSet>(this, TEXT("BotwMoves"));
    if (Set->Initialize(this, ModoriRecord())) Moves = Set;
    else UE_LOG(LogTemp, Warning, TEXT("Modori: no merged move set (build unreal.modori_botw)"));
}

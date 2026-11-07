#include "MoverCharacter.h"
#include "AtelierData.h"
#include "AdventureMoveSet.h"
#include "HairSpringComponent.h"
#include "SeatCorrectiveComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Dom/JsonObject.h"

AMoverCharacter::AMoverCharacter()
{
    SprintSpeedMultiplier = 1.f;   // the reference rig's sprint: the dash clip's own stride speed
    // Every character's export faces +X, the way the game's characters face (pipeline/rig.py).
    GetMesh()->SetRelativeRotation(FRotator::ZeroRotator);
}

void AMoverCharacter::PostInitializeComponents()
{
    Super::PostInitializeComponents();
    DefinitionAssetPath = DefinitionPath;   // read by AWandererCharacter::BeginPlay
    if (ClothTeleportDistance > 0.f) GetMesh()->SetTeleportDistanceThreshold(ClothTeleportDistance);
    if (ClothTeleportRotation > 0.f) GetMesh()->SetTeleportRotationThreshold(ClothTeleportRotation);
}

void AMoverCharacter::BeginPlay()
{
    Super::BeginPlay();
    // Its move record and posed grips (assets/characters/grips/<id>), read when it enters the world.
    const TSharedPtr<FJsonObject> Record = AtelierReadJson(AtelierDataPath(CharacterId / TEXT("adventure.json")));
    const TSharedPtr<FJsonObject> Grips = AtelierReadJson(AtelierDataPath(CharacterId / TEXT("grips.json")));
    UAdventureMoveSet* Set = NewObject<UAdventureMoveSet>(this, TEXT("AdventureMoves"));
    if (Set->Initialize(this, Record, Grips)) Moves = Set;
    else
    {
        DisablePlayerMovement();
        UE_LOG(LogTemp, Error, TEXT("%s: no merged move set (build unreal.%s_pawn)"), *DisplayName, *CharacterId.Replace(TEXT("-"), TEXT("_")));
    }
    if (GetNetMode() != NM_DedicatedServer && HairSpringMorphs.Num() == 2)
    {
        HairSpring = NewObject<UHairSpringComponent>(this, TEXT("HairSpring"));
        HairSpring->Morphs = HairSpringMorphs;
        HairSpring->AddTickPrerequisiteActor(this);   // the spring follows this frame's head
        HairSpring->RegisterComponent();
    }
    if (!SeatCorrectivePrefix.IsEmpty())
    {
        SeatCorrectives = NewObject<USeatCorrectiveComponent>(this, TEXT("SeatCorrectives"));
        SeatCorrectives->Prefix = SeatCorrectivePrefix;
        SeatCorrectives->RegisterComponent();
    }
}

void AMoverCharacter::GetSkatePoseMorphs(const USkeletalMeshComponent* Mesh, TConstArrayView<FTransform> Pose,
                                         TArray<TPair<FName, float>>& Morphs) const
{
    if (SeatCorrectives) SeatCorrectives->PoseMorphs(Mesh, Pose, Morphs);
}

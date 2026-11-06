#pragma once
#include "WandererCharacter.h"
#include "MoverCharacter.generated.h"

class UHairSpringComponent;
class USeatCorrectiveComponent;

/**
 * A playable character with the merged move set, defined entirely by data: each one is a Blueprint, BP_<Name>, that
 * Scripts/character_pawn.py generates from its character.toml [game] table and its body's import. The Blueprint holds
 * the values below and the capsule and mesh offset on its component templates, so a crouch restores them from the
 * class defaults as for any character. Content/Data/<id>/character.json, written last by the same step, registers it
 * with FPlayableCharacter (-rider=, the character switch and shared games), which can rescan while the game runs.
 */
UCLASS(Abstract, Blueprintable)
class YORIMICHI_API AMoverCharacter : public AWandererCharacter
{
    GENERATED_BODY()
public:
    AMoverCharacter();
    virtual void PostInitializeComponents() override;
    virtual void BeginPlay() override;
    virtual FString GetPlayableName() const override { return DisplayName; }
    virtual FString GetBikeRig() const override { return BikeRig; }
    virtual bool PlantsFeet() const override { return true; }
    virtual float GetSkateClothingClearance() const override { return SkateClothingClearance; }
    virtual int32 GetSkateCollisionHullDirections() const override { return SkateCollisionHullDirections; }
    virtual void GetSkatePoseMorphs(const USkeletalMeshComponent* Mesh, TConstArrayView<FTransform> Pose,
                                    TArray<TPair<FName, float>>& Morphs) const override;
    /** A longer-legged character moves the sailboat stance by its leg length; the others keep it as it was fitted. */
    virtual float SailboatReach(float LegLength) const override
    {
        return bLegScaledSailboat ? FMath::Clamp(LegLength / 55.f, 1.f, 1.6f) : 1.f;
    }

    /** Its id (assets/characters/<id>): its runtime data is Content/Data/<id>/. */
    UPROPERTY(EditDefaultsOnly, Category = "Character") FString CharacterId;
    /** Its name for -rider=, the character switch and the menu. */
    UPROPERTY(EditDefaultsOnly, Category = "Character") FString DisplayName;
    /** Its merged move set's definition (adventure.toml's `definition`), as an object path. */
    UPROPERTY(EditDefaultsOnly, Category = "Character") FString DefinitionPath;
    /** The bike clips' folder name (/Game/<BikeRig>Bike). */
    UPROPERTY(EditDefaultsOnly, Category = "Character") FString BikeRig;
    /** How far its clothes reach beyond its body's collision capsules (cm), for the skating rider. */
    UPROPERTY(EditDefaultsOnly, Category = "Character") float SkateClothingClearance = 0.f;
    /** The skating bail collision's hull resolution: more keeps rounded soles. */
    UPROPERTY(EditDefaultsOnly, Category = "Character") int32 SkateCollisionHullDirections = 256;
    UPROPERTY(EditDefaultsOnly, Category = "Character") bool bLegScaledSailboat = false;
    /** A cloth mesh restarts from the skinned pose after a jump this far (cm) or this sharp (degrees); 0 keeps the
     *  engine's. */
    UPROPERTY(EditDefaultsOnly, Category = "Character") float ClothTeleportDistance = 0.f;
    UPROPERTY(EditDefaultsOnly, Category = "Character") float ClothTeleportRotation = 0.f;
    /** Hair spring morph targets (forward, sideways): none for a character without them. */
    UPROPERTY(EditDefaultsOnly, Category = "Character") TArray<FName> HairSpringMorphs;
    /** The seat correctives' morph target prefix (SeatCorrectiveComponent.h): empty for a character without them. */
    UPROPERTY(EditDefaultsOnly, Category = "Character") FString SeatCorrectivePrefix;

private:
    UPROPERTY() TObjectPtr<UHairSpringComponent> HairSpring;
    UPROPERTY() TObjectPtr<USeatCorrectiveComponent> SeatCorrectives;
};

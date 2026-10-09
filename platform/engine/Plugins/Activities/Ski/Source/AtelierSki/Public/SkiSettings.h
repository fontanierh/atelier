#pragma once
#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "SkiSettings.generated.h"

class UMaterialInterface;
class UStaticMesh;

/** Project Settings > Plugins > Ski: section [/Script/AtelierSki.SkiSettings] of the game's DefaultGame.ini. */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Ski"))
class ATELIERSKI_API USkiSettings : public UDeveloperSettings
{
    GENERATED_BODY()
public:
    virtual FName GetCategoryName() const override { return TEXT("Plugins"); }

    /** Keeps the lean inside what the edges hold at the current speed (0: plain physics). */
    UPROPERTY(Config, EditAnywhere, Category = Assists, meta = (ClampMin = 0, ClampMax = 1)) float BalanceAssist = .85f;
    /** Levels the body toward the slope below in the air. */
    UPROPERTY(Config, EditAnywhere, Category = Assists, meta = (ClampMin = 0, ClampMax = 1)) float AirAssist = .35f;
    /** A small yaw torque from the spin stick in the air. */
    UPROPERTY(Config, EditAnywhere, Category = Assists, meta = (ClampMin = 0, ClampMax = 1)) float SpinAssist = .2f;

    /** One ski, 1 m long along X, centred, its base at Z 0; scaled to 175 cm. None: a box. */
    UPROPERTY(Config, EditAnywhere, Category = Look) TSoftObjectPtr<UStaticMesh> SkiMesh;
    UPROPERTY(Config, EditAnywhere, Category = Look) TSoftObjectPtr<UMaterialInterface> SkiMaterial;
    /** The terrain park's snow. None: a plain white material. */
    UPROPERTY(Config, EditAnywhere, Category = Look) TSoftObjectPtr<UMaterialInterface> SnowMaterial;
    /** Boot centre to boot centre (cm). */
    UPROPERTY(Config, EditAnywhere, Category = Look, meta = (ClampMin = 10)) float StanceWidth = 24.f;

    /** The character's body as an active ragdoll that follows the skiing pose and goes limp in a crash (ski.Physical
     *  overrides it). Off, or a mesh with fewer than six physics bodies: the pose alone. */
    UPROPERTY(Config, EditAnywhere, Category = Body) bool bPhysicalRider = true;
    /** Every joint toward the pose (Hz). */
    UPROPERTY(Config, EditAnywhere, Category = Body, meta = (ClampMin = 0)) float JointStrength = 14.f;
    /** The feet and hands toward the pose, held from the pelvis (Hz). */
    UPROPERTY(Config, EditAnywhere, Category = Body, meta = (ClampMin = 0)) float FeetStrength = 18.f;
    UPROPERTY(Config, EditAnywhere, Category = Body, meta = (ClampMin = 0)) float HandStrength = 4.f;
    /** The joints' strength left in a crash, as a fraction: muscle tone, not a pose. */
    UPROPERTY(Config, EditAnywhere, Category = Body, meta = (ClampMin = 0, ClampMax = 1)) float CrashTone = .12f;
    /** How long a crash lasts before the skier is back up (s). */
    UPROPERTY(Config, EditAnywhere, Category = Body, meta = (ClampMin = .5)) float CrashTime = 3.f;

    /** Turns the view toward the direction of travel above walking speed (1/s; 0: the player's camera alone). */
    UPROPERTY(Config, EditAnywhere, Category = Camera, meta = (ClampMin = 0)) float CameraFollow = 1.2f;
};

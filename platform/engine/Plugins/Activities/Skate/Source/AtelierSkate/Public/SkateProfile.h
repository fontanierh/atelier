#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "SkateProfile.generated.h"

class USkateRuntimeAsset;
class USkateCollisionAsset;

UENUM(BlueprintType)
enum class ESkateDifficulty : uint8
{
    Easy,
    Normal,
    Hardcore
};

/** Structural validation values exposed together to Blueprint and Python callers. */
USTRUCT(BlueprintType)
struct ATELIERSKATE_API FSkateProfileValidationReport
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Skate|Profile")
    bool bValid = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Skate|Profile")
    TArray<FString> Issues;
};

/** Reusable native skating content and tuning. Defaults reproduce the stock controller presets. */
UCLASS(BlueprintType)
class ATELIERSKATE_API USkateProfile : public UPrimaryDataAsset
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Skate|Content", meta = (AssetBundles = "Skate"))
    TSoftObjectPtr<USkateRuntimeAsset> RuntimeData;

    /** Cooked collision sources for the worlds in which this profile is used. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Skate|Content", meta = (AssetBundles = "Skate"))
    TArray<TSoftObjectPtr<USkateCollisionAsset>> CollisionDataCatalog;

    /** Seconds between fallback discovery scans for collision actors that do not publish a revision. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Skate|Content", meta = (ClampMin = "0.05", ClampMax = "5"))
    float CollisionScanPeriodSeconds = .25f;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Skate|Controller")
    ESkateDifficulty Difficulty = ESkateDifficulty::Normal;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Skate|Controller")
    bool bGoofy = false;

    /** 0 loose / 1 tight; feeds the original steering scalar. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Skate|Controller", meta = (ClampMin = "0", ClampMax = "1"))
    float TruckTightness = .5f;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Skate|Controller", meta = (ClampMin = "0.5", ClampMax = "2"))
    float PopHeightScale = 1.f;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Skate|Controller", meta = (ClampMin = "0.5", ClampMax = "3"))
    float AirSpinScale = 1.f;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Skate|Controller", meta = (ClampMin = "0.5", ClampMax = "2"))
    float PushSpeedScale = 1.f;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Skate|Controller", meta = (ClampMin = "0.5", ClampMax = "3"))
    float PushPowerScale = 1.f;

    /** 0 is stock vertical-only support; 1 assists straight airs from lips down to about 50 degrees. */
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Skate|Controller", meta = (ClampMin = "0", ClampMax = "1"))
    float VertAssist = 0.f;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Skate|Board", meta = (AllowedClasses = "/Script/Engine.StaticMesh", AssetBundles = "Skate"))
    FSoftObjectPath DeckMesh;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Skate|Board", meta = (AllowedClasses = "/Script/Engine.StaticMesh", AssetBundles = "Skate"))
    FSoftObjectPath TruckMesh;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Skate|Board", meta = (AllowedClasses = "/Script/Engine.StaticMesh", AssetBundles = "Skate"))
    FSoftObjectPath WheelMesh;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Skate|Audio")
    FString SoundFolder;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Skate|Audio", meta = (AllowedClasses = "/Script/Engine.SoundWave", AssetBundles = "Skate"))
    TArray<FSoftObjectPath> FallSounds;

    /** Original preset name accepted by the unchanged native controller. */
    UFUNCTION(BlueprintPure, Category = "Skate|Profile")
    FString GetDifficultyPreset() const;

    /** Runtime-safe structural validation; does not synchronously load referenced content. */
    UFUNCTION(BlueprintCallable, Category = "Skate|Profile")
    bool ValidateProfile(TArray<FString>& OutErrors) const;

    /** The same structural validation as ValidateProfile, with a stable struct return for scripting. */
    UFUNCTION(BlueprintPure, Category = "Skate|Profile")
    FSkateProfileValidationReport ValidateProfileReport() const;

#if WITH_EDITOR
    virtual EDataValidationResult IsDataValid(FDataValidationContext& Context) const override;
#endif
};

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MegaParkLayout.generated.h"

/** Original rail identity and curve data, with contact points in Unreal centimetres. */
USTRUCT(BlueprintType)
struct YORIMICHIASSETS_API FMegaParkRail
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite) FString SourceId;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) bool Closed = false;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) TArray<FVector> Points;
    /** Untouched big-endian 120-byte cubic segment payloads; retained for native curve consumers. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite) TArray<FString> OriginalSegments;
};

/** What the park keeps from its source besides meshes: the grind paths, relative to the park, and the upper deck
 *  start, in world space. The standalone level saves it (AMegaParkLayout); the island fills it from park.json. */
USTRUCT(BlueprintType)
struct YORIMICHIASSETS_API FMegaParkLayoutData
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite) FString SourceManifestHash;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) TArray<FMegaParkRail> Rails;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) FVector SpawnGround = FVector::ZeroVector;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) float SpawnYaw = 0.f;
};

/** The standalone park level's layout, placed where the park's origin is. Data only: the level's game mode
 *  (AMegaParkGameMode) builds the park's grind paths and player services from it when play starts (docs/MEGAPARK.md). */
UCLASS()
class YORIMICHIASSETS_API AMegaParkLayout : public AActor
{
    GENERATED_BODY()
public:
    AMegaParkLayout();
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Source") FMegaParkLayoutData Layout;
};

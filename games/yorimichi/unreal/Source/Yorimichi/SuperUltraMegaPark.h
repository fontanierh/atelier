#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GameFramework/GameModeBase.h"
#include "JapanWorld.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "SuperUltraMegaPark.generated.h"

class UStaticMesh;

/** Original rail identity and curve data, with contact points in Unreal centimetres. */
USTRUCT(BlueprintType)
struct FMegaParkRail
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite) FString SourceId;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) bool Closed = false;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) TArray<FVector> Points;
    /** Untouched big-endian 120-byte cubic segment payloads; retained for native curve consumers. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite) TArray<FString> OriginalSegments;
};

/** Level-owned grind paths. Render and collision geometry are ordinary StaticMeshActors. */
UCLASS()
class YORIMICHI_API ASuperUltraMegaPark : public AActor
{
    GENERATED_BODY()
public:
    ASuperUltraMegaPark();
    virtual void BeginPlay() override;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Source") FString SourceManifestHash;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Source") TArray<FMegaParkRail> Rails;
};

/** Standalone park level: uses the existing player without spawning the island over the imported park. */
UCLASS()
class YORIMICHI_API AMegaParkGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    AMegaParkGameMode();
    virtual void BeginPlay() override;
};

/** Player services for an authored level, without generating the island or its effects. */
UCLASS()
class YORIMICHI_API AMegaParkWorld : public AJapanWorld
{
    GENERATED_BODY()
public:
    AMegaParkWorld();
    virtual void BeginPlay() override;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) FVector SpawnGround;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) float SpawnYaw = 0.f;
};

/** Import audit: exports the actual built LOD triangles for source comparison. */
UCLASS()
class YORIMICHI_API UMegaParkValidation : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable) static bool DumpMeshTriangles(UStaticMesh* Mesh, FVector Origin, const FString& Path);
    UFUNCTION(BlueprintCallable) static bool ReviewCamera(FVector Location, FVector Target, float Fov = 65.f);
    UFUNCTION(BlueprintCallable) static void RestorePlayerCamera();
};

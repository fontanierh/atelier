#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SkiPark.generated.h"

class UProceduralMeshComponent;
class UMaterialInterface;
struct FSkiParkData;

/** A terrain park (README.md, "Park"): the native park's heightfield (Private/Native/SkiPark.h) as a snow surface with
 *  collision, its jumps built for their speed windows. The actor's location is the park's origin and its yaw the fall
 *  line (park x forward, y to the left); pitch and roll are ignored. Skiers inside it read the exact surface, not the
 *  mesh. Place it on ground shaped to its base (Base) so the run-out meets the slope. */
UCLASS()
class ATELIERSKI_API ASkiPark : public AActor
{
    GENERATED_BODY()
public:
    ASkiPark();
    virtual ~ASkiPark() override;
    virtual void OnConstruction(const FTransform& Transform) override;
    virtual void BeginPlay() override;

    /** The surface at a world point (cm): its height and upward normal. False outside the park. */
    bool Sample(double X, double Y, double& OutZ, FVector& OutNormal) const;
    /** Where a run starts: on the snow at the top, facing down the fall line (cm, degrees). */
    UFUNCTION(BlueprintPure, Category = Ski) FVector GetStartLocation() const;
    UFUNCTION(BlueprintPure, Category = Ski) float GetStartYaw() const { return GetActorRotation().Yaw; }

    /** Grid spacing down the fall line and across it (cm). */
    UPROPERTY(EditAnywhere, Category = Ski, meta = (ClampMin = 10)) float AlongSpacing = 50.f;
    UPROPERTY(EditAnywhere, Category = Ski, meta = (ClampMin = 10)) float AcrossSpacing = 100.f;
    /** Snow beyond the park's edges and ends (m). */
    UPROPERTY(EditAnywhere, Category = Ski, meta = (ClampMin = 0)) float Margin = 12.f;

private:
    void Build();
    bool InPark(double LocalX, double LocalY) const;

    UPROPERTY(VisibleAnywhere, Category = Ski) TObjectPtr<UProceduralMeshComponent> Surface;
    UPROPERTY() TObjectPtr<UMaterialInterface> DefaultMaterial;
    TUniquePtr<FSkiParkData> Data;
    bool bBuilt = false;
};

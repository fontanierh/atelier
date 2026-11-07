#pragma once
#include "CoreMinimal.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/AssetUserData.h"
#include "BikeMeshComponent.generated.h"

/** Cooked with each steering child; complete group identity and original true bounds. */
UCLASS()
class YORIMICHI_API UBikeSteeringBoundsData : public UAssetUserData
{
    GENERATED_BODY()
public:
    UPROPERTY() FVector Origin = FVector::ZeroVector;
    UPROPERTY() FVector Extent = FVector::ZeroVector;
    UPROPERTY() double SphereRadius = 0.;
    UPROPERTY() TArray<FName> Members;
};

/** Independent steering geometry, culled with the predecessor's complete logical bounds. */
UCLASS()
class YORIMICHI_API UBikeMeshComponent : public UStaticMeshComponent
{
    GENERATED_BODY()
public:
    static const TArray<FName>& SteeringNames();
    static bool ReadGroupBounds(const TArray<UStaticMesh*>& Parts, FBoxSphereBounds& OutBounds);
    void SetLogicalBounds(const FBoxSphereBounds& Bounds);
    /** Configure only from the complete saved group containing this component mesh. */
    UFUNCTION(BlueprintCallable, Category="Yorimichi|Import")
    bool UseSavedSteeringBounds(const TArray<UStaticMesh*>& Parts);
    /** Explicit evidence fixture only: native supported component creation/registration.
     * Production BikeComponent creates its own complete steering joint and children. */
    UFUNCTION(BlueprintCallable, Category="Yorimichi|Import")
    static UBikeMeshComponent* CreateEvidenceComponent(AActor* Owner, UStaticMesh* Mesh,
        const TArray<UStaticMesh*>& Parts);
    bool HasLogicalBoundsOverride() const { return bHasLogicalBounds; }
    const FBoxSphereBounds& GetLogicalBoundsOverride() const { return LogicalBounds; }
    /** Editor-only exact imported source bounds observation/persistence, without changing build settings. */
    UFUNCTION(BlueprintCallable, Category="Yorimichi|Import")
    static bool PrepareSteeringBounds(const TArray<UStaticMesh*>& Parts);
    UFUNCTION(BlueprintCallable, Category="Yorimichi|Import")
    static FString SteeringBounds(const TArray<UStaticMesh*>& Parts);
    /** Exact saved-source/build-policy render and cooked counts within the raw source budget. */
    UFUNCTION(BlueprintCallable, Category="Yorimichi|Import")
    static bool ValidatePart(UStaticMesh* Mesh, int32 ExpectedSourceTriangles);
    virtual FBoxSphereBounds CalcBounds(const FTransform& LocalToWorld) const override;
private:
    FBoxSphereBounds LogicalBounds = FBoxSphereBounds(ForceInit);
    bool bHasLogicalBounds = false;
};

#pragma once
#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "SkateCollisionAsset.generated.h"

class UStaticMesh;
class UPhysicalMaterial;

/** Explicit retail surface transport. Unreal SurfaceType is not a retail index. */
USTRUCT(BlueprintType)
struct ATELIERSKATE_API FSkateCollisionSurfaceProfile
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Skate") TObjectPtr<UPhysicalMaterial> PhysicalMaterial;
    /** low7: grind material; bits7..11: physics surface category; other bits retained. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Skate", meta=(ClampMin="0", ClampMax="65535")) int32 PackedSurface=0;
    /** False preserves the stock contact material loaded by the native session. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Skate") bool bOverrideContactMaterial=false;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Skate", meta=(ClampMin="0")) float StaticFriction=0;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Skate", meta=(ClampMin="0")) float DynamicFriction=0;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Skate", meta=(ClampMin="0", ClampMax="1")) float Restitution=0;
};

USTRUCT()
struct ATELIERSKATE_API FSkateCollisionConvexIndices
{
    GENERATED_BODY()
    UPROPERTY() TArray<int32> Indices;
};

/** Cooked local collision LOD. These properties survive render CPU-buffer stripping. */
UCLASS(BlueprintType)
class ATELIERSKATE_API USkateCollisionMeshData : public UDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(VisibleAnywhere, Category="Skate") TSoftObjectPtr<UStaticMesh> SourceMesh;
    UPROPERTY(VisibleAnywhere, Category="Skate") int32 FormatVersion=1;
    UPROPERTY(VisibleAnywhere, Category="Skate") int32 SourceLODForCollision=0;
    UPROPERTY(VisibleAnywhere, Category="Skate") int32 BakedLOD=0;
    UPROPERTY(VisibleAnywhere, Category="Skate") FGuid SourceBodySetupGuid;
    UPROPERTY(VisibleAnywhere, Category="Skate") FString GeometryHash;
    UPROPERTY() TArray<FVector3f> Positions;
    UPROPERTY() TArray<FVector4f> TangentZ;
    UPROPERTY() TArray<int32> Indices;
    UPROPERTY() TArray<int32> TriangleMaterialSlots;
    UPROPERTY() TArray<FSkateCollisionConvexIndices> ConvexIndices;
    bool Validate(TArray<FString>& Errors) const;
};

/** Catalog is a cooked hard-reference root; include /Game/SkateNative in cook rules. */
UCLASS(BlueprintType)
class ATELIERSKATE_API USkateCollisionAsset : public UDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(VisibleAnywhere, Category="Skate") int32 FormatVersion=1;
    /** Rebuilding immutable mesh geometry increments this value; editable member identities are scanned directly. */
    UPROPERTY(VisibleAnywhere, Category="Skate") int32 Revision=0;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Skate") TArray<TObjectPtr<USkateCollisionMeshData>> Meshes;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Skate") TArray<FSkateCollisionSurfaceProfile> SurfaceProfiles;
    const USkateCollisionMeshData* FindMesh(const UStaticMesh* Mesh) const;
    const FSkateCollisionSurfaceProfile* FindProfile(const UPhysicalMaterial* Material) const;
    bool Validate(TArray<FString>& Errors) const;
};

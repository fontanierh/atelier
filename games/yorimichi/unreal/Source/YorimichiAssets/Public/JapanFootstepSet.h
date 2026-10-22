#pragma once
#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "JapanFootstepSet.generated.h"

class USoundAttenuation;
class USoundWave;

/** One surface's pool of sliced one-shots. */
USTRUCT(BlueprintType)
struct YORIMICHIASSETS_API FJapanFootstepBank
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere,BlueprintReadWrite) TArray<TObjectPtr<USoundWave>> Steps;
};

/** The footstep library: one pool per surface, built by Scripts/import_footsteps.py from the
 *  Sonniss masters, sliced by assets/audio/footsteps/slice.py. */
UCLASS(BlueprintType)
class YORIMICHIASSETS_API UJapanFootstepSet : public UDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere,BlueprintReadWrite) TMap<FName,FJapanFootstepBank> Surfaces;
    /** Painterly material name with the MI_ prefix stripped -> surface key. */
    UPROPERTY(EditAnywhere,BlueprintReadWrite) TMap<FName,FName> MaterialSurfaces;
    UPROPERTY(EditAnywhere,BlueprintReadWrite) TObjectPtr<USoundAttenuation> Attenuation;
    UPROPERTY(EditAnywhere,BlueprintReadWrite) FName DefaultSurface = TEXT("grass");
    /** Under the forest canopy the ground is still the terrain material, so the lake bounds
     *  decide it instead. Empty disables the override. */
    UPROPERTY(EditAnywhere,BlueprintReadWrite) FName CanopySurface = TEXT("leaves");
    const FJapanFootstepBank* Find(FName Surface) const;
};

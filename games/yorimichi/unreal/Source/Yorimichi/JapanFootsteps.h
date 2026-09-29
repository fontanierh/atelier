#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Engine/DataAsset.h"
#include "JapanFootsteps.generated.h"

class AJapanWorld;
class USoundAttenuation;
class USoundWave;

/** One surface's pool of sliced one-shots. */
USTRUCT(BlueprintType)
struct FJapanFootstepBank
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere,BlueprintReadWrite) TArray<TObjectPtr<USoundWave>> Steps;
};

/** The footstep library: one pool per surface, built by Scripts/import_footsteps.py from the
 *  sliced Sonniss masters in japan/audio/footsteps. */
UCLASS(BlueprintType)
class YORIMICHI_API UJapanFootstepSet : public UDataAsset
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

/** Plays a footstep when a foot bone plants.
 *
 *  No anim notifies: the animation graph is native C++ with no Blueprint to hang them on, and
 *  the clips are regenerated from Blender on every character pass, which would drop them. Foot
 *  bone height above the capsule floor works for every clip, blend and play rate instead, and
 *  costs one trace per footfall rather than one per frame. */
UCLASS()
class YORIMICHI_API UJapanFootstepComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    UJapanFootstepComponent();
    virtual void BeginPlay() override;
    virtual void TickComponent(float Dt,ELevelTick TickType,FActorComponentTickFunction* Function) override;
    /** A landing plants both feet at once; Weight scales with the drop. */
    void Land(const FHitResult& Hit,float Weight);
    FName SurfaceAt(const FHitResult& Hit) const;
    bool IsReady() const { return Set != nullptr; }
private:
    UPROPERTY() TObjectPtr<UJapanFootstepSet> Set;
    UPROPERTY() TObjectPtr<AJapanWorld> Landscape;
    // Per foot: planted means the sound has already fired and the foot must swing clear again.
    bool bPlanted[2] = {true,true};
    float Height[2] = {0.f,0.f};
    float SincePlant[2] = {0.f,0.f};
    // Per surface shuffled queue, so the same one-shot never comes round twice in a row.
    TMap<FName,TArray<int32>> Bags;
    void Plant(int32 Side,const FVector& Foot,float Speed);
    void Play(FName Surface,const FVector& At,float Volume,float Pitch);
};

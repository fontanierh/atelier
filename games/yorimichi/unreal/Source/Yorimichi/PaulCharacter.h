#pragma once
#include "WandererCharacter.h"
#include "GarconCharacter.generated.h"

/** The HarasValley boy, with Yorimichi's complete move set on his own skeleton. */
UCLASS()
class YORIMICHI_API AGarconCharacter : public AWandererCharacter
{
    GENERATED_BODY()
public:
    AGarconCharacter();
    virtual void BeginPlay() override;
    virtual FString GetPlayableName() const override { return Name(); }
    virtual FString GetBikeRig() const override { return TEXT("Garcon"); }
    virtual bool PlantsFeet() const override { return true; }
    static FString Name() { return TEXT("Garcon"); }
    static bool IsBuilt();
};

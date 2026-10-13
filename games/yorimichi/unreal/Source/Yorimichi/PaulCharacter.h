#pragma once
#include "WandererCharacter.h"
#include "PaulCharacter.generated.h"

/** The HarasValley boy, with Yorimichi's complete move set on his own skeleton. */
UCLASS()
class YORIMICHI_API APaulCharacter : public AWandererCharacter
{
    GENERATED_BODY()
public:
    APaulCharacter();
    virtual void BeginPlay() override;
    virtual FString GetPlayableName() const override { return Name(); }
    virtual FString GetBikeRig() const override { return TEXT("Paul"); }
    virtual bool PlantsFeet() const override { return true; }
    static FString Name() { return TEXT("Paul"); }
    static bool IsBuilt();
};

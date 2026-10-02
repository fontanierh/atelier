#pragma once
#include "CoreMinimal.h"
#include "WandererCharacter.h"
#include "BotwRider.generated.h"

/**
 * A BOTW character as the player (-rider=<Name>, e.g. -rider=Bokoblin): the same controls, animation graph and
 * skateboarding as Cairo, on the character's own mesh. import_botw.py makes its definition, DA_<Name>Rider, with a
 * locomotion blend of its idle, walk and run clips and the bone map the board's retargeter reads (GetSkateBone).
 */
UCLASS()
class YORIMICHI_API ABotwRider : public AWandererCharacter
{
    GENERATED_BODY()
public:
    ABotwRider(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
    virtual void BeginPlay() override;
    /** The rider the command line asks for, when its definition was imported; empty otherwise. */
    static FString Requested();
    /** The pawn class a game mode uses: this class when a rider is requested, else null (the mode's own default). */
    static UClass* PawnOverride();
};

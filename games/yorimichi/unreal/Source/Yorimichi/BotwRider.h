#pragma once
#include "CoreMinimal.h"
#include "WandererCharacter.h"
#include "BotwRider.generated.h"

/**
 * A BOTW character as the player (-rider=<Name>, e.g. -rider=Bokoblin): the same controls, animation graph and
 * skateboarding as Cairo, on the character's own mesh. import_botw.py makes its definition, DA_<Name>Rider, with a
 * locomotion blend of its idle, walk and run clips and the bone map the board's retargeter reads (GetSkateBone). A rider
 * whose roster entry has a move set (Link) plays it (UBotwMoveSet): BOTW's jumps, paraglider, climbing, swimming and
 * sword and shield.
 */
UCLASS()
class YORIMICHI_API ABotwRider : public AWandererCharacter
{
    GENERATED_BODY()
public:
    ABotwRider(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
    virtual void BeginPlay() override;
    virtual void ConfigureNetworkRider(const FString& Name, bool bShield) override;
    // Crouching keeps the mesh where Fit stood it (ACharacter puts it back to the class default's height).
    virtual void OnStartCrouch(float HalfHeightAdjust, float ScaledHalfHeightAdjust) override;
    virtual void OnEndCrouch(float HalfHeightAdjust, float ScaledHalfHeightAdjust) override;
    /** The rider the command line asks for, when its definition was imported; empty otherwise. "CairoBotw" is Cairo with
     *  the BotW move set (ACairoCharacter::BotwName). */
    static FString Requested();
    /** The pawn class a game mode uses when a rider is requested (this class, or Cairo's for CairoBotw), else null (the
     *  mode's own default). */
    static UClass* PawnOverride();
    /** The BOTW characters the character switch offers: those with a move set (Link) and an imported rider definition,
     *  in roster order. Checks the definitions exist without loading them. */
    static TArray<FString> Available();
    /** The playing character's name: the rider's, "Cairo" or "CairoBotw". */
    static FString NameOf(const AWandererCharacter* Character);
    /** A playable name as the character switch shows it. */
    static FString Label(const FString& Name);
    /** The Esc menu's character switch: From's player becomes Name ("Cairo", "CairoBotw" or a rider), standing where From
     *  stood and looking the same way; From is destroyed. Refused (null) on the zeppelin and before From is ready. The
     *  menu offers Cairo with the merged move set whenever it is built. */
    static AWandererCharacter* SwitchPlayer(AWandererCharacter* From, const FString& Name);
private:
    FString RiderName;
    float FitMeshZ = 0.f;
    /** Sizes the capsule and stands the mesh in it from the rider's roster entry. */
    void Fit();
};

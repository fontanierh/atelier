#pragma once
#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "WandererDefinition.generated.h"

class USkeletalMesh;
class UAnimSequence;
class UBlendSpace;
class UStaticMesh;

/** Gameplay timing of one sword clip, in clip seconds at 1x (from the game-r13 manifest). */
USTRUCT(BlueprintType)
struct FWandererSwordClip
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, BlueprintReadOnly) FName Role;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float Duration = 0.f;
    // Blade sweeps register hits only inside [ActiveStart, ActiveEnd].
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float ActiveStart = -1.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float ActiveEnd = -1.f;
    // A buffered attack press chains into the next strike from LinkStart; movement/roll/dash cancel from Cancel.
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float LinkStart = -1.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float Cancel = -1.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float Counter = -1.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) bool RootMotion = false;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float EndYaw = 0.f;
    // Where the blade meets a target (strikes, combat-r02): bearing from the facing at the start, positive to the
    // character's left (the clip's own convention), and distance in cm from the start position.
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float ContactYaw = 0.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float ContactDistance = -1.f;
};

/** Cookable character content: no loose animation files or runtime skeleton baking. */
UCLASS(BlueprintType)
class YORIMICHI_API UWandererDefinition : public UDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TObjectPtr<USkeletalMesh> Mesh;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TObjectPtr<UBlendSpace> Locomotion;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TObjectPtr<UBlendSpace> Crouching;
    // Locomotion with the sword swinging in the right hand (game-r16), same samples and speeds as Locomotion. Only its
    // right arm is played, over the body's locomotion, while the sword is out. Null: the guard's arm is held instead.
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TObjectPtr<UBlendSpace> ArmedLocomotion;
    // The same for Crouching: the crouch clips' own right arm with the sword.
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TObjectPtr<UBlendSpace> ArmedCrouching;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TMap<FName, TObjectPtr<UAnimSequence>> Actions;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) bool UseAuthoredMovement = false;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) FVector2D RestAnkleHeights = FVector2D(11.2,11.2);
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float SoleHeight = .65f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TArray<FVector2D> GroundDashProfile;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TArray<FVector2D> AirDashProfile;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TArray<FVector2D> RollProfile;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float RollDiveTakeoff = 0.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float RollDiveTouchdown = 0.f;
    // Framing and authored gait speeds belong to each character's content.
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float CameraHeight = 35.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float WalkSpeed = 90.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float JogSpeed = 180.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float RunSpeed = 300.f;
    // Speed of the fastest locomotion sample (a sprint clip); the graph only speeds playback up beyond it. 0 = the run clip is the top.
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float SprintSpeed = 0.f;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) float CrouchSpeed = 50.f;
    // Sword combat set (game-r13): the bokken static mesh, its rest attachment relative to the hand bone,
    // the blade segment in mesh-local cm and per-clip gameplay windows. Empty when the set is not installed.
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TObjectPtr<UStaticMesh> SwordMesh;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) FName SwordAttachBone = TEXT("hand_R");
    UPROPERTY(EditAnywhere, BlueprintReadOnly) FTransform SwordAttach;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) FVector SwordBladeStart = FVector::ZeroVector;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) FVector SwordBladeEnd = FVector::ZeroVector;
    UPROPERTY(EditAnywhere, BlueprintReadOnly) TArray<FWandererSwordClip> SwordClips;
    UAnimSequence* FindAction(FName Name) const;
    const FWandererSwordClip* FindSwordClip(FName Role) const;
    bool HasSwordSet() const { return SwordMesh != nullptr && SwordClips.Num() > 0; }
};

/** Headless content authoring support; the resulting blend spaces are ordinary saved assets. */
UCLASS()
class YORIMICHI_API UWandererContentLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category="Wanderer|Authoring")
    static bool ConfigureBlendSpace(UBlendSpace* Asset, const TArray<UAnimSequence*>& Clips, const TArray<float>& Speeds);
    UFUNCTION(BlueprintCallable, Category="Wanderer|Authoring")
    static bool ConfigureMeshLODs(USkeletalMesh* Asset);
};

#pragma once
#include "WandererCharacter.h"
#include "NoxCharacter.generated.h"

/** Nox: the approved separate head/body assembly with the full merged move set and
 * procedural bike clips. Skate poses retarget to the same humanoid contract at runtime.
 * Select with -rider=Nox or the character menu once unreal.nox_adventure is built.
 */
UCLASS()
class YORIMICHI_API ANoxCharacter : public AWandererCharacter
{
    GENERATED_BODY()
public:
    ANoxCharacter();
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    virtual FString GetPlayableName() const override { return Name(); }
    virtual FString GetBikeRig() const override { return TEXT("Nox"); }
    virtual bool PlantsFeet() const override { return true; }
    /** The bomber and hoodie extend beyond the torso skin. */
    virtual float GetSkateClothingClearance() const override { return 3.f; }
    /** Retain the rounded boot soles in the fitted bail collision. */
    virtual int32 GetSkateCollisionHullDirections() const override { return 1024; }
    /** His seat correctives for that pose (NoxSeatMorph.h), as DriveSeat sets them, so the skin measures sample the skin
     *  as drawn. */
    virtual void GetSkatePoseMorphs(const USkeletalMeshComponent* Mesh, TConstArrayView<FTransform> Pose,
                                    TArray<TPair<FName, float>>& Morphs) const override;
    // Only his longer legs move the sailboat stance; Cairo and the others keep it as it was fitted.
    virtual float SailboatReach(float LegLength) const override { return FMath::Clamp(LegLength / 55.f, 1.f, 1.6f); }
    /** His name for -rider= and the character switch. */
    static FString Name() { return TEXT("Nox"); }
    /** His definition and move record (Content/Data/nox/adventure.json) are imported; checked on disk, never loaded. */
    static bool IsBuilt();

private:
    /** Finds the seat correctives' targets and bones on the mesh's current asset. An asset with no seat target and no
     *  contact data has none (logged once). One with either needs every moving target, unambiguous, its bones, and
     *  valid USkinMorphContactData holding those targets; otherwise it logs FAILED and leaves them off (every weight 0). */
    void ResolveSeat();
    /** Sets the seat correctives for the mesh's final pose (animation, the skating retarget, physics or a streamed
     *  pose), each time its bone transforms are finalized. */
    void DriveSeat();
    /** Both hips' flexion (degrees, forward positive) in a component-space pose of the resolved asset. */
    bool SeatFlexion(TConstArrayView<FTransform> Pose, float& FlexL, float& FlexR) const;

    FDelegateHandle SeatFinalized;
    TWeakObjectPtr<USkeletalMeshComponent> SeatComponent;
    TWeakObjectPtr<const USkeletalMesh> SeatMesh;
    /** The native target of each grid cell (NoxSeat::Index); NAME_None for a zero cell the model does not carry. */
    TArray<FName> SeatTargets;
    /** The weights last set, per grid cell. */
    TArray<float> SeatShown;
    int32 SeatPelvis = INDEX_NONE;
    int32 SeatThighs[2] = {INDEX_NONE, INDEX_NONE};
    FQuat SeatPelvisBind = FQuat::Identity;
    FQuat SeatThighBinds[2] = {FQuat::Identity, FQuat::Identity};
    /** Each thigh's neutral head-to-shin direction, and his forward and up, in component space. */
    FVector SeatAxes[2] = {FVector::DownVector, FVector::DownVector};
    FVector SeatForward = FVector::ForwardVector;
    FVector SeatUp = FVector::UpVector;
    bool bSeatResolved = false;
    bool bSeatReady = false;
};

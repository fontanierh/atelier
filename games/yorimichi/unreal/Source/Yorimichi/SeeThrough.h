#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "SeeThrough.generated.h"

class AJapanWorld;
class UMaterialParameterCollection;
class UStaticMesh;

/** Camera see-through (docs/CAMERA.md). The switches are japan.SeeThrough, japan.SeeThroughHole and
 *  japan.SeeThroughRadius. */
namespace JapanSeeThrough
{
    YORIMICHI_API bool IsEnabled();
    /** The fallback: the first version's round hole round Cairo and the tree house room cutaway (off by default). */
    YORIMICHI_API bool IsHole();
    YORIMICHI_API float Radius();
    /** On the tree house's instance groups. The camera arm keeps above the floor he stands on there, and in hole
     *  mode its probe passes them. */
    extern YORIMICHI_API const FName Tag;

    // How a mesh group fades, in its custom primitive data 0 (the materials' FadeMode):
    // - solid: stops the camera (the arm stays in front of it), and only fades right at the lens (5 to 15 cm);
    // - instances: lets the camera through, and each instance fades whole, from its own position and bounds, where it
    //   hides Cairo or crowds the lens;
    // - pieces: lets the camera through, and each piece of the merged mesh fades whole, from the centre and axis baked
    //   in its UV channels 1 to 4;
    // - near only: lets the camera through, and only fades near the lens (10 to 40 cm).
    constexpr int32 FadeSolid = 0;
    constexpr int32 FadeInstances = 1;
    constexpr int32 FadePieces = 2;
    constexpr int32 FadeNearOnly = 3;
    /** The fade mode of the world.json group Key drawn with Mesh. */
    YORIMICHI_API int32 FadeMode(const FString& Key, const UStaticMesh* Mesh);
}

/** Feeds /Game/SeeThrough/MPC_SeeThrough every frame from the player's pawn:
 *  - where Cairo stands;
 *  - where the camera is, smoothed;
 *  - how strong the fades are;
 *  - the trail of where he walked in the last second.
 *  The materials that read it (unreal/Scripts/see_through.py) use it as Breath of the Wild does:
 *  - the thin things between the camera and him fade out whole and come back;
 *  - everything fades right at the lens;
 *  - he fades when the camera comes too close;
 *  - the noren part round him and swing back along the trail he walked.
 *  With japan.SeeThroughHole 1 it drives the first version instead: a round hole round him, and in the tree house the
 *  room's near walls and roof cut away and the camera probe passing the house (AJapanWorld::SetSeeThroughProbe). */
UCLASS()
class YORIMICHI_API USeeThroughComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    USeeThroughComponent();
    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

private:
    UPROPERTY() TObjectPtr<UMaterialParameterCollection> Collection;
    TWeakObjectPtr<AJapanWorld> House;
    bool bLookedUp = false;
    bool bHouseCut = false;
    bool bLogged = false;
    int32 LoggedHole = -1;
    float Strength = 0.f;
    float HoleBlend = 0.f;
    bool bEyeSet = false;
    FVector Eye = FVector::ZeroVector;
    int32 Room = INDEX_NONE;
    float RoomBlend = 0.f;
    FVector Trail[4] = {FVector::ZeroVector, FVector::ZeroVector, FVector::ZeroVector, FVector::ZeroVector};
    double TrailTime[4] = {0., 0., 0., 0.};
    int32 TrailFilled = 0;
    FVector LastAt = FVector::ZeroVector;
};

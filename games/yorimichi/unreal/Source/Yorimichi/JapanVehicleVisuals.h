#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "Components/SkeletalMeshComponent.h"

namespace JapanVehicleVisuals
{
/** CMC owns the smoothing residual; vehicle pitch/lean only replaces the authored base. */
inline void SetRiderPose(ACharacter* Rider,const FVector& Location,const FQuat& Rotation,bool PreserveSmoothing=true)
{
    auto* Mesh=Rider->GetMesh();
    FVector Residual=FVector::ZeroVector;
    FQuat Turn=FQuat::Identity;
    const bool Online=Rider->GetNetMode()!=NM_Standalone;
    if(Online&&PreserveSmoothing&&!Rider->IsLocallyControlled())
    {
        Residual=Mesh->GetRelativeLocation()-Rider->GetBaseTranslationOffset();
        Turn=Mesh->GetRelativeRotation().Quaternion()*Rider->GetBaseRotationOffset().Inverse();
    }
    if(Online)Rider->CacheInitialMeshOffset(Location,Rotation.Rotator());
    Mesh->SetRelativeLocationAndRotation(Location+Residual,(Turn*Rotation).GetNormalized());
}

/** Remove the authored mesh base from CMC's smoothed mesh to get a visual capsule frame.
 * Boat graphics follow this frame; simulation and collision keep using the real capsule. */
inline FTransform SmoothedRoot(const ACharacter* Rider)
{
    if(Rider->GetNetMode()==NM_Standalone||Rider->IsLocallyControlled())return Rider->GetActorTransform();
    const auto* Mesh=Rider->GetMesh();
    const FTransform Base(Rider->GetBaseRotationOffset(),Rider->GetBaseTranslationOffset(),Mesh->GetRelativeScale3D());
    return Base.Inverse()*Mesh->GetComponentTransform();
}
}

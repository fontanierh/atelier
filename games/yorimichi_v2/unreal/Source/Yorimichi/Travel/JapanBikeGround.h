#pragma once
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Components/SceneComponent.h"

namespace JapanBikeGround
{
/** Finish the grounded step-off placement before its activity snapshot is published.
 * This runs only the ordinary swept floor adjustment, without consuming movement time. */
inline bool SettlePark(ACharacter* Rider)
{
    auto* Movement=Rider?Rider->GetCharacterMovement():nullptr;
    if(!Movement||!Movement->IsMovingOnGround()||!Movement->UpdatedComponent)return false;
    Movement->FindFloor(Movement->UpdatedComponent->GetComponentLocation(),Movement->CurrentFloor,false);
    if(!Movement->CurrentFloor.IsWalkableFloor())return false;
    Movement->AdjustFloorHeight();
    Movement->SetBaseFromFloor(Movement->CurrentFloor);
    return true;
}
}

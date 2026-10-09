#pragma once
#include "PlayerStateCoordinator.h"
#include "AirPhaseRuntime.h"
#include "GrindRuntime.h"
namespace atelier::skate
{
// Air borrows the very same physical/processed/toolkit/post owners here. Its
// binding computes real selector inputs before grab publication is consumed.
bool CompletePlayerPostInput(PlayerStateCoordinatorOwners,AirPhaseOwners,
    const PlayerGrindMaterials&,GrindRuntime&,std::string& error);
}

// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AirTrajectorySelectorTypes.h"
namespace atelier::skate
{
struct AirTrajectoryLaunchBatch
{
    std::vector<AirTrajectoryQueryRequest> requests;
    std::vector<Vec4> velocities;
    Vec4 origin,board_position,local_board_position,local_com_position,com_displacement;
};
bool AdjustAirTrajectoryLaunchVelocity(AirLaunchInfo&,AirSelectorInput,const AirTrajectorySelectorSettings&);
std::vector<Vec4> AirTrajectoryCandidateVelocities(const AirLaunchInfo&,const AirTrajectorySelectorSettings&);
AirTrajectoryLaunchBatch BuildAirTrajectoryLaunchBatch(const AirLaunchInfo&,AirSelectorInput,const AirTrajectorySelectorSettings&);
void AdjustAirTrajectoryVelocity(AirTrajectory&,std::int32_t frame,Vec4 adjustment,float maximum);
}

#pragma once
#include "AirTrajectorySelectorTypes.h"
namespace atelier::skate
{
// Updates candidates in source order. A service error retains all preceding
// mutations and leaves all_miss unchanged, matching Result propagation.
bool ScoreAirTrajectoryCandidates(AirTrajectoryCandidate* candidates,std::size_t count,
    std::uint16_t pass,bool adjusted_on_vert,AirSelectorInput,const AirTrajectorySelectorSettings&,
    AirTrajectorySelectionServices&,bool& all_miss,std::string& error);
}

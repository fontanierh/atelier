#pragma once
#include "WipeoutPhysicalState.h"
#include "AirTrajectoryRuntime.h"
namespace atelier::skate
{
struct WipeoutPredictionPending {AirTrajectoryQueryResult result;AirTrajectory trajectory;bool surface_query;};
struct WipeoutPrediction
{
    AirTrajectoryQueryResult result=AirTrajectoryQueryResult::Miss();
    std::optional<WipeoutPredictionPending> pending;
    void Reset(){pending.reset();result=AirTrajectoryQueryResult::Miss();}
    bool Advance(WipeoutPhysicalState&,const WorldGeometry&,Vec4 com_position,Vec4 gravity,std::string& error);
};
}

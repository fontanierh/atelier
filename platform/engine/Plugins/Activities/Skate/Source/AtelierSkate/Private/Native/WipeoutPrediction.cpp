// SPDX-License-Identifier: Apache-2.0
#include "WipeoutPrediction.h"
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
bool WipeoutPrediction::Advance(WipeoutPhysicalState& state,const WorldGeometry& world,Vec4 position,Vec4 gravity,std::string& error)
{
    if(pending){const auto completed=*pending;pending.reset();result=completed.result;
        if(completed.surface_query){if(!(result.contact_time>=0)||(result.surface&0xf80)!=0x600){state.below_surface=false;state.special_surface=false;}}
        else if(result.contact_time>=0){state.predicted_time=result.contact_time;state.imminent_surface_twelve=(result.surface&0xf80)==0x600&&result.contact_time<0.1f;state.predicted_position=AirTrajectoryPositionAt(completed.trajectory,result.contact_time);}
        else state.predicted_position=AirTrajectoryPositionAt(completed.trajectory,3.0f);
    }
    const bool surface_query=state.below_surface;state.surface_query=surface_query;AirTrajectoryQueryRequest request;
    if(surface_query){position[1]=state.surface_height+0.1f;request={{position,{0,-0.2f,0,0},{},1.0f},0.01f,1.0f,1.0f};}
    else request={{position,state.velocity,gravity,3.0f},0.3f,1.0f,1.0f};
    AirTrajectoryQueryResult completed;if(!AirTrajectoryRuntime::Query(world,request,completed,error))return false;
    result=completed;pending=WipeoutPredictionPending{completed,request.trajectory,surface_query};return true;
}
}

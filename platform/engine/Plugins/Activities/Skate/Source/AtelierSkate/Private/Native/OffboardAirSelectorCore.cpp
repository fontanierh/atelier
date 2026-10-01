// SPDX-License-Identifier: Apache-2.0
#include "OffboardAirMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
OffboardAirSelectorCore::OffboardAirSelectorCore(OffboardAirLaunchPacket p):sampling(OffboardAirSampling::ResetSampling(p.scalar_100)),launch(p)
{sampling.restart_allowed_8493=false;sampling.selection.landing_frame_8480=0;}
void OffboardAirSelectorCore::Reset(){const auto p=launch;*this=OffboardAirSelectorCore(p);sampling=OffboardAirSampling::ResetSampling(launch.scalar_100);}
void OffboardAirSelectorCore::Exit(){sampling.pending_8492=false;sampling.preinitialized_8494=false;}
AirTrajectoryQueryRequest OffboardAirRequest(AirTrajectory t,float radius){t.scalar_48=2;return {t,radius,.25f,1.2f};}
bool ValidateOffboardAirRequest(AirTrajectoryQueryRequest q,std::string& error)
{
    const std::array<float,4> scalars{q.trajectory.scalar_48,q.radius,q.start_error,q.end_error};
    for(const auto v:scalars)if(!std::isfinite(v)||v<=0){error="Invalid native BipedAir trajectory request";return false;}
    for(const auto& v:{q.trajectory.position,q.trajectory.velocity,q.trajectory.acceleration})for(const auto x:v)if(!std::isfinite(x)){error="Invalid native BipedAir trajectory request";return false;}
    error.clear();return true;
}
bool OffboardAirSelectorCore::BeginLaunch(OffboardAirLaunchPacket p,Vec4 gravity,OffboardAirQuerySettings s,std::vector<AirTrajectoryQueryRequest>& requests,std::string& error)
{
    std::vector<OffboardAirCandidate> next;Vec4 offset{},correction{};if(!offboard_air_math::Prepare(p,gravity,s,next,offset,correction,error))return false;
    Reset();launch=p;sampling.selection.candidate_scalar_100=p.scalar_100;sampling.SeedFallback(p.position_32,p.velocity_0,gravity);
    offset_8272=offset;correction_8304=correction;candidates=std::move(next);requests.clear();
    for(const auto& c:candidates)requests.push_back(OffboardAirRequest(c.trajectory,s.sphere_radius));
    for(const auto& q:requests)predictions.push_back({AirTrajectoryQueryResult::Miss(),q});scores.assign(requests.size(),0);
    error.clear();return true;
}
bool OffboardAirSelectorCore::BeginRequery(std::uint32_t flags2472,std::uint32_t flags2488,float radius,std::optional<AirTrajectoryQueryRequest>& output,std::string& error)
{
    output.reset();if((flags2472&0x10000000)!=0||(flags2488&0x400000)!=0||!sampling.restart_allowed_8493){error.clear();return true;}
    const auto request=OffboardAirRequest(selected_candidate.trajectory,radius);if(!ValidateOffboardAirRequest(request,error))return false;
    sampling.restart_allowed_8493=false;requery_pending_8499=true;
    if(!predictions.empty())predictions[0]={AirTrajectoryQueryResult::Miss(),request};output=request;error.clear();return true;
}
}

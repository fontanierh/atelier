// SPDX-License-Identifier: Apache-2.0
#include "OffboardAirSelector.h"
#include "OffboardAirMath.h"
#include "OffboardStaticScene.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
void OffboardAirSelector::Reset(){core=OffboardAirSelectorCore();completed_launch_.reset();completed_requery_.reset();}
bool OffboardAirSelector::Launch(const WorldGeometry& world,OffboardAirLaunchPacket packet,Vec4 gravity,OffboardAirContext context,std::string& error)
{
    auto next=core;std::vector<AirTrajectoryQueryRequest> requests;if(!next.BeginLaunch(packet,gravity,settings.query,requests,error))return false;
    const auto scene=OffboardStaticScene::Create(world,error);if(!scene)return false;std::vector<AirTrajectoryQueryResult> results;results.reserve(requests.size());
    for(const auto& request:requests){AirTrajectoryQueryResult result;if(!scene->Trajectory(request,context.matching_group_2952,0x6000,result,error))return false;results.push_back(result);}
    core=std::move(next);completed_launch_=std::move(results);completed_requery_.reset();error.clear();return true;
}
bool OffboardAirSelector::ConsumeLaunch(const WorldGeometry& world,OffboardAirContext context,float half,std::optional<std::size_t>& output,std::string& error)
{
    output.reset();if(!completed_launch_||!core.sampling.pending_8492){error.clear();return true;}
    auto next=core;if(!next.ObserveLaunch(*completed_launch_,error))return false;const auto first=next.candidates[0];const auto prediction=next.predictions[0];
    std::optional<OffboardAirLedgeAdjustment> adjustment;
    if(const auto search=SearchOffboardAirLedge(first,prediction,context))
    {
        const std::vector<OffboardGroundEdgeBody> empty;const std::vector<OffboardGroundAlternateRecord> alternates;const std::vector<OffboardGroundIndexedBody> indexed;
        const auto scene=OffboardGroundScene::Create(world,{empty,empty,alternates,indexed,false},error);if(!scene)return false;
        const auto edges=scene->EdgeCandidates(*search),filtered=FilterOffboardAirLedges(edges,first.trajectory.position);
        const auto chosen=ChooseOffboardAirLedge(first,prediction,context,settings.query.sphere_radius,filtered);
        if(chosen)
        {
            if(!std::isfinite(half)||half<=0){error="BipedAir ledge requires actual positive board half-wheelbase";return false;}
            if(const auto lines=OffboardAirLedgeLines(*chosen,half))
            {
                std::vector<OffboardLineProbe> probes;for(const auto& line:*lines)probes.push_back({offboard_air_math::Lanes(line.start),offboard_air_math::Lanes(line.end),line.radius});
                const auto static_scene=OffboardStaticScene::Create(world,error);if(!static_scene)return false;std::vector<std::optional<OffboardLineHit>> hits;
                if(!static_scene->Lines(probes,context.matching_group_2952,hits,error)||!ConsumeOffboardAirLedgeLines(hits.size(),error))return false;adjustment=chosen;
            }
        }
    }
    std::size_t index=0;if(!next.SelectLaunch(context,first,adjustment,index,error))return false;core=std::move(next);completed_launch_.reset();output=index;error.clear();return true;
}
bool OffboardAirSelector::Requery(const WorldGeometry& world,OffboardAirContext context,std::uint32_t flags2472,std::uint32_t flags2488,bool& output,std::string& error)
{
    output=false;auto next=core;std::optional<AirTrajectoryQueryRequest> request;if(!next.BeginRequery(flags2472,flags2488,settings.query.sphere_radius,request,error))return false;
    if(!request){error.clear();return true;}const auto scene=OffboardStaticScene::Create(world,error);if(!scene)return false;AirTrajectoryQueryResult result;
    if(!scene->Trajectory(*request,context.matching_group_2952,0x6000,result,error))return false;core=std::move(next);completed_requery_=OffboardAirPrediction{result,*request};
    if(completed_launch_&&!completed_launch_->empty())(*completed_launch_)[0]=result;if(!core.predictions.empty())core.predictions[0]={result,*request};output=true;error.clear();return true;
}
bool OffboardAirSelector::ConsumeRequery(bool& output,std::string& error)
{
    output=false;if(!completed_requery_){error.clear();return true;}const auto prediction=core.predictions.empty()?*completed_requery_:core.predictions[0];
    if(!core.CompleteRequery(prediction,error))return false;completed_requery_.reset();output=true;error.clear();return true;
}
bool OffboardAirSelector::Consume(const WorldGeometry& world,OffboardAirContext context,float half,std::optional<std::size_t>& output,std::string& error)
{
    core.sampling.preinitialized_8494=false;output.reset();if(core.sampling.pending_8492&&!ConsumeLaunch(world,context,half,output,error))return false;
    if(core.requery_pending_8499){bool consumed=false;if(!ConsumeRequery(consumed,error))return false;}core.sampling.restart_allowed_8493=true;error.clear();return true;
}
}

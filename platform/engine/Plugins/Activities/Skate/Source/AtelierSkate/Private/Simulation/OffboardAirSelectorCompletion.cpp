#include "OffboardAirMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
bool OffboardAirSelectorCore::ObserveLaunch(const std::vector<AirTrajectoryQueryResult>& results,std::string& error)
{
    using namespace offboard_air_math;if(!sampling.pending_8492||results.size()!=candidates.size()){error="BipedAir launch completion does not match pending batch";return false;}
    const auto count=std::min(std::min(candidates.size(),predictions.size()),results.size());
    for(std::size_t n=0;n<count;++n)
    {
        auto& c=candidates[n];auto& p=predictions[n];const auto result=results[n];p.result=result;
        if(Valid(result)){c.contact_position_96=result.contact_position;c.normal_64=SuggestedNormal(result);p.result.contact_normal=c.normal_64;
            c.contact_velocity_80=AirTrajectoryVelocityAt(c.trajectory,float(result.contact_frame)*Step());c.landing_frame_116=result.contact_frame;c.valid_120=true;}
        else{c.normal_64=Up;c.contact_velocity_80={};c.landing_frame_116=120;c.valid_120=false;}
    }
    error.clear();return true;
}
bool OffboardAirSelectorCore::SelectLaunch(OffboardAirContext context,OffboardAirCandidate original_first,std::optional<OffboardAirLedgeAdjustment> ledge,std::size_t& output,std::string& error)
{
    using namespace offboard_air_math;if(!sampling.pending_8492||candidates.empty()){error="BipedAir select without pending launch";return false;}
    if(ledge){ledge->Apply(candidates[0]);ledge_normal_8320=candidates[0].normal_64;ledge_selected_8496=true;}
    for(std::size_t n=0;n<candidates.size();++n)
    {
        const auto c=candidates[n];scores[n]=0;if(!c.valid_120)continue;
        const auto original=n==0?original_first:c;const auto displacement=Sub(original.contact_position_96,original.trajectory.position),normal=original.normal_64;
        const auto time=float(c.landing_frame_116)*Step();float ledge_bonus=n==0&&ledge_selected_8496?1:0,time_penalty=0;
        if(time<=.5f){ledge_bonus=0;time_penalty=-1-(.5f-time)*2;}const float center_bonus=n==0?1:0;
        if((predictions[n].result.surface&0xf80)==0x300)predictions[n].result.contact_normal=context.up_544;
        auto normal_penalty=VectorMin(2.2222223f*((normal[1]-.45f)*5),0);if(Dot(normal,launch.forward_64)>0)normal_penalty=0;
        auto forward=VectorMax(Dot(launch.forward_64,displacement),1),height=VectorMax(displacement[1],0);
        if(n>=launch.kind_108){if(displacement[1]<.4f)height-=10000;else{height*=8;forward=Dot(launch.secondary_velocity_16,displacement);}}
        scores[n]=((((0+forward)+height)+normal_penalty)+center_bonus)+time_penalty+ledge_bonus;
    }
    auto best=Bits(0xccbebc20);std::size_t index=0;for(std::size_t n=0;n<scores.size();++n)if(scores[n]>best){best=scores[n];index=n;}
    selected_index=index;selected_candidate=candidates[index];if(sampling.Commit(selected_candidate,predictions[index],offset_8272))just_changed_8497=true;
    output=index;error.clear();return true;
}
bool OffboardAirSelectorCore::CompleteRequery(OffboardAirPrediction prediction,std::string& error)
{
    using namespace offboard_air_math;if(!requery_pending_8499){error="BipedAir requery completion without submission";return false;}
    requery_pending_8499=false;if(!predictions.empty())predictions[0]=prediction;if(!Valid(prediction.result)){error.clear();return true;}
    const auto result=prediction.result;
    if(requery_count_8488<=0){requery_position_8352=result.contact_position;requery_normal_8368=SuggestedNormal(result);}
    else
    {
        const auto delta=Sub(requery_position_8352,result.contact_position);
        if(Dot(delta,delta)>.0001f)
        {
            requery_position_8352=result.contact_position;requery_normal_8368=SuggestedNormal(result);auto& s=sampling.selection;
            s.landing_frame_8480=result.contact_frame;s.scalar_8392=float(result.contact_frame)*Step();
            s.velocity_6160=AirTrajectoryVelocityAt(prediction.request.trajectory,float(result.contact_frame)*Step());s.position_6176=result.contact_position;s.normal_6144=SuggestedNormal(result);
        }
    }
    requery_count_8488=WrappingAdd(requery_count_8488,1);error.clear();return true;
}
}

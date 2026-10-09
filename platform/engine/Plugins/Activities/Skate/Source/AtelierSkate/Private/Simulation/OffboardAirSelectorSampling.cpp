#include "OffboardAirMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
void BipedAirTrajectoryResult::Reset()
{
    position_272={};velocity_288={};normal_304={};contact_velocity_320={};contact_position_336={};
    time_remaining_384=0;duration_388=0;scalar_392=0;frame_400=0;valid_404=false;word_408=0;
}
OffboardAirSampling OffboardAirSampling::ResetSampling(float retained)
{OffboardAirSampling s;s.selection.candidate_scalar_100=retained;return s;}
void OffboardAirSampling::SeedFallback(Vec4 p,Vec4 v,Vec4 g){fallback_8208={p,v,g,2};pending_8492=true;}
bool OffboardAirSampling::Commit(OffboardAirCandidate c,OffboardAirPrediction& p,Vec4 offset)
{
    using namespace offboard_air_math;pending_8492=false;const auto time=float(WrappingNeg(c.start_frame_112))*Step();
    if(Valid(p.result)){p.result.contact_frame=WrappingAdd(p.result.contact_frame,c.start_frame_112);p.result.contact_time-=time;}
    Shift(p.request.trajectory,time);auto trajectory=c.trajectory;Shift(trajectory,time);
    for(std::size_t n=0;n<4;++n)trajectory.position[n]+=(-offset[n]);
    auto duration=selection.scalar_8392;auto word=selection.word_8396;const auto contact=Valid(p.result);
    if(contact){duration=float(c.landing_frame_116)*Step();word=c.special_121?2:(p.result.surface>>7)&0x1f;}
    selection={trajectory,c.normal_64,c.contact_velocity_80,c.contact_position_96,c.valid_120,true,c.landing_frame_116,duration,word,c.contact_position_96[1]};
    preinitialized_8494=true;return contact;
}
void OffboardAirSampling::Sample(std::int32_t frame,float timestep,const PointGraph<8>& curve,BipedAirTrajectoryResult& out)
{
    using namespace offboard_air_math;frame_8484=frame;const auto time=float(frame)*Step();const auto s=selection;
    if(pending_8492){out.position_272=AirTrajectoryPositionAt(fallback_8208,time);out.velocity_288=AirTrajectoryVelocityAt(fallback_8208,time);out.valid_404=false;out.contact_position_336={};out.normal_304=Up;out.contact_velocity_320={};}
    else
    {
        elapsed_8388+=timestep;blend_8384=curve.Evaluate(elapsed_8388);const auto first=AirTrajectoryPositionAt(s.trajectory_8144,time),second=AirTrajectoryPositionAt(fallback_8208,time);
        for(std::size_t n=0;n<4;++n)out.position_272[n]=std::fma(second[n],1-blend_8384,first[n]*blend_8384);
        out.velocity_288=AirTrajectoryVelocityAt(s.trajectory_8144,time);out.valid_404=s.valid_6200;out.contact_position_336=s.position_6176;out.normal_304=s.normal_6144;out.contact_velocity_320=s.velocity_6160;
    }
    out.time_remaining_384=s.result_present_3888?float(WrappingSub(s.landing_frame_8480,frame))*Step():0;out.duration_388=s.scalar_8392;out.frame_400=frame;out.adjustment_352=adjustment_8336;
    const auto apex=AirTrajectoryHighestPosition(s.trajectory_8144);out.apex_368=apex.first;out.apex_time_396=apex.second;out.word_408=s.word_8396;out.scalar_392=s.candidate_scalar_100;
}
}

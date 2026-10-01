// SPDX-License-Identifier: Apache-2.0
#include "BipedAirState.h"
#include "BipedAirMath.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace biped_air_math;
void BipedAirState::Reset()
{
    flags_544_550={false,false,false,false,true,false,false};height_432=0;body_offset_436=0;blend_440=0;
    time_remaining_444=0;duration_448=-1;frame_452=0;body_target_416={};result.Reset();local_contact_464={};adjustment_496={};
    vector_512={0,0,1,0};restart_normal_528={0,0,1,0};
}
void BipedAirState::BeginEnter(BipedAirEnterInput i){Reset();BeginEnterAfterReset(i);}
void BipedAirState::BeginEnterAfterReset(BipedAirEnterInput i)
{frame_80=i.animation_frame;flags_544_550[6]=(i.flags_2484&0x4000)!=0;frame_144=SkeletonIdentity;frame_208=i.animation_frame;initial_up_480=i.animation_frame[1];active=true;}
void BipedAirState::FinishEnter(BipedAirEnterInput i)
{body_target_416=i.body_position_15872;height_432=HeightDot(HeightSub(i.body_position_15872,i.position_592),i.up_544);body_offset_436=HeightDot(HeightSub(i.body_position_15936,i.body_position_15872),i.up_544);}
bool BipedAirState::LaunchPacket(const OffboardAirLaunchInput& i,const BipedControllerState& b,const PointGraph<8>& turn,
    OffboardAirLaunchSettings settings,OffboardAirLaunchPacket& packet,std::string& error) const
{auto next=OffboardAirLaunchPacket::Initialized(0);if(!ProduceOffboardAirLaunch(next,b,turn,settings,i,false,error))return false;packet=next;return true;}
void BipedAirState::Exit(OffboardAirSampling& selector){selector.pending_8492=false;selector.preinitialized_8494=false;active=false;}
std::int32_t BipedAirState::BeginUpdate(){frame_452=offboard_air_math::WrappingAdd(frame_452,1);return frame_452;}
void BipedAirState::UpdateTimes()
{
    const float duration=result.duration_388;duration_448=HeightSelect(duration-offboard_air_math::Step(),duration,offboard_air_math::Step());
    if(result.valid_404){time_remaining_444=result.time_remaining_384;const float blend=1-time_remaining_444/duration_448,lower=HeightSelect(-blend,0,blend);blend_440=HeightSelect(1-lower,lower,1);}
    else{blend_440=0;time_remaining_444=10;duration_448=10;}
}
void BipedAirState::UpdateCadence(BipedControllerState& b,float requested)
{
    if(result.valid_404)
    {
        b.correction_target_592=result.contact_position_336;auto& phase=b.cadence.phase;
        if(requested>=0&&time_remaining_444>0){phase.forward_target=true;const float delta=requested-phase.phase;phase.target=requested;phase.duration=time_remaining_444;phase.rate=delta<0?(delta+1)/time_remaining_444:delta/time_remaining_444;}
        phase.Advance();const auto frame=b.motion.frame_0;const auto delta=HeightSub(result.contact_position_336,frame[3]);
        local_contact_464={HeightDot(frame[0],delta),HeightDot(frame[1],delta),HeightDot(frame[2],delta),0};
    }
    else local_contact_464={0,0,1,0};cadence=b.cadence;
}
BipedAirOutput BipedAirState::Output() const
{return {time_remaining_444,result.velocity_288,duration_448,local_contact_464,result.word_408,result.scalar_392,float(frame_452)*offboard_air_math::Step(),result.apex_time_396,initial_up_480,frame_80[3],result.normal_304,result.contact_position_336,frame_144[2],result.apex_368,time_remaining_444<=offboard_air_math::Step(),flags_544_550[4],true};}
void PublishBipedAirFields(BipedAirOutput p,OffBoardOutputFields& out)
{
    const auto raw=[](Vec4 v){RawVector r;std::memcpy(r.data(),v.data(),16);return r;};
    out.scalar_32=p.scalar_32;out.vector_64=raw(p.vector_64);out.scalar_92=p.scalar_92;out.vector_96=raw(p.vector_96);out.word_144=p.word_144;
    out.scalar_148=p.scalar_148;out.scalar_152=p.scalar_152;out.scalar_156=p.scalar_156;out.vector_160=raw(p.vector_160);out.vector_176=raw(p.vector_176);
    out.vector_192=raw(p.vector_192);out.vector_208=raw(p.vector_208);out.vector_224=raw(p.vector_224);out.vector_240=raw(p.vector_240);
    out.flag_320=p.flag_320;out.flag_328=p.flag_328;out.trajectory_valid_331=p.flag_331;
}
}

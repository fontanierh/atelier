#include "OffboardControllerMath.h"
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
std::int32_t CadenceCast(float value)
{
    if(std::isnan(value))return 0;
    if(value>=2147483648.0f)return std::numeric_limits<std::int32_t>::max();
    if(value<=-2147483648.0f)return std::numeric_limits<std::int32_t>::min();
    return static_cast<std::int32_t>(value);
}
float CadenceWrap(float lower,float value,float upper)
{
    std::int32_t count=0;
    if(value<lower)count=CadenceCast(std::floor((upper-value)/(upper-lower)));
    else if(value>upper)
    {
        const auto positive=CadenceCast(std::floor((value-lower)/(upper-lower)));
        const auto bits=std::uint32_t{0}-static_cast<std::uint32_t>(positive);std::memcpy(&count,&bits,sizeof(count));
    }
    return biped_math::Clamp(std::fma(upper-lower,static_cast<float>(count),value),lower,upper);
}
float CadenceSelectRate(float a,float b,float lower,float upper,float both)
{
    if(a>=lower&&a<=upper)return b>=lower&&b<=upper?both:a;
    if(b>=lower&&b<=upper)return b;
    const auto da=a<lower?lower-a:a-upper,db=b<lower?lower-b:b-upper;
    return biped_math::Clamp(da<db?a:b,lower,upper);
}
BipedVector3 CadenceSubtract(BipedVector3 a,BipedVector3 b){for(std::size_t n=0;n<3;++n)a[n]-=b[n];return a;}
float CadenceDot(BipedVector3 a,BipedVector3 b){return (a[0]*b[0]+a[1]*b[1])+a[2]*b[2];}
BipedVector3 CadenceReject(BipedVector3 value,BipedVector3 axis)
{const auto projection=CadenceDot(axis,value);for(std::size_t n=0;n<3;++n)value[n]-=axis[n]*projection;return value;}
float CadenceLength(BipedVector3 v){return biped_math::Root(CadenceDot(v,v));}
}
void BipedPhase::Request(float next,float time)
{
    if(time>.1f)time-=.1f;if(target==next&&duration==std::optional<float>(time))return;
    const auto delta=next-phase;target=next;duration=time;forward_target=true;rate=delta<0?(delta+1.0f)/time:delta/time;
}
void BipedPhase::Stop()
{
    float next=0,best=biped_math::Bits(0x7149f2ca);
    for(const auto candidate:std::array<float,2>{0,.5f})
    {
        const auto raw=candidate-phase,wrapped=CadenceWrap(0,raw+1.0f,1);
        const auto distance=std::abs(raw)<std::abs(wrapped)?std::abs(raw):std::abs(wrapped);
        if(distance<best){next=candidate;best=distance;}
    }
    forward_target=false;duration=.2f;target=next;const auto distance=std::abs(next-phase);
    rate=biped_math::Select(distance-(1.0f-distance),1.0f-distance,distance)*5.0f;
}
void BipedPhase::Advance()
{
    if(target<0){const auto next=std::fma(rate,biped_math::Step(),phase);phase=next-std::floor(next);}
    else if(forward_target)
    {
        if(phase==target)return;const auto goal=target<phase?target+1.0f:target,old=phase,next=std::fma(rate,biped_math::Step(),old);
        phase=old<goal&&next>=goal?target:next-std::floor(next);
    }
    else
    {
        const auto old=phase;auto next=old+CadenceWrap(-.5f,target-old,.5f);const auto step=rate*biped_math::Step();
        if(old>next+step)next=old-step;else if(old<next-step)next=old+step;phase=CadenceWrap(0,next,1);
    }
}
void BipedPhase::AdjustTargets(float a,float b,float time,float upper)
{
    const auto da=CadenceWrap(0,a-phase,1),db=CadenceWrap(0,b-phase,1);
    if(da>=1)rate=biped_math::Clamp(db/time,0,upper);
    else if(db>=1)rate=biped_math::Clamp(da/time,0,upper);
    else {const auto inverse=1.0f/time,first=da*inverse,second=db*inverse;rate=CadenceSelectRate(first,second,0,upper,biped_math::Select(first-second,second,first));}
}
void BipedPhase::AdjustContact(float time,float lower,float upper)
{
    const auto inverse=1.0f/time,a=CadenceWrap(0,.45f-phase,1)*inverse,b=CadenceWrap(0,.95f-phase,1)*inverse;
    const auto preferred=std::abs(rate-a)<std::abs(rate-b)?a:b;rate=CadenceSelectRate(a,b,lower,upper,preferred);
}
void BipedCadence::Update(const BipedCadenceInput& input,std::array<float,4> thresholds)
{
    auto motion=CadenceSubtract(input.motion_512,input.motion_reference_272);
    if(input.reject_enabled_708)motion=CadenceReject(motion,input.reject_axis_400);
    auto magnitude=CadenceLength(CadenceReject(motion,input.up_144));
    for(std::size_t n=0;n<4;++n)if(magnitude<=thresholds[n]){locomotion_index=static_cast<std::uint32_t>(n);break;}
    if(!(input.requested_phase_296<0))phase.Request(input.requested_phase_296,input.requested_duration_288);
    else if(locomotion_index==0){if(!(phase.target>=0))phase.Stop();}
    else
    {
        const auto animation=input.animation_motion_224;const BipedVector3 horizontal{animation[0],0,animation[2]};
        const auto horizontal_length=CadenceLength(horizontal);
        if(horizontal_length>biped_math::Bits(0x3a83126f))
        {
            BipedVector3 local{};for(std::size_t n=0;n<3;++n){const auto row=input.frame_rows_0_16_32[n];local[n]=std::fma(row[2],motion[2],std::fma(row[1],motion[1],row[0]*motion[0]));}
            const auto projection=(1.0f/horizontal_length)*CadenceDot(local,horizontal);magnitude=biped_math::Root(std::fma(local[1],local[1],projection*projection));
        }
        const auto animation_length=CadenceLength(animation);phase.rate=animation_length<biped_math::Bits(0x3a83126f)?0:magnitude/animation_length;phase.target=-1;
        if(!input.reject_enabled_708&&!input.suppress_adjustment_353&&(input.contact_flags_176&0x180)!=0)
        {
            const auto time=(CadenceLength(CadenceSubtract(input.contact_point_96,input.frame_position_48))-.2f)/magnitude;
            const auto lower=phase.rate*.4f,upper=phase.rate*2.5f;
            if(time>biped_math::Bits(0x3c088889))
            {
                if((input.contact_flags_176&0x100)!=0){const auto target=phase.phase>.37f&&phase.phase<=.87f?.9f:.4f;phase.AdjustTargets(target,target,time,upper);}
                else phase.AdjustContact(time,lower,upper);
            }
        }
    }
    phase.Advance();
}
}

#include "BipedAirState.h"
#include "BipedAirMath.h"
#include "WipeoutOrientation.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace offboard_air_math;
std::optional<Vec4> BipedAirState::AnimationAdjustment(Vec4 value)
{
    if(flags_544_550[1]){if(value[1]>.1f){const auto delta=Sub(value,adjustment_496);if(Dot(delta,delta)>.001f){adjustment_496=Add(adjustment_496,LimitLength3(delta,.2f));return adjustment_496;}}}
    else if(flags_544_550[0]&&value[1]>.1f){flags_544_550[1]=true;adjustment_496=value;return value;}
    return std::nullopt;
}
void BipedAirState::OrientSample(float angle,std::uint32_t flags)
{
    if(!flags_544_550[0]&&result.valid_404)
    {
        frame_80=frame_208;auto up=Up;
        if(result.normal_304[1]>.85f)up=LimitAngle(UnitOr(Add(result.normal_304,Up),frame_80[1]),frame_80[1],(result.time_remaining_384*180)*Bits(0x3c8efa35));
        else if(frame_80[1][1]<.71f)flags_544_550[5]=true;
        LandingOrientation(result.contact_velocity_320,up,result.time_remaining_384,angle,flags);flags_544_550[0]=true;flags_544_550[2]=false;
    }
    UpdateTimes();frame_208=InterpolateMatrix(frame_80,frame_144,blend_440).first;
    // Original Air turns native interpolation scratch lanes into geometry here.
    for(auto& v:frame_208)v[3]=0;
}
void BipedAirState::LandingOrientation(Vec4 velocity,Vec4 up,float remaining,float start,std::uint32_t flags)
{
    if(flags_544_550[6])
    {
        vector_512=frame_80[2];const auto horizontal=Flat(velocity);
        if(Dot(horizontal,horizontal)>.01f){const float angle=(flags&4)!=0?-start:start;vector_512=Unit(Rotate(Unit(horizontal),Up,-angle));}
        frame_144=BipedBuildSurfaceFrame(up,vector_512);return;
    }
    const float degrees=std::abs(WrapAngle(WipeoutProjectedAngle(frame_208[2],velocity,up))*Bits(0x42652ee1));
    if(flags_544_550[2]){frame_80=frame_208;if(degrees>90)return;}
    frame_144=frame_208;if(remaining<.033f){frame_80=frame_208;return;}
    const auto tangent=Sub(velocity,Mul(up,Dot(velocity,up)));
    auto right=Length(tangent)>1?UnitOr(Cross(up,velocity),frame_144[0]):UnitOr(Cross(up,frame_208[2]),frame_144[0]);
    if(Length(tangent)>1&&degrees>90&&degrees/remaining>540){flags_544_550[5]=true;right=Mul(right,-1);}
    frame_144[0]=right;frame_144[1]=up;frame_144[2]=UnitOr(Cross(right,up),frame_144[2]);
}
float BipedAirState::LandingAssistLimit(float elapsed)
{const float time=Select(-(elapsed-.034f),0,elapsed-.034f),blend=Clamp(-(time*6.25f-1),0,1);return (1-blend)*.5f+blend*3.5f;}
void BipedAirState::FinishLandingLatch(){if(time_remaining_444<=0&&result.valid_404&&result.normal_304[1]>.1f)flags_544_550[4]=false;}
}

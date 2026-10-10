#include "WipeoutControls.h"
#include "WipeoutPhysicalMath.h"
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace wipeout_physical_math;
Vec4 WipeoutResponseNormal(std::optional<Vec4> support,std::optional<Vec4> prediction)
{if(support&&(*support)[1]>0)return *support;if(prediction&&(*prediction)[1]>0)return *prediction;return {0,1,0,0};}
void TriggerWipeoutResponse(WipeoutPhysicalState& s,SkeletonBody& body,Vec4 normal,std::array<float,2> input)
{
    s.response_frames=0;s.response_start_speed=Length(s.velocity);float strength=s.ResponseStrength();
    s.response_count=s.maximum_speed*0.1f<1?s.response_count+1:0;s.maximum_speed=0;s.extra_weight=0;s.response_scalar=0;
    if(strength==0)return;s.response_time=0;strength=strength-1.0f>=0?1:strength;s.response_scalar=strength;s.extra_weight=strength;
    Vec4 control{input[0],0,input[1],0};const float projection=Dot3(normal,control);if(projection<0)control=Sub(control,Scale(normal,projection));
    const auto velocity=Scale(Madd(normal,0,Scale(control,1.25f)),strength);AddWipeoutBodyVelocity(body,velocity);
}
void UpdateWipeoutResponseCounter(WipeoutPhysicalState& s,bool contact)
{
    s.response_finished=false;if(s.response_frames<0)return;s.response_frames=Increment(s.response_frames);
    if(s.response_frames==3){const float factor=s.response_start_speed<1?1.0f-s.response_start_speed:s.response_start_speed*0.2f;s.response_change=(Length(s.velocity)-s.response_start_speed)*(factor+1.0f);}
    if(s.response_frames==8){s.response_frames=-1;s.response_finished=true;if(!contact)s.response_change=std::fabs(s.response_change)*2.0f;s.response_change=Clamp((s.response_change-0.1f)*0.2f,0,1);}
}
namespace
{
void Release(WipeoutPhysicalState& s,SkeletonBody& body,SkeletonDrives& targets,const WipeoutDriveSettings& settings)
{if(!s.retained_velocity_active)return;SetWipeoutLinearRoot(targets,settings,0);SetWipeoutBodyVelocity(body,s.retained_velocity);s.retained_velocity_active=false;s.velocity={};}
}
void UpdateWipeoutRetainedVelocity(WipeoutPhysicalState& s,SkeletonBody& body,SkeletonDrives& targets,const WipeoutDriveSettings& settings,bool contact,std::uint32_t flags,Vec4 velocity)
{
    const bool requested=(flags&8)!=0;
    if(s.retained_velocity_active||requested){
        if(contact){s.allow_retained_velocity=false;Release(s,body,targets,settings);}
        else if(!requested)Release(s,body,targets,settings);
        else if(!s.retained_velocity_active&&s.allow_retained_velocity&&velocity[1]<2){SetWipeoutLinearRoot(targets,settings,1);s.retained_velocity_active=true;s.retained_velocity=s.velocity;}
    }
    if(s.retained_velocity_active){s.velocity=s.retained_velocity;s.time-=Step();}
}
namespace {float Fade(float duration,float time){const float divisor=duration==0?0.01f:duration;return Clamp((duration-time)/divisor,0,1);}}
WipeoutWeightOutput UpdateWipeoutWeights(WipeoutPhysicalState& s,const WipeoutPhysicalSettings& settings,bool contact,bool applied,std::uint32_t flags,std::array<float,2> gesture)
{
    const float target=Fade(settings.remove_target_time,s.time);
    if(s.special_surface||(std::fabs(gesture[0])<0.2f&&std::fabs(gesture[1])<0.2f)){
        const float step=contact?settings.collision_weight_step:-settings.collision_weight_step;s.collision_weight=Clamp(s.collision_weight+step,0,1);
    }else s.collision_weight=0;
    const float fade=Fade(settings.remove_drives_time,s.time),squared=fade*fade;
    const bool enabled=(applied||(flags&0x00080000)!=0)&&!s.special_surface;
    const float step=enabled?settings.controlled_weight_step:-settings.controlled_weight_step;s.controlled_weight=Clamp(s.controlled_weight+step,0,1);
    const float available=1.0f-s.collision_weight,start=available*squared;
    return {target,start,s.collision_weight,(available-start)*s.controlled_weight,s.extra_weight*0.03f};
}
}

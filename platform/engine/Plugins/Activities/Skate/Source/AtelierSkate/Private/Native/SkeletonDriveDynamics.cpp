#include "SkeletonDriveDynamics.h"
#include <cstdlib>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t w){float f;std::memcpy(&f,&w,4);return f;}
DriveParams Hard(float velocity,float strength){return {velocity,0,strength,DriveType::Hard};}
DriveParams Soft(float spring,float damping,float strength){return {spring,damping,strength,DriveType::Soft};}
DriveParams Interpolate(DriveInterpolation s,float strength,float progress)
{
    const float spring0=s.spring[0]*strength,strength0=s.strength[0]*strength;
    const float spring=std::fma(s.spring[1]*strength-spring0,progress,spring0);
    const float force=std::fma(s.strength[1]*strength-strength0,progress,strength0);
    const float damping=std::fma(s.damping[1]-s.damping[0],progress,s.damping[0]);
    const auto nonnegative=[](float value){return value>=0.0f ? value:0.0f;};
    return {nonnegative(spring)*Float(0x426fffff),nonnegative(damping),nonnegative(force)*Float(0x4560fffe),DriveType::Hard};
}
}
void BoneDriveDynamics::Enable(std::size_t channel,float strength,BoneDriveSettings settings)
{
    if(channel>=2)std::abort();if(mode>5)return;if(mode!=5)transition_active=false;
    const auto a=settings.animation[channel];const float frequency=Float(0x426fffff),squared=Float(0x4560fffe);
    DriveDynamics d;
    switch(mode)
    {
    case 0:d={Hard(a.linear_displacement*frequency,a.linear_strength*squared),Hard(a.angular_displacement*frequency,a.angular_strength*squared)};break;
    case 1:d={Hard(Float(0x4415ffff),Float(0x470c9fff)),Hard(Float(0x4415ffff),Float(0x470c9fff))};break;
    case 2:d={Hard(0,0),Hard(a.angular_displacement*frequency,a.angular_strength*squared)};break;
    case 3:d={Soft(0,0,0),Soft(settings.collision_soft_displacement*strength,200,(settings.collision_soft_strength*strength)*squared)};break;
    case 4:d={strength<=0.5f ? Soft(0,0,0):Soft((settings.ragdoll_soft_displacement*strength)*0.5f,200,(strength*settings.ragdoll_soft_strength)*squared),
        Soft(settings.ragdoll_soft_displacement*strength,200,(strength*settings.ragdoll_soft_strength)*squared)};break;
    case 5:
    {
        if(!transition_active){transition_active=true;transition_counter=1;}
        else if(transition_counter<settings.transition_calls)transition_counter+=1;
        const float progress=transition_counter/settings.transition_calls;
        d={Interpolate(settings.transition_linear,strength,progress),Interpolate(settings.transition_angular,strength,progress)};break;
    }
    default:std::abort();
    }
    channels[channel]=d;
}
}

// SPDX-License-Identifier: Apache-2.0
#include "SkeletonLanding.h"
#include <cstdlib>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float LandingFloat(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
float LandingSelect(float selector,float positive,float negative){return selector>=0.0f?positive:negative;}
Vec4 LandingSubtract(Vec4 a,Vec4 b){for(unsigned i=0;i<4;++i)a[i]-=b[i];return a;}
Vec4 LandingScale(Vec4 a,float amount){for(auto& v:a)v*=amount;return a;}
}
void LandingAdjustment::Update(LandingInput input,const LandingSettings& settings,SkateboardOffset& offset)
{
    const float step=LandingFloat(0x3c888889);
    const bool from_offboard=previous_filtered_state==6&&input.filtered_state==1,from_air=previous_filtered_state==2&&input.filtered_state==1;
    const bool ground=(from_offboard||from_air)&&(input.flags_2476&0x10000000)!=0,manual=from_air&&input.balance!=0.0f;
    const bool grind=previous_filtered_state==2&&input.filtered_state==3&&(input.flags_2468&0x20)==0;
    const bool coffin_flag=(input.flags_2472&1)!=0,coffin=coffin_flag&&(grind||from_air),cancel=(input.flags_2476&0x40000000)!=0&&!coffin_flag;
    if(cancel)active=false;bool first_ground_update=false;
    if(!cancel&&!active&&(ground||coffin||manual||grind))
    {
        time=0.0f;active=true;kind=coffin?3u:manual?2u:ground?0u:1u;first_ground_update=kind==0;
        const float initial_velocity=(grind||coffin)?previous_com_velocity:input.physical_com_velocity_along_up;
        const float lower=LandingSelect(-settings.maximum_velocity-initial_velocity,-settings.maximum_velocity,initial_velocity);
        velocity=LandingSelect(-lower,lower,0.0f);previous_animation_height=std::numeric_limits<float>::max();position=input.physical_com_height;
    }
    if(active)
    {
        float spring=0.0f,damping=0.0f,blend=0.0f;bool release=false,allow_upwards=true;
        switch(kind)
        {
        case 0:spring=settings.ground_spring;damping=settings.ground_damping;allow_upwards=false;blend=1.0f;release=input.filtered_state!=1||(input.flags_2476&0x10000000)==0;break;
        case 1:spring=settings.grind_spring;damping=settings.grind_damping;blend=settings.grind_blend.Evaluate(time);release=input.filtered_state!=3;break;
        case 2:spring=settings.manual_spring;damping=settings.manual_damping;blend=settings.manual_blend.Evaluate(time);release=input.filtered_state!=1;break;
        case 3:blend=1.0f;release=input.filtered_state!=1||time>settings.coffin_time||!coffin_flag;break;
        default:break;
        }
        const float animation_height=input.animation_com_height;
        if(kind==3)
        {
            const float ratio=std::fabs(velocity)/settings.coffin_maximum_velocity,positive_ratio=LandingSelect(-ratio,0.0f,ratio),scale=LandingSelect(1.0f-positive_ratio,positive_ratio,1.0f);
            position=std::fma(settings.coffin_height.Evaluate(time/settings.coffin_time),scale,settings.coffin_base_height);
        }
        else
        {
            float target=settings.desired_com_height;
            if(kind==1)
            {
                if(time>settings.grind_animation_target_time)
                {
                    const float minimum=desired_grind_com-settings.grind_target_delta,maximum=desired_grind_com+settings.grind_target_delta;
                    const float lower=LandingSelect(minimum-animation_height,minimum,animation_height);target=LandingSelect(maximum-lower,lower,maximum);
                }
                desired_grind_com=target;
            }
            const float displacement=position-target,previous_velocity=velocity,spring_force=-(displacement*spring);
            const float acceleration=-std::fma(previous_velocity,damping,-spring_force),candidate=std::fma(acceleration,step,previous_velocity);
            const float lower=LandingSelect(-settings.maximum_velocity-candidate,-settings.maximum_velocity,candidate),maximum=allow_upwards?settings.maximum_velocity:0.0f;
            velocity=LandingSelect(maximum-lower,lower,maximum);
            const float integrated=std::fma((velocity+previous_velocity)*0.5f,step,displacement),height=integrated+target;
            position=LandingSelect(height-settings.minimum_height,height,settings.minimum_height);
        }
        float displacement=animation_height-position;
        if(first_ground_update)
        {
            const float correction=velocity*LandingFloat(0x3c75c28f),lower=LandingSelect(-0.1f-correction,-0.1f,correction),down=LandingSelect(-lower,lower,0.0f),combined=down+displacement;
            displacement=LandingSelect(combined,combined,0.0f);
        }
        if(kind==0&&time>settings.ground_minimum_compression_time&&previous_animation_height<animation_height&&displacement>0.0f)release=true;
        if(kind==1&&(input.flags_2468&0x20)!=0)release=true;if(time>1.5f)release=true;
        const bool force_blend=(input.flags_2468&(1u<<21))!=0;
        if((!release&&blend>=0.05f)||force_blend)
        {
            float frames=kind==3?settings.coffin_blend_frames:15.0f;if(force_blend){active=false;frames=6.0f;}offset.RefreshHeight(displacement*blend,frames);
        }
        else active=false;time+=step;previous_animation_height=animation_height;
    }
    previous_com_velocity=input.physical_com_velocity_along_up;previous_filtered_state=input.filtered_state;
}
Mat4 LandingOnBoardSkateRoot(Mat4 old,Vec4 com,std::uint32_t flags,float ground_y,LandingOnBoardSettings settings)
{
    auto position=com;position[1]=old[3][1]+settings.root_y_offset;
    if((flags&1)!=0)
    {
        const float requested=(ground_y+settings.capsule_length)+settings.capsule_radius,minimum=position[1],maximum=position[1]+0.3f;
        if(!(minimum<=maximum))std::abort();position[1]=requested<minimum?minimum:requested>maximum?maximum:requested;
    }
    return {old[2],old[0],old[1],position};
}
void UpdateLandingOnBoardRoot(SkeletonRootFrames& roots,Vec4 com,Vec4 local_com,float spin,std::optional<std::uint32_t> frames,bool reversed)
{
    roots.initialize_heading=true;float angle=spin;if(frames){const float magnitude=LandingFloat(0x40490fdb)/static_cast<float>(*frames);angle=reversed?magnitude:-magnitude;}
    const auto [sin,cos]=SinCos(angle);const Mat4 yaw{{{cos,0.0f,-sin,0.0f},{0.0f,1.0f,0.0f,0.0f},{sin,0.0f,cos,0.0f},{0.0f,0.0f,0.0f,0.0f}}};
    auto frame=ComposeSkeletonAffine(roots.animation_to_world,yaw);if(frames)frame=OrthonormalizeSkeletonFrame(frame);const Vec4 up{0.0f,1.0f,0.0f,0.0f};
    const auto deviation=Cross3(frame[1],up);const float epsilon=LandingFloat(0x37800000);
    if(Dot3(deviation,deviation)>epsilon)
    {
        const auto unnormalized=Cross3(up,frame[2]);const float squared=Dot3(unnormalized,unnormalized);
        if(squared>epsilon){const auto right=LandingScale(unnormalized,InverseLengthSquared(squared,2));const Mat4 target{right,up,Cross3(right,up),frame[3]};frame=InterpolateAffine(frame,target,0.1f);}
    }
    auto rotation=frame;rotation[3]={};frame[3]=LandingSubtract(com,TransformSkeletonPoint(rotation,local_com));roots.ResetInitialAlignment(OrthonormalizeSkeletonFrame(frame));
}
std::optional<Mat4> LandingOnBoardPoseAdjustment(const Mat4& inverse_root,const Mat4& actual,const Mat4& mapped,Vec4 offset,float velocity_y,std::uint32_t flags,float time,const PointGraph<8>& blend)
{
    if(!(velocity_y<0.0f)||(flags&2)!=0)return std::nullopt;auto target=ComposeSkeletonAffine(inverse_root,actual);auto rotation=inverse_root;rotation[3]={};auto correction=TransformSkeletonPoint(rotation,offset);correction[1]=0.0f;
    if(target[3][1]>mapped[3][1])correction[1]=target[3][1]-mapped[3][1];for(unsigned i=0;i<4;++i)target[3][i]=mapped[3][i]+correction[i];
    const auto blended=InterpolateAffine(mapped,target,blend.Evaluate(time));auto adjustment=ComposeSkeletonAffine(blended,InverseSkeletonRigid(mapped));adjustment[3][1]=-adjustment[3][1];return adjustment;
}
}

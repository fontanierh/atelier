// SPDX-License-Identifier: Apache-2.0
#include "SkeletonCollisionMode.h"
#include "SkeletonCollisionFeedback.h"
#include <cstdlib>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
SkeletonCollisionMode::SkeletonCollisionMode(SkeletonCollisionSettings input,bool cull_all_self_pairs):settings(input)
{
    for(std::size_t i=0;i<parts.size();++i)parts[i]={false,i==0 ? 4u:0u,5,i>=1 && i<24 ? settings.normal_material:ContactMaterial{}};
    for(auto& row:self_culling)row.fill(true);
    if(!cull_all_self_pairs)for(const auto& pair:std::array<std::array<std::size_t,2>,6>{{{14,4},{14,8},{23,4},{23,8},{4,18},{8,22}}})
    {self_culling[pair[0]][pair[1]]=false;self_culling[pair[1]][pair[0]]=false;}
    if(settings.enabled)NormalCollision();else DisableAll(true);normal_self_culling_=self_culling;
}
void SkeletonCollisionMode::DisableHandplantContacts(std::uint32_t frames)
{pending_reenable=true;for(std::size_t part:{7,3,8,4,1}){disable_count[part]=frames;parts[part].enabled=false;}}
void SkeletonCollisionMode::ResetBodyState(SkeletonCollisionFeedback& feedback)
{is_ragdoll=false;feedback.Reset();disable_count={};pending_reenable=false;}
bool SkeletonCollisionMode::SelectDriven(std::uint32_t mode,std::string& error)
{
    if(mode==3){SelectBiped();error.clear();return true;}
    if(mode==5 || mode==6)NormalCollision();else if(mode==1){EnableEligibleBones();SetGroup(3);}
    else {error="Skeleton collision selector requires its non-driven physical setup";return false;}
    partial_ragdoll=false;DisableRoot();parts[24].enabled=false;parts[25].enabled=false;error.clear();return true;
}
void SkeletonCollisionMode::NormalCollision(){SetGroup(5);DisableRoot();EnableEligibleBones();}
void SkeletonCollisionMode::DisableAll(bool clear_counts)
{
    DisableRoot();parts[24].enabled=false;parts[25].enabled=false;
    for(std::size_t part=1;part<24;++part){parts[part].enabled=false;if(clear_counts)disable_count[part]=0;}
}
void SkeletonCollisionMode::EnableBone(std::size_t part)
{
    if(part>=disable_count.size())std::abort();
    if(disable_count[part]==0){parts[part].enabled=true;parts[part].volume_group=0;}parts[part].part_group=5;
}
void SkeletonCollisionMode::FinishContactFrame()
{
    if(!pending_reenable)return;bool remaining=false;
    for(std::size_t part=0;part<disable_count.size();++part)
        if(disable_count[part]!=0 && disable_count[part]<0x80000000u)
        {--disable_count[part];const bool enabled=disable_count[part]==0;parts[part].enabled=enabled;remaining=remaining || !enabled;}
    pending_reenable=remaining;
}
void SkeletonCollisionMode::NormalBone(std::size_t part,bool has_collision)
{
    if(part>=disable_count.size())std::abort();
    if(has_collision){if(disable_count[part]==0){parts[part].enabled=true;parts[part].volume_group=0;}}
    else {parts[part].enabled=false;parts[part].volume_group=4;disable_count[part]=0;}
}
void SkeletonCollisionMode::RestoreNormalProperties(SkeletonBody& skeleton)
{
    self_culling=normal_self_culling_;SetGroup(5);
    for(std::size_t part=0;part<SkeletonPartCount;++part)
    {
        const auto& animated=skeleton.definition.parts[part];auto& body=skeleton.BodiesMut()[part];
        body.inertia.linear_drag=0;body.inertia.angular_drag=0;
        if(part>=1 && part<24)
        {
            body.inertia.inverse_mass=animated.inverse_mass_animated;
            const auto tensor=animated.animated.dynamics.inverse_tensor;body.inertia.inverse_tensor=tensor;
            float minimum=tensor.x;if(minimum>=tensor.y)minimum=tensor.y;if(minimum>=tensor.z)minimum=tensor.z;
            body.inertia.spherical=1.0f/minimum;body.rates.world_inverse_inertia=WorldInverseInertia(body.rates.basis,tensor);
            parts[part].material=settings.normal_material;
        }
    }
    if(settings.enabled)NormalCollision();else DisableAll(true);is_ragdoll=false;
}
void SkeletonCollisionMode::ApplyRagdollProperties(SkeletonBody& skeleton,bool inverse_mass,bool inverse_inertia,
    std::array<float,2> drag,std::array<ContactMaterial,2> materials)
{
    constexpr std::array<std::uint32_t,26> culled{{0x03ffffff,0x03fff447,0x03fffc47,0x039b8479,0x03bb8479,0x039f8479,0x03ffffff,
        0x03b987c1,0x03bb87c1,0x03f987c1,0x03ffffff,0x03fffc45,0x03fffc47,0x03fffc47,0x03fffc47,0x03ffffff,
        0x038fffff,0x038ffd7f,0x03cffc67,0x03ffffff,0x03f8ffff,0x03f8ffd7,0x03fcfe47,0x03ffffff,0x03ffffff,0x03ffffff}};
    bool all=true;for(const auto& row:normal_self_culling_)for(bool c:row)all=all && c;
    for(std::size_t a=0;a<26;++a)for(std::size_t b=0;b<26;++b)self_culling[a][b]=all || (culled[a]&(1u<<b))!=0;
    SetGroup(6);for(auto& body:skeleton.BodiesMut()){body.inertia.linear_drag=drag[0];body.inertia.angular_drag=drag[1];}
    for(std::size_t part=1;part<24;++part)
    {
        const auto& authored=skeleton.definition.parts[part];auto& body=skeleton.BodiesMut()[part];
        disable_count[part]=0;parts[part].enabled=true;pending_reenable=false;parts[part].material=materials[part==1 || part==3 || part==7 ? 1:0];
        if(inverse_mass)body.inertia.inverse_mass=authored.inverse_mass_ragdoll;
        if(inverse_inertia)
        {
            const auto tensor=authored.ragdoll.dynamics.inverse_tensor;body.inertia.inverse_tensor=tensor;
            float minimum=tensor.x;if(minimum>=tensor.y)minimum=tensor.y;if(minimum>=tensor.z)minimum=tensor.z;body.inertia.spherical=1.0f/minimum;
        }
        body.rates.world_inverse_inertia=WorldInverseInertia(body.rates.basis,body.inertia.inverse_tensor);
    }
    is_ragdoll=true;
}
void SkeletonCollisionMode::FinishRagdollRequest(std::uint32_t mode)
{
    switch(mode)
    {
    case 7:case 10:partial_ragdoll=false;DisableRoot();parts[24].enabled=false;parts[25].enabled=false;break;
    case 8:for(std::size_t part=1;part<24;++part)parts[part].material={.5f,.3f,.4f};break;
    case 9:SetGroup(7);break;
    default:std::abort();
    }
}
void SkeletonCollisionMode::SetGroup(std::uint32_t group){assembly_group=group;for(auto& part:parts)part.part_group=group;}
void SkeletonCollisionMode::SelectBiped()
{
    SetGroup(6);DisableAll(false);
    for(std::size_t part:{17,21,15,19,16,20}){EnableBone(part);parts[part].part_group=17;}
    for(std::size_t part:{5,4,3,9,8,7,2,1})EnableBone(part);
    for(std::size_t part:{6,10,11,12,13,14,23}){EnableBone(part);parts[part].part_group=18;}
    partial_ragdoll=true;for(std::size_t part:{24,25}){parts[part].part_group=20;parts[part].enabled=true;}
}
void SkeletonCollisionMode::DisableRoot(){parts[0].volume_group=4;parts[0].enabled=false;disable_count[0]=0;}
void SkeletonCollisionMode::EnableEligibleBones()
{for(std::size_t part=1;part<24;++part)if(disable_count[part]==0){parts[part].enabled=true;parts[part].volume_group=0;}}
}

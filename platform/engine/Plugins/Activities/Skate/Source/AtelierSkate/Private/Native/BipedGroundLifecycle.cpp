// SPDX-License-Identifier: Apache-2.0
#include "BipedGroundLifecycle.h"
#include "StockSettingsReader.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Word(std::uint32_t w){float f;std::memcpy(&f,&w,4);return f;}
float GroundDot(Vec4 a,Vec4 b){return (a[0]*b[0]+a[1]*b[1])+a[2]*b[2];}
float GroundLength(Vec4 v){const float q=GroundDot(v,v);float r=ReciprocalSquareRootEstimate(q);for(unsigned n=0;n<2;++n)r=std::fma(r*.5f,std::fma(-q,r*r,1.0f),r);return q==0?0:q*r;}
RawVector Raw(Vec4 v){RawVector out;std::memcpy(out.data(),v.data(),16);return out;}
}
bool BipedGroundCollisionSettings::Load(const SettingsDatabase& data,std::string& error)
{
    StockSettingsReader reader(data);BipedGroundCollisionSettings next;
    const char* names[]={"Wipeout_OB_VehicleScalar","Wipeout_OB_VehicleContact","Wipeout_OB_SkeletonMaxDisp","Wipeout_OB_SkeletonMaxContactArms","Wipeout_OB_SkeletonMaxContact","Wipeout_OB_MinSpeed","Wipeout_OB_MaxSquash","Hash_472174920C68FBE3"};
    float* fields[]={&next.vehicle_scalar,&next.vehicle_contact,&next.maximum_displacement,&next.maximum_arm_contact,&next.maximum_body_contact,&next.minimum_speed,&next.maximum_squash,&next.special_scalar};
    for(unsigned n=0;n<8;++n)if(!reader.Float("physics_wipeout","default",names[n],*fields[n],error))return false;
    *this=next;error.clear();return true;
}
void CheckBipedGroundCollision(WipeoutRequests& requests,const BipedGroundCollisionSettings& s,const BipedGroundCollisionInput& i)
{
    requests.mode=4;if(GroundDot(i.skeleton_velocity_16336,i.skeleton_velocity_16336)<=s.minimum_speed*s.minimum_speed)return;
    const float requested=(i.shared.flags_2480&0x80)!=0?s.special_scalar:1.0f;float vehicle=1;
    if(i.contact_flag_4072){if(i.contact_force_4056>s.vehicle_contact)requests.Request(7,0);vehicle=s.vehicle_scalar;}
    const float scalar=requested-vehicle>=0?vehicle:requested;
    if(i.shared.maximum_pose_error>scalar*s.maximum_squash)requests.Request(18,0);
    else{const float limit=s.maximum_displacement*scalar;if(GroundDot(i.shared.pose_error,i.shared.pose_error)>limit*limit)requests.Request(1,0);
        else if(CheckWipeoutRegionalForce(i.shared,s.maximum_body_contact*scalar,s.maximum_arm_contact*vehicle))requests.Request(0,0);}
}
void PostBipedGround(BipedGroundState& state,WipeoutRequests& requests,const BipedGroundCollisionSettings& settings,const BipedGroundPostInput& i)
{
    CheckBipedGroundCollision(requests,settings,i.collision);
    if((i.processed_flags_2484&0x400)!=0)
    {
        if(state.flags_144_to_150[6]&&state.flags_144_to_150[2])requests.Request(31,0);
        state.elapsed_168=0;
        if(state.flags_144_to_150[2]||state.angle_172>Word(0x3fc90fdb)||i.ground_kind_356==2||i.ground_kind_356==4||.5f>state.frame_80[1][1])requests.Request(31,0);
        else if(!(GroundDot(i.processed_velocity_608,i.skeleton_displacement_16304)>=GroundLength(i.processed_velocity_608)*Word(0xbca3d70a)))requests.Request(32,0);
    }
    else
    {
        const auto a=std::abs(GroundDot(i.skeleton_displacement_16304,state.frame_80[1])),b=std::abs(GroundDot(i.skeleton_displacement_16288,state.frame_80[1]));
        if(a>Word(0x3eb33333)||b>Word(0x3e19999a))state.elapsed_168+=Word(0x3c888889);else state.elapsed_168=0;
        if(!(state.elapsed_168<Word(0x3d4cccce)))requests.Request(32,0);
    }
    if(state.flags_144_to_150[1])requests.Request(28,0);
}
BipedGroundPublication PublishBipedGround(const BipedGroundState& state,const BipedGroundPublicationInput& i)
{
    const bool near=i.ground_flags_752_to_754[1]||!(state.distance_164>=Word(0x3daaaaab));
    const bool blocked=state.flags_144_to_150[3]||(i.contact_flags_368&8)!=0;
    float distance=Word(0x501502f9);if(i.ground_flags_752_to_754[0]&&(i.contact_flags_368&1)!=0){Vec4 delta;for(unsigned n=0;n<4;++n)delta[n]=i.contact_position_192[n]-i.query_position_816[n];distance=GroundLength(delta);}
    const float projection=GroundDot(i.motion_up_864,i.motion_vector_1040);Vec4 motion;for(unsigned n=0;n<4;++n)motion[n]=i.motion_vector_1040[n]-i.motion_up_864[n]*projection;
    std::array<bool,2> hands;for(unsigned n=0;n<2;++n)hands[n]=(i.hand_flags[n][0]&&!i.hand_flags[n][1])||i.hand_flags[n][2];
    return {state.counter_152,state.counter_156,(i.processed_flags_2476&0x400000)!=0&&!state.flags_144_to_150[0],state.flags_144_to_150[0],i.ground_kind_356,i.ground_scalar_360,blocked,near&&!blocked,distance,i.ground_flags_752_to_754[2],state.flags_144_to_150[2]?1.0f:0.0f,state.flags_144_to_150[2],motion,true,hands};
}
BipedStatePublication PublishBipedGroundFields(BipedGroundPublication p,PhysicalPlayerInput& physical)
{
    auto& o=physical.off_board;o.flag_304=p.offboard_flag_304;o.kind_88=p.offboard_kind_88;o.scalar_112=p.offboard_scalar_112;
    o.flag_329=p.offboard_flag_329;o.flag_330=p.offboard_flag_330;o.distance_116=p.offboard_distance_116;o.flag_334=p.offboard_flag_334;
    o.scalar_32=p.offboard_scalar_32;o.flag_328=p.offboard_flag_328;for(unsigned n=0;n<2;++n)o.flags_306_307[n]=p.offboard_hand_flags_306_307[n];
    physical.reckoning.vector_144=Raw(p.animation_vector_144);physical.reckoning.flag_164=p.animation_flag_164;
    physical.state.counter_36=p.physics_counter_36;physical.state.skitch_value_40=p.physics_counter_40;
    return {p.physics_counter_36,p.physics_counter_40,p.physics_flag_86};
}
}

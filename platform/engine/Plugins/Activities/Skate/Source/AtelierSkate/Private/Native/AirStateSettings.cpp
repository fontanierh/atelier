// SPDX-License-Identifier: Apache-2.0
#include "AirStateSettings.h"
#include "GravityScale.h"
#include "StockSettingsReader.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
std::int32_t Signed(std::uint32_t word) {std::int32_t value;std::memcpy(&value,&word,4);return value;}
Vec4 Vector(std::array<std::uint32_t,4> words) {Vec4 value;for (std::size_t i=0;i<4;++i) value[i]=Float(words[i]);return value;}
bool Scalar(const SettingsDatabase& data,std::string_view category,std::string_view key,std::string_view name,float& value,std::string& error)
{return StockSettingsReader(data).Float(category,key,name,value,error);}
}
bool AirStateSettings::Load(const SettingsDatabase& data,std::string& error)
{
    AirStateSettings value;std::vector<std::uint32_t> words;
    if (!StockSettingsReader(data).Words("physics_airstates","default","BodySpinInputFilter",16,words,error)) return false;
    for (std::size_t i=0;i<8;++i) {value.state.body_spin_over_time_320.x[i]=Float(words[i]);value.state.body_spin_over_time_320.y[i]=Float(words[i+8]);}
    constexpr std::array<std::string_view,5> names{"easy","normal","hardcore","motorized","test"};
    for (std::size_t i=0;i<names.size();++i) if (!Scalar(data,"physics_mode",names[i],"GrindLockDist",value.grind_lock_distance[i],error)) return false;
    if (!Scalar(data,"physics_airstates","default","SpeedToAlignToGround_PhysAir",value.state.landing_normal_blend_388,error)||
        !Scalar(data,"physics_airstates","default","MaxSpinSpeed",value.state.body_spin_scale_428,error)||
        !Scalar(data,"physics_airstates","default","DontAlignAnglePhysicsAir",value.state.landing_normal_angle_limit_444,error)) return false;
    if (!Scalar(data,"physics_steering","default","SteeringTiltBlending",value.steering_blend,error)) return false;
    *this=std::move(value);error.clear();return true;
}
PhysicsAirFrame BindPhysicsAirFrame(const AirStateBindingInput& p)
{
    return {Vector(p.vectors_400_416[0]),Float(p.vectors_464_480_496_512_528[2][1]),Vector(p.vectors_544_560_592_608[2]),Vector(p.vectors_544_560_592_608[3]),
        Vector(p.jump_reference),p.flags_2468,Signed(p.state_2504),Signed(p.category_2516),Signed(p.jump_fix_frames),p.timestep_2604,p.body_spin,p.gravity_2648,p.state_timer_2664};
}
bool BindAirSelectorInput(const AirStateBindingInput& p,const AirStateSettings& settings,AirSelectorInput& output,std::string& error)
{
    if (p.state_variant_index_2528>=settings.grind_lock_distance.size()) {error="Invalid trajectory physics mode "+std::to_string(p.state_variant_index_2528);return false;}
    output={p.world_gravity,Vector(p.vectors_464_480_496_512_528[0]),Vector(p.vectors_464_480_496_512_528[2]),Vector(p.vectors_464_480_496_512_528[3]),
        Vector(p.vectors_544_560_592_608[0]),Float(p.vectors_400_416[0][1]),p.transition_2636,p.state_2504,p.flags_2472,p.flags_2476,p.external_physics_flags,settings.grind_lock_distance[p.state_variant_index_2528]};
    // The source world gravity producer explicitly sets the fourth lane zero.
    output.gravity[3]=0;error.clear();return true;
}
bool BindAirLaunchInfo(const AirStateBindingInput& p,AirLaunchInfo& output,std::string& error)
{
    if (!p.toolkit_deck) {error="Air launch requires current BoardToolkit";return false;}
    AirLaunchInfo value;value.reckoning_transform=p.reckoning_system;value.reckoning_inverse=p.reckoning_inverse;
    value.start_velocity=Vector(p.vectors_400_416[0]);value.com_velocity=Vector(p.prepared_jump_704);
    value.skeleton_vector_160=p.skeleton_local_centre_of_mass;value.skeleton_vector_176=p.skeleton_local_board_position;
    value.board_position=(*p.toolkit_deck)[3];value.animation_com_position=Vector(p.vectors_544_560_592_608[2]);
    value.cone_angle_x=p.trajectory_cone_x;value.cone_angle_z=p.trajectory_cone_z;value.timestep=p.timestep_2604;value.trajectory_count=(p.flags_2468&0x2000)!=0?7:1;
    output=std::move(value);error.clear();return true;
}
Vec4 PhysicsAirHostComAcceleration() {return {0,(Float(0xc11ccccd)*GravityScale()),0,0};}
}

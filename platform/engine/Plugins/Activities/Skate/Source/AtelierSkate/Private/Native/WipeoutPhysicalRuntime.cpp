// SPDX-License-Identifier: Apache-2.0
#include "WipeoutPhysicalRuntime.h"
#include "WipeoutControls.h"
#include "WipeoutPhysicalMath.h"
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace wipeout_physical_math;
bool WipeoutPhysicalRuntime::Load(const SettingsDatabase& data,const PhysicsSkeleton& physical,std::string& error)
{
    WipeoutPhysicalRuntime candidate;const char* names[]={"free_fall","cannon_ball","judo_kick","swan_dive","torpedo"};
    std::array<bool,5> okay;std::array<std::string,5> profile_errors;
    // Original array::map evaluates all five profile Result values before the
    // ragdoll/state/drive constructor fields and propagates them only afterward.
    for(unsigned i=0;i<5;++i)okay[i]=WipeoutControlProfile::Load(data,names[i],candidate.profiles[i],profile_errors[i]);
    if(!candidate.ragdoll.Load(data,physical,error)||!WipeoutPhysicalSettings::Load(data,candidate.settings,error)
        ||!WipeoutDriveSettings::Load(data,physical,candidate.drives,error))return false;
    for(unsigned i=0;i<5;++i)if(!okay[i]){error=profile_errors[i];return false;}
    *this=std::move(candidate);error.clear();return true;
}
bool WipeoutPhysicalRuntime::Enter(WipeoutPhysicalOwners o,std::string& error)
{
    auto& p=o.physical;const auto& input=o.input.processed;o.life.skeleton_elapsed_16505=false;
    state=WipeoutPhysicalState{};contact.Reset();prediction.Reset();p.board_wiping_out=true;p.board.SetCollisionGroup(7);
    p.board.BodiesMut()[6].inertia.angular_drag=0;
    const ContactMaterial material{settings.board_friction,settings.board_friction,settings.board_restitution};
    p.settings.board.collision.wheel_material=material;p.settings.board.collision.truck_material=material;p.settings.board.collision.deck_material=material;
    o.ground.steering.targets={};p.board.HookMut().drive.DisableAngular();p.board.HookMut().drive.DisableLinear();
    for(auto& limb:o.ik.state.limbs){limb.board_blend=0;limb.external_blend=0;limb.mode=foot_ik::Mode::Disabled;}o.ik.state.EnableFeet(false);
    SetWipeoutAngularRoot(p.skeleton_drives,drives,0.5f);SetWipeoutLinearRoot(p.skeleton_drives,drives,0);
    if(input.flags_2488&0x00200000)BlendWipeoutBodyVelocity(p.skeleton,FromWords(input.vectors_880_896_912_928_944[4]));
    if(o.wipeout.state.reasons[6]){
        const auto normal=FromWords(input.vectors_544_560_592_608[0]);RemoveWipeoutNormalVelocity(p.skeleton,normal);
        for(auto& part:p.board.BodiesMut()){const auto v=part.rates.linear_velocity;const Vec4 value{v.x,v.y,v.z,0};const auto next=Sub(value,Scale(normal,Dot3(normal,value)));part.rates.linear_velocity={next[0],next[1],next[2]};}
        p.board.BodiesMut()[6].rates.angular_velocity={};
    }
    LimitWipeoutBodyVelocity(p.skeleton,20);
    if(input.flags_2468&4)p.skeleton.ApplyPartDisplacement(12,Scale(FromWords(input.vector_1520),settings.push_force));
    if(input.probe_1792.byte_104)AddWipeoutBodyVelocity(p.skeleton,FromWords(input.probe_1792.vector_80));
    state.special_surface=(input.flags_2488&0x40000000)!=0;state.surface_height=input.collision_scalar_2924;
    if(!ragdoll.Request(o.life.skeleton_controller,state.special_surface?10:8,p.skeleton,p.skeleton_joints,p.skeleton_collision,error))return false;
    for(auto& part:p.skeleton.BodiesMut())part.inertia.linear_drag=0;
    state.move_board=(input.flags_2472&0x800)!=0;state.board_offset=FromWords(input.vectors_720_784_800_816_832_864[3]);state.board_move_frames=0;
    state.predicted_time=std::numeric_limits<float>::max();state.airborne_frames=15;
    if(input.flags_2468&8)SetWipeoutBodyVelocity(p.skeleton,FromWords(input.vectors_544_560_592_608[3]));state.velocity=p.board_frames.com_velocity;return true;
}
void WipeoutPhysicalRuntime::Exit(WipeoutPhysicalOwners o)
{
    auto& p=o.physical;p.board_wiping_out=false;p.board.BodiesMut()[6].inertia.angular_drag=settings.deck_angular_drag;p.board.SetCollisionGroup(4);
    p.settings.board.collision.wheel_material=settings.standard_materials[0];p.settings.board.collision.truck_material=settings.standard_materials[1];p.settings.board.collision.deck_material=settings.standard_materials[2];state.prevent_manual=false;
}
void WipeoutPhysicalRuntime::PostPhysics(WipeoutPhysicalOwners o)
{state.PostPhysics(o.physical.skeleton.record.velocities[23],o.physical.skeleton.record.velocities[1],o.physical.collision_feedback.flags.compliant,settings.recovery);}
WipeoutPhysicalOutput WipeoutPhysicalRuntime::Fill(WipeoutPhysicalOwners o) const
{
    const auto& f=o.physical.collision_feedback;const auto normal=WipeoutResponseNormal(f.flags.compliant?std::optional<Vec4>(f.highest_normal):std::nullopt,
        prediction.result.contact_time>=0?std::optional<Vec4>(prediction.result.landing_normal):std::nullopt);return state.Output(o.physical.skeleton.record.pose[23],normal);
}
bool WipeoutPhysicalRuntime::UpdateContact(WipeoutPhysicalOwners o,bool actual_contact,Vec4 velocity,Vec4 effective,std::array<float,2> controls,std::string& error)
{
    auto& p=o.physical;const auto& f=p.collision_feedback;
    contact.material10.Update(p.skeleton,velocity,f.flags.material_10?std::optional<Vec4>(f.material_normals[0]):std::nullopt);
    contact.material11.Update(p.skeleton,velocity,f.flags.material_11?std::optional<Vec4>(f.material_normals[1]):std::nullopt,effective,controls);
    state.material_ten_response=contact.material10.finished;const bool air_mode=!actual_contact&&!(state.predicted_time<=0.3f),air_changed=state.air_collision_mode!=air_mode;
    state.air_collision_mode=air_mode;const bool material_changed=state.material_eleven_response!=contact.material11.active;state.material_eleven_response=contact.material11.active;
    if(!state.special_surface&&(air_changed||material_changed))return ragdoll.Request(o.life.skeleton_controller,state.material_eleven_response?9:air_mode?11:8,p.skeleton,p.skeleton_joints,p.skeleton_collision,error);
    return true;
}
}

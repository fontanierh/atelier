#include "WipeoutRuntime.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float WipeoutBits(std::uint32_t bits){float value;std::memcpy(&value,&bits,4);return value;}
float WipeoutLength(Vec4 v)
{
    const auto sq=Dot3(v,v);const auto inv=InverseLengthSquared(sq,2);
    return sq==0?0:sq*inv;
}
float WipeoutSelectedMax(float a,float b){return a-b>=0?a:b;}
void WipeoutVehicle(WipeoutRequests& state,const WipeoutSettings& s,const WipeoutFrame& f)
{if (f.vehicle_force>(f.flags_2476&8?s.ground.skitch_contact:s.ground.vehicle_contact)) state.Request(7,0);}
void WipeoutClosing(WipeoutRequests& state,const WipeoutFrame& f,float xz,float y)
{
    if (!f.board_contact) return;
    const auto& v=f.closing_velocity;const auto& m=f.world_to_animation;Vec4 local{};
    for (std::size_t i=0;i<4;++i) local[i]=std::fma(m[2][i],v[2],std::fma(m[1][i],v[1],m[0][i]*v[0]));
    if (WipeoutLength({local[0],0,local[2],local[3]})>xz||std::abs(local[1])>y)
    {state.Request(2,0);if (CheckWipeoutRegionalForce(f,1,20)) state.Request(0,0);}
}
void WipeoutLeaning(WipeoutRequests& state,const WipeoutSettings& s,const WipeoutFrame& f)
{if (f.animation_up[1]<s.lean_contact_y&&f.compliant&&f.highest_normal[1]>WipeoutBits(0x3f34fdf4)) state.Request(19,0);}
void WipeoutBadLanding(WipeoutRequests& state,const WipeoutSettings& s,const WipeoutMode& mode,const WipeoutFrame& f,bool use_com)
{
    if (!mode.check_bad_landing||!f.board_contact) return;
    const auto velocity=use_com?f.com_velocity:f.deck_velocity;auto normal=f.board_contact_normal;
    if (f.grind_selected)
    {
        if (f.grind_normal_valid) normal=f.grind_normal;
        if (-Dot3(normal,velocity)>s.air.max_grind_speed*mode.bad_landing_scale) state.Request(8,0);
    }
    else
    {
        const auto into=-Dot3(normal,velocity);Vec4 tangent{};
        for (std::size_t i=0;i<4;++i) tangent[i]=std::fma(normal[i],into,velocity[i]);
        const auto limit=s.air.max_landing_angle.Evaluate(WipeoutLength(tangent))*mode.bad_landing_scale;
        if (std::abs(f.landing_angle)>limit) state.Request(5,0);
        const auto speed_limit=f.board_material_flags&(1u<<31)?s.air.max_stairs_speed:s.air.max_landing_speed;
        if (into>speed_limit*mode.bad_landing_scale) state.Request(6,into);
    }
}
}
bool CheckWipeoutRegionalForce(const WipeoutFrame& frame,float body,float arms)
{
    const auto& f=frame.regions_force;
    const auto a=WipeoutSelectedMax(f[0],f[1]),b=WipeoutSelectedMax(f[5],f[4]),c=WipeoutSelectedMax(f[7],f[6]);
    return WipeoutSelectedMax(WipeoutSelectedMax(a,b),c)>body||WipeoutSelectedMax(f[2],f[3])>arms;
}
void CheckWipeoutAirCollision(WipeoutRequests& state,const WipeoutSettings& s,const WipeoutMode& mode,const WipeoutFrame& f)
{
    if (mode.check_squash&&f.maximum_pose_error>s.air.max_squash) state.Request(18,0);
    else if (Dot3(f.pose_error,f.pose_error)>s.air.max_displacement*s.air.max_displacement) state.Request(1,0);
    else if (CheckWipeoutRegionalForce(f,s.air.max_contact,s.air.max_arm_contact)) state.Request(0,0);
}
void CheckWipeoutAir(WipeoutRequests& state,const WipeoutSettings& s,const WipeoutMode& mode,const WipeoutFrame& f,bool use_com)
{
    if (state.mode!=2) {state.mode=2;state.contact_frames=0;}
    if (f.board_contact) state.contact_frames=4;
    if (state.contact_frames>0) --state.contact_frames;
    if (state.cooldown>0) {state.cooldown-=f.timestep;return;}
    WipeoutVehicle(state,s,f);const auto& a=s.air;
    const bool body_flip=(f.flags_2476&(1u<<26))!=0;
    const auto scalar=body_flip?a.body_flip_scalar:1,deck_scalar=body_flip?a.body_flip_acc_scalar:1;
    float xz,y;
    if ((f.flags_2472&(1u<<15))!=0&&f.jump_fix_frames>a.ignore_danger_frames) {xz=a.xz_trick;y=a.y_trick;}
    else if (f.wheel_contact) {xz=mode.ground_xz*deck_scalar;y=s.ground.y_acceleration;}
    else {xz=a.xz_acceleration*deck_scalar;y=a.y_acceleration;}
    if (f.board_material_flags&(1u<<29)) xz*=a.light_dmo_scalar;
    WipeoutClosing(state,f,xz,y);const auto displacement=a.max_displacement*scalar;
    if (mode.check_squash&&f.maximum_pose_error>a.max_squash*scalar) state.Request(18,0);
    else if (Dot3(f.pose_error,f.pose_error)>displacement*displacement) state.Request(1,0);
    else if (CheckWipeoutRegionalForce(f,a.max_contact*scalar,a.max_arm_contact)) state.Request(0,0);
    if (f.flip_active&&f.flip_requested_speed==0&&f.system_up_y<0) state.Request(4,0);
    WipeoutBadLanding(state,s,mode,f,use_com);WipeoutLeaning(state,s,f);
    if ((f.flags_2476&(1u<<26))!=0&&f.compliant) state.Request(21,0);
    if ((f.flags_2472&(1u<<6))!=0&&(f.compliant||f.board_contact)) state.Request(21,0);
}
void CheckWipeoutGround(WipeoutRequests& state,const WipeoutSettings& s,const WipeoutMode& mode,const WipeoutFrame& f)
{
    state.EnterGround();
    if (state.cooldown>0) {state.cooldown-=f.timestep;return;}
    const auto& g=s.ground;const auto vehicle=f.group_8?g.vehicle_scalar:1;
    const auto trick=f.flags_2472&(1u<<15)?WipeoutBits(0x3e99999a):1;
    const auto skitch=f.flags_2476&8?g.skitch_scalar:1,arms=f.flags_2476&8?g.skitch_arms_scalar:1;
    const auto skater=(f.flags_2472&(1u<<28))==0&&f.maximum_skater_force>0?g.skater_scalar:1;
    const auto scale=((vehicle*trick)*skitch)*skater;
    const auto squash=f.flags_2476&(1u<<30)?g.max_squash_coffin:g.max_squash,displacement=g.max_displacement*scale;
    if ((mode.check_squash||f.time_on_ground>WipeoutBits(0x3d4ccccd))&&f.maximum_pose_error>vehicle*squash) state.Request(18,0);
    else if (Dot3(f.pose_error,f.pose_error)>displacement*displacement) state.Request(1,0);
    else if (CheckWipeoutRegionalForce(f,g.max_contact*scale,g.max_arm_contact*arms)) state.Request(0,0);
    WipeoutVehicle(state,s,f);
    if ((f.flags_2484&(1u<<21))==0)
    {
        const auto cosine=VectorMin(VectorMin(Dot3(f.deck[0],f.input_board[0]),Dot3(f.deck[1],f.input_board[1])),Dot3(f.deck[2],f.input_board[2]));
        if (Acos(VectorMin(VectorMax(cosine,-1),1))>g.max_deck_error) state.Request(3,0);
    }
    float xz,y;
    if (f.flags_2472&(1u<<15)) {xz=s.air.xz_trick;y=s.air.y_trick;}
    else
    {
        xz=mode.ground_xz;y=g.y_acceleration;
        if (f.board_material_flags&(1u<<30)) {const auto scalar=f.flags_2472&(1u<<28)?g.ai_scalar:g.player_scalar;xz*=scalar;y*=scalar;}
        if (f.board_material_flags&(1u<<29)) xz*=g.light_dmo_scalar;
        if (f.flags_2476&8) {xz*=g.skitch_acc_scalar;y*=g.skitch_acc_scalar;}
        if (f.flags_2484&(1u<<21)) {xz=0;y=0;}
    }
    WipeoutClosing(state,f,xz,y);
    const float skitch_gate=f.flags_2476&(1u<<23)?0:1,slide_gate=f.flags_2468&(1u<<5)?0:1;
    const auto speed=(g.balance_min_speed-f.speed)/g.balance_min_speed;
    const auto amount=(speed*(1-f.animation_up[1]))*slide_gate;
    const auto delta=std::fma(amount,skitch_gate,-g.balance_base);
    state.balance=delta>0?state.balance+delta:0;
    if (state.balance>g.balance_total) state.Request(11,0);
    if (f.conflicting) state.Request(16,0);
    WipeoutLeaning(state,s,f);
}
void CheckWipeoutGroundAnimation(WipeoutRequests& state,const WipeoutSettings& s,const WipeoutMode& mode,const WipeoutFrame& f,float scale)
{
    CheckWipeoutGround(state,s,mode,f);
    if (CheckWipeoutRegionalForce(f,s.air.max_contact,s.air.max_arm_contact)) state.Request(0,0);
    if (f.opposing_contact>s.ground.opposing_contact*scale) state.Request(20,0);
}
void CheckWipeoutPlant(WipeoutRequests& state,const WipeoutSettings& s,const WipeoutFrame& f)
{
    state.mode=3;
    if (f.maximum_pose_error>s.ground.max_squash) state.Request(18,0);
    else if (WipeoutLength(f.pose_error)>s.air.max_displacement) state.Request(1,0);
    else if (CheckWipeoutRegionalForce(f,s.air.max_contact,s.air.max_arm_contact)) state.Request(0,0);
    WipeoutClosing(state,f,s.air.xz_trick,s.air.y_trick);
}
bool WipeoutRuntime::Load(const SettingsDatabase& data,std::string& error)
{
    WipeoutSettings next{};std::array<WipeoutMode,5> next_modes{};
    if (!LoadWipeoutSettings(data,next,next_modes,error)) return false;
    WipeoutRequests next_state;next_state.InitializePlayer();settings=std::move(next);modes=next_modes;state=next_state;error.clear();return true;
}
const WipeoutMode* WipeoutRuntime::Mode(const ProcessedPhysicsInput& p,std::string& error) const
{
    if (p.state_variant_index_2528>=modes.size()) {error="Undefined wipeout physics mode "+std::to_string(p.state_variant_index_2528);return nullptr;}
    return &modes[p.state_variant_index_2528];
}
bool WipeoutRuntime::CheckAirCollision(const ProcessedPhysicsInput& p,const WipeoutFrame& frame,std::string& error)
{const auto mode=Mode(p,error);if (!mode) return false;CheckWipeoutAirCollision(state,settings,*mode,frame);error.clear();return true;}
bool WipeoutRuntime::CheckGround(const WipeoutObservations& input,std::string& error)
{const auto mode=Mode(input.processed,error);if (!mode) return false;WipeoutFrame f;if (!input.Frame(f,error)) return false;CheckWipeoutGround(state,settings,*mode,f);error.clear();return true;}
bool WipeoutRuntime::CheckGroundAnimation(const WipeoutObservations& input,float scale,std::string& error)
{const auto mode=Mode(input.processed,error);if (!mode) return false;WipeoutFrame f;if (!input.Frame(f,error)) return false;CheckWipeoutGroundAnimation(state,settings,*mode,f,scale);error.clear();return true;}
bool WipeoutRuntime::CheckAir(const WipeoutObservations& input,bool use_com,std::string& error)
{const auto mode=Mode(input.processed,error);if (!mode) return false;WipeoutFrame f;if (!input.Frame(f,error)) return false;CheckWipeoutAir(state,settings,*mode,f,use_com);error.clear();return true;}
bool WipeoutRuntime::CheckPlant(const WipeoutObservations& input,std::string& error)
{WipeoutFrame f;if (!input.Frame(f,error)) return false;CheckWipeoutPlant(state,settings,f);error.clear();return true;}
}

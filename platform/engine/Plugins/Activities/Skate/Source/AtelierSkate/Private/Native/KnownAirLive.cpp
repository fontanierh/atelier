// SPDX-License-Identifier: Apache-2.0
#include "KnownAirPrivate.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::known_air
{
namespace
{
Vec4 Vector(const RawVector& words){return {Bits(words[0]),Bits(words[1]),Bits(words[2]),Bits(words[3])};}
Vec3 XYZ(Vec4 value){return {value[0],value[1],value[2]};}
}
std::optional<Live> Live::Create(AirPhaseOwners o,const KnownAirConfiguration& c,std::string& error)
{
    const auto& selector=o.trajectory.selector;
    if (!selector.Selection()) {error="KnownAir requires its actual winning query result";return std::nullopt;}
    const auto com=selector.LocalComPosition();if (!com) {error="KnownAir requires selector local COM";return std::nullopt;}
    const auto board=selector.BoardPosition();if (!board) {error="KnownAir requires selector board position";return std::nullopt;}
    if (!o.toolkit) {error="KnownAir requires prepared board toolkit";return std::nullopt;}
    error.clear();return Live(o,*o.toolkit,*selector.Selection(),*com,*board,c);
}
bool Live::Finish(std::string& error) const
{if (first_error) {error=*first_error;return false;}error.clear();return true;}
void Live::ResetFlip()
{
    auto& riding=owners.physical.riding;auto& frames=riding.reckoning_frames;const auto n=riding.reckoning.up;
    const auto up=Rotate(frames.body_flip,{n.x,n.y,n.z,0});riding.reckoning.up=XYZ(up);
    frames.heading=Rotate(frames.body_flip,frames.heading);frames.body_flip=SkeletonIdentity;
    auto& state=owners.air_reckoning.state;state.flip_active=false;state.flip_speed=0;state.flip_side=false;state.flip_angle=0;
}
void Live::BeginFlip(bool side)
{
    auto& state=owners.air_reckoning.state;if (state.flip_active) return;
    auto& frames=owners.physical.riding.reckoning_frames;frames.body_flip=SkeletonIdentity;state.flip_speed=0;state.flip_angle=0;
    auto basis=frames.system;if (toolkit.control_sign<0) {basis[0]=Scale(basis[0],-1);basis[2]=Scale(basis[2],-1);}
    const auto v=owners.animation_input.fields.body_spin*4;const auto lo=Select(-v,0,v),blend=Select(1-lo,lo,1);
    const auto adjustment=Scale(configuration.flip_axis_adjustment,blend);Vec4 axis{};
    for (std::size_t i=0;i<4;++i) axis[i]=std::fma(basis[2][i],adjustment[2],std::fma(basis[1][i],adjustment[1],basis[0][i]));
    state.flip_axis=Normalize(axis).first;if (side) state.flip_axis=Scale(state.flip_axis,-1);
    state.flip_side=side;state.flip_active=true;
}
void Live::RequestCollision(std::uint32_t state)
{std::string error;const auto ok=owners.life.skeleton_controller.Request(state,owners.physical.skeleton_collision,error);Record(ok,error);}
void Live::UpdateCollision()
{
    const auto& p=owners.processed;std::string error;
    const auto ok=owners.life.skeleton_controller.UpdateAir(p.flags_2472,Bits(p.vectors_400_416[0][1]),owners.physical.skeleton_collision,error);Record(ok,error);
}
void Live::StartGrind()
{
    if (selection.grind) {owners.skeleton_input.grind_air.Start(selection.grind->AirTarget());owners.skeleton_input.grind_air_started=true;}
    else Record(false,"KnownAir grind lock has no accepted trajectory target");
}
std::pair<std::int32_t,Vec4> Live::Closest(Vec4 com,Vec4 zero) const
{
    const auto t=selection.com_trajectory;float best=100000000;auto offset=zero;
    for (std::int32_t i=0;i<100;++i)
    {
        const auto delta=Sub(com,AirTrajectoryPositionAt(t,static_cast<float>(i)*Bits(0x3c888889)));const auto squared=Dot3(delta,delta);
        if (squared>best) return {i-1,offset};best=squared;offset=delta;
    }
    return {0,zero};
}
KnownAirPrediction Live::Prediction() const
{return {Trajectory(selection.prediction.request.trajectory),selection.prediction.result.contact_time,selection.prediction.result.contact_frame};}
void Live::Reckoning(Vec4 normal,float blend,float spin,float flip)
{
    std::string error;PhysicsAirReckoningFields fields;
    const auto ok=owners.air_reckoning.Update(owners.physical.riding,owners.processed,owners.animation_input.extra.physical_body_spin,normal,blend,spin,flip,fields,error);Record(ok,error);
}
void Live::Skeleton(Vec4 target_com)
{
    auto& f=owners.physical;const auto collision=AirPhaseCollisionInput(f);std::string error;Mat4 target;
    const auto ok=UpdateKnownSkeletonAir(owners.skeleton_input,owners.skeleton_air,f.riding.reckoning_frames.system,target_com,
        owners.packet,owners.processed,owners.SkeletonOwners(),owners.packet.hierarchy,collision,target,error);Record(ok,error);
}
void Live::Footplant(const KnownAirState& state,const KnownAirFrame& frame)
{
    if ((frame.flags_2480&0x04000000)==0||(frame.flags_2476&0x04000000)!=0||state.time_in_state_180<=Bits(0x3dcccccd))
    {owners.footplant.Reset();return;}
    auto t=selection.com_trajectory;const auto time=static_cast<float>(state.trajectory_index_216)*Bits(0x3c888889);
    // Both source updates sample the unshifted trajectory before writing it.
    const auto position=AirTrajectoryPositionAt(t,time),velocity=AirTrajectoryVelocityAt(t,time);t.position=position;t.velocity=velocity;
    const KnownAirFootplantInput input{t,state.collision_time_196-state.time_in_state_180,state.collision_position_112,state.landing_normal_64};
    const FootplantPredictionFrame f{owners.processed,toolkit,owners.animated,owners.physical,owners.grind_world.Primitives()};
    owners.footplant.UpdateCandidate(input,f);owners.footplant.UpdateLaunch(input);std::string error;
    const auto ok=owners.footplant.ConsumeAndSubmit(input,f,owners.ik,owners.physical.skeleton_collision,error);Record(ok,error);
}
void Live::Wipeout(bool use_com)
{std::string error;const auto ok=owners.wipeout.CheckAir(AirPhaseWipeoutObservations(owners),use_com,error);Record(ok,error);}
Vec4 Live::BoardVelocity() const
{const auto v=owners.physical.board.Bodies()[6].rates.linear_velocity;return {v.x,v.y,v.z,0};}
void Live::SetBoardVelocity(Vec4 velocity)
{for (auto& body:owners.physical.board.BodiesMut()) body.rates.linear_velocity=XYZ(velocity);}
Vec4 Live::BoardForward() const
{
    const auto part=owners.physical.board.PartTransforms()[6];const auto c=part.basis.columns[2];
    return Scale({c[0],c[1],c[2],0},owners.processed.flags_2468&(1u<<20)?-1:1);
}
bool Frame(AirPhaseOwners o,std::uint32_t next,KnownAirFrame& output,std::string& error)
{
    if (!o.toolkit) {error="KnownAir requires current BoardToolkit";return false;}
    const auto& selection=o.trajectory.selector.Selection();if (!selection) {error="KnownAir requires a completed selected trajectory";return false;}
    const auto& p=o.processed;const auto& t=*o.toolkit;KnownAirFrame f{};
    f.start_flip_reference_96=t.deck[2];f.alternate_head_target_112=t.deck[3];f.velocity_400=Vector(p.vectors_400_416[0]);
    f.ground_normal_464=Vector(p.vectors_464_480_496_512_528[0]);f.start_height_484=Bits(p.vectors_464_480_496_512_528[1][1]);
    f.skater_up_544=Vector(p.vectors_544_560_592_608[0]);f.flags_2468=p.flags_2468;f.flags_2472=p.flags_2472;f.flags_2476=p.flags_2476;
    f.flags_2480=p.flags_2480;f.flags_2484=p.flags_2484;f.flags_2488=p.flags_2488;std::memcpy(&f.next_physics_state_2500,&next,4);
    f.delta_time_2604=p.timestep_2604;f.forward_speed_2612=p.scalar_2612;f.body_spin_input_2640=o.animation_input.fields.body_spin;
    f.selector_landing_normal_2656=selection->landing_normal;output=f;error.clear();return true;
}
KnownAirReckoningFields ReckoningFields(AirPhaseOwners o)
{
    const auto up=o.physical.riding.reckoning.up;
    return {{up.x,up.y,up.z,0},o.physical.riding.reckoning_frames.heading,o.air_reckoning.state.spin_angle,o.air_reckoning.state.spin_speed};
}
}

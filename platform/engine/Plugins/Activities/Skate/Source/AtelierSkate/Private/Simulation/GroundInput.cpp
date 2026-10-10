#include "GroundInput.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec4 Raw(RawVector words) {Vec4 value;for (std::size_t i=0;i<4;++i) std::memcpy(&value[i],&words[i],4);return value;}
Vec4 Four(Vec3 value) {return {value.x,value.y,value.z,0};}
Vec3 Three(Vec4 value) {return {value[0],value[1],value[2]};}
float Float(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
}
BoardToolkit PrepareGroundToolkit(GroundRuntime& runtime,const BoardRuntime& board,const ProcessedPhysicsInput& p)
{
    auto result=BoardToolkit::FromBoard(board,p.flags_2468,p.scalar_2612,
        Raw(p.vectors_464_480_496_512_528[0]),runtime.retained_board_normal);
    runtime.retained_board_normal=result.filtered_normal;return result;
}
GroundContactFrame GroundWallContactFrame(const PhysicalBoardProbes& probes,float time2752,float time2756)
{
    return {Four(probes.wall.start),Four(probes.wall.point),Four(probes.wall.normal),
        probes.wall.surface_tag,probes.wall.hit,time2752,time2756};
}
GroundBoardInput PrepareGroundBoardInput(const GroundSettings& s,const BoardToolkit& t,
    const ProcessedPhysicsInput& p,const ScalarAttributeInputs& f,const ContactEventState& contacts,
    const PumpingState& pumping,float unintentional_pump_scalar,const PhysicalRidingOutputs& riding,
    float board_at_y_delta,const std::array<AffineTransform,2>& base_trucks,GroundInputObservations extra)
{
    const auto normal=Raw(p.vectors_464_480_496_512_528[0]);
    const auto velocity=Raw(p.vectors_400_416[0]),angular=Raw(p.vectors_400_416[1]);
    const auto axis544=Raw(p.vectors_544_560_592_608[0]);
    const auto ground_normal=Four(riding.reckoning.ground_normal);
    const auto& ground=riding.reckoning_frames.ground;
    Vec4 edge_delta;for (std::size_t i=0;i<4;++i) edge_delta[i]=t.deck[3][i]-extra.edge_point[i];
    const auto hang_axis=Raw(p.vectors_720_784_800_816_832_864[4]);
    return {
        {f.turn,f.hard_turn,t.absolute_speed,t.control_sign,f.balance,p.truck_tightness_2760,
            (p.flags_2468&0x08000000)!=0},
        // The core replaces both zero placeholders before consuming them.
        {0,p.scalar_2612,0,p.truck_tightness_2760,s.wobble_activation,s.wobble_amplitude},
        p.flags_2468,p.flags_2472,
        GroundWallContactFrame(riding.probes,p.time_on_ground_2752,p.signed_ground_time_2756),ground_normal,
        {p.flags_2468,p.flags_2472,contacts.push_speed*s.push_target_multiplier,p.scalar_2612,
            t.absolute_speed,t.total_mass,p.timestep_2604,f.brake,Three(t.forward),
            Three(t.horizontal_forward),s.surface_braking_factor},
        {p.time_on_ground_2752,p.crouch_2776,p.crouch_delta_2780,pumping.absorption,
            s.foot_force_offset,s.absorption_front,s.absorption_rear,s.foot_force_offset,
            f.balance,p.scalar_2656,t.transverse_up,velocity,axis544},
        {p.flags_2468,p.flags_2476,std::int32_t(p.wheel_count_2556),
            std::int32_t(p.spin_same_direction_frames_2580),p.timestep_2604,p.scalar_2612,
            p.scalar_2652,p.scalar_2656,p.spin_input_2672,f.balance,p.time_since_last_input_2748,
            0,t.effective[2],t.forward,angular,normal,t.effective[2],t.total_mass},
        {0,normal,velocity,t.deck[0],p.scalar_2656,p.scalar_2764},
        {p.flags_2476,unintentional_pump_scalar,pumping.pump_acceleration,t.total_mass,
            p.timestep_2604,t.forward_velocity,{Float(0x358637bd),Float(0x358637bd),Float(0x358637bd),Float(0x358637bd)}},
        {0,p.scalar_2764,f.turn,t.forward,velocity,normal},
        {f.balance,p.spin_input_2672,p.flags_2472,p.timestep_2604,p.scalar_2612,p.scalar_2652,
            f.raw_turn,riding.heading_adjust_factor,t.forward_velocity,normal,
            Raw(p.vectors_720_784_800_816_832_864[0]),ground},
        {p.flags_2468,f.balance,t.deck[2],t.deck[0],axis544},
        {f.balance,t.control_sign,p.state_timer_2664,t.absolute_speed,board_at_y_delta,p.timestep_2604,
            false,(p.flags_2468&0x20000000)!=0,(p.flags_2472&0x08000000)!=0,
            (p.flags_2472&0x04000000)!=0,(p.flags_2468&0x00100000)!=0,
            ground[0],ground[2],t.deck[2],Raw(p.effective_anim_transform_192[2]),angular,
            Four(base_trucks[0].translation),Four(base_trucks[1].translation)},
        {p.flags_2468,t.absolute_speed,f.balance,extra.manual_drag_2724,ground_normal[1]},
        p.signed_ground_time_2756,extra.trajectory_state_bits,
        {p.scalar_2652,t.deck[2]},
        {extra.edge_flags,p.scalar_2652,t.deck[1][1],Dot3(hang_axis,hang_axis)>0},
        {extra.edge_flags,p.scalar_2652,t.deck[0][1],t.deck[1][1],Dot3(t.deck[1],edge_delta)},
        {p.flags_2488,std::int32_t(p.frames_since_teleport_2584),p.flags_2472}
    };
}
}

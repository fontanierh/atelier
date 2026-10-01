// SPDX-License-Identifier: Apache-2.0
#include "KnownAirPrivate.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::known_air
{
void Enter(KnownAirState& state,const KnownAirFrame& frame,const KnownAirSettings& settings,const KnownAirModeSettings& mode,Live& live)
{
    auto& o=live.owners;auto& f=o.physical;
    f.board.HookMut().drive.EnableAngularOnly(o.life.board_animated_290);o.life.skeleton_controller.flag_18=true;
    live.RequestCollision(7);o.life.skeleton_elapsed_16505=false;o.ik.EnableFeet(true);
    state.body_flipping_211=false;state.grind_air_adjust_activated_212=false;state.targeting_grind_213=false;
    live.ResetFlip();o.footplant.enabled=false;o.footplant.Reset();state.reached_apex_208=false;state.time_in_state_180=0;
    state.start_y_184=frame.start_height_484;state.max_y_188=f.board.PartTransforms()[6].translation.y;state.com_max_y_192=f.board_frames.centre_of_mass[1];
    InitializeTrajectory(state,frame,settings,mode,live);
    if (o.trajectory.selector.GrindLockedToMiddle()) {live.StartGrind();state.targeting_grind_213=true;}
    const auto closest=live.Closest(f.board_frames.centre_of_mass,{});state.trajectory_index_216=closest.first;state.trajectory_follow_offset_144=closest.second;
    state.start_flipped_210=0>Dot3(frame.velocity_400,frame.start_flip_reference_96);
}
void Exit(KnownAirState& state,KnownAirFrame& frame,const KnownAirSettings& settings,KnownAirReckoningFields& reckoning,Live& live)
{
    live.ResetFlip();if (frame.next_physics_state_2500==100) RestoreVelocity(state,frame,settings,live);
    live.owners.trajectory.selector.Reset();reckoning.body_spin_speed_1572=0;reckoning.body_spin_angle_1568=0;
    live.owners.skeleton_input.grind_air_started=false;live.owners.skeleton_input.grind_air_active=false;
}
void Update(KnownAirState& state,const KnownAirFrame& frame,const KnownAirSettings& settings,const KnownAirModeSettings& mode,const KnownAirReckoningFields& reckoning,Live& live)
{
    auto& o=live.owners;auto& f=o.physical;live.Footplant(state,frame);
    if (o.trajectory.selector.JustChanged()) InitializeTrajectory(state,frame,settings,mode,live);
    live.UpdateCollision();const auto flip=FlipSpeed(state,frame,settings,mode,reckoning,live),spin=SpinSpeed(state,frame,settings,mode,reckoning);
    const auto remaining=(state.collision_time_196-state.time_in_state_180)/frame.delta_time_2604,after_lead=remaining-3;
    const auto alignment=Select(after_lead-2,after_lead,2);
    if (!state.grind_air_adjust_activated_212&&(state.reached_apex_208||alignment<settings.frames_for_grind_air_assist_436))
    {const auto started=o.skeleton_input.grind_air_started;o.skeleton_input.grind_air_active=started;state.grind_air_adjust_activated_212=true;}
    if (state.targeting_grind_213&&state.grind_air_adjust_activated_212&&o.skeleton_input.grind_air_adjusting)
    {
        for (const std::size_t part:std::array<std::size_t,6>{15,16,17,19,20,21})
        {f.skeleton_collision.pending_reenable=true;f.skeleton_collision.disable_count[part]=2;f.skeleton_collision.parts[part].enabled=false;}
    }
    live.Reckoning(state.landing_normal_64,1/alignment,spin,flip);Follow(state,frame,settings,live);live.Skeleton(state.target_com_position_160);
    if (state.time_in_state_180<Bits(0x3d75c28f)) f.correction.pending=true;
    o.skeleton_input.head_tracking_history[5]=frame.flags_2472&0x00400000?frame.alternate_head_target_112:state.collision_position_112;
    o.skeleton_input.head_tracking_active=true;o.ground.steering.Update(0,o.settings.steering_blend,o.processed.flags_2468,o.processed.flags_2472);
    const auto board_y=f.board.PartTransforms()[6].translation.y;if (!(state.max_y_188>board_y)) state.max_y_188=board_y;
    if ((frame.flags_2468&8)==0) state.time_in_state_180+=frame.delta_time_2604;
    const auto com_y=f.board_frames.centre_of_mass[1];state.com_max_y_192=Select(state.com_max_y_192-com_y,state.com_max_y_192,com_y);
}
void Post(KnownAirState& state,const KnownAirFrame& frame,const KnownAirModeSettings& mode,const KnownAirWipeoutSettings& settings,KnownAirWipeoutRequest& request,Live& live)
{
    if (!state.reached_apex_208&&live.BoardVelocity()[1]<0) state.reached_apex_208=true;
    live.Wipeout(true);
    if (!mode.upside_down_falling_wipeout_enabled_2||(frame.flags_2468&0x20)!=0||!(frame.skater_up_544[1]<settings.air_falling_min_up_y_260)) return;
    if (Dot3(state.landing_normal_64,frame.skater_up_544)<settings.air_falling_max_angle_264)
    {request.requested_35=true;request.scalar_116=0;++request.counter_200;}
}
}

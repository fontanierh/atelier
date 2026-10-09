#include "SlidePhaseRuntime.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
bool SlidePhaseRuntime::Load(const SettingsDatabase& data,std::string& error)
{
    SlideStateSettings next;
    if(!next.Load(data,error))return false;
    state={};settings=std::move(next);error.clear();return true;
}
void SlidePhaseRuntime::Enter(SlidePhaseOwners o)
{
    EnterSlideState(state,o.physical.board,
        {o.life.skeleton_elapsed_16505,o.air_reckoning.state.spin_angle,
         o.air_reckoning.state.spin_speed,o.life.board_animated_290,
         o.ground.manual,o.wipeout.state.mode,o.wipeout.state.balance},
        o.processed.category_2516,o.processed.scalar_2656);
}
void SlidePhaseRuntime::Exit(SlidePhaseOwners o)
{
    ExitSlideState(state,o.physical.settings.board.collision.wheel_material,
        o.physical.settings.board.standard_wheel_material);
}
bool SlidePhaseRuntime::Advance(SlidePhaseOwners o,std::string& error)
{return AdvanceSlidePhase(state,settings,o,error);}
WipeoutObservations SlidePhaseWipeoutObservations(SlidePhaseOwners o)
{
    const auto& f=o.physical;
    return {o.processed,f.riding.ground,f.collision_feedback,f.DeckFrame(),
        f.board_frames.animation_target,f.roots.world_to_animation,f.collision_pose_error,
        f.collision_maximum_error,o.jump_fix_frames,o.air_reckoning.state,
        f.riding.reckoning_frames.system[1][1],o.trajectory.selector.GrindLockedToMiddle(),
        o.trajectory.selector.GrindNormal()};
}
bool SlidePhaseRuntime::PostPhysics(SlidePhaseOwners o,std::string& error)
{return o.wipeout.CheckGround(SlidePhaseWipeoutObservations(o),error);}
}

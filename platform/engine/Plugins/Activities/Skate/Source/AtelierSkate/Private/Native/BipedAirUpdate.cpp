#include "BipedAirRuntime.h"
#include "BipedAirMath.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace{Vec4 Value(RawVector w){Vec4 v;std::memcpy(v.data(),w.data(),16);return v;}}
bool BipedAirRuntime::Update(BipedRuntimeOwners v,BipedGroundRuntime& ground,std::string& error)
{
    const auto p=v.processed;
    if(!v.life.skeleton_controller.Request((p.flags_2484&2)!=0?7:4,v.physical.skeleton_collision,error))return false;
    const auto frame=state.BeginUpdate();UpdateBipedAirFeet(v.feet,v.processed,v.physical.animation_record,v.physical.roots,v.ik.state);
    v.ground.steering.Update(0,v.air_settings.steering_blend,p.flags_2468,p.flags_2472);
    if(const auto adjustment=state.AnimationAdjustment(v.animation_input.fields.animation_end_com))v.selector.AdjustAnimation(offboard_air_math::WrappingSub(frame,1),*adjustment,state.frame_144);
    state.result.Reset();v.selector.Sample(frame,offboard_air_math::Step(),state.result);state.OrientSample(v.animation_input.extra.biped_start_angle,p.flags_2476);
    const auto up=Value(p.vectors_544_560_592_608[0]),position=Value(p.vectors_544_560_592_608[2]);
    const auto response=state.CollisionResponse(v.physical.collision_extra_errors,up,v.selector.core.sampling.restart_allowed_8493);
    if(response.request_52)v.wipeout.state.Request(32,0);
    if(response.restart)
    {
        OffboardAirLaunchPacket packet;if(!LaunchPacket(v,ground,packet,error))return false;const auto feet=HeightInput(v);
        const float height=BipedAirProjectedHeight(feet.bone15,feet.bone19,position,up);packet=state.RestartPacket(packet,*response.restart,position,up,height);
        if(!v.selector.Launch(v.physical.world,packet,BipedRuntimeGravity(v.physical),BipedRuntimeAirContext(v.processed),error))return false;
        state.FinishRestart(EffectiveBipedAirFrame(v.physical.roots.animation_to_world,v.processed.flags_2476),*response.restart);
    }
    state.CorrectRestartedSample();state.CorrectHeight(HeightInput(v));bool queried;
    if(!v.selector.Requery(v.physical.world,BipedRuntimeAirContext(v.processed),p.flags_2472,p.flags_2488,queried,error))return false;
    if(!v.toolkit){error="BipedAir Skeleton requires the completed BoardToolkit";return false;}
    Mat4 target;if(!UpdateBipedSkeletonAir(v.skeleton_input,v.skeleton_air,{state.frame_208,state.result.position_272,state.body_target_416,state.body_offset_436,v.toolkit->deck[2]},ground.skeleton_state,v.processed,v.SkeletonOwners(),v.hierarchy,BipedRuntimeCollision(v.physical),v.air_reckoning,target,error))return false;
    state.UpdateCadence(ground.controller.state,v.animation_input.fields.cadence_end_percent);
    auto scene=OffboardStaticScene::Create(v.physical.world,error);if(!scene)return false;
    if(!v.landing.Assist(*scene,{v.processed,v.toolkit},BipedAirState::LandingAssistLimit(p.state_timer_2664),error))return false;
    state.FinishLandingLatch();error.clear();return true;
}
}

// SPDX-License-Identifier: Apache-2.0
#include "GroundPhaseRuntime.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec4 Raw(const RawVector& words)
{Vec4 result;std::memcpy(result.data(),words.data(),sizeof(result));return result;}
Vec4 Lanes(Vec3 v) {return {v.x,v.y,v.z,0};}
Vec3 Xyz(Vec4 v) {return {v[0],v[1],v[2]};}
std::string ServiceSourceDebug(const std::string& source)
{
    std::string result="\"";
    constexpr char hex[]="0123456789abcdef";
    for(const unsigned char c:source)
    {
        switch(c)
        {
        case '"':result+="\\\"";break;
        case '\\':result+="\\\\";break;
        case '\n':result+="\\n";break;
        case '\r':result+="\\r";break;
        case '\t':result+="\\t";break;
        case '\0':result+="\\0";break;
        default:
            if(c<0x20||c==0x7f)
            {
                result+="\\u{";
                if(c>=16)result+=hex[c>>4];
                result+=hex[c&15];result+='}';
            }
            else result+=static_cast<char>(c);
        }
    }
    result+='"';return result;
}
std::string BoardErrorDebug(const GroundBoardError& error)
{
    if(error.kind==GroundBoardError::Kind::Manual)
        return error.manual.kind==ManualError::Kind::Angle
            ?"Manual(Angle(IntegerConversionUnavailable))"
            :"Manual(Measurement("+ServiceSourceDebug(error.manual.measurement)+"))";
    if(error.kind==GroundBoardError::Kind::Drag)
        return error.drag==DragBindingError::PartOutsideAssembly
            ?"Drag(PartOutsideAssembly)":"Drag(InertiaOutsideStorage)";
    constexpr const char* stages[]={"CenterOfMassHeight","SetWheelMaterials","ContactResponse",
        "UpdateBodyAccumulator","SetAnimatedVelocity","WriteProcessedVelocity","BuildAnimatedPose",
        "PublishAnimatedPose","UpdateExternalPlayer","CommitExternalPlayer","FinalizeAnimatedBoard",
        "CollisionForce","ApplyCollisionVector","CollisionProjection","ManualEffect","PushForceSquared",
        "AntiFlipNudge","ApplyCollisionDecay","ApplyStraighten","ApplyHeading","ApplyAntiFlip","ApplyManual",
        "HangUps","HalfpipeWheelCatch","Pinning","StrongForceSquared"};
    return "Service { stage: "+std::string(stages[static_cast<std::size_t>(error.stage)])+
        ", source: "+ServiceSourceDebug(error.source)+" }";
}
class Lifecycle final:public GroundLifecycleServices
{
    GroundPhaseOwners owners;
    Vec4& predicted;
public:
    Lifecycle(GroundPhaseOwners o,Vec4& prediction):owners(o),predicted(prediction){}
    bool SetSkeletonCollisionState(std::uint32_t state,std::string& error) override
    {
        if(state!=6){error="Ground requested a non-ground skeleton collision state";return false;}
        return owners.life.skeleton_controller.RequestGround(owners.physical.skeleton_collision,error);
    }
    bool EnterAirLandingModifier(bool reverse,std::string&) override
    {owners.wobble.Trigger(true,reverse);return true;}
    bool MoveFutureDeck(Vec3 delta,std::string&) override
    {
        owners.physical.skeleton_drives.targets.ApplyFutureDeckDisplacement(delta);
        predicted[0]+=delta.x;predicted[1]+=delta.y;predicted[2]+=delta.z;return true;
    }
    void InvalidateOffboardGrab() override {owners.grab.Invalidate();}
};
class Launch final:public GroundLaunchScheduler
{
    GroundPhaseOwners owners;
    AirSelectorInput selector;
    AirTrajectoryGrindContext context;
public:
    Launch(GroundPhaseOwners o,AirSelectorInput input):owners(o),selector(input),
        context(AirTrajectoryGrindContext::FromProcessed(o.processed,o.physical.DeckFrame()[3])){}
    bool LaunchAndUpdate(const GroundLaunchInfo& info,std::string& error) override
    {
        auto input=selector;input.board_vertical_velocity=info.velocity[1];bool launched,valid;
        if(!owners.trajectory.Launch(info.SelectorLaunch(),input,owners.physical.world,launched,error))return false;
        return owners.trajectory.Update(input,owners.physical.world,context,valid,error);
    }
};
bool SelectorInput(GroundPhaseOwners o,AirSelectorInput& output,std::string& error)
{
    const auto& p=o.processed;
    // BindAirSelectorInput consumes precisely this processed/world subset;
    // launch/frame-only fields of its wider input view are never read here.
    AirStateBindingInput input{};
    input.vectors_400_416=p.vectors_400_416;
    input.vectors_464_480_496_512_528=p.vectors_464_480_496_512_528;
    input.vectors_544_560_592_608=p.vectors_544_560_592_608;
    input.state_variant_index_2528=p.state_variant_index_2528;
    input.transition_2636=p.transition_2636;input.state_2504=p.state_2504;
    input.flags_2472=p.flags_2472;input.flags_2476=p.flags_2476;
    input.external_physics_flags=p.external_physics_1616.flags;
    input.world_gravity=Lanes(o.physical.settings.board.step.simulation.gravity_acceleration);
    return BindAirSelectorInput(input,o.air_settings,output,error);
}
}
void ResetGroundBoardState(GroundStateRuntime& ground,GroundRuntime& runtime,
    GroundPhaseLifecycle& life,bool& wiping_out)
{
    ground.steering.deck_tilt=0;ground.steering.targets={0,0};
    runtime.ResetBoardToolkit();life.board_animated_290=0;wiping_out=false;
}
bool EnterGroundPhase(GroundPhaseOwners o,std::string& error)
{
    if(!o.toolkit){error="Ground entry requires PlayerInput's current board toolkit";return false;}
    auto& physical=o.physical;const auto& p=o.processed;
    LiveBoardPossessionEffects effects(physical.board,o.life.board_animated_290,physical.board_wiping_out,
        physical.possession_live,physical.settings.board.collision,p.timestep_2604);
    effects.StandardBoard();physical.possession_live.PublishVolumes(physical.settings.board.collision);
    auto board_flags=static_cast<std::uint8_t>(static_cast<unsigned>(physical.board_wiping_out)<<7);
    auto prediction=physical.roots.predicted_board_position;Lifecycle services(o,prediction);
    const bool result=o.ground.Enter(physical.board,p,o.animation_input,*o.toolkit,
        {o.ik.state,o.life.skeleton_elapsed_16505,o.air_reckoning.state.spin_angle,
         o.air_reckoning.state.spin_speed,board_flags,o.life.board_animated_290,
         o.wipeout.mode,o.wipeout.balance,services},error);
    physical.board_wiping_out=(board_flags&0x80)!=0;return result;
}
std::optional<GroundBoardOutcome> AdvanceGroundPhase(GroundPhaseOwners o,const GroundSettings& settings,std::string& error)
{
    // Submission occurs even when a later selector/toolkit validation fails.
    const auto& p=o.processed;
    o.handplant.GroundQuery(p,o.grind_world);
    AirSelectorInput selector;if(!SelectorInput(o,selector,error))return std::nullopt;
    if(!o.toolkit){error="Ground update requires PlayerInput's current board toolkit";return std::nullopt;}
    if(o.life.pending_wall_jump){error="Ground wall jump is pending its trajectory selector continuation";return std::nullopt;}
    const auto edge=o.life.edge.value_or(GroundPhaseEdge{0,{},{},{}});
    auto& physical=o.physical;const auto& toolkit=*o.toolkit;
    const auto normal=Raw(p.vectors_464_480_496_512_528[0]),up=Raw(p.vectors_544_560_592_608[0]);
    const auto initial_velocity=Raw(p.vectors_400_416[0]);auto velocity=initial_velocity;
    auto predicted=physical.roots.predicted_board_position;Lifecycle services(o,predicted);Launch launch(o,selector);
    const GroundLaunchPhysical launch_physical{physical.riding.reckoning_frames,
        physical.board_frames.local_centre_of_mass,physical.board_frames.local_board_position,
        toolkit.deck[3],Raw(p.vectors_544_560_592_608[2]),initial_velocity,Raw(p.prepared_jump_704),p.flags_2468,p.timestep_2604};
    GroundPhysicalFrame frame{physical.animation_record,
        {normal,up,velocity,toolkit.total_mass,p.gravity_2648,p.scalar_2652,0},
        {p.flags_2472,Raw(p.collision_pose_error_736),Raw(p.vectors_400_416[1]),toolkit.travel_direction,
         up,Lanes(physical.riding.reckoning.ground_normal),p.timestep_2604,toolkit.total_mass},
        {edge.start,edge.end,Xyz(edge.point)},velocity,physical.settings.board.collision.wheel_material,
        o.wipeout,p.timestep_2604,&launch_physical,launch};
    std::memcpy(&frame.wall_ride.contact_count,&p.wheel_count_2556,4);
    GroundUpdateError detail;
    const auto result=o.ground.Update(o.runtime,physical.board,physical.world,settings,
        {p,o.animation_input,physical.riding,o.animated,physical.animation_record,physical.board_frames,toolkit,
         physical.settings.board.step.base_truck_transforms,
         {o.life.manual_drag_2724,p.external_physics_1616.flags,edge.flags,edge.point}},
        frame,{o.ik.state,o.life.skeleton_elapsed_16505,physical.correction.pending,services},detail);
    // Publish completed physical side effects even when a later branch fails.
    std::memcpy(o.processed.vectors_400_416[0].data(),velocity.data(),sizeof(velocity));
    physical.roots.predicted_board_position=predicted;
    if(!result)error=detail.stage==GroundUpdateError::Stage::Board
        ?"Native Ground board update: "+BoardErrorDebug(detail.board):detail.source;
    else error.clear();
    return result;
}
bool UpdateGroundSkeletonInput(GroundPhaseOwners o,SkeletonInputRuntime& skeleton,SkeletonAir& air,
    const std::vector<Mat4>& globals,std::string& error)
{
    auto& physical=o.physical;
    const SkeletonInputCollision collision{physical.collision_feedback.flags.compliant,
        physical.collision_feedback.flags.has_impulse,physical.collision_pose_error,
        physical.skeleton_collision.partial_ragdoll,physical.collision_feedback.drive_weight};
    Mat4 target;
    if(!skeleton.UpdateGround(physical.riding.reckoning_frames.system,o.processed,
        {physical,o.animated,o.ik,o.animation_input},globals,collision,target,error))return false;
    air.CapturePhysicsError(physical.board,target);return true;
}
}

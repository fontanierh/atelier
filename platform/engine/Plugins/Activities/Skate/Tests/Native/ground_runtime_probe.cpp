// The checker prefixes the unchanged physical/pose/dispatcher probe adapters.
#include "GroundStateRuntime.h"
#include "SkeletonController.h"
#include "OffboardGrabCache.h"
#include "AirStateSettings.h"
struct GroundInputReader:Input
{
    Vec3 Three(){return {Float(),Float(),Float()};}
    Mat4 Matrix(){return ::Matrix();}
    template<std::size_t N>PointGraph<N> Curve(){return {Floats<N>(),Floats<N>()};}
};
struct GroundOutputWriter:Output
{
    explicit GroundOutputWriter(std::vector<std::uint32_t>& w):Output{w}{}
    void Value(Vec3 v){Float(v.x);Float(v.y);Float(v.z);}
    void Value(Vec4 v){for(float f:v)Float(f);}
    void Value(const Mat4& m){for(const auto& v:m)Value(v);}
    template<std::size_t N>void Curve(const PointGraph<N>& c){for(float f:c.x)Float(f);for(float f:c.y)Float(f);}
};
// GENERATED_GROUND_PROTOCOL
namespace
{
Vec4 GroundRaw(RawVector w){Vec4 v;for(unsigned n=0;n<4;++n)std::memcpy(&v[n],&w[n],4);return v;}
struct GroundLife
{
    SkeletonControllerState controller;
    bool elapsed=false;
    std::uint8_t animated=0;
    float manual_drag=0,spin_angle=0,spin_speed=0;
    WipeoutRequests wipeout;
    OffboardGrabCache grab;
    std::vector<std::uint32_t> trace;
    std::optional<GroundLaunchInfo> pending_launch;
};
void GroundTrace(GroundLife& life,std::uint32_t id,const std::vector<std::uint32_t>& values)
{life.trace.push_back(id);life.trace.push_back(std::uint32_t(values.size()));life.trace.insert(life.trace.end(),values.begin(),values.end());}
class GroundLifecycle final:public GroundLifecycleServices
{
public:
    PhysicalSimulationRuntime& physical;GroundLife& life;SkeletonWobble& wobble;
    GroundLifecycle(PhysicalSimulationRuntime& p,GroundLife& l,SkeletonWobble& w):physical(p),life(l),wobble(w){}
    bool SetSkeletonCollisionState(std::uint32_t state,std::string& error)override
    {if(state!=6){error="Ground requested a non-ground skeleton collision state";return false;}return life.controller.RequestGround(physical.skeleton_collision,error);}
    bool EnterAirLandingModifier(bool reverse,std::string&)override
    {wobble.Trigger(true,reverse);return true;}
    bool MoveFutureDeck(Vec3 delta,std::string&)override
    {
        std::vector<std::uint32_t> words;GroundOutputWriter o(words);o.Value(delta);GroundTrace(life,3,words);
        physical.skeleton_drives.targets.ApplyFutureDeckDisplacement(delta);
        physical.roots.predicted_board_position[0]+=delta.x;physical.roots.predicted_board_position[1]+=delta.y;physical.roots.predicted_board_position[2]+=delta.z;return true;
    }
    void InvalidateOffboardGrab()override{GroundTrace(life,4,{});life.grab.Invalidate();}
};
class PendingGroundTrajectory final:public GroundLaunchScheduler
{
public:
    GroundLife& life;AirSelectorInput selector;
    PendingGroundTrajectory(GroundLife& l,AirSelectorInput s):life(l),selector(s){}
    bool LaunchAndUpdate(const GroundLaunchInfo& info,std::string& error)override
    {
        life.pending_launch=info;auto input=selector;input.board_vertical_velocity=info.velocity[1];
        std::vector<std::uint32_t> words;GroundOutputWriter o(words);Observe(o,info);Observe(o,info.SelectorLaunch());Observe(o,input);GroundTrace(life,7,words);
        error="Pending actual trajectory Launch/Update continuation";return false;
    }
};
OffboardGrabRecord GroundGrabRecord(std::uint32_t seed)
{
    OffboardGrabRecord record;for(unsigned n=0;n<72;++n)record.words[n]=seed*101u+n*17u;
    auto geometry=std::make_shared<OffboardGrabGeometry>();geometry->id=seed+1;geometry->word_60=seed^0xa5a55a5a;
    for(unsigned n=0;n<1+seed%4;++n)geometry->points.push_back({float(seed)*.125f,float(n)*.25f,-float(n)*.5f,0});
    for(unsigned n=0;n<seed%3;++n)geometry->approach_vectors.push_back({float(n)*.25f,1,0,-0.0f});
    record.geometry=geometry;return record;
}
void SeedGroundGrab(OffboardGrabCache& owner,std::uint32_t seed,std::uint8_t flags)
{
    owner=OffboardGrabCache{};owner.flags_12836=flags;owner.interactable_latched=(seed&1)!=0;
    owner.query_position={float(seed),.125f,-.25f,-0.0f};owner.validation_position={-.5f,float(seed)*.25f,.75f,0};
    for(unsigned n=0;n<seed%3;++n)
    {OffboardGrabQuery q{};q.position=owner.query_position;q.sort_position=owner.validation_position;q.bounds_frame=SkeletonIdentity;q.bounds_frame[3]=q.position;q.bounds_extents={.25f,.5f,.75f,1};q.margin=.125f;q.angle_a=-.25f;q.angle_b=.375f;q.mode=n;q.capacity=seed+n;q.selection_flags_2948=flags;q.matching_id_2952=-std::int32_t(seed);owner.queries.push_back(q);}
    for(unsigned n=0;n<1+seed%3;++n){owner.pending.push_back(GroundGrabRecord(seed+n));owner.validated.push_back(GroundGrabRecord(seed+n+10));}
    if(seed&1){owner.query_result=owner.pending;owner.validation=std::vector<std::optional<OffboardGrabHit>>{std::nullopt,OffboardGrabHit{.375f,std::nullopt},OffboardGrabHit{-.0f,seed+1}};}
    for(unsigned n=0;n<2;++n){if(seed&(1u<<n))owner.requests[n]=OffboardGrabDescriptor{n+1,seed+n};if(seed&(2u<<n))owner.data[n]=GroundGrabRecord(seed+20+n);owner.data_ready[n]=(seed&(4u<<n))!=0;}
    if(seed&2){std::array<OffboardGrabLine,5> lines;for(unsigned n=0;n<5;++n)lines[n]={{float(n),.25f,.5f,0},{float(n),-.25f,-.5f,0},.125f,-std::int32_t(seed),seed+n,2,seed^n};owner.interactable_request=lines;}
    if(seed%3==1)owner.interactable_result=std::optional<std::uint32_t>{};else if(seed%3==2)owner.interactable_result=std::optional<std::uint32_t>{seed+31};
}
void OutGroundGrabRecord(const OffboardGrabRecord& r)
{Out(r.words);const auto& g=*r.geometry;Out(g.id);Out(std::uint32_t(g.points.size()));for(auto v:g.points)Out(v);Out(std::uint32_t(g.approach_vectors.size()));for(auto v:g.approach_vectors)Out(v);Out(g.word_60);}
void OutGroundGrab(const OffboardGrabCache& s)
{
    Out(std::uint32_t(s.queries.size()));for(const auto& q:s.queries){Out(q.position);Out(q.sort_position);Out(q.bounds_frame);Out(q.bounds_extents);Out(q.margin);Out(q.angle_a);Out(q.angle_b);Out(q.mode);Out(std::uint32_t(q.capacity));Out(std::uint32_t(q.capacity>>32));Out(q.selection_flags_2948);Out(std::uint32_t(q.matching_id_2952));}
    Out(std::uint32_t(s.query_result.has_value()));if(s.query_result){Out(std::uint32_t(s.query_result->size()));for(const auto& r:*s.query_result)OutGroundGrabRecord(r);}
    for(const auto* records:{&s.pending,&s.validated}){Out(std::uint32_t(records->size()));for(const auto& r:*records)OutGroundGrabRecord(r);}
    Out(std::uint32_t(s.validation.has_value()));if(s.validation){Out(std::uint32_t(s.validation->size()));for(auto hit:*s.validation){Out(std::uint32_t(hit.has_value()));if(hit){Out(hit->fraction);Out(std::uint32_t(hit->assembly.has_value()));if(hit->assembly)Out(*hit->assembly);}}}
    for(auto d:s.requests){Out(std::uint32_t(d.has_value()));if(d){Out(d->kind);Out(d->id);}}for(const auto& r:s.data){Out(std::uint32_t(r.has_value()));if(r)OutGroundGrabRecord(*r);}for(bool b:s.data_ready)Out(std::uint32_t(b));
    Out(std::uint32_t(s.interactable_request.has_value()));if(s.interactable_request)for(auto l:*s.interactable_request){Out(l.start);Out(l.end);Out(l.radius);Out(std::uint32_t(l.group));Out(l.reject_flags);Out(std::uint32_t(l.source_pool_mask));Out(l.selection_flags);}
    Out(std::uint32_t(s.interactable_result.has_value()));if(s.interactable_result){Out(std::uint32_t(s.interactable_result->has_value()));if(*s.interactable_result)Out(**s.interactable_result);}Out(std::uint32_t(s.interactable_latched));Out(std::uint32_t(s.flags_12836));Out(s.query_position);Out(s.validation_position);
}
void OutGroundOwner(const GroundStateRuntime& s,const GroundRuntime& runtime,const GroundSettings& settings,const GroundLife& life,const SkeletonWobble& wobble)
{
    GroundOutputWriter o(output);Observe(o,s.state);Observe(o,s.pumping);Out(s.wobble.words);Observe(o,s.steering);Observe(o,s.speed);Observe(o,s.manual);Out(s.heading_previous);Out(std::uint32_t(s.entered));Out(s.output_settings.pushable_speed_terms_4_8);Out(s.output_settings.mode_speed_threshold_0);for(bool b:s.auto_push_enabled)Out(std::uint32_t(b));for(float f:{s.entry_settings.deck_angular_drag,s.entry_settings.powerslide_exit,s.entry_settings.landing_strength,s.entry_settings.landing_offset})Out(f);Observe(o,s.pumping_settings.settings);for(const auto& mode:s.pumping_settings.modes){Observe(o,mode.controller);Out(mode.unintentional_scalar);}
    Observe(o,settings);Out(runtime.retained_board_normal);const auto& w=runtime.wall_ride;Out(w.anti_gravity_vs_time.x);Out(w.anti_gravity_vs_time.y);for(float f:{w.max_dot_floor_wall,w.foot_force_time,w.auto_jump_height,w.max_time,w.velocity_time_to_consider,w.auto_jump_y_down_scalar,w.auto_jump_force})Out(f);Observe(o,runtime.collision);Out(runtime.deck_center_to_truck);Out(runtime.launch_cone_x);Out(runtime.launch_cone_z);
    const auto& c=runtime.contact;Out(std::uint32_t(c.active_2731));Out(c.tag_16_force.tag);Out(c.tag_16_force.force_world);Out(c.tag_16_force.point_body);Out(c.vector_2688);Out(c.scalar_2704);Out(std::uint32_t(c.animated_board_2708));Out(std::uint32_t(runtime.collision_force.has_value()));if(runtime.collision_force){Out(runtime.collision_force->force_2528);Out(runtime.collision_force->point_2544);Out(runtime.collision_force->vector_2592);}
    Out(life.controller.effective);Out(life.controller.requested);for(bool b:{life.controller.has_request,life.controller.override_enabled,life.controller.flag_18,life.elapsed})Out(std::uint32_t(b));Out(std::uint32_t(life.animated));Out(life.manual_drag);Out(life.spin_angle);Out(life.spin_speed);Out(std::uint32_t(wobble.active));Out(std::uint32_t(wobble.landing));Out(wobble.time);Out(wobble.amplitude);Out(wobble.direction);for(bool b:life.wipeout.reasons)Out(std::uint32_t(b));Out(life.wipeout.values);Out(life.wipeout.count);Out(life.wipeout.cooldown);Out(std::uint32_t(life.wipeout.contact_frames));Out(life.wipeout.balance);Out(life.wipeout.mode);Out(std::uint32_t(life.pending_launch.has_value()));if(life.pending_launch)Observe(o,*life.pending_launch);OutGroundGrab(life.grab);Out(std::uint32_t(life.trace.size()));for(auto word:life.trace)Out(word);
}
void OutGroundPhysics(const PhysicsGroundOutput& s)
{
    Out(std::uint32_t(s.skateboard_motion_4.is_push_accelerating));Out(std::uint32_t(s.skateboard_motion_4.is_at_pushable_speed));Out(std::uint32_t(s.velocity_projection_36.has_value()));if(s.velocity_projection_36){Out(s.velocity_projection_36->velocity_without_axis_component);Out(std::uint32_t(s.velocity_projection_36->active));}
    const auto& g=s.ground_32;for(bool b:{g.wall_ride_exit,g.anti_flip_nudge_present,g.is_pinning})Out(std::uint32_t(b));Out(g.anti_flip_torque);Out(g.time_to_skitch);Out(g.skitch_spline_height);Out(g.processed_scalar_2720);Out(std::uint32_t(g.processed_flag_2484_bit_13));const auto& r=s.state_28;Out(r.grab_spline_type);Out(r.grab_spline_object_id);Out(std::uint32_t(r.flag_84));Out(std::uint32_t(r.has_world_grab_intent_without_object));Out(std::uint32_t(r.manual_correction_write_78.has_value()));if(r.manual_correction_write_78)Out(std::uint32_t(*r.manual_correction_write_78));for(bool b:{s.intents_52.has_world_grab_intent,s.intents_52.selected_mode_below_speed_threshold_58,s.is_grabbing_object_72_304,s.manual_opposition_56_168,s.push_suppressed_20_596})Out(std::uint32_t(b));
}
void OutGroundOutcome(const GroundBoardOutcome& s)
{Out(std::uint32_t(s.kind));Out(std::uint32_t(s.tag_15_queued));Out(std::uint32_t(s.ordinary.manual_correction));Out(s.ordinary.terminal_force_tag);Out(std::uint32_t(s.ordinary.terminal_force_queued));Out(std::uint32_t(s.ordinary.speed_model_reset));}
void GroundResult(bool success,const std::string& error){Out(std::uint32_t(success));Out(error);}
bool GroundTick(GroundInputReader& i,PhysicalSimulationRuntime& r,AnimatedSkeleton& animated,FootIk& ik,SkeletonInputRuntime& owner,PhysicsAnimationInput& input,SkeletonWobble& wobble,const SkeletonWobbleSettings& ws,AnimationPoseEvaluator& evaluator,AdjustedFrame& state,Actions& actions,GroundStateRuntime& ground,GroundRuntime& runtime,const GroundSettings& settings,GroundLife& life,const AirStateSettings& air)
{
    const bool processed=ProcessDispatcher(i,r,animated,ik,owner,input,wobble,ws,evaluator,state,actions);
    const auto pose=i.Word();const bool enter=i.Word()!=0;auto& p=state.input;p.state_2504=i.Word();p.category_2516=i.Word();p.state_variant_index_2528=i.Word();p.state_timer_2664=i.Float();p.time_since_last_input_2748=i.Float();p.truck_tightness_2760=i.Float();p.crouch_2776=i.Float();p.crouch_delta_2780=i.Float();p.spin_input_2672=i.Float();p.transition_2636=i.Float();p.frames_since_teleport_2584=i.Word();life.manual_drag=i.Float();const auto trajectory=i.Word(),edge_flags=i.Word();const auto edge_point=i.Floats<4>();const auto edge_start=i.Three(),edge_end=i.Three();const bool launch_present=i.Word()!=0,coffin=i.Word()!=0,solve=i.Word()!=0;
    if(!processed)return false;life.trace.clear();life.pending_launch.reset();std::string error;
    p.wheel_count_2556=std::uint32_t(r.riding.ground.wheel_contact_count);p.scalar_2612=r.riding.motion.speed;p.scalar_2616=r.riding.motion.ground_speed;p.scalar_2652=r.riding.motion.forward_speed;p.scalar_2656=r.riding.motion.ground_speed;p.scalar_2764=0;
    p.vectors_400_416[0]=Raw(Four(r.board.Bodies()[6].rates.linear_velocity));p.vectors_400_416[1]=Raw(Four(r.board.Bodies()[6].rates.angular_velocity));p.vectors_464_480_496_512_528[0]=Raw(Four(r.riding.ground.wheel_normal));p.vectors_464_480_496_512_528[1]=p.vectors_464_480_496_512_528[2]=Raw(Four(r.riding.ground.parts[6].point));p.vectors_464_480_496_512_528[3]=Raw(r.roots.heading_alignment[2]);p.vectors_464_480_496_512_528[4]=Raw(Four(r.riding.ground.overall_normal));p.vectors_544_560_592_608[0]=Raw(r.roots.animation_to_world[1]);p.vectors_544_560_592_608[2]=Raw(r.skeleton.record.centre_of_mass);p.vectors_544_560_592_608[3]=Raw(r.skeleton.record.centre_of_mass_velocity);p.collision_pose_error_736=Raw(r.collision_pose_error);p.effective_anim_transform_192={Raw(r.roots.animation_to_world[0]),Raw(r.roots.animation_to_world[1]),Raw(r.roots.animation_to_world[2]),Raw(r.roots.animation_to_world[3])};p.time_on_ground_2752=float(r.ticks)*p.timestep_2604;p.signed_ground_time_2756=p.time_on_ground_2752;
    const auto toolkit=PrepareGroundToolkit(runtime,r.board,p);GroundLifecycle lifecycle(r,life,wobble);
    if(enter){LiveBoardPossessionEffects effects(r.board,life.animated,r.board_wiping_out,r.possession_live,r.settings.board.collision,p.timestep_2604);effects.StandardBoard();r.possession_live.PublishVolumes(r.settings.board.collision);std::uint8_t flags=std::uint8_t(r.board_wiping_out)<<7;const bool entered=ground.Enter(r.board,p,input,toolkit,{ik.state,life.elapsed,life.spin_angle,life.spin_speed,flags,life.animated,life.wipeout.mode,life.wipeout.balance,lifecycle},error);r.board_wiping_out=(flags&0x80)!=0;GroundResult(entered,error);if(!entered)return false;}
    // Original GroundPacketInputs reads forward speed2652 and absolute speed2616.
    const PhysicalGroundPacket packet{r.riding.ground.wheel_normal,r.riding.ground.overall_normal,p.scalar_2652,p.scalar_2616,r.riding.ground.wheel_contact_count};r.riding.UpdateGroundReckoning(r.board,{r.animation_record.ComToDeck(),input.extra.physical_body_spin},p.flags_2468,input.fields.balance,coffin,packet);ground.state.push_suppressed_2730=false;
    std::vector<std::uint32_t> pending;GroundOutputWriter po(pending);po.Word(p.flags_2476);po.Word(p.state_2508);po.Value(toolkit.deck);po.Value(r.roots.animation_to_world);GroundTrace(life,5,pending);
    AirStateBindingInput binding{};binding.vectors_400_416=p.vectors_400_416;binding.vectors_464_480_496_512_528=p.vectors_464_480_496_512_528;binding.vectors_544_560_592_608=p.vectors_544_560_592_608;binding.world_gravity=Four(r.settings.board.step.simulation.gravity_acceleration);binding.transition_2636=p.transition_2636;binding.state_2504=p.state_2504;binding.flags_2472=p.flags_2472;binding.flags_2476=p.flags_2476;binding.external_physics_flags=p.external_physics_1616.flags;binding.state_variant_index_2528=p.state_variant_index_2528;AirSelectorInput selector;
    if(!BindAirSelectorInput(binding,air,selector,error)){GroundResult(false,error);return false;}GroundOutputWriter observation(output);Observe(observation,selector);
    const auto normal=GroundRaw(p.vectors_464_480_496_512_528[0]),up=GroundRaw(p.vectors_544_560_592_608[0]),initial=GroundRaw(p.vectors_400_416[0]);Vec4 velocity=initial;
    const GroundLaunchPhysical launch{r.riding.reckoning_frames,r.board_frames.local_centre_of_mass,r.board_frames.local_board_position,toolkit.deck[3],GroundRaw(p.vectors_544_560_592_608[2]),initial,GroundRaw(p.prepared_jump_704),p.flags_2468,p.timestep_2604};PendingGroundTrajectory trajectory_boundary(life,selector);
    const GroundPhysicalFrame physical{r.animation_record,{normal,up,initial,toolkit.total_mass,p.gravity_2648,p.scalar_2652,std::int32_t(p.wheel_count_2556)},{p.flags_2472,GroundRaw(p.collision_pose_error_736),GroundRaw(p.vectors_400_416[1]),toolkit.travel_direction,up,Four(r.riding.reckoning.ground_normal),p.timestep_2604,toolkit.total_mass},{edge_start,edge_end,{edge_point[0],edge_point[1],edge_point[2]}},velocity,r.settings.board.collision.wheel_material,life.wipeout,p.timestep_2604,launch_present?&launch:nullptr,trajectory_boundary};
    GroundUpdateError failure;auto outcome=ground.Update(runtime,r.board,r.world,settings,{p,input,r.riding,animated,r.animation_record,r.board_frames,toolkit,r.settings.board.step.base_truck_transforms,{life.manual_drag,trajectory,edge_flags,edge_point}},physical,{ik.state,life.elapsed,r.correction.pending,lifecycle},failure);p.vectors_400_416[0]=Raw(velocity);
    Out(std::uint32_t(outcome.has_value()));if(!outcome){Out(std::uint32_t(failure.stage));Out(std::uint32_t(failure.board.kind));Out(std::uint32_t(failure.board.stage));Out(failure.source);Out(failure.board.source);return false;}const auto outcome_start=output.size();OutGroundOutcome(*outcome);GroundTrace(life,9,std::vector<std::uint32_t>(output.begin()+std::ptrdiff_t(outcome_start),output.end()));if(p.state_variant_index_2528<5)OutGroundPhysics(ground.Output(p,input,toolkit));
    GroundTrace(life,6,pending);const auto globals=Hierarchy(evaluator,pose);r.board_frames.UpdateComLift(r.roots.animation_to_world,animated.animation_hips[3],.02f);const SkeletonInputOwners owners{r,animated,ik,input};Mat4 frame=SkeletonIdentity;const bool adjusted=owner.UpdateGround(r.riding.reckoning_frames.system,p,owners,globals,{r.collision_feedback.flags.compliant,r.collision_feedback.flags.has_impulse,r.collision_pose_error,r.skeleton_collision.partial_ragdoll,r.collision_feedback.drive_weight},frame,error);Out(frame);GroundResult(adjusted,error);if(!adjusted)return false;
    pending.clear();GroundOutputWriter capture(pending);capture.Value(frame);capture.Value(r.board_frames.animation_target);GroundTrace(life,8,pending);
    r.processed_flags_2468=p.flags_2468;if(!solve)return true;if(!r.Solve(ground.steering.targets,error)){GroundResult(false,error);return false;}Out(std::uint32_t(r.contact_count));Out(std::uint32_t(r.solved_drives?r.solved_drives->rows.size():0));r.FinishBoardOutputs({p.state_2508,packet.wheel_normal,{r.roots.animation_to_world[1][0],r.roots.animation_to_world[1][1],r.roots.animation_to_world[1][2]},{toolkit.deck[3][0],toolkit.deck[3][1],toolkit.deck[3][2]},float(r.ticks)*p.timestep_2604});PhysicalFeedbackInput feedback{p.state_2508,p.category_2512,p.flags_2472,p.flags_2480,{},{}};feedback.vectors_464_480_496_512_528[0]=Four(packet.wheel_normal);feedback.vectors_464_480_496_512_528[1]=feedback.vectors_464_480_496_512_528[2]=Four(r.riding.ground.parts[6].point);feedback.vectors_464_480_496_512_528[4]=Four(packet.dynamic_up);feedback.vectors_880_896_912_928_944[0]=animated.animation_hips[3];feedback.vectors_880_896_912_928_944[1]={0,1,0,0};r.PublishFeedback(feedback);
    auto observed=r.DeckFrame();const auto sample=wobble.Update(ws);ApplySkeletonWobble(sample,observed);Out(std::uint32_t(sample.sampled));Out(sample.tilt);Out(sample.squish);Out(std::uint32_t(sample.remains_active));Out(observed);const auto post=ik.PostPhysics(r.skeleton,{p.state_2508,p.category_2512,r.riding.ground.part_contact_count!=0,false,p.flags_2468,p.flags_2484,p.state_timer_2664,p.player_state_value_2520,r.roots.world_to_animation,observed});for(bool b:post)Out(std::uint32_t(b));r.skeleton.PublishPhysicalRecord(r.DeckFrame());const bool finished=r.FinishFrame(error);GroundResult(finished,error);return finished;
}
}
int main(int argc,char** argv)
{
    if(argc==3&&std::string_view(argv[2])=="--load-only")
    {
        SettingsDatabase data;std::string error;if(!data.Load(FileBytes(argv[1]),error))return 2;const auto stage=Word();bool ok=false;
        if(stage==0){GroundStateRuntime value;ok=value.Load(data,true,error);}else if(stage==1){GroundRuntime value;ok=value.Load(data,error);}else if(stage==2){GroundProfiles value;ok=value.Load(data,error);}else std::abort();GroundResult(ok,error);for(auto w:output)for(unsigned j=0;j<4;++j)std::cout.put(static_cast<char>(w>>(j*8)));return 0;
    }
    if(argc!=5)return 2;SettingsDatabase data;PhysicsSkeletons physical;AnimationPoseFrames frames;std::string error;if(!data.Load(FileBytes(argv[1]),error)||!physical.Load(FileBytes(argv[2]),argv[4],error)||!frames.rig.Load(FileBytes(argv[3]),error)){std::cerr<<error;return 2;}const auto* bank=physical.Find("PHYS_TPOSE");if(!bank)return 2;AnimationPoseEvaluator evaluator(std::move(frames));const auto settings=PhysicalSimulationSettings::Load(data,*bank,evaluator.frames.rig,error);const auto animated_settings=AnimatedSkeletonSettings::Load(data,*bank,evaluator.frames.rig,false,error);const auto ws=SkeletonWobbleSettings::Load(data,error);AirStateSettings air;GroundProfiles profiles;if(!settings||!animated_settings||!ws||!air.Load(data,error)||!profiles.Load(data,error)){std::cerr<<error;return 2;}
    GroundInputReader i;const auto count=i.Word();for(unsigned c=0;c<count;++c)
    {
        const auto spawn=ReadAffine();auto world=ReadWorld(settings->board.floor_material);const bool seams=i.Word()!=0;const auto mode=i.Word(),surface=i.Word();const auto tuning=ReadTrainerTuning(i);auto selected=profiles.Select(mode,surface,error);if(!selected){std::cerr<<error;return 2;}auto active=selected->Tuned(tuning);auto value=PhysicalSimulationRuntime::Initialize(*settings,data,evaluator,std::move(world),spawn,error);if(!value){std::cerr<<error;return 2;}auto& r=*value;if(seams)r.EnableImportedFloorSeams();AnimatedSkeleton animated(*animated_settings);const auto loaded=FootIk::Load(data,evaluator.frames.rig,animated,error);const auto runtime=SkeletonInputRuntime::Load(data,error);if(!loaded||!runtime){std::cerr<<error;return 2;}auto ik=*loaded;auto owner=*runtime;PhysicsAnimationInput input;if(!input.Load(data,evaluator.frames.rig,"normal",error)){std::cerr<<error;return 2;}GroundStateRuntime ground;GroundRuntime board_runtime;if(!ground.Load(data,true,error)||!board_runtime.Load(data,error)){std::cerr<<error;return 2;}GroundLife life;SkeletonWobble wobble;AdjustedFrame state;Actions actions;const auto n=i.Word();Out(c);Out(n);const auto mark=output.size();Out(0u);const auto initial=output.size();Out(0u);Snapshot(r);OutAdjusted(animated,ik,owner.grind_air,state.queries);ObserveDispatcher(owner,input,wobble,life.elapsed,state.input,actions);const auto ground_initial=output.size();OutGroundOwner(ground,board_runtime,active,life,wobble);Out(std::uint32_t(output.size()-ground_initial));output[initial]=output.size()-initial-1;
        for(unsigned k=0;k<n;++k)
        {
            const auto op=i.Word();Out(op);const auto at=output.size();Out(0u);const auto payload=output.size();Out(0u);
            switch(op)
            {
            case 0:{const auto success=output.size();Out(0u);output[success]=GroundTick(i,r,animated,ik,owner,input,wobble,*ws,evaluator,state,actions,ground,board_runtime,active,life,air);break;}
            case 1:ground.Exit(board_runtime,r,state.input);break;
            case 2:{const auto m=i.Word(),s=i.Word();auto choice=profiles.Select(m,s,error);GroundResult(bool(choice),error);if(choice)active=choice->Tuned(tuning);break;}
            case 3:ground.state=ReadPhysicsGroundState(i);ground.pumping=ReadPumpingState(i);ground.entered=i.Word()!=0;break;
            case 4:{const auto seed=i.Word();SeedGroundGrab(life.grab,seed,std::uint8_t(i.Word()));break;}
            case 5:life.grab.Invalidate();break;case 6:life.grab.EnterReset();break;
            case 7:r.ReplaceWorld(ReadWorld(r.settings.board.floor_material));break;
            case 8:ground.steering.deck_tilt=0;ground.steering.targets={0,0};board_runtime.ResetBoardToolkit();life.animated=0;r.board_wiping_out=false;break;
            case 9:{const auto t=PrepareGroundToolkit(board_runtime,r.board,state.input);GroundResult(UpdatePhysicalRevertPumping(ground.pumping,ground.pumping_settings,t,r.riding,r.animation_record,state.input,i.Float(),error),error);break;}
            case 10:life.controller.effective=i.Word();life.controller.requested=i.Word();life.controller.has_request=i.Word()!=0;life.controller.override_enabled=i.Word()!=0;life.controller.flag_18=i.Word()!=0;life.elapsed=i.Word()!=0;life.animated=std::uint8_t(i.Word());life.spin_angle=i.Float();life.spin_speed=i.Float();life.wipeout.mode=i.Word();life.wipeout.balance=i.Float();r.board_wiping_out=i.Word()!=0;break;
            default:std::abort();
            }
            output[payload]=output.size()-payload-1;Snapshot(r);OutAdjusted(animated,ik,owner.grind_air,state.queries);ObserveDispatcher(owner,input,wobble,life.elapsed,state.input,actions);const auto ground_observation=output.size();OutGroundOwner(ground,board_runtime,active,life,wobble);Out(std::uint32_t(output.size()-ground_observation));output[at]=output.size()-at-1;
        }output[mark]=output.size()-mark-1;
    }if(std::cin.peek()!=std::char_traits<char>::eof())return 2;for(auto w:output)for(unsigned j=0;j<4;++j)std::cout.put(static_cast<char>(w>>(j*8)));
}

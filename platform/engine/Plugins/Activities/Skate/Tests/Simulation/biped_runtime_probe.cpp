#include "BipedGroundRuntime.h"
#include "BipedAirRuntime.h"
#include "SkeletonLineQueries.h"
#include "PlayerInputPhase.h"
#include "PlayerStateRuntime.h"
[[noreturn]]void Fail(const char* e){std::cerr<<e;std::exit(2);}
struct BipedInput:Input
{
    template<std::size_t N>std::array<std::uint32_t,N> Words(){std::array<std::uint32_t,N> a;for(auto& w:a)w=Word();return a;}
    template<class T,std::size_t N,class F>std::array<T,N> Array(F f){std::array<T,N>a;for(auto& v:a)v=f(*this);return a;}
    template<class T,class F>std::optional<T> Optional(F f){return Word()?std::optional<T>{f(*this)}:std::nullopt;}
    Vec3 Vector(){const auto x=Float(),y=Float(),z=Float();return {x,y,z};}
    float Scalar(){return Float();}
    std::string Text(){std::string s;const auto n=Word();for(unsigned k=0;k<n;++k)s+=char(Word());return s;}
    template<std::size_t N>PointGraph<N> Curve(){return {Floats<N>(),Floats<N>()};}
};
struct BipedOutput:Output
{
    void Scalar(float f){Float(f);}void Vector(Vec3 v){Float(v.x);Float(v.y);Float(v.z);}
    void Value(Vec4 v){Floats(v);}void Value(Mat4 m){Matrix(m);}
    template<std::size_t N>void Curve(PointGraph<N> c){Floats(c.x);Floats(c.y);}
};
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-function"
// GENERATED_WORLD
// GENERATED_PROTOCOL
// GENERATED_PROVIDER
#pragma clang diagnostic pop
namespace
{
void GroundOwnerOut(BipedOutput& o,const BipedGroundRuntime& g)
{
    Observe(o,g.controller.state);o.Word(g.result.has_value());if(g.result)Observe(o,*g.result);Observe(o,g.state);biped_contact::PrefixOut(o,g.contact);
    const auto& i=g.controller.settings.movement_intent;for(const auto& graph:{i.sprint_blend,i.slide_steering})o.Curve(graph);o.Curve(i.sprint_speed);o.Curve(i.normal_speed);o.Float(i.sprint_time_cap);
    const auto& v=g.controller.settings.movement_velocity;for(const auto& graph:{v.slope_speed_scalar,v.slope_mode_speed,v.turn_vs_speed,v.turn_delta_vs_speed,g.controller.settings.slide_vs_slope,g.controller.settings.slide_vs_speed})o.Curve(graph);
    o.Word(g.geometry_adjustment.has_value());if(g.geometry_adjustment)biped_geometry::AdjustmentOut(o,*g.geometry_adjustment);
    o.Matrix(g.skeleton_state.retained_board);o.Floats(g.skeleton_state.ground_normal_smoothing);o.Curve(g.skeleton_state.tilt_vs_rotation);o.Curve(g.skeleton_state.tilt_vs_slope);
    biped_geometry::OwnerOut(o,g.geometry);o.Curve(g.movement_vs_stick_angle);o.Curve(g.turn_vs_stick_angle);o.Float(g.air_launch.jump_speed_scalar);o.Float(g.air_launch.jump_height);
    const auto& c=g.collision_settings;for(auto x:{c.vehicle_scalar,c.vehicle_contact,c.maximum_displacement,c.maximum_arm_contact,c.maximum_body_contact,c.minimum_speed,c.maximum_squash,c.special_scalar})o.Float(x);
    const auto& b=g.grab_settings;o.Floats(b.extent_0);o.Floats(b.extent_16);o.Floats(b.offset_32);for(auto x:{b.angle_436,b.angle_440,b.margin_444,b.angle_452,b.angle_456})o.Float(x);
}
void AirOwnerOut(BipedOutput& o,const BipedAirRuntime& a)
{Observe(o,a.state);for(const auto& c:{a.checks.skeleton_air,a.checks.offboard_air})for(auto x:{c.squash,c.displacement,c.body_contact,c.arm_contact})o.Float(x);o.Float(a.checks.offboard_min_speed);}
WipeoutObservations Observations(BipedRuntimeOwners v,const AirTrajectoryRuntime& trajectory,const PlayerStateRuntime& state)
{
    const auto& p=v.physical;return {v.processed,p.riding.ground,p.collision_feedback,p.DeckFrame(),p.board_frames.animation_target,p.roots.world_to_animation,p.collision_pose_error,p.collision_maximum_error,state.post.jump_fix_frames,v.air_reckoning.state,p.riding.reckoning_frames.system[1][1],trajectory.selector.GrindLockedToMiddle(),trajectory.selector.GrindNormal()};
}
void ActualPacket(ProcessedPhysicsInput& x,const PhysicalSimulationRuntime& p,const PlayerInputState& lines)
{
    const auto velocity=p.board.Bodies()[6].rates.linear_velocity;x.vectors_400_416[0]=Raw(Vec4{velocity.x,velocity.y,velocity.z,0});x.vectors_400_416[1]=x.vectors_400_416[0];
    x.vectors_544_560_592_608[2]=Raw(p.skeleton.record.centre_of_mass);x.vectors_544_560_592_608[3]=Raw(p.skeleton.record.centre_of_mass_velocity);x.collision_pose_error_736=Raw(p.collision_pose_error);
    for(unsigned k=0;k<4;++k)x.effective_anim_transform_192[k]=Raw(p.roots.animation_to_world[k]);
    x.line_tests_960_1008_1056={lines.left_line_test_1536,lines.right_line_test_1584,lines.hips_line_test_1488};
}
bool SolveFeedback(BipedRuntimeOwners v,std::string& error)
{
    auto& p=v.physical;const auto& x=v.processed;if(!p.Solve({0,0},error))return false;
    if(!v.toolkit){error="Postphysics wall probe requires the current board toolkit";return false;}const auto& t=*v.toolkit;
    const auto up=Decode(x.vectors_544_560_592_608[0]),normal=Decode(x.vectors_464_480_496_512_528[0]);p.processed_flags_2468=x.flags_2468;
    p.FinishBoardOutputs({x.state_2508,{normal[0],normal[1],normal[2]},{up[0],up[1],up[2]},{t.deck[3][0],t.deck[3][1],t.deck[3][2]},x.time_on_ground_2752});
    PhysicalFeedbackInput f{x.state_2508,x.category_2512,x.flags_2472,x.flags_2480,{},{}};
    for(unsigned k=0;k<5;++k){f.vectors_464_480_496_512_528[k]=Decode(x.vectors_464_480_496_512_528[k]);f.vectors_880_896_912_928_944[k]=Decode(x.vectors_880_896_912_928_944[k]);}
    p.PublishFeedback(f);return p.FinishFrame(error);
}
void PossessionOut(BipedOutput& o,const PhysicalSimulationRuntime& p)
{
    const auto& f=p.controller_fields;o.Word(f.word_444);o.Word(f.state_448);o.Word(f.system_on_452);const auto& s=p.possession.state;const auto& r=s.retrieval;
    o.Matrix(r.initial_0);o.Matrix(r.target_64);o.Matrix(r.current_128);for(auto x:{r.elapsed_192,r.duration_196,r.progress_200,r.weight_204})o.Float(x);
    for(const auto& h:s.hands){o.Matrix(h.child);o.Matrix(h.parent);for(const auto& d:h.dynamics)for(auto w:d)o.Word(w);}o.Word(s.selected_hand_424);
    const auto& l=p.possession_live;o.Word(l.volumes.deck);o.Word(l.volumes.trucks);o.Word(l.volumes.wheels);o.Word(std::uint32_t(l.volumes.deck_children.size()));for(auto b:l.volumes.deck_children)o.Word(b);
    o.Floats(l.alignment.first_1008);o.Floats(l.alignment.second_1024);o.Float(l.alignment.factor_1040);o.Word(l.alignment.flag_1044);o.Word(l.alignment_active);o.Word(p.board_wiping_out);
    for(const auto m:{p.settings.board.collision.wheel_material,p.settings.board.collision.truck_material,p.settings.board.collision.deck_material}){o.Float(m.static_friction);o.Float(m.dynamic_friction);o.Float(m.restitution);}
    o.Word(p.settings.board.collision.truck_collisions);o.Word(std::uint32_t(p.settings.board.collision.deck_geometry.children.size()));for(const auto& c:p.settings.board.collision.deck_geometry.children)o.Word(c.collision_enabled);
}
void BipedSnapshot(BipedOutput& o,const BipedGroundRuntime& g,const BipedAirRuntime& a,BipedRuntimeOwners v,const AirTrajectoryRuntime& trajectory,const OffboardGrabCache& grab,const std::optional<OffboardToolkitInput>& last,const BipedStatePublication& returned,const PlayerInputState& lines,const PlayerStateRuntime& player_state)
{
    o.Word(16);Block(o,[&]{GroundOwnerOut(o,g);});Block(o,[&]{AirOwnerOut(o,a);});Block(o,[&]{biped_contact::OwnerOut(o,v.contact);});
    Block(o,[&]{biped_selector::OwnerOut(o,v.selector,v.selector.core.launch,a.state.result);biped_selector::SettingsOut(o,v.selector.settings);});
    Block(o,[&]{biped_landing::OwnerOut(o,v.landing);});Block(o,[&]{biped_grab::OwnerOut(o,grab);});Block(o,[&]{Observe(o,v.feet);});
    Block(o,[&]{Observe(o,v.publication);o.Word(returned.word_36);o.Word(returned.word_40);o.Word(returned.flag_86);});Block(o,[&]{Observe(o,v.processed);});
    Block(o,[&]{const auto& c=v.life.skeleton_controller;o.Word(c.effective);o.Word(c.requested);o.Word(c.has_request);o.Word(c.override_enabled);o.Word(c.flag_18);o.Word(v.life.skeleton_elapsed_16505);o.Word(v.life.board_animated_290);o.Float(v.life.manual_drag_2724);o.Word(v.life.edge.has_value());o.Word(v.life.pending_wall_jump.has_value());});
    Block(o,[&]{const auto& p=v.physical;o.Word(std::uint32_t(p.board.Forces().Count()));for(std::size_t n=0;n<p.board.Forces().Count();++n){const auto& f=p.board.Forces().Entries()[n];o.Word(f.tag);VectorOut(o,f.force_world);VectorOut(o,f.point_body);}o.Word(std::uint32_t(p.contact_count));o.Word(std::uint32_t(p.network_contacts));o.Wide(p.ticks);o.Word(p.failed);});
    Block(o,[&]{ObserveFeedback(o,v.physical.collision_feedback);});Block(o,[&]{WipeoutFrame f;std::string e;const bool valid=Observations(v,trajectory,player_state).Frame(f,e);o.Status(valid,e);if(valid)Observe(o,f);});
    Block(o,[&]{o.Word(last.has_value());if(last)for(const auto& x:{last->position,last->forward,last->up,last->right,last->velocity,last->animation_up,last->animation_right})o.Floats(x);});
    Block(o,[&]{Observe(o,lines);});Block(o,[&]{PossessionOut(o,v.physical);});
}
}
int main(int argc,char** argv)
{
    if(argc!=7&&argc!=8)return 2;SettingsDatabase data;PhysicsSkeletons skeletons;AnimationPoseFrames frames;std::string error;
    if(!data.Load(File(argv[1]),error))return 2;
    AnimationMetadata metadata,other;if(!metadata.Load(File((std::string(argv[6])+"/bank-0.skate").c_str()),error)||!other.Load(File((std::string(argv[6])+"/bank-1.skate").c_str()),error)||!metadata.Merge(other,error))return 2;
    if(argc==8)
    {
        auto ground=BipedGroundRuntime::Load(data,metadata,error);BipedAirRuntime air;if(!ground||!air.Load(data,error))return 2;BipedOutput o;
        o.Status(true,"");Block(o,[&]{GroundOwnerOut(o,*ground);});Block(o,[&]{AirOwnerOut(o,air);});
        SettingsDatabase invalid;if(!invalid.Load(File(argv[7]),error))return 2;auto next=BipedGroundRuntime::Load(invalid,metadata,error);BipedAirRuntime next_air;bool okay=bool(next);
        if(okay)okay=next_air.Load(invalid,error);if(okay){ground=std::move(next);air=std::move(next_air);}o.Status(okay,error);
        Block(o,[&]{GroundOwnerOut(o,*ground);});Block(o,[&]{AirOwnerOut(o,air);});for(const auto w:o.words)for(unsigned n=0;n<4;++n)std::cout.put(char(w>>(n*8)));return std::cout?0:2;
    }
    if(!skeletons.Load(File(argv[2]),argv[4],error)||!frames.rig.Load(File(argv[3]),error))return 2;
    const auto* definition=skeletons.Find("PHYS_TPOSE");if(!definition)return 2;AnimationPoseEvaluator evaluator(std::move(frames));if(!evaluator.LoadAuthoredClips(argv[5],error))return 2;
    const auto settings=PhysicalSimulationSettings::Load(data,*definition,evaluator.frames.rig,error);
    const auto asettings=AnimatedSkeletonSettings::Load(data,*definition,evaluator.frames.rig,false,error);if(!settings||!asettings)return 2;AirStateSettings air_settings;if(!air_settings.Load(data,error))return 2;
    BipedInput i;i.data.assign(std::istreambuf_iterator<char>(std::cin),{});BipedOutput o;const auto count=i.Word();o.Word(count);
    for(unsigned c=0;c<count;++c)
    {
        auto world=ReadBipedWorld(i);std::vector<GrabObject> objects;const auto objects_count=i.Word();for(unsigned k=0;k<objects_count;++k)objects.push_back(biped_grab::Object(i));std::vector<GrabMeshAssembly> bindings;const auto binding_count=i.Word();for(unsigned k=0;k<binding_count;++k)bindings.push_back({i.Word(),i.Word()});
        auto registry=OffboardGrabRegistry::Create(world,std::move(objects),std::move(bindings),error);if(!registry)Fail(error.c_str());
        auto value=PhysicalSimulationRuntime::Initialize(*settings,data,evaluator,std::move(world),settings->Spawn({0,-.035f,0}),error);if(!value)Fail(error.c_str());auto& p=*value;
        AnimatedSkeleton animated(*asettings);auto ik=FootIk::Load(data,evaluator.frames.rig,animated,error);auto input=SkeletonInputRuntime::Load(data,error);auto sair=SkeletonAir::Load(data,error);
        PhysicsAnimationInput anim;Handplant h;AirReckoning reckoning;FootplantRuntime f;AirTrajectoryRuntime trajectory;GroundStateRuntime ground;WipeoutRuntime wipeout;
        if(!ik||!input||!sair||!anim.Load(data,evaluator.frames.rig,"normal",error)||!h.Load(data,error)||!reckoning.Load(data,error)||!f.Load(data,error)||!trajectory.Load(data,error)||!ground.Load(data,true,error)||!wipeout.Load(data,error))Fail(error.c_str());
        auto bground=BipedGroundRuntime::Load(data,metadata,error);BipedAirRuntime bair;LandingDeck landing;OffboardAirSelectorSettings selected;if(!bground||!bair.Load(data,error)||!landing.Load(data,error)||!selected.Load(data,error))Fail(error.c_str());
        OffboardContactToolkit contact;OffboardAirSelector selector(selected);BoardPossessionManager feet;OffboardGrabCache grab;OffboardGrabRuntime grab_runtime(grab);GroundPhaseLifecycle life;
        ProcessedPhysicsInput processed{};ResetProcessedPhysicsInput(processed);PhysicalPlayerInput publication{};ResetPhysicalPlayerOutputs(publication);PlayerInputState line_state{};if(!LoadPlayerInputState(data,line_state,error))Fail(error.c_str());PhysicsPosePacket pose;std::optional<BoardToolkit> toolkit;std::optional<OffboardToolkitInput> last;BipedStatePublication returned{};
        auto player_state=PlayerStateRuntime::Load(data,"normal",error);if(!player_state)Fail(error.c_str());
        const BipedRuntimeOwners owners{p,processed,publication,toolkit,animated,*ik,anim,*input,*sair,pose.hierarchy,ground,life,air_settings,reckoning,wipeout,contact,selector,feet,landing,grab_runtime};
        const auto snapshot=[&]{BipedSnapshot(o,*bground,bair,owners,trajectory,grab,last,returned,line_state,*player_state);FootSnapshot(o,f,trajectory,publication.air,wipeout.state,p.skeleton_collision);Snapshot(o,h,reckoning,*sair,p,animated,*ik,*input,anim,processed,life.board_animated_290);};
        const auto n=i.Word();o.Word(n);snapshot();for(unsigned k=0;k<n;++k)
        {
            const auto op=i.Word();o.Word(op);error.clear();bool okay=true;
            switch(op)
            {
            case 0:{processed=ReadProcessedPhysicsInput(i);anim.fields.animation_translation=i.Floats<4>();anim.fields.animation_end_com=i.Floats<4>();anim.fields.animation_time=i.Float();anim.fields.magnitude_scale=i.Float();anim.fields.turn_scale=i.Float();anim.fields.cadence_end_percent=i.Float();anim.fields.animation_physics_blend_seconds=i.Float();anim.extra.offboard_magnitude=i.Float();anim.extra.offboard_turn=i.Float();anim.extra.biped_world_x=i.Float();anim.extra.biped_world_z=i.Float();anim.extra.biped_start_angle=i.Float();anim.extra.physical_body_spin=i.Float();anim.extra.look_x=i.Float();anim.extra.look_y=i.Float();ActualPacket(processed,p,line_state);break;}
            case 1:{const auto kind=i.Word();pose.hierarchy.clear();if(kind!=4){static const char* names[]={"RIG_TPOSE","POSTURE_STIFF_POSE","POSTURE_SLOUCH_POSE","POSTURE_BUFF_POSE"};PoseCommand cmd;cmd.kind=PoseCommand::Kind::Pose;cmd.name=names[kind];std::vector<Sqt> local;if(!evaluator.Evaluate({cmd},local,error)||!evaluator.Hierarchy(local,pose.hierarchy,error))Fail(error.c_str());}const auto deck=p.DeckFrame();LandingInput land{0,processed.flags_2468,processed.flags_2472,processed.flags_2476,0,p.skeleton.record.centre_of_mass_velocity[1],p.skeleton.record.centre_of_mass[1]-deck[3][1],0};okay=animated.ProcessPose(owners.SkeletonOwners().AnimationOwners(),pose.hierarchy,land,processed.timestep_2604,processed.flags_2468,processed.flags_2472,std::nullopt,error);break;}
            case 2:if(i.Word())toolkit=BoardToolkit::FromBoard(p.board,processed.flags_2468,processed.scalar_2612,Decode(processed.vectors_464_480_496_512_528[0]),{0,1,0,0});else toolkit.reset();break;
            case 3:okay=bair.ConsumeSelector(owners,error);break;case 4:contact.BeginInput();break;case 5:okay=bground->Enter(owners,error);break;
            case 6:{OffboardToolkitInput next;okay=bground->Update(owners,{std::int32_t(contact.readiness),contact.prefix},next,error);if(okay)last=next;break;}
            case 7:{if(!last){okay=false;error="No completed Ground toolkit submission";break;}auto scene=OffboardStaticScene::Create(p.world,error);okay=scene&&contact.Submit(*last,std::int32_t(processed.actor_query_2952),*scene,error);if(okay)okay=bground->SubmitGeometry(owners,error);break;}
            case 8:case 13:{WipeoutFrame frame;okay=Observations(owners,trajectory,*player_state).Frame(frame,error);if(okay){if(op==8)bground->PostPhysics(owners,frame);else okay=bair.PostPhysics(owners,frame,error);}break;}
            case 9:okay=bground->Fill(owners,returned,error);break;case 10:bground->Exit(contact);break;
            case 11:okay=bair.Enter(owners,*bground,error);break;case 12:okay=bair.Update(owners,*bground,error);break;case 14:bair.Fill(owners);break;case 15:bair.Exit(selector);break;
            case 16:okay=p.BeginBoardQueries(error);if(okay)okay=p.FinishBoardQueries(error);break;case 17:okay=SolveFeedback(owners,error);break;
            case 18:{SkeletonLineTests next;okay=QuerySkeletonLines(p.world,p.skeleton,next,error);if(okay)next.Publish(line_state);break;}
            case 19:okay=grab_runtime.ExecuteQueries(OffboardGrabScene(p.world,*registry),error);break;case 20:okay=grab_runtime.Sync(OffboardGrabScene(p.world,*registry),{processed.actor_query_2948,std::int32_t(processed.actor_query_2952)},error);break;
            case 21:{const auto result=grab_runtime.Publish();Block(o,[&]{for(const auto& r:result.records)biped_grab::RecordOption(o,r);biped_grab::ObjectOption(o,result.object);});break;}
            case 22:{auto next=TryReadBipedWorld(i,error);okay=bool(next);if(next)p.ReplaceWorld(std::move(*next));break;}case 23:selector.Reset();break;case 24:bground->Reset(contact);break;
            case 25:life.skeleton_controller.override_enabled=i.Word()!=0;break;case 26:pose.flags=i.Word();pose.air_dismount_revert_frames=std::int32_t(i.Word());break;case 27:sair->CapturePhysicsError(p.board,p.board_frames.animation_target);break;
            case 28:contact.Refresh();break;case 29:feet.Reset();break;case 30:landing.Reset();break;default:return 2;
            }
            o.Status(okay,error);snapshot();
        }
    }
    if(i.at!=i.data.size())return 2;for(auto w:o.words)for(unsigned k=0;k<4;++k)std::cout.put(char(w>>(8*k)));return std::cout?0:2;
}

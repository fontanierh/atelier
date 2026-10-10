// The checker prefixes immutable actual owner observation/wire helpers.
#include "AirPhaseRuntime.h"
#include "KnownAirRuntime.h"
#include "SlidePhaseRuntime.h"
#include "PlayerInputPhase.h"
[[noreturn]]void Fail(const char* e){std::cerr<<e;std::exit(2);}
struct AirInput:Input
{
    template<std::size_t N>std::array<std::uint32_t,N> Words(){std::array<std::uint32_t,N> v;for(auto& x:v)x=Word();return v;}
    template<class T,std::size_t N,class F>std::array<T,N> Array(F f){std::array<T,N> a;for(auto& x:a)x=f(*this);return a;}
    template<class T,class F>std::optional<T> Optional(F f){return Word()?std::optional<T>{f(*this)}:std::nullopt;}
    Vec3 Vector(){const float x=Float(),y=Float(),z=Float();return {x,y,z};}
    std::string Text(){const auto n=Word();std::string s;for(unsigned k=0;k<n;++k)s+=char(Word());return s;}
    template<std::size_t N>PointGraph<N> Curve(){return {Floats<N>(),Floats<N>()};}
};
struct AirOutput:Output
{
    void Value(Vec4 v){Floats(v);}void Value(Mat4 m){Matrix(m);}
    template<std::size_t N>void Curve(PointGraph<N> c){Floats(c.x);Floats(c.y);}
};
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-function"
// GENERATED_PROTOCOL
// GENERATED_PROVIDER
// GENERATED_SLIDE_PROTOCOL
#pragma clang diagnostic pop
namespace {
void SlideOwnerOut(AirOutput& o,const SlidePhaseRuntime& r)
{
    const auto& s=r.state;for(float f:{s.start_speed,s.steering_push,s.damped_turn})o.Float(f);o.Word(s.flag48);o.Word(s.wall_riding);
    const auto& t=r.settings.settings;for(const auto* c:{&t.input_remap,&t.remap_vs_speed,&t.force_vs_angle,&t.force_vs_speed})o.Curve(*c);
    for(float f:{t.softest_wheel_force,t.softest_wheel_spin,t.angular_force,t.force_y_offset})o.Float(f);
    o.Word(std::uint32_t(r.settings.surfaces.size()));for(const auto& p:r.settings.surfaces){o.Curve(p.surface.speed_to_force);o.Float(p.surface.yaw_strength);o.Float(p.surface.yaw_damping);o.Float(p.material.static_friction);o.Float(p.material.dynamic_friction);o.Float(p.material.restitution);}o.Float(r.settings.manual_scalar);
}
void GroundSlideOut(AirOutput& o,const SlidePhaseOwners& v)
{
    Observe(o,v.ground.manual);Observe(o,v.ground.steering);Observe(o,v.ground.pumping);
    Observe(o,v.ground_settings.steering);Observe(o,v.ground_settings.manual);Observe(o,v.ground_settings.manual_mode);Observe(o,v.ground_settings.force);
    for(const auto* m:{&v.physical.settings.board.collision.wheel_material,&v.physical.settings.board.standard_wheel_material}){o.Float(m->static_friction);o.Float(m->dynamic_friction);o.Float(m->restitution);}
    o.Floats(v.ground_runtime.retained_board_normal);const auto& c=v.ground_runtime.contact;
    o.Word(c.active_2731);o.Word(c.tag_16_force.tag);VectorOut(o,c.tag_16_force.force_world);VectorOut(o,c.tag_16_force.point_body);o.Floats(c.vector_2688);o.Float(c.scalar_2704);o.Word(c.animated_board_2708);
    o.Word(v.ground_runtime.collision_force.has_value());if(v.ground_runtime.collision_force){const auto& f=*v.ground_runtime.collision_force;o.Floats(f.force_2528);o.Floats(f.point_2544);o.Floats(f.vector_2592);}
}
void PhaseSnapshot(AirOutput& o,const SlidePhaseRuntime& phase,const SlidePhaseOwners& v)
{
    auto& p=v.physical;o.Word(7);
    Block(o,[&]{SlideOwnerOut(o,phase);});
    Block(o,[&]{GroundSlideOut(o,v);});
    Block(o,[&]{Observe(o,v.processed);o.Word(v.jump_fix_frames);});
    Block(o,[&]{const auto& c=v.life.skeleton_controller;for(auto w:{c.effective,c.requested})o.Word(w);for(bool b:{c.has_request,c.override_enabled,c.flag_18,v.life.skeleton_elapsed_16505})o.Word(b);o.Word(v.life.board_animated_290);o.Float(v.life.manual_drag_2724);o.Word(v.life.edge.has_value());o.Word(v.life.pending_wall_jump.has_value());});
    Block(o,[&]{o.Word(std::uint32_t(p.board.Forces().Count()));for(std::size_t k=0;k<ForceCapacity;++k){const auto& f=p.board.Forces().Entries()[k];o.Word(f.tag);VectorOut(o,f.force_world);VectorOut(o,f.point_body);}o.Word(std::uint32_t(p.contact_count));o.Word(std::uint32_t(p.network_contacts));o.Wide(p.ticks);o.Word(p.failed);});
    Block(o,[&]{// GENERATED_COLLISION_OBSERVER
    });
    Block(o,[&]{WipeoutFrame frame;std::string error;const bool valid=SlidePhaseWipeoutObservations(v).Frame(frame,error);o.Status(valid,error);if(valid)Observe(o,frame);o.Word(v.wipeout.RequestsRunout(v.processed));o.Word(v.wipeout.RequestsWipeout(v.processed));});
}
void ActualPacket(ProcessedPhysicsInput& x,const PhysicalSimulationRuntime& p)
{
    x.vectors_400_416[0]=Raw(Vec4{p.board.Bodies()[6].rates.linear_velocity.x,p.board.Bodies()[6].rates.linear_velocity.y,p.board.Bodies()[6].rates.linear_velocity.z,0});
    x.vectors_400_416[1]=Raw(Vec4{p.board.Bodies()[6].rates.angular_velocity.x,p.board.Bodies()[6].rates.angular_velocity.y,p.board.Bodies()[6].rates.angular_velocity.z,0});x.vectors_544_560_592_608[2]=Raw(p.skeleton.record.centre_of_mass);x.vectors_544_560_592_608[3]=Raw(p.skeleton.record.centre_of_mass_velocity);
    x.collision_pose_error_736=Raw(p.collision_pose_error);x.effective_anim_transform_192={};for(std::size_t k=0;k<4;++k)x.effective_anim_transform_192[k]=Raw(p.roots.animation_to_world[k]);
}
bool SolveFeedback(AirPhaseOwners v,std::string& error)
{
    auto& p=v.physical;const auto& x=v.processed;if(!p.Solve({0,0},error))return false;
    if(!v.toolkit){error="Postphysics wall probe requires the current board toolkit";return false;}
    const auto& t=*v.toolkit;const auto up=Decode(x.vectors_544_560_592_608[0]);const auto ground=Decode(x.vectors_464_480_496_512_528[0]);
    p.processed_flags_2468=x.flags_2468;
    p.FinishBoardOutputs({x.state_2508,{ground[0],ground[1],ground[2]},{up[0],up[1],up[2]},{t.deck[3][0],t.deck[3][1],t.deck[3][2]},x.time_on_ground_2752});
    PhysicalFeedbackInput f{x.state_2508,x.category_2512,x.flags_2472,x.flags_2480,{},{}};
    for(std::size_t k=0;k<5;++k){f.vectors_464_480_496_512_528[k]=Decode(x.vectors_464_480_496_512_528[k]);f.vectors_880_896_912_928_944[k]=Decode(x.vectors_880_896_912_928_944[k]);}
    p.PublishFeedback(f);return p.FinishFrame(error);
}
}
int main(int argc,char** argv)
{
    if(argc!=6&&argc!=7)return 2;SettingsDatabase data;PhysicsSkeletons skeletons;AnimationPoseFrames frames;std::string error;
    if(!data.Load(File(argv[1]),error)||!skeletons.Load(File(argv[2]),argv[4],error)||!frames.rig.Load(File(argv[3]),error))return 2;
    AirStateSettings air_settings;GroundProfiles profiles;SlidePhaseRuntime loaded;if(!air_settings.Load(data,error)||!profiles.Load(data,error)||!loaded.Load(data,error))return 2;
    if(argc==7){loaded.state.Enter(.731f);SettingsDatabase invalid;if(!invalid.Load(File(argv[6]),error))return 2;AirOutput out;const bool okay=loaded.Load(invalid,error);out.Status(okay,error);SlideOwnerOut(out,loaded);for(auto w:out.words)for(unsigned k=0;k<4;++k)std::cout.put(char(w>>(8*k)));return 0;}
    const auto* definition=skeletons.Find("PHYS_TPOSE");if(!definition)return 2;AnimationPoseEvaluator evaluator(std::move(frames));if(!evaluator.LoadAuthoredClips(argv[5],error))return 2;
    const auto settings=PhysicalSimulationSettings::Load(data,*definition,evaluator.frames.rig,error);const auto asettings=AnimatedSkeletonSettings::Load(data,*definition,evaluator.frames.rig,false,error);if(!settings||!asettings)return 2;
    AirInput i;i.data=std::vector<std::uint8_t>(std::istreambuf_iterator<char>(std::cin),{});AirOutput o;const auto count=i.Word();o.Word(count);
    for(unsigned c=0;c<count;++c)
    {
        auto world=FixtureWorld(i.Word());auto provider=std::make_shared<PlayerGrindStaticProvider>(ReadProvider(i));
        auto value=PhysicalSimulationRuntime::Initialize(*settings,data,evaluator,std::move(world),settings->Spawn({0,-.035f,0}),error);if(!value)return 2;auto& p=*value;
        AnimatedSkeleton animated(*asettings);auto ik=FootIk::Load(data,evaluator.frames.rig,animated,error);auto input=SkeletonInputRuntime::Load(data,error);auto sair=SkeletonAir::Load(data,error);
        PhysicsAnimationInput anim;Handplant h;AirReckoning reckoning;FootplantRuntime f;AirTrajectoryRuntime trajectory;GroundRuntime ground_runtime;GroundStateRuntime ground;WipeoutRuntime wipeout;SlidePhaseRuntime phase;
        if(!ik||!input||!sair||!anim.Load(data,evaluator.frames.rig,"normal",error)||!h.Load(data,error)||!reckoning.Load(data,error)||!f.Load(data,error)||!trajectory.Load(data,error)||!ground_runtime.Load(data,error)||!ground.Load(data,true,error)||!wipeout.Load(data,error)||!phase.Load(data,error)){std::cerr<<error;return 2;}
        trajectory.BindGrindWorld(provider);GroundPhaseLifecycle life;ProcessedPhysicsInput processed{};ResetProcessedPhysicsInput(processed);std::optional<BoardToolkit> toolkit;RawVector jump{};std::uint32_t jump_frames=0;PhysicsPosePacket packet;AirOutputFields publication{};auto profile=profiles.Select(1,1,error);if(!profile)return 2;
        const AirPhaseOwners physical_view{p,processed,toolkit,ground,ground_runtime,life,animated,*ik,anim,*input,*sair,reckoning,f,wipeout,*provider,trajectory,air_settings,{jump,jump_frames},packet};
        const auto owners=[&]{return SlidePhaseOwners{p,processed,toolkit,ground,ground_runtime,life,animated,*ik,anim,*input,*sair,reckoning,wipeout,trajectory,air_settings,*profile,packet,jump_frames};};
        const auto snapshot=[&]{PhaseSnapshot(o,phase,owners());FootSnapshot(o,f,trajectory,publication,wipeout.state,p.skeleton_collision);Snapshot(o,h,reckoning,*sair,p,animated,*ik,*input,anim,processed,life.board_animated_290);};
        const auto n=i.Word();o.Word(n);snapshot();
        for(unsigned k=0;k<n;++k)
        {
            const auto op=i.Word();o.Word(op);error.clear();bool okay=true;
            switch(op)
            {
            case 0:processed=ReadProcessedPhysicsInput(i);jump=i.Words<4>();jump_frames=i.Word();anim.fields.body_spin=i.Float();anim.extra.physical_body_spin=i.Float();anim.extra.body_adjust[0]=i.Float();anim.extra.body_adjust[1]=-anim.extra.body_adjust[0];ActualPacket(processed,p);break;
            case 1:{const auto kind=i.Word();packet.hierarchy.clear();if(kind!=4){static const char* names[]={"RIG_TPOSE","POSTURE_STIFF_POSE","POSTURE_SLOUCH_POSE","POSTURE_BUFF_POSE"};PoseCommand command;command.kind=PoseCommand::Kind::Pose;command.name=names[kind];std::vector<Sqt> pose;if(!evaluator.Evaluate({command},pose,error)||!evaluator.Hierarchy(pose,packet.hierarchy,error))return 2;}const auto deck=p.DeckFrame();LandingInput landing{0,processed.flags_2468,processed.flags_2472,processed.flags_2476,0,p.skeleton.record.centre_of_mass_velocity[1],p.skeleton.record.centre_of_mass[1]-deck[3][1],0};okay=animated.ProcessPose(physical_view.SkeletonOwners().AnimationOwners(),packet.hierarchy,landing,processed.timestep_2604,processed.flags_2468,processed.flags_2472,std::nullopt,error);break;}
            case 2:if(i.Word())toolkit=BoardToolkit::FromBoard(p.board,processed.flags_2468,processed.scalar_2612,Decode(processed.vectors_464_480_496_512_528[0]),{0,1,0,0});else toolkit.reset();break;
            case 3:phase.Enter(owners());break;case 4:okay=phase.Advance(owners(),error);break;case 5:phase.Exit(owners());break;case 6:okay=phase.PostPhysics(owners(),error);break;
            case 13:if(!toolkit){error="Slide query preparation requires current BoardToolkit";okay=false;}else{const auto normal=Decode(processed.vectors_464_480_496_512_528[0]),up=Decode(processed.vectors_544_560_592_608[0]);const auto deck=toolkit->deck[3];p.riding.probes.PrepareWall({processed.state_2508,{normal[0],normal[1],normal[2]},{up[0],up[1],up[2]},{deck[0],deck[1],deck[2]},processed.time_on_ground_2752});okay=p.BeginBoardQueries(error);if(okay)okay=p.FinishBoardQueries(error);}break;
            case 14:okay=SolveFeedback(physical_view,error);break;case 15:p.ReplaceWorld(FixtureWorld(i.Word()));break;case 16:trajectory.selector.Reset();break;case 17:life.skeleton_controller.override_enabled=i.Word()!=0;break;case 18:packet.flags=i.Word();packet.air_dismount_revert_frames=std::int32_t(i.Word());break;case 19:sair->CapturePhysicsError(p.board,p.board_frames.animation_target);break;
            case 20:trajectory.BindGrindWorld(std::make_shared<PlayerGrindStaticProvider>(ReadProvider(i)));break;
            case 22:wipeout.state.ClearAfterSelection();break;
            case 23:{const auto mode=i.Word(),surface=i.Word();auto next=profiles.Select(mode,surface,error);okay=bool(next);if(next)profile=next;break;}
            case 24:anim.fields.turn=i.Float();anim.fields.hard_turn=i.Float();anim.fields.balance=i.Float();anim.fields.slide=i.Float();anim.fields.raw_turn=anim.fields.turn;break;
            case 25:{AffineTransform target;for(auto& column:target.basis.columns)for(auto& v:column)v=i.Float();target.translation=i.Vector();p.board.SetTransform(target);const auto velocity=i.Vector(),angular=i.Vector();for(auto& body:p.board.BodiesMut()){body.rates.linear_velocity=velocity;body.rates.angular_velocity=angular;}ActualPacket(processed,p);break;}
            case 26:ground.pumping.Reset();break;
            case 27:{const auto tag=i.Word();const auto force=i.Vector(),point=i.Vector();p.board.ForcesMut().Append({tag,force,point});break;}
            case 28:processed.surface_mode_2540=i.Word();processed.state_variant_index_2528=i.Word();break;
            case 29:okay=trajectory.Load(data,error);break;
            case 30:trajectory.BindGrindWorld(provider);break;
            default:return 2;
            }
            o.Status(okay,error);snapshot();
        }
    }
    if(i.at!=i.data.size())return 2;for(auto w:o.words)for(unsigned k=0;k<4;++k)std::cout.put(char(w>>(8*k)));return std::cout?0:2;
}

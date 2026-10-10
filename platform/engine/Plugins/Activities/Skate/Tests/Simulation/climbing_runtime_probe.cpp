// GENERATED_COMPLETE_OWNER_HELPERS
#include "ClimbingRuntime.h"
#include "SimulationClock.h"
#include "AnimationMetadata.h"
#include <cassert>
#include <cmath>
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-function"
// GENERATED_ADDITIONAL_OBSERVERS
// GENERATED_RIDING_OBSERVERS
#pragma clang diagnostic pop
// GENERATED_WORLD_INPUT
namespace {
using namespace climbing_math;
void TransformOut(AirOutput& o,const Transform& t){o.Floats(std::array<float,3>{t.scale.x,t.scale.y,t.scale.z});o.Floats(t.rotation);o.Floats(std::array<float,3>{t.translation.x,t.translation.y,t.translation.z});}
void PoseOut(AirOutput& o,const std::vector<Mat4>& p){o.Word(std::uint32_t(p.size()));for(const auto& m:p)o.Matrix(m);}
void LedgeOut(AirOutput& o,const ClimbingLedge& l){for(auto v:{l.anchor,l.landing,l.forward,l.palms[0],l.palms[1],l.normals[0],l.normals[1]}){o.Float(v.x);o.Float(v.y);o.Float(v.z);}}
void ClimberOut(AirOutput& o,const ClimbingRuntime& r){
  o.Word(bool(r.clips));o.Word(std::uint32_t(r.indices.size()));for(auto i:r.indices)o.Word(std::uint32_t(i));o.Float(r.cooldown);o.Word(bool(r.active));
  if(r.active){const auto& a=*r.active;o.Word(std::uint32_t(a.phase));o.Float(a.time);LedgeOut(o,a.ledge);TransformOut(o,a.start_root);o.Word(std::uint32_t(a.entry.size()));for(const auto& v:a.entry)TransformOut(o,v);PoseOut(o,a.fallback);o.Matrix(a.board_world);o.Matrix(a.physical_board_world);o.Word(a.carry_board);}
  o.Word(bool(r.approach));if(r.approach){LedgeOut(o,r.approach->ledge);o.Float(r.approach->weight);}
  o.Word(std::uint32_t(r.ground_entry.size()));for(const auto& t:r.ground_entry)TransformOut(o,t);
}
class GlobalStages final:public ClimbingGlobalStages {
public:
  const GroundStateRuntime& ground;const SkaterAnimation& animation;const AnimationPhysicalFeedback& feedback;
  const SimulationExchange& exchange;SimulationClock& clock;unsigned finished=0,resumed=0;
  GlobalStages(const GroundStateRuntime& g,const SkaterAnimation& a,const AnimationPhysicalFeedback& f,const SimulationExchange& x,SimulationClock& c):ground(g),animation(a),feedback(f),exchange(x),clock(c){}
  bool AdvanceCamera(ClimbingFrame& f,camera::CameraRuntime& camera,std::string& error)override{
    const camera::CameraPublicationFrame publication{f.physical,f.player.processed,f.player.physical,f.player.toolkit?&*f.player.toolkit:nullptr,ground,f.animation_input,animation,feedback,f.centre_of_mass_output,f.selected_state.Active().state,false};camera::CameraOutputResult output;
    return camera::AdvanceCameraOutput(publication,exchange,camera,output,error);
  }
  void FinishClockTick()override{++finished;clock.FinishTick();}
  bool ResumeAfterClimb(ClimbingFrame&,std::string&)override{++resumed;std::abort();}
};
bool Loaded(const std::string& path,AnimationLoadedGraph& g,std::string& error){return g.source.Load(File(path.c_str()),error)&&g.binding.Bind(g.source,error)&&g.runtime.FromBinding(g.binding,error);}
}
int main(int argc,char** argv){
  if(argc!=8)return 2;const std::string fixtures=argv[6],metadata=argv[7];
  SettingsDatabase data;PhysicsSkeletons skeletons;AnimationPoseFrames frames;std::string error;
  if(!data.Load(File(argv[1]),error)||!skeletons.Load(File(argv[2]),argv[4],error)||!frames.rig.Load(File(argv[3]),error))return 2;
  AirStateSettings air_settings;if(!air_settings.Load(data,error))return 2;
  auto source=std::make_shared<AnimationSource>();AnimationMetadata second;
  if(!source->metadata.Load(File((metadata+"/bank-0.skate").c_str()),error)||!second.Load(File((metadata+"/bank-1.skate").c_str()),error)||!source->metadata.Merge(second,error))return 2;
  source->evaluator=std::make_shared<AnimationPoseEvaluator>(std::move(frames));auto& evaluator=*source->evaluator;
  if(!evaluator.LoadAuthoredClips(argv[5],error))return 2;const auto* definition=skeletons.Find("PHYS_TPOSE");if(!definition)return 2;
  const auto settings=PhysicalSimulationSettings::Load(data,*definition,evaluator.frames.rig,error);const auto asettings=AnimatedSkeletonSettings::Load(data,*definition,evaluator.frames.rig,false,error);if(!settings||!asettings)return 2;
  AnimationStockGraphs graphs;if(!Loaded(fixtures+"/actor.action.simulation",graphs.action,error)||!Loaded(fixtures+"/actor.motion.simulation",graphs.motion,error))return 2;
  AirInput i;i.data=std::vector<std::uint8_t>(std::istreambuf_iterator<char>(std::cin),{});AirOutput o;const auto count=i.Word();o.Word(count);
  for(unsigned c=0;c<count;++c){
    auto world=ReadClimbWorld(i);auto provider=std::make_shared<PlayerGrindStaticProvider>(ReadProvider(i));
    auto value=PhysicalSimulationRuntime::Initialize(*settings,data,evaluator,std::move(world),settings->Spawn({0,-.035f,0}),error);if(!value)return 2;auto& p=*value;
    AnimatedSkeleton animated(*asettings);auto ik=FootIk::Load(data,evaluator.frames.rig,animated,error);auto input=SkeletonInputRuntime::Load(data,error);auto sair=SkeletonAir::Load(data,error);
    PhysicsAnimationInput anim;Handplant h;AirReckoning reckoning;FootplantRuntime f;AirTrajectoryRuntime trajectory;GroundRuntime ground_runtime;GroundStateRuntime ground;WipeoutRuntime wipeout;KnownAirRuntime known;AirPhaseRuntime phase;
    auto player=PlayerInputRuntime::Load(data,error);OffboardAirSelectorSettings offboard_settings;
    if(!ik||!input||!sair||!player||!offboard_settings.Load(data,error)||!anim.Load(data,evaluator.frames.rig,"normal",error)||!h.Load(data,error)||!reckoning.Load(data,error)||!f.Load(data,error)||!trajectory.Load(data,error)||!ground_runtime.Load(data,error)||!ground.Load(data,true,error)||!wipeout.Load(data,error)||!known.Load(data,error)){std::cerr<<error;return 2;}
    trajectory.BindGrindWorld(provider);GroundPhaseLifecycle life;auto& processed=player->processed;auto& toolkit=player->toolkit;RawVector jump{};std::uint32_t jump_frames=0;PhysicsPosePacket packet;AirOutputFields& publication=player->physical.air;KnownAirOutput last{};
    const AirPhaseOwners owners{p,processed,toolkit,ground,ground_runtime,life,animated,*ik,anim,*input,*sair,reckoning,f,wipeout,*provider,trajectory,air_settings,{jump,jump_frames},packet};
    OffboardAirSelector offboard(offboard_settings);BoardPossessionManager feet;PhysicalPlayerStateLifecycle selected(PhysicalStateId::Sleeping);
    std::unique_ptr<SkaterAnimation> animation;if(!SkaterAnimation::FromSource(data,graphs,"",source,animation,error))return 2;
    std::vector<Mat4> render_pose;if(!animation->EvaluateInitialPose(render_pose,error))return 2;std::uint64_t generation=0;
    CentreOfMassFilter com;CentreOfMassOutput com_output{};SimulationClock clock;SimulationExchange exchange(0);AnimationPhysicalFeedback feedback{};
    camera::CameraRuntime camera;Graph camera_graph;if(!camera_graph.Load(File((fixtures+"/camera-0/graph.simulation").c_str()),error)||!camera.Load(data,camera_graph,File((fixtures+"/camera-0/camera.simulation").c_str()),error))return 2;
    std::vector<std::string> rig_names;for(const auto& bone:evaluator.frames.rig.bones)rig_names.push_back(bone.name);
    ClimbingRuntime climber;ClimbingClipFile converted;if(!ReadClimbingClipFile(File((fixtures+"/climbing.simulation").c_str()),converted,error)||!climber.Load(converted,rig_names,error))return 2;
    DerivedControllerInput controller(std::array<std::uint32_t,26>{});std::optional<Vec4> direction;GlobalStages stages(ground,*animation,feedback,exchange,clock);
    const auto frame=[&]{return ClimbingFrame{p,*player,animated,*ik,anim,com,com_output,render_pose,generation,selected,offboard,feet};};
    const auto snapshot=[&]{
      Block(o,[&]{ClimberOut(o,climber);});
      Block(o,[&]{Observe(o,player->player);Observe(o,player->physical);o.Word(player->PendingTeleport().has_value());if(player->PendingTeleport())o.Matrix(*player->PendingTeleport());});
      Block(o,[&]{PoseOut(o,render_pose);o.Wide(generation);o.Word(std::uint32_t(selected.Active().state));o.Word(p.controller_fields.state_448);o.Floats(com.velocity);o.Floats(com.position);o.Floats(com.position_velocity);o.Floats(com.accumulated_error);o.Word(com.position_valid);for(auto v:{com_output.velocity,com_output.acceleration,com_output.position})o.Floats(v);o.Float(anim.extra.look_x);o.Float(anim.extra.look_y);o.Word(clock.TicksUntilReset());o.Wide(clock.PeriodNanoseconds());o.Word(camera.frame.has_value());o.Word(camera.latest_subject.has_value());o.Word(std::uint32_t(camera.simulation_rate_requests.size()));});
      Block(o,[&]{Observe(o,feet);});
      Block(o,[&]{SelectorOut(o,offboard);});
      Block(o,[&]{climb_riding_obs::RidingOut(o,p.riding);climb_riding_obs::PendingOut(o,p.riding);o.Word(std::uint32_t(p.board.SolvedContacts().size()));for(const auto& contact:p.board.SolvedContacts()){for(auto w:contact.words)o.Word(w);o.Word(std::uint32_t(contact.reaction_a));o.Word(std::uint32_t(contact.reaction_b));}});
      PhaseSnapshot(o,phase,known,owners,last,publication);FootSnapshot(o,f,trajectory,publication,wipeout.state,p.skeleton_collision);Snapshot(o,h,reckoning,*sair,p,animated,*ik,*input,anim,processed,life.board_animated_290);
    };
    const auto n=i.Word();o.Word(n);snapshot();
    for(unsigned k=0;k<n;++k){const auto op=i.Word();o.Word(op);error.clear();bool okay=true;std::optional<bool> result;
      switch(op){
      case 0:{processed=ReadProcessedPhysicsInput(i);jump=i.Words<4>();jump_frames=i.Word();anim.fields.body_spin=i.Float();anim.extra.physical_body_spin=i.Float();const auto adjust=i.Float();anim.extra.body_adjust={adjust,-adjust};ActualPacket(processed,p);break;}
      case 30:{selected=PhysicalPlayerStateLifecycle(*ParsePhysicalStateId(i.Word()));player->physical.reckoning.vector_16=Raw(i.Floats<4>());processed.flags_2476=i.Word();const bool present=i.Word();const auto vector=i.Floats<4>();direction=present?std::optional<Vec4>(vector):std::nullopt;break;}
      case 31:{const auto phase=i.Word();const bool carry=i.Word()!=0;const auto time=i.Float();const auto feet_point=i.Vector(),facing=i.Vector();const auto ledge=FindAirClimbingLedge(p.world,feet_point,facing);if(!ledge){okay=false;error="Fixture has no real climbing ledge";break;}const auto& c=climber.clips->reach;auto entry=c.Sample(0);const auto root=climbing_math::Matrix(p.roots.animation_to_world);climber.active=ClimbingAttached{ClimbingPhase(phase),time,*ledge,Transform::FromMatrix(root),entry,render_pose,Multiply(root,c.Globals(entry)[c.Index("SKATEBOARD_ROOT")]),climbing_math::Matrix(p.DeckFrame()),carry};break;}
      case 32:{std::array<std::uint32_t,26> words;for(auto& w:words)w=i.Word();controller=DerivedControllerInput(words);break;}
      case 33:{bool handled=false;okay=climber.Advance(frame(),{controller,direction},camera,stages,handled,error);if(okay)result=handled;break;}
      case 34:okay=climber.Approach(frame(),{controller,direction},error);break;
      case 35:{const auto root=i.Array<Vec4,4>([](AirInput& v){return v.Floats<4>();});const auto size=i.Word();std::vector<Mat4> pose(render_pose.begin(),render_pose.begin()+std::min<std::size_t>(size,render_pose.size()));okay=climber.PublishPose(frame(),root,std::move(pose),error);break;}
      case 36:{const auto root=i.Array<Vec4,4>([](AirInput& v){return v.Floats<4>();});AffineTransform a;for(unsigned x=0;x<3;++x)for(unsigned y=0;y<3;++y)a.basis.columns[x][y]=root[x][y];a.translation={root[3][0],root[3][1],root[3][2]};p.board.SetTransform(a);break;}
      case 37:climber.active.reset();climber.approach.reset();climber.cooldown=i.Float();break;
      case 38:okay=player->RequestTeleport(i.Array<Vec4,4>([](AirInput& v){return v.Floats<4>();}),error);break;
      case 39:climber.active.reset();climber.ground_entry.clear();break;
      case 40:{const auto which=i.Word(),count=i.Word();std::vector<std::string> names;for(unsigned j=0;j<count;++j)names.push_back(i.Text());if(!count)names=rig_names;std::optional<ClimbingClipFile> file;if(which){ClimbingClipFile data;if(!ReadClimbingClipFile(File((fixtures+"/climbing-loaders/"+std::to_string(which)+"/climbing.simulation").c_str()),data,error)){okay=false;break;}file=std::move(data);}okay=climber.Load(file,names,error);break;}
      case 41:{const auto feet_point=i.Vector(),facing=i.Vector();const auto ledge=FindAirClimbingLedge(p.world,feet_point,facing);if(!ledge){okay=false;error="Fixture has no real climbing ledge";break;}const auto& c=climber.clips->reach;const auto globals=c.Globals(c.Sample(c.Duration()));const auto yaw=RotationY(std::atan2(ledge->forward.x,ledge->forward.z));const auto position=Add(Sub(ledge->anchor,Rotate(yaw,c.Hands(globals))),Rotate(yaw,ClimbingContactClearance(c,globals)));const auto root=Transform{position,yaw,{1,1,1}}.ToMatrix();auto pose=render_pose;for(std::size_t j=0;j<climber.indices.size();++j)pose[climber.indices[j]]=Simulation(globals[j]);okay=climber.PublishPose(frame(),root,std::move(pose),error);break;}
      case 42:p.controller_fields.state_448=i.Word();break;
      case 43:{const auto marker=i.Word();feet.word_300=marker;feet.words_308_to_316={marker,marker+1,marker+2};feet.flags_304_to_307={true,true,true,true};for(auto& hand:feet.hands){hand.word_80=marker;hand.flag_84=true;hand.flags_104_to_107={true,true,true,true};}break;}
      case 44:generation=i.Wide();player->player.update_count_1316=i.Word();break;
      default:return 2;
      }
      o.Status(okay,error);o.Word(result.has_value());if(result)o.Word(*result);snapshot();
    }
    assert(stages.finished==0&&stages.resumed==0);assert(!camera.frame&&!camera.latest_subject&&camera.simulation_rate_requests.empty());
  }
  if(i.at!=i.data.size())return 2;for(auto w:o.words)for(unsigned k=0;k<4;++k)std::cout.put(char(w>>(8*k)));return std::cout?0:2;
}

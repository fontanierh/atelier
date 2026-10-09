// Generated helper prefixes are observations/wire readers, never reset logic.
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-function"
#include "footplant_helpers.inc"
#include "PlayerTeleportRuntime.h"
#include "SkeletonWobble.h"
#include "PlayerGrindInput.h"
namespace {
// GENERATED_CANONICAL_PROTOCOL
// GENERATED_GROUND_PROTOCOL
struct TeleportActions final:ActionMap {
 std::array<float,18> values{};std::vector<std::uint32_t> calls;
 float Value(std::uint32_t a)override{calls.push_back(a);if(a<64||a>81)std::abort();return values[a-64];}
 std::uint8_t State(std::uint32_t a)override{return Value(a)!=0;}
};
void ResetOut(Output& o,float v){o.Float(v);}
void ResetOut(Output& o,std::uint32_t v){o.Word(v);}
void ResetOut(Output& o,std::int32_t v){o.Word(std::uint32_t(v));}
void ResetOut(Output& o,Vec3 v){o.Floats(std::array<float,3>{v.x,v.y,v.z});}
template<class T,std::size_t N>void ResetOut(Output& o,const std::array<T,N>& v){for(auto x:v)ResetOut(o,x);}
// GENERATED_COLLISION_OBSERVERS
// GENERATED_RIDING_OBSERVER
// GENERATED_GRAB_OBSERVER
void ToolkitOut(Output& o,const BoardToolkit& t){for(auto m:{t.deck,t.effective,t.inverse_effective})o.Matrix(m);for(auto v:{t.side,t.up,t.forward,t.horizontal_forward,t.transverse_up,t.forward_velocity,t.travel_direction,t.filtered_normal})o.Floats(v);o.Floats(std::array<float,3>{t.absolute_speed,t.control_sign,t.total_mass});}
void TeleportGroundOut(Output& o,const GroundStateRuntime& s,const GroundRuntime& r){Observe(o,s.state);Observe(o,s.pumping);for(auto w:s.wobble.words)o.Word(w);Observe(o,s.steering);Observe(o,s.speed);Observe(o,s.manual);o.Float(s.heading_previous);o.Word(s.entered);o.Floats(r.retained_board_normal);}
void CollisionOut(Output& o,const SkeletonInputCollision& c){o.Word(c.contact_4070);o.Word(c.has_pose_error_4077);o.Floats(c.pose_error_16272);o.Word(c.partial_ragdoll);o.Float(c.drive_weight_4028);}
void GrindOut(Output& o,const GrindAir& g){for(auto v:{g.offset_delta,g.offset,g.angle_delta,g.angles})o.Floats(v);o.Word(bool(g.selected_kind));o.Word(std::uint32_t(g.selected_kind.value_or(0)));o.Floats(g.headings);}
void TeleportSnapshot(Output& o,const PlayerInputRuntime& owner,const GroundStateRuntime& ground,const GroundRuntime& gr,const SkeletonControllerState& controller,float manual_drag,bool elapsed,std::uint8_t animated,const SkeletonWobble& w,const Handplant& hand,const AirReckoning& air,const SkeletonAir& sair,const FootplantRuntime& foot,const WipeoutRequests& wipeout,const OffboardGrabCache& grab,const PhysicalSimulationRuntime& p,const AnimatedSkeleton& a,const FootIk& ik,const SkeletonInputRuntime& input,const PhysicsAnimationInput& anim,const SkeletonInputCollision& collision,bool teleported,const TeleportActions& actions){
 o.Word(9);
 Block(o,[&]{Observe(o,owner.player);Observe(o,owner.physical);Observe(o,owner.processed);o.Word(bool(owner.toolkit));if(owner.toolkit)ToolkitOut(o,*owner.toolkit);});
 Block(o,[&]{TeleportGroundOut(o,ground,gr);});
 Block(o,[&]{for(auto v:{controller.effective,controller.requested,std::uint32_t(controller.has_request),std::uint32_t(controller.override_enabled),std::uint32_t(controller.flag_18),std::uint32_t(elapsed),std::uint32_t(animated)})o.Word(v);o.Float(manual_drag);o.Word(w.active);o.Word(w.landing);o.Floats(std::array<float,3>{w.time,w.amplitude,w.direction});o.Word(w.SelectedLandingCurves());o.Word(input.reenable_requested);o.Word(input.teleporting);o.Word(input.force_mode);for(auto v:input.head_tracking_history)o.Floats(v);o.Word(input.head_tracking_active);o.Word(input.grind_air_started);o.Word(input.grind_air_active);o.Word(input.grind_air_adjusting);GrindOut(o,input.grind_air);Observe(o,anim.fields);Observe(o,anim.extra);Observe(o,anim.contacts);Observe(o,anim.output);Observe(o,anim.JumpCache());Observe(o,anim.Settings());for(bool b:anim.HeightOverrides())o.Word(b);o.Word(std::uint32_t(anim.RightToe()));o.Word(std::uint32_t(anim.BoneNames().size()));for(auto n:anim.BoneNames())for(auto v:n)o.Word(v);o.Word(std::uint32_t(actions.calls.size()));for(auto v:actions.calls)o.Word(v);});
 Block(o,[&]{ResetOutMode(o,p.skeleton_collision);ResetOutFeedback(o,p.collision_feedback);});
 Block(o,[&]{OutGroundGrab(o,grab);});
 Block(o,[&]{FootOwnerOut(o,foot);for(bool b:wipeout.reasons)o.Word(b);o.Floats(wipeout.values);o.Word(wipeout.count);o.Float(wipeout.cooldown);o.Word(std::uint32_t(wipeout.contact_frames));o.Float(wipeout.balance);o.Word(wipeout.mode);CollisionOut(o,collision);o.Word(teleported);});
 Block(o,[&]{Snapshot(o,hand,air,sair,p,a,ik,input,anim,owner.processed,animated);});
 Block(o,[&]{ResetOutGround(o,p.riding);o.Word(p.board_wiping_out);o.Word(p.board.CollisionGroup());o.Word(std::uint32_t(p.board.Forces().Count()));for(std::size_t k=0;k<p.board.Forces().Count();++k){const auto& f=p.board.Forces().Entries()[k];o.Word(f.tag);ResetOut(o,f.force_world);ResetOut(o,f.point_body);}});
 Block(o,[&]{o.Word(bool(p.riding.pending_wheel_queries));if(p.riding.pending_wheel_queries)for(auto h:*p.riding.pending_wheel_queries){o.Word(bool(h));if(h){o.Float(h->fraction);ResetOut(o,h->normal);o.Word(h->surface_tag);}}const auto& b=p.riding.probes;o.Word(bool(b.wall_line));if(b.wall_line){ResetOut(o,b.wall_line->start);ResetOut(o,b.wall_line->end);}auto hit=[&](std::optional<BoardProbeHit> h){o.Word(bool(h));if(h){ResetOut(o,h->point);ResetOut(o,h->normal);o.Word(h->surface_tag);}};o.Word(bool(b.pending));if(b.pending){hit(b.pending->deck);o.Word(bool(b.pending->wall));if(b.pending->wall)hit(*b.pending->wall);}});
}
std::vector<Mat4> TeleportGlobals(const AnimationPoseEvaluator& e,std::uint32_t kind,std::string& error){if(kind==4)return {};const std::array<const char*,4> names{"RIG_TPOSE","POSTURE_STIFF_POSE","POSTURE_SLOUCH_POSE","POSTURE_BUFF_POSE"};PoseCommand command;command.kind=PoseCommand::Kind::Pose;command.name=names[kind==5?0:kind];std::vector<Sqt> pose;std::vector<Mat4> globals;if(!e.Evaluate({command},pose,error)||!e.Hierarchy(pose,globals,error))std::abort();if(kind==5)globals.resize(1);return globals;}
}
int main(int argc,char** argv){
 if(argc!=6)return 2;SettingsDatabase data;PhysicsSkeletons skeletons;AnimationPoseFrames frames;std::string error;
 if(!data.Load(File(argv[1]),error)||!skeletons.Load(File(argv[2]),argv[4],error)||!frames.rig.Load(File(argv[3]),error))return 2;
 const auto* definition=skeletons.Find("PHYS_TPOSE");if(!definition)return 2;AnimationPoseEvaluator evaluator(std::move(frames));if(!evaluator.LoadAuthoredClips(argv[5],error))return 2;
 const auto settings=PhysicalSimulationSettings::Load(data,*definition,evaluator.frames.rig,error);const auto asettings=AnimatedSkeletonSettings::Load(data,*definition,evaluator.frames.rig,false,error);if(!settings||!asettings)return 2;
 Input i{{std::istreambuf_iterator<char>(std::cin),{}},0};Output o;const auto count=i.Word();o.Word(count);
 for(unsigned c=0;c<count;++c){auto physical=PhysicalSimulationRuntime::Initialize(*settings,data,evaluator,World(i),settings->Spawn({0,-.035f,0}),error);if(!physical)return 2;auto& p=*physical;AnimatedSkeleton a(*asettings);auto ik=FootIk::Load(data,evaluator.frames.rig,a,error);auto input=SkeletonInputRuntime::Load(data,error);auto sair=SkeletonAir::Load(data,error);auto owner=PlayerInputRuntime::Load(data,error);PhysicsAnimationInput anim;Handplant hand;AirReckoning air;FootplantRuntime foot;GroundStateRuntime ground;GroundRuntime gr;
 if(!ik||!input||!sair||!owner||!anim.Load(data,evaluator.frames.rig,"normal",error)||!hand.Load(data,error)||!air.Load(data,error)||!foot.Load(data,error)||!ground.Load(data,true,error)||!gr.Load(data,error)){std::cerr<<error;return 2;}
 PlayerGrindMaterials materials(p.settings.board);SkeletonControllerState controller;bool elapsed=false;std::uint8_t animated=0;SkeletonWobble wobble;OffboardGrabCache grab;WipeoutRequests wipeout;wipeout.InitializePlayer();bool teleported=false;TeleportActions actions;
 PlayerTeleportRuntime reset({ground,controller,*sair,foot,hand,grab,wipeout,wobble,elapsed,animated});PlayerInputOwners owners{p,gr,*input,a,*ik,anim,materials};auto collision=Collision(p);const auto rows=i.Word();o.Word(rows);
 // Original lifecycle manual_drag begins at zero and is retained by reset.
 float manual_drag=0;
 auto snapshot=[&]{const auto start=o.words.size();TeleportSnapshot(o,*owner,ground,gr,controller,manual_drag,elapsed,animated,wobble,hand,air,*sair,foot,wipeout,grab,p,a,*ik,*input,anim,collision,teleported,actions);(void)start;};snapshot();
 for(unsigned r=0;r<rows;++r){const auto op=i.Word();o.Word(op);bool okay=true;std::vector<std::uint32_t> extra;error.clear();switch(op){
 case 0:owner->player=ReadPlayerInputState(i);owner->physical=ReadPhysicalPlayerInput(i);owner->processed=ReadProcessedPhysicsInput(i);break;
 case 1:{const auto requested=i.Matrix();const auto publication=ReadAnimationPacketFields(i);const auto external=ReadExternalPhysicsInput(i);const auto packet=ReadPacket(i,publication,external);const auto kind=i.Word(),n=i.Word();std::vector<AnimationAttribute> attrs;for(unsigned k=0;k<n;++k)attrs.push_back(i.Attribute());actions.values=i.Floats<18>();actions.calls.clear();teleported=i.Word()!=0;const auto globals=TeleportGlobals(evaluator,kind,error);collision=Collision(p);okay=reset.ResetPlayer(owners,requested,owner->player,owner->physical,owner->processed,{packet,{globals,attrs,actions},collision,teleported},error);break;}
 case 2:{const auto seed=i.Word();controller.override_enabled=i.Word()!=0;controller.requested=3;controller.has_request=true;controller.effective=seed%3==0?5:3;controller.flag_18=true;elapsed=false;animated=173;manual_drag=.317f;ground.entered=(seed&1)!=0;ground.steering.Update(.731f,.137f,0x2000,0);ground.steering.activation_time={.317f,.731f};gr.retained_board_normal={.317f,.731f,-.137f,-.0f};p.board_wiping_out=true;wobble.Trigger((seed&1)!=0,(seed&2)!=0);input->reenable_requested=false;input->force_mode=seed+7;input->head_tracking_active=true;input->head_tracking_history.fill({.137f,.317f,.731f,-.0f});p.collision_pose_error={.137f,.317f,.731f,-.0f};wipeout.EnterGround();wipeout.Request(2,.137f);wipeout.Request(24,.731f);SeedGroundGrab(grab,seed,0xc0);foot.enabled=true;foot.Start({.137f,.731f,-.317f,0},{2.731f,.137f,.317f,0});hand.Launch({{.137f,.731f,-.317f,0},{{-2,.731f,-.317f,0},{2,.731f,-.317f,0},17},1},{.137f,.731f,-.317f,0},{2.731f,.137f,.317f,0},{0,0,1,0},{0,0,1,0},{0,0,1,0});p.board.ForcesMut().Append({seed,{.137f,.317f,.731f},{-.731f,.137f,.317f}});owner->toolkit=BoardToolkit::FromBoard(p.board,owner->processed.flags_2468,owner->processed.scalar_2612,Decode(owner->processed.vectors_464_480_496_512_528[0]),gr.retained_board_normal);gr.retained_board_normal=owner->toolkit->filtered_normal;collision=Collision(p);break;}
 case 6:{okay=p.Solve({0,0},error);if(okay){const auto& v=owner->processed;PhysicalFeedbackInput f;f.state_2508=v.state_2508;f.category_2512=v.category_2512;f.flags_2472=v.flags_2472;f.flags_2480=v.flags_2480;for(unsigned n=0;n<5;++n){f.vectors_464_480_496_512_528[n]=Decode(v.vectors_464_480_496_512_528[n]);f.vectors_880_896_912_928_944[n]=Decode(v.vectors_880_896_912_928_944[n]);}p.PublishFeedback(f);collision=Collision(p);}break;}
 case 5:{const auto part=i.Word(),value=i.Word();extra.push_back(std::uint32_t(ik->bone_indices[part]));ik->bone_indices[part]=value;break;}
 case 3:{const auto m=HorizontalPlayerTeleportSpawn(i.Matrix());Output out;out.Matrix(m);extra=std::move(out.words);break;}
 case 4:okay=p.riding.StartWheelQueries(p.board,p.world,error)&&p.riding.probes.Start(p.board,p.world,error);break;
 default:return 2;}
 o.Status(okay,error);o.Word(std::uint32_t(extra.size()));for(auto v:extra)o.Word(v);snapshot();(void)manual_drag;
 }
 }if(i.at!=i.data.size())return 2;for(auto w:o.words)for(unsigned n=0;n<4;++n)std::cout.put(char(w>>(n*8)));
}
#pragma clang diagnostic pop

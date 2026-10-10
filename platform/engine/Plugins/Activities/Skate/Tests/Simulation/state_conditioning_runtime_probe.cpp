// GENERATED_SIMULATION_OWNER_PREFIX
#include "PlayerStateConditioning.h"
#include "AnimationStatePublication.h"
namespace {
void ConditioningGrindOut(Output& o,const GrindFilteredOutput& g){o.Word(std::uint32_t(g.kind));o.Word(std::uint32_t(g.scorable_id));for(auto w:g.name)o.Word(w);for(auto w:g.scoring_name)o.Word(w);o.Word(g.on_front);o.Float(g.crouch);o.Wide(g.pathed_guid);o.Wide(g.local_guid);}
void ConditioningOut(Output& o,const PlayerStateConditioning& c){const auto& s=c.filtered;for(auto w:{std::uint32_t(s.category),std::uint32_t(s.previous_category),std::uint32_t(s.previous_physics_state),std::uint32_t(s.air_count),std::uint32_t(s.nonspecific_count),std::uint32_t(s.nonspecific_collision_free_count),std::uint32_t(s.nonspecific_collision_count),std::uint32_t(s.frames_since_ground_stairs),std::uint32_t(s.must_change)})o.Word(w);ConditioningGrindOut(o,s.CachedGrind());o.Word(bool(c.filtered_output));if(c.filtered_output){const auto& f=*c.filtered_output;o.Word(std::uint32_t(f.category));o.Word(std::uint32_t(f.previous_category));o.Word(f.grinding);ConditioningGrindOut(o,f.grind);o.Float(f.last_grind_distance);}const auto& l=c.landing_quality;o.Floats(std::array<float,4>{l.landing_adjust_80,l.sideways_speed_84,l.forward_speed_88,l.spin_92});o.Word(l.landing_type_96);o.Word(l.landing_data_167);}
void AnimationConditioningOut(Output& o,const AnimationStatePublication& p){o.Word(p.conditions.category);o.Word(p.conditions.grinding);TextOut(o,p.conditions.grind_name);const auto& g=p.grind;o.Word(g.grinding);for(auto w:g.grind_name)o.Word(w);o.Floats(std::array<float,3>{g.deck_velocity.x,g.deck_velocity.y,g.deck_velocity.z});o.Floats(std::array<float,3>{g.effective_board_forward.x,g.effective_board_forward.y,g.effective_board_forward.z});o.Word(g.processed_bit20);o.Word(p.animation_mirrored);o.Floats(std::array<float,3>{g.animation_height,g.physical_crouch,g.raw_skeleton_twist});const auto& c=p.grind_conditions;o.Word(c.filtered_grinding_80);o.Word(c.blunting_136);o.Word(c.approach_268);o.Word(c.trick_out_240);o.Word(c.air_grind_443);o.Float(c.air_time_184);o.Word(c.dropping_in_324);}
}
int main(int argc,char** argv){
// GENERATED_SIMULATION_OWNER_INITIALIZATION
 Input i{{std::istreambuf_iterator<char>(std::cin),{}},0};Output o;const auto count=i.Word();o.Word(count);
 for(unsigned c=0;c<count;++c){
// GENERATED_SIMULATION_OWNER_CONSTRUCTION
 const auto provider=ReadProvider(i);(void)provider;GrindRuntime grind;GroundSettings gs;AirStateSettings as;AirTrajectoryRuntime trajectory;TrainerTuning trainer;
 if(!grind.Load(data,error)||!gs.Load(data,"normal","smooth",error)||!as.Load(data,error)||!trajectory.Load(data,error)){std::cerr<<error;return 2;}
 auto globals=TeleportGlobals(evaluator,0,error);bool fakie=false;std::uint32_t jump_fix=1000;(void)jump_fix;
 const auto rows=i.Word();o.Word(rows);PlayerStateConditioning conditioning;if(!conditioning.Load(data,error))return 2;
 PhysicalPlayerStateLifecycle lifecycle(PhysicalStateId::Sleeping);KnownAirState known_air;PhysicsPosePacket animation_packet;
 auto frame=[&](){return GrindRuntimeOwners{p,*owner,ground,gr,life,a,*ik,anim,*input,*sair,air,wipeout,trajectory,gs,as,trainer,globals};};
 auto snapshot=[&]{o.Word(3);Block(o,[&]{TeleportSnapshot(o,*owner,ground,gr,life.skeleton_controller,life.manual_drag_2724,life.skeleton_elapsed_16505,life.board_animated_290,wobble,hand,air,*sair,foot,wipeout,grab,p,a,*ik,*input,anim,collision,teleported,actions);});Block(o,[&]{GrindOwnerOut(o,grind,owner->grind->jumper);});Block(o,[&]{ConditioningOut(o,conditioning);});};snapshot();
 for(unsigned r=0;r<rows;++r){const auto op=i.Word();o.Word(op);bool okay=true;std::vector<std::uint32_t> extra;error.clear();switch(op){
// GENERATED_SIMULATION_PACKET_RESET_CASES
 case 6: {okay=p.Solve({0,0},error);if(okay){const auto& v=owner->processed;PhysicalFeedbackInput f;f.state_2508=v.state_2508;f.category_2512=v.category_2512;f.flags_2472=v.flags_2472;f.flags_2480=v.flags_2480;for(unsigned n=0;n<5;++n){f.vectors_464_480_496_512_528[n]=Decode(v.vectors_464_480_496_512_528[n]);f.vectors_880_896_912_928_944[n]=Decode(v.vectors_880_896_912_928_944[n]);}p.PublishFeedback(f);}break;}
 case 10:{const auto state=ParsePhysicalStateId(i.Word());if(!state)std::abort();lifecycle=PhysicalPlayerStateLifecycle(*state);okay=grind.Enter(*state,frame(),error);break;}
 case 12:owner->toolkit=BoardToolkit::FromBoard(p.board,owner->processed.flags_2468,owner->processed.scalar_2612,Decode(owner->processed.vectors_464_480_496_512_528[0]),gr.retained_board_normal);gr.retained_board_normal=owner->toolkit->filtered_normal;break;
 case 13:okay=grind.Advance(frame(),error);break;
 case 14:okay=grind.Fill(frame(),error);break;
 case 20:grind.Observe(ManagerRead(i));break;
 case 22:{globals=TeleportGlobals(evaluator,i.Word(),error);fakie=i.Word()!=0;animation_packet.riding_fakie=fakie;jump_fix=i.Word();trainer.grind_pop=i.Float();break;}
 case 28:air.state.spin_angle=i.Float();air.state.spin_speed=i.Float();air.state.secondary_lean_angle=i.Float();break;
 case 34:okay=p.riding.StartWheelQueries(p.board,p.world,error)&&p.riding.FinishWheelQueries(error);if(okay)p.riding.FinishPostPhysics(p.board,p.board_wiping_out,owner->processed.flags_2468,owner->processed.timestep_2604);break;
 case 40:{auto state=ParsePhysicalStateId(i.Word());if(!state)std::abort();lifecycle=PhysicalPlayerStateLifecycle(*state);known_air.targeting_grind_213=i.Word()!=0;break;}
 case 41:{std::optional<PhysicsGroundOutput> output;if(lifecycle.Active().state==PhysicalStateId::PhysicsGround){if(!owner->toolkit){okay=false;error="State output requires actual board toolkit";break;}output=ground.Output(owner->processed,anim,*owner->toolkit);}okay=conditioning.Publish(grind,frame(),lifecycle,output,known_air,animation_packet,error);break;}
 case 42:conditioning.PublishLandingQuality(p,*owner,air);break;
 case 43:{const float height=i.Float();const bool mirrored=i.Word()!=0;const auto z=p.riding.motion.effective_basis.columns[2];AnimationStatePublication out;okay=PublishAnimationState(owner->physical,conditioning.filtered_output,height,mirrored,{z[0],z[1],z[2]},out,error);if(okay){Output record;AnimationConditioningOut(record,out);extra=std::move(record.words);}break;}
 case 44:conditioning.ResetFilteredForTeleport();break;
 case 45:{const auto lane=i.Word();const auto word=i.Word();if(lane==0)owner->physical.grinds.animation_name_156.reset();else if(lane==1)owner->physical.grinds.scoring_name_176.reset();else if(lane==2)owner->physical.grinds.words_136_140[0]=word;else if(lane==3)owner->physical.grinds.words_136_140[1]=word;else if(lane==4)owner->physical.filtered_state_0=word;else if(lane>=5&&lane<10){if(!owner->physical.grinds.animation_name_156)owner->physical.grinds.animation_name_156=AttributeName{};(*owner->physical.grinds.animation_name_156)[lane-5]=word;}else return 2;break;}
 case 46:{const auto flags=i.Word();const auto& p=ConditionerCapabilityContext{(flags&1)!=0,(flags&2)!=0,(flags&4)!=0,(flags&8)!=0};extra.push_back(p.Capabilities());break;}
 case 47:owner->UpdateDynamicNormal(p.riding,p.settings.board.step.simulation.gravity_acceleration);okay=owner->PublishBoard(p.riding,error);break;
 case 48:{const auto velocity=i.Floats<3>();for(auto& b:p.board.BodiesMut())b.rates.linear_velocity={velocity[0],velocity[1],velocity[2]};break;}
 default:return 2;}
 collision=Collision(p);o.Status(okay,error);o.Word(std::uint32_t(extra.size()));for(auto w:extra)o.Word(w);snapshot();
 }
 }if(i.at!=i.data.size())return 2;for(auto w:o.words)for(unsigned n=0;n<4;++n)std::cout.put(char(w>>(n*8)));
}
#pragma clang diagnostic pop

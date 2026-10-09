// The checker prefixes complete accepted physical/pose/dispatcher adapters.
#include "SkeletonBiped.h"
namespace
{
void BipedSettingsOut(const BipedSkeletonState& s){Out(s.retained_board);Out(s.ground_normal_smoothing);Out(s.tilt_vs_rotation.x);Out(s.tilt_vs_rotation.y);Out(s.tilt_vs_slope.x);Out(s.tilt_vs_slope.y);}
void ObserveBiped(const BipedSkeletonState& s,const SkeletonAir& a,const AirReckoning& air)
{
 BipedSettingsOut(s);
 const auto& v=air.state;for(float x:{v.spin_angle,v.spin_speed,v.secondary_lean_angle,v.flip_angle,v.flip_speed,v.flip_requested_speed})Out(x);Out(v.spin_transform);Out(v.flip_axis);Out(std::uint32_t(v.flip_active));Out(std::uint32_t(v.flip_side));
 Out(a.board_animation.rotation_error);Out(std::uint32_t(a.board_animation.blending));Out(a.settings.slow.x);Out(a.settings.slow.y);Out(a.settings.fast.x);Out(a.settings.fast.y);
 const auto& p=air.settings;Out(p.ground_normal_smoothing);for(const auto& g:{p.max_up_angle_delta,p.tilt_vs_rotation,p.tilt_vs_slope}){Out(g.x);Out(g.y);}Out(p.body_spin.derivative_floor);Out(p.body_spin.acceleration_limit);for(const auto& g:p.body_spin.curves){Out(g.x);Out(g.y);}Out(p.body_spin.input_fade_threshold);
 for(const auto& x:{p.body_flip.smoothing,p.body_flip.maximum_speed,p.body_flip.spin_scale}){Out(std::uint32_t(x.has_value()));if(x)Out(*x);}Out(p.body_flip.missing_attribute_value);for(const auto& m:air.modes){Out(std::uint32_t(m.easy_body_spins));Out(std::uint32_t(m.perfect_body_flips));}for(const auto& g:air.stock_spin_curves){Out(g.x);Out(g.y);}Out(air.stock_spin_acceleration);
}
void BipedSnapshot(PhysicalSimulationRuntime& r,const AnimatedSkeleton& a,const FootIk& ik,const SkeletonInputRuntime& input,const PhysicsAnimationInput& attributes,const SkeletonWobble& wobble,bool elapsed,const AdjustedFrame& state,const Actions& actions,const BipedSkeletonState& biped,const SkeletonAir& board,const AirReckoning& air)
{Snapshot(r);OutAdjusted(a,ik,input.grind_air,state.queries);ObserveDispatcher(input,attributes,wobble,elapsed,state.input,actions);ObserveBiped(biped,board,air);}
bool SolveBiped(PhysicalSimulationRuntime& r,AnimatedSkeleton& a,FootIk& ik,AdjustedFrame& state,std::string& error)
{
 const auto& p=state.input;if(!r.Solve({0,0},error))return false;Out(std::uint32_t(r.contact_count));Out(std::uint32_t(r.solved_drives?r.solved_drives->rows.size():0));const auto wheel=r.riding.ground.wheel_normal,normal=r.riding.ground.overall_normal;const auto toolkit=BoardToolkit::FromBoard(r.board,p.flags_2468,r.riding.motion.speed,Four(normal),Four(r.riding.reckoning.ground_normal));r.FinishBoardOutputs({p.state_2508,wheel,{r.roots.animation_to_world[1][0],r.roots.animation_to_world[1][1],r.roots.animation_to_world[1][2]},{toolkit.deck[3][0],toolkit.deck[3][1],toolkit.deck[3][2]},float(r.ticks)*p.timestep_2604});PhysicalFeedbackInput feedback{p.state_2508,p.category_2512,p.flags_2472,p.flags_2480,{},{}};feedback.vectors_464_480_496_512_528[0]=Four(wheel);
 feedback.vectors_464_480_496_512_528[1]=feedback.vectors_464_480_496_512_528[2]=Four(r.riding.ground.parts[6].point);feedback.vectors_464_480_496_512_528[4]=Four(normal);feedback.vectors_880_896_912_928_944[0]=a.animation_hips[3];feedback.vectors_880_896_912_928_944[1]={0,1,0,0};r.PublishFeedback(feedback);const auto deck=r.DeckFrame();const auto post=ik.PostPhysics(r.skeleton,{p.state_2508,p.category_2512,r.riding.ground.part_contact_count!=0,false,p.flags_2468,p.flags_2484,p.state_timer_2664,p.player_state_value_2520,r.roots.world_to_animation,deck});for(bool b:post)Out(std::uint32_t(b));r.skeleton.PublishPhysicalRecord(deck);return r.FinishFrame(error);
}
}
int main(int argc,char** argv)
{
 if(argc<2)return 2;SettingsDatabase data;std::string error;if(!data.Load(FileBytes(argv[1]),error))return 2;BipedSkeletonState settings;const auto loaded=settings.Load(data,error);Out(std::uint32_t(loaded));Out(error);BipedSettingsOut(settings);if(!loaded||argc==3){for(auto w:output)for(unsigned n=0;n<4;++n)std::cout.put(char(w>>(8*n)));return std::cout?0:2;}
 if(argc!=5)return 2;PhysicsSkeletons physical;AnimationPoseFrames frames;if(!physical.Load(FileBytes(argv[2]),argv[4],error)||!frames.rig.Load(FileBytes(argv[3]),error))return 2;const auto* bank=physical.Find("PHYS_TPOSE");if(!bank)return 2;AnimationPoseEvaluator evaluator(std::move(frames));const auto simulation=PhysicalSimulationSettings::Load(data,*bank,evaluator.frames.rig,error);const auto animation=AnimatedSkeletonSettings::Load(data,*bank,evaluator.frames.rig,false,error);const auto ws=SkeletonWobbleSettings::Load(data,error);if(!simulation||!animation||!ws)return 2;const auto board_initial=SkeletonAir::Load(data,error);AirReckoning air_initial;if(!board_initial||!air_initial.Load(data,error))return 2;
 Input i;const auto count=i.Word();Out(count);for(unsigned c=0;c<count;++c)
 {
  const auto spawn=ReadAffine();auto world=ReadWorld(simulation->board.floor_material);const bool seams=i.Word()!=0;auto runtime=PhysicalSimulationRuntime::Initialize(*simulation,data,evaluator,std::move(world),spawn,error);if(!runtime)return 2;auto& r=*runtime;if(seams)r.EnableImportedFloorSeams();AnimatedSkeleton animated(*animation);const auto ik_initial=FootIk::Load(data,evaluator.frames.rig,animated,error);auto owner_initial=SkeletonInputRuntime::Load(data,error);if(!ik_initial||!owner_initial)return 2;auto ik=*ik_initial;auto owner=*owner_initial;PhysicsAnimationInput attributes;if(!attributes.Load(data,evaluator.frames.rig,"normal",error))return 2;auto biped=settings;auto board=*board_initial;auto air=air_initial;SkeletonWobble wobble;AdjustedFrame state;Actions actions;bool elapsed=false;const auto n=i.Word();Out(c);Out(n);const auto mark=output.size();Out(0u);const auto initial=output.size();Out(0u);BipedSnapshot(r,animated,ik,owner,attributes,wobble,elapsed,state,actions,biped,board,air);output[initial]=output.size()-initial-1;
  for(unsigned k=0;k<n;++k)
  {
   const auto op=i.Word();Out(op);const auto at=output.size();Out(0u);const auto payload=output.size();Out(0u);error.clear();
   if(op==0)
   {
    const auto prepared_at=output.size();Out(0u);const auto prepared=ProcessDispatcher(i,r,animated,ik,owner,attributes,wobble,*ws,evaluator,state,actions);output[prepared_at]=std::uint32_t(prepared);
    const auto branch=i.Word();const auto frame=Matrix();const auto com=i.Floats<4>();const auto body=i.Floats<4>();const auto lift=i.Float();const auto forward=i.Floats<4>();const auto pose=i.Word();const bool solve=i.Word()!=0;const auto globals=pose==4?std::vector<Mat4>{}:Hierarchy(evaluator,pose);Mat4 target=SkeletonIdentity;bool ok=false;
    if(prepared)
    {
     const auto owners=SkeletonInputOwners{r,animated,ik,attributes};const auto collision=SkeletonInputCollision{r.collision_feedback.flags.compliant,r.collision_feedback.flags.has_impulse,r.collision_pose_error,r.skeleton_collision.partial_ragdoll,r.collision_feedback.drive_weight};
     if(branch==0)ok=UpdateBipedSkeletonGround(owner,board,{frame,com},biped,state.input,owners,globals,collision,air,target,error);else if(branch==1)ok=UpdateBipedSkeletonAir(owner,board,{frame,com,body,lift,forward},biped,state.input,owners,globals,collision,air,target,error);else std::abort();r.processed_flags_2468=state.input.flags_2468;if(ok&&solve)ok=SolveBiped(r,animated,ik,state,error);
    }
    Out(std::uint32_t(ok));Out(error);Out(target);
   }
   else if(op==1){const auto target=Matrix();board.CapturePhysicsError(r.board,target);}
   else if(op==2)board.ResetBoard();else if(op==3)biped.retained_board=Matrix();else if(op==4)r.ReplaceWorld(ReadWorld(r.settings.board.floor_material));else if(op==5)owner.ResetForTeleport({r,animated,ik,attributes},wobble,elapsed);else if(op==6){const auto flags=i.Word(),cool=i.Word();for(auto& b:r.skeleton.BodiesMut()){b.state_flags=flags;b.rates.cool_down=cool;}}else if(op==7){const BipedReckoningInput value{i.Floats<4>(),i.Floats<4>(),i.Floats<4>(),i.Float(),i.Word()!=0,i.Word()!=0,i.Float()};const auto v=UpdateBipedReckoning(r.riding.reckoning,r.riding.reckoning_frames,r.riding.body_spin,air.state,biped,value);Out(v.dynamic_up_1136);Out(v.up_1152);Out(v.target_1168);Out(v.velocity_1184);Out(v.ground_normal_1216);}else if(op==8){air.state.spin_angle=i.Float();air.state.spin_speed=i.Float();air.state.secondary_lean_angle=i.Float();}else std::abort();
   output[payload]=output.size()-payload-1;BipedSnapshot(r,animated,ik,owner,attributes,wobble,elapsed,state,actions,biped,board,air);output[at]=output.size()-at-1;
  }output[mark]=output.size()-mark-1;
 }
 if(std::cin.peek()!=std::char_traits<char>::eof())return 2;for(auto w:output)for(unsigned n=0;n<4;++n)std::cout.put(char(w>>(8*n)));return std::cout?0:2;
}

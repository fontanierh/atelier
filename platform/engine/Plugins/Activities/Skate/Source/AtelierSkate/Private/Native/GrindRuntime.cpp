#include "GrindRuntime.h"
#include "GrindRuntimeInternal.h"
#include "WipeoutObservations.h"
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace grind_detail;
void GrindPhysicalState::Enter(PlayerGrindFamily family,Mat4 board)
{
    substate=1;leaving=false;already_jumped=false;just_jumped=false;tipslide_97_98_99={};frame=board;
    updates=0;crouch=0;leaving_updates=0;jump_velocity={};
    if(family==PlayerGrindFamily::Boardslide||family==PlayerGrindFamily::Darkslide){slide_wipeout=false;preparing_jump=false;}
}
bool GrindRuntime::Load(const SettingsDatabase& data,std::string& error)
{
    GrindRuntimeSettings loaded;if(!GrindRuntimeSettings::Load(data,loaded,error))return false;
    states={};active.reset();nonspecific_active=false;nonspecific_jumped=false;nonspecific_jump_velocity={};
    orientation_random=MotionConditionRandom{};settings=loaded;manager.reset();pending_wipeout_impulse.reset();chromosome=GrindChromosome{};camera=GrindCamera{};return true;
}
bool GrindRuntime::Enter(PhysicalStateId selected,GrindRuntimeOwners o,std::string& error)
{
    auto& board=o.physical.board;
    if(selected==PhysicalStateId::Nonspecific){nonspecific_active=true;nonspecific_jumped=false;nonspecific_jump_velocity={};o.life.skeleton_elapsed_16505=true;
        o.air_reckoning.state.spin_angle=0;o.air_reckoning.state.spin_speed=0;board.HookMut().drive.DisableAnimation(o.life.board_animated_290);return true;}
    const auto family=Family(selected);if(!family){error="Grind Enter requires selected state400..405";return false;}
    if(active){error="Grind Enter requires prior Exit";return false;}
    if(!o.input.toolkit){error="Grind Enter requires current board toolkit";return false;}
    const auto frame=o.input.toolkit->deck;
    board.HookMut().drive.DisableAnimation(o.life.board_animated_290);o.life.skeleton_elapsed_16505=true;
    for(const std::size_t part:{19,15,20,16}){auto& c=o.physical.skeleton_collision;c.parts[part].volume_group=4;c.parts[part].enabled=false;c.disable_count[part]=0;}
    board.BodiesMut()[6].inertia.angular_drag=Float(0x40666665);states[std::size_t(*family)].Enter(*family,frame);active=family;return true;
}
bool GrindRuntime::Exit(GrindRuntimeOwners o,std::string& error)
{
    if(nonspecific_active){nonspecific_active=false;return true;}
    if(!active){error="Grind Exit requires active physical state";return false;}
    for(const std::size_t part:{19,15,20,16})o.physical.skeleton_collision.NormalBone(part,o.physical.skeleton.definition.bones[part].has_collision);
    auto& board=o.physical.board;board.BodiesMut()[6].inertia.angular_drag=settings.standard_angular_drag;
    board.HookMut().drive.DisableAnimation(o.life.board_animated_290);GrindClearWheelSpin(board);
    states[std::size_t(*active)].leaving=false;active.reset();return true;
}
bool GrindRuntime::Advance(GrindRuntimeOwners o,std::string& error)
{
    if(nonspecific_active){
        if(!ExecuteNonspecific(o,error))return false;
        if(!o.input.toolkit){error="701 requires BoardToolkit";return false;}
        const auto frame=o.input.toolkit->deck;const float sign=(o.input.processed.flags_2484&0x00200000)?-1.0f:1.0f;
        return Reckon(o,settings.reckoning,Scale(frame[1],sign),frame[2],0.98f,error);
    }
    if(!active){error="Grind Update requires active family";return false;}
    if(!manager){error="Grind Update requires manager observation";return false;}
    if(!o.input.toolkit){error="Grind Update requires BoardToolkit";return false;}
    const auto family=*active;const auto observed=*manager;const auto frame=o.input.toolkit->deck;auto& state=states[std::size_t(family)];
    state.just_jumped=false;const bool tipped=state.tipslide_97_98_99[0];
    if(!tipped){state.direction=observed.geometry.direction_1136;state.normal=observed.geometry.normal_1152;state.across=Cross(state.direction,state.normal);}
    const auto normal=tipped?frame[1]:observed.geometry.target_up_1168;
    const float smoothing=!tipped&&observed.surface.reckon_blend_selector_1500>0?0.9f:0.7f;
    if(!Reckon(o,settings.reckoning,normal,frame[2],smoothing,error))return false;
    const auto& p=o.input.processed;const bool slide=family==PlayerGrindFamily::Boardslide||family==PlayerGrindFamily::Darkslide;
    const bool user_exit=(p.flags_2476&0x20000000)&&(!slide||observed.geometry.kind_1464==2);
    const bool should_exit=(observed.engagement.kind_1248==2&&((observed.geometry.flags_1476&0x08000000)||(observed.control.flags_2488&0x10000000))&&p.scalar_2652<1)
        ||(observed.control.flags_1516&0x80000000)||user_exit||(state.updates>60&&p.scalar_2652<0.15f);
    if(state.substate==1&&should_exit)state.substate=2;
    if(!Execute(o,observed,error))return false;
    auto& next=states[std::size_t(family)];next.leaving_updates=next.substate==2?Increment(next.leaving_updates):0;
    if(next.leaving_updates>35)o.wipeout.Request(17,0);
    next.crouch=std::fabs(Dot3(frame[2],next.normal))*0.4f;
    o.ground.steering.Update(0,o.air_settings.steering_blend,p.flags_2468,p.flags_2472);
    const auto velocity=FloatVector(p.vectors_400_416[0]);
    for(std::size_t i=0;i<4;++i)o.skeleton_input.head_tracking_history[5][i]=std::fma(velocity[i],settings.look_ahead,observed.geometry.point_1120[i]);
    o.skeleton_input.head_tracking_active=true;next.updates=Increment(next.updates);return true;
}
bool GrindRuntime::ConditionOutputs(GrindRuntimeOwners o,bool fakie,std::string& error)
{
    auto& out=o.input.physical.grinds;out.grinding_316=out.words_136_140[1]==1||out.words_136_140[1]==2;
    std::optional<PlayerGrindFamily> family;if(out.words_136_140[0]<6)family=PlayerGrindFamily(out.words_136_140[0]);
    if(out.grinding_316&&!family){error="Active grind has invalid native family "+std::to_string(out.words_136_140[0]);return false;}
    const auto deck=o.physical.board.PartTransforms()[6];const auto effective=Lanes(o.physical.riding.motion.effective_basis.columns[2]);
    const auto com=Lanes(o.physical.board.Bodies()[6].rates.position);
    GrindChromosomeInput input{o.input.physical.state.category_12,out.grinding_316!=0,(o.input.processed.flags_2468&0x00200000)!=0,family,
        Lanes(deck.basis.columns[0]),Lanes(deck.basis.columns[2]),Lanes(deck.translation),effective,effective,com,
        {o.physical.skeleton.record.pose[19][0],o.physical.skeleton.record.pose[15][0]},fakie,FloatVector(out.point_16),FloatVector(out.direction_0),FloatVector(out.normal_32),FloatVector(out.across_48)};
    chromosome.InitializeHostFakie(fakie);std::optional<GrindChromosomePublication> publication;
    if(!chromosome.Update(input,publication,error))return false;
    return !publication||chromosome.Publish(*publication,out,error);
}
bool GrindRuntime::Post(GrindRuntimeOwners o,std::uint32_t jump_fix,std::string& error)
{
    WipeoutObservations observations{o.input.processed,o.physical.riding.ground,o.physical.collision_feedback,o.physical.DeckFrame(),o.physical.board_frames.animation_target,
        o.physical.roots.world_to_animation,o.physical.collision_pose_error,o.physical.collision_maximum_error,jump_fix,o.air_reckoning.state,o.physical.riding.reckoning_frames.system[1][1],
        o.trajectory.selector.GrindLockedToMiddle(),o.trajectory.selector.GrindNormal()};
    WipeoutFrame frame;if(!observations.Frame(frame,error))return false;CheckGrindPost(o.wipeout,settings.post,frame);return true;
}
bool GrindRuntime::FilteredOutput(const GrindOutputFields& out,GrindFilteredOutput& result,std::string& error)
{
    if(!out.animation_name_156){error="Missing native grind name reset/publication";return false;}
    if(!out.scoring_name_176){error="Missing native scoring grind name reset/publication";return false;}
    std::int32_t kind,scorable;std::memcpy(&kind,&out.words_136_140[0],4);std::memcpy(&scorable,&out.scorable_id_152,4);
    result={kind,scorable,*out.animation_name_156,*out.scoring_name_176,out.flag_318!=0,out.crouch_132,out.spline_guids_224_232[0],out.spline_guids_224_232[1]};return true;
}
}

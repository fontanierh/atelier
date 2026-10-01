// SPDX-License-Identifier: Apache-2.0
// Actual shared owner constructors/observers are staged from the reset proof.
// GENERATED_NATIVE_OWNER_PREFIX
#include "GrindRuntime.h"
#include "GrindNames.h"
namespace {
// GENERATED_PROVIDER_READER
// GENERATED_GRIND_WORLD
std::uint32_t FloatBits(float v){std::uint32_t out;std::memcpy(&out,&v,4);return out;}
void JumperOut(Output& o,const PlayerGrindJumper& j){o.Word(j.launched);o.Word(j.cooldown);o.Word(j.family);o.Float(j.energy);o.Word(j.geometry.geometry_kind);for(auto v:{j.geometry.high_side,j.geometry.normal,j.geometry.direction,j.geometry.upmost,j.geometry.point})o.Floats(v);}
PlayerGrindJumper JumperRead(Input& i){PlayerGrindJumper j;j.launched=i.Word()!=0;j.cooldown=i.Word();j.family=i.Word();j.energy=i.Float();j.geometry.geometry_kind=i.Word();j.geometry.high_side=i.Floats<4>();j.geometry.normal=i.Floats<4>();j.geometry.direction=i.Floats<4>();j.geometry.upmost=i.Floats<4>();j.geometry.point=i.Floats<4>();return j;}
PlayerGrindObservation ManagerRead(Input& i){PlayerGrindObservation m;auto& g=m.geometry;g.point_1120=i.Floats<4>();g.direction_1136=i.Floats<4>();g.normal_1152=i.Floats<4>();g.target_up_1168=i.Floats<4>();g.primitive_start_1264=i.Floats<4>();g.primitive_end_1280=i.Floats<4>();if(i.Word())g.spline_guids_1296=std::array<std::uint64_t,2>{i.Wide(),i.Wide()};g.upmost_normal_1408=i.Floats<4>();g.high_side_1440=i.Floats<4>();g.kind_1464=i.Word();g.flags_1476=i.Word();g.impact_speed_1492=i.Float();auto& s=m.surface;s.audio_surface_1468=i.Word();s.material_1472=i.Word();s.friction_vs_time_1496=i.Float();s.reckon_blend_selector_1500=i.Float();s.gravity_relief_1512=i.Float();auto& c=m.control;c.family=PlayerGrindFamily(i.Word());c.flags_1516=i.Word();c.flags_2468=i.Word();c.flags_2488=i.Word();c.translation_2796=i.Float();c.balance_2800=i.Float();c.exit_lean=i.Float();m.engagement.velocity_1184=i.Floats<4>();m.engagement.kind_1248=i.Word();auto& j=m.jumper;j.geometry_kind_16=i.Word();j.family_20=PlayerGrindFamily(i.Word());j.energy_24=i.Float();j.high_side_32=i.Floats<4>();j.normal_48=i.Floats<4>();j.direction_64=i.Floats<4>();j.upmost_normal_80=i.Floats<4>();j.point_96=i.Floats<4>();return m;}
void ManagerOut(Output& o,const PlayerGrindObservation& m){const auto& g=m.geometry;for(auto v:{g.point_1120,g.direction_1136,g.normal_1152,g.target_up_1168,g.primitive_start_1264,g.primitive_end_1280})o.Floats(v);o.Word(bool(g.spline_guids_1296));if(g.spline_guids_1296)for(auto v:*g.spline_guids_1296)o.Wide(v);o.Floats(g.upmost_normal_1408);o.Floats(g.high_side_1440);o.Word(g.kind_1464);o.Word(g.flags_1476);o.Float(g.impact_speed_1492);const auto& s=m.surface;o.Word(s.audio_surface_1468);o.Word(s.material_1472);o.Floats(std::array<float,3>{s.friction_vs_time_1496,s.reckon_blend_selector_1500,s.gravity_relief_1512});const auto& c=m.control;o.Word(std::uint32_t(c.family));o.Word(c.flags_1516);o.Word(c.flags_2468);o.Word(c.flags_2488);o.Floats(std::array<float,3>{c.translation_2796,c.balance_2800,c.exit_lean});o.Floats(m.engagement.velocity_1184);o.Word(m.engagement.kind_1248);const auto& j=m.jumper;o.Word(j.geometry_kind_16);o.Word(std::uint32_t(j.family_20));o.Float(j.energy_24);for(auto v:{j.high_side_32,j.normal_48,j.direction_64,j.upmost_normal_80,j.point_96})o.Floats(v);}
void PoseOut(Output& o,const GrindApproachPose& p){o.Floats(p.right);o.Floats(p.position);for(auto v:p.feet)o.Floats(v);o.Word(p.fakie);}
void ComponentsOut(Output& o,const std::optional<GrindComponents>& c){o.Word(bool(c));if(c)for(auto v:*c)o.Word(v);}
void GrindOwnerOut(Output& o,const GrindRuntime& g,const PlayerGrindJumper& jumper){for(const auto& s:g.states){for(auto v:{s.direction,s.normal,s.across})o.Floats(v);o.Float(s.crouch);o.Word(s.leaving);o.Word(s.substate);o.Word(s.classification_104);o.Word(s.just_jumped);o.Floats(s.jump_velocity);o.Word(s.slide_wipeout);o.Floats(s.slide_impulse);for(bool v:s.tipslide_97_98_99)o.Word(v);o.Matrix(s.frame);o.Word(s.already_jumped);o.Word(std::uint32_t(s.updates));o.Word(std::uint32_t(s.leaving_updates));o.Word(s.preparing_jump);}o.Word(bool(g.active));if(g.active)o.Word(std::uint32_t(*g.active));o.Word(g.nonspecific_active);o.Word(g.nonspecific_jumped);o.Floats(g.nonspecific_jump_velocity);for(auto v:g.orientation_random.words)o.Word(v);o.Word(bool(g.manager));if(g.manager)ManagerOut(o,*g.manager);o.Word(bool(g.pending_wipeout_impulse));if(g.pending_wipeout_impulse)o.Floats(*g.pending_wipeout_impulse);const auto& c=g.chromosome;o.Word(std::uint32_t(c.history.size()));for(auto v:c.history)PoseOut(o,v);PoseOut(o,c.saved);o.Word(c.saved_fakie_initialized);o.Word(c.approach);o.Word(c.previous_category);o.Word(bool(c.previous_kind));if(c.previous_kind)o.Word(std::uint32_t(*c.previous_kind));o.Word(std::uint32_t(c.away_frames));o.Word(c.reversed);o.Word(bool(c.orientation));if(c.orientation)o.Word(*c.orientation);ComponentsOut(o,c.pending);o.Word(std::uint32_t(c.pending_frames));ComponentsOut(o,c.animation);ComponentsOut(o,c.scoring);JumperOut(o,jumper);}
void GrindSettingsOut(Output& o,const GrindRuntimeSettings& s){auto graph=[&](const auto& g){o.Floats(g.x);o.Floats(g.y);};o.Float(s.standard_angular_drag);graph(s.pin_vs_slope);o.Float(s.look_ahead);graph(s.exit_assist);o.Floats(std::array<float,5>{s.post.max_arm_contact_164,s.post.max_body_contact_168,s.post.xz_acceleration_204,s.post.max_displacement_208,s.post.max_angular_deck_error_212});o.Floats(s.reckoning.ground_normal_smoothing);graph(s.reckoning.tilt_vs_rotation);graph(s.reckoning.tilt_vs_slope);o.Float(s.substate.animated_board_threshold);const auto& c=s.substate.collision;o.Floats(std::array<float,4>{c.maximum_velocity_delta,c.force_y_offset,c.force_scalar,c.target_displacement_velocity});graph(c.torque_vs_angle);for(auto mode:s.substate.vertical)for(auto family:mode)o.Floats(family);}
void CameraOut(Output& o,const GrindCamera& c){for(auto v:{c.current,c.previous,c.error,c.midpoint})o.Floats(v);o.Word(c.family);o.Word(c.active);}
void TextOut(Output& o,std::string_view text){o.Word(std::uint32_t(text.size()));for(unsigned char c:text)o.Word(c);}
void Names(Output& o){for(std::uint32_t n=0;n<384;++n){auto k=n;GrindComponents c;for(int i=5;i>=0;--i){const std::uint32_t b=i==5?6:i==4?4:2;c[std::size_t(i)]=k%b;k/=b;}auto name=LookupGrindName(c);if(!name)std::abort();o.Word(std::uint32_t(name->skating_id));TextOut(o,name->attribute);TextOut(o,name->display);o.Word(std::uint32_t(name->scorable_id));for(auto word:EncodeAnimationName(name->attribute))o.Word(word);}for(unsigned lane=0;lane<6;++lane){GrindComponents c{};c[lane]=lane==5?6:lane==4?4:2;o.Word(bool(LookupGrindName(c)));}}
}
int main(int argc,char** argv){
 if(argc==3&&std::string_view(argv[2])=="--settings-only"){SettingsDatabase d;std::string e;if(!d.Load(File(argv[1]),e))return 2;GrindRuntimeSettings s;Output o;const bool ok=GrindRuntimeSettings::Load(d,s,e);o.Status(ok,e);if(ok)GrindSettingsOut(o,s);for(auto w:o.words)for(unsigned n=0;n<4;++n)std::cout.put(char(w>>(n*8)));return 0;}
// GENERATED_NATIVE_OWNER_INITIALIZATION
 Input i{{std::istreambuf_iterator<char>(std::cin),{}},0};Output o;const auto count=i.Word();o.Word(count);
 for(unsigned c=0;c<count;++c){
// GENERATED_NATIVE_OWNER_CONSTRUCTION
 const auto provider=ReadProvider(i);GrindRuntime grind;GroundSettings gs;AirStateSettings as;AirTrajectoryRuntime trajectory;TrainerTuning trainer;
 if(!grind.Load(data,error)||!gs.Load(data,"normal","smooth",error)||!as.Load(data,error)||!trajectory.Load(data,error)){std::cerr<<error;return 2;}
 auto globals=TeleportGlobals(evaluator,0,error);bool fakie=false;std::uint32_t jump_fix=1000;GroundPhaseLifecycle life;
 const auto rows=i.Word();o.Word(rows);float manual_drag=0;
 auto frame=[&](){return GrindRuntimeOwners{p,*owner,ground,gr,life,a,*ik,anim,*input,*sair,air,wipeout,trajectory,gs,as,trainer,globals};};
 auto snapshot=[&]{o.Word(4);Block(o,[&]{TeleportSnapshot(o,*owner,ground,gr,life.skeleton_controller,life.manual_drag_2724,life.skeleton_elapsed_16505,life.board_animated_290,wobble,hand,air,*sair,foot,wipeout,grab,p,a,*ik,*input,anim,collision,teleported,actions);});Block(o,[&]{GrindOwnerOut(o,grind,owner->grind->jumper);});Block(o,[&]{CameraOut(o,grind.camera);});Block(o,[&]{GrindSettingsOut(o,grind.settings);});};snapshot();
 for(unsigned r=0;r<rows;++r){const auto op=i.Word();o.Word(op);bool okay=true;std::vector<std::uint32_t> extra;error.clear();switch(op){
// GENERATED_NATIVE_PACKET_RESET_CASES
 case 10:{const auto state=ParsePhysicalStateId(i.Word());if(!state)std::abort();okay=grind.Enter(*state,frame(),error);break;}
 case 11:okay=grind.Exit(frame(),error);break;
 case 12:owner->toolkit=BoardToolkit::FromBoard(p.board,owner->processed.flags_2468,owner->processed.scalar_2612,Decode(owner->processed.vectors_464_480_496_512_528[0]),gr.retained_board_normal);gr.retained_board_normal=owner->toolkit->filtered_normal;break;
 case 13:okay=grind.Advance(frame(),error);break;
 case 14:okay=grind.Fill(frame(),error);break;
 case 15:okay=grind.ConditionOutputs(frame(),fakie,error);break;
 case 16:grind.ConditionCamera(owner->physical.grinds);break;
 case 17:okay=grind.Post(frame(),jump_fix,error);break;
 case 18:owner->toolkit.reset();break;
 case 19:grind.manager.reset();break;
 case 20:grind.Observe(ManagerRead(i));break;
 case 21:owner->grind->jumper=JumperRead(i);break;
 case 22:{const auto pose=i.Word();fakie=i.Word()!=0;jump_fix=i.Word();trainer.grind_pop=i.Float();globals=TeleportGlobals(evaluator,pose,error);break;}
 case 23:{const auto count=i.Word();for(unsigned k=0;k<count;++k)p.board.ForcesMut().Append({k,{.137f,.317f,.731f},{-.731f,.137f,.317f}});break;}
 case 24:{const auto part=i.Word(),value=i.Word();extra.push_back(std::uint32_t(ik->bone_indices[part]));ik->bone_indices[part]=value;break;}
 case 25:{GrindFilteredOutput output;okay=grind.FilteredOutput(owner->physical.grinds,output,error);if(okay){extra.push_back(std::uint32_t(output.kind));extra.push_back(std::uint32_t(output.scorable_id));for(auto v:output.name)extra.push_back(v);for(auto v:output.scoring_name)extra.push_back(v);extra.push_back(output.on_front);extra.push_back(FloatBits(output.crouch));extra.push_back(std::uint32_t(output.pathed_guid));extra.push_back(std::uint32_t(output.pathed_guid>>32));extra.push_back(std::uint32_t(output.local_guid));extra.push_back(std::uint32_t(output.local_guid>>32));}break;}
 case 26:{const auto count=i.Word();float v;for(unsigned k=0;k<count;++k){const auto family=PlayerGrindFamily(i.Word());const auto mode=i.Word();const auto strength=i.Float();Output result;std::string e;const bool ok=grind.settings.substate.Vertical(family,mode,strength,v,e);result.Status(ok,e);if(ok)result.Float(v);result.Float(GrindGeometrySideJump(family,i.Word()));extra.insert(extra.end(),result.words.begin(),result.words.end());}break;}
 case 27:{Output result;Names(result);extra=std::move(result.words);break;}
 case 28:air.state.spin_angle=i.Float();air.state.spin_speed=i.Float();air.state.secondary_lean_angle=i.Float();break;
 case 30:{const auto air_counter=std::int32_t(i.Word());const bool air_target=i.Word()!=0;auto& v=owner->processed;const auto& ex=anim.extra;PlayerGrindLiveHost live(p.board,p.settings.board,materials);std::optional<PlayerGrindPending> pending;const PlayerGrindPreContext pre{p.DeckFrame(),air_counter,v.state_2504,air_target,anim.fields.balance,ex.grind_translation,ex.grind_stability_nudge,ex.grind_up_down,ex.grind_grab_min_height};okay=owner->grind->PreUpdate(v,provider,p.world,pre,live,pending,error);if(okay){const PlayerGrindPostContext post{p.DeckFrame(),anim.fields.balance,ex.grind_translation,ex.grind_stability_nudge,ex.grind_up_down,ex.grind_grab_min_height};std::optional<PlayerGrindPostResult> result;okay=owner->grind->PostUpdate(v,p.world,std::move(*pending),post,live,result,error);if(okay){owner->grind_observation=std::make_unique<PlayerGrindObservation>(result->observation);grind.Observe(result->observation);extra.push_back(std::uint32_t(result->wipeout_reasons.size()));for(auto reason:result->wipeout_reasons){extra.push_back(std::uint32_t(reason));wipeout.Request(reason,0);}}}break;}
 case 31:p.world=GrindWorld(i.Word());break;
 case 34:okay=p.riding.StartWheelQueries(p.board,p.world,error)&&p.riding.FinishWheelQueries(error);if(okay)p.riding.FinishPostPhysics(p.board,p.board_wiping_out,owner->processed.flags_2468,owner->processed.timestep_2604);break;
 case 32:p.board.ClearForces();break;
 default:return 2;}
 collision=Collision(p);o.Status(okay,error);o.Word(std::uint32_t(extra.size()));for(auto v:extra)o.Word(v);snapshot();(void)manual_drag;
 }
 }if(i.at!=i.data.size())return 2;for(auto w:o.words)for(unsigned n=0;n<4;++n)std::cout.put(char(w>>(n*8)));
}
#pragma clang diagnostic pop

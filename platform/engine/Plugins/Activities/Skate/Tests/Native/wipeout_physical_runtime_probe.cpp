// SPDX-License-Identifier: Apache-2.0
// Shared canonical owner constructors and observations come from the reset proof.
// GENERATED_NATIVE_OWNER_PREFIX
#include "WipeoutPhysicalRuntime.h"
namespace {
// GENERATED_WIPEOUT_PROTOCOL
void WipeoutQueryOut(Output& o,const AirTrajectoryQueryResult& q){o.Floats(q.contact_position);o.Floats(q.contact_normal);o.Floats(q.landing_normal);o.Float(q.contact_time);o.Matrix(q.contact_transform);o.Word(std::uint32_t(q.contact_frame));o.Word(q.surface);o.Word(q.geometry);}
void WipeoutTrajectoryOut(Output& o,const AirTrajectory& t){o.Floats(t.position);o.Floats(t.velocity);o.Floats(t.acceleration);o.Float(t.scalar_48);}
void WipeoutOwnerOut(Output& o,const WipeoutPhysicalRuntime& w){ObserveWipeoutState(o,w.state);const auto& a=w.contact.material10;for(auto v:{a.previous_velocity,a.normal,a.target_velocity})o.Floats(v);o.Float(a.time);o.Word(a.phase);o.Word(a.finished);const auto& b=w.contact.material11;for(auto v:{b.normal,b.previous_velocity,b.velocity})o.Floats(v);o.Word(std::uint32_t(b.frames_since_contact));o.Word(std::uint32_t(b.active_frames));o.Word(b.contact_latched);o.Word(b.active);WipeoutQueryOut(o,w.prediction.result);o.Word(bool(w.prediction.pending));if(w.prediction.pending){const auto& p=*w.prediction.pending;WipeoutQueryOut(o,p.result);WipeoutTrajectoryOut(o,p.trajectory);o.Word(p.surface_query);}}
void WipeoutSettingsOut(Output& o,const WipeoutPhysicalRuntime& w){const auto& r=w.ragdoll.settings;for(auto v:r.normal_limits)for(auto x:v)o.Word(x);for(auto v:r.ragdoll_limits)for(auto x:v)o.Word(x);o.Word(r.inverse_mass);o.Word(r.inverse_inertia);o.Floats(r.drag);for(auto m:r.materials)o.Floats(std::array<float,3>{m.static_friction,m.dynamic_friction,m.restitution});const auto& s=w.settings;const auto& v=s.recovery;o.Floats(std::array<float,6>{v.minimum_time,v.minimum_settled,v.maximum_time,v.fade_time,v.over_speed,v.over_minimum_time});o.Floats(std::array<float,8>{s.remove_target_time,s.remove_drives_time,s.controlled_weight_step,s.collision_weight_step,s.board_restitution,s.board_friction,s.deck_angular_drag,s.push_force});for(auto m:s.standard_materials)o.Floats(std::array<float,3>{m.static_friction,m.dynamic_friction,m.restitution});const auto& d=w.drives;for(auto b:d.bone)o.Floats(b);o.Floats(d.root);o.Floats(d.strength);o.Floats(std::array<float,3>{d.hook_spring,d.hook_strength,d.hook_damping});for(const auto& p:w.profiles)ObserveWipeoutProfile(o,p);}
// The serialized world is authored transport. Its tags drive actual shared
// solver reports; its query metadata drives actual trajectory queries.
WorldGeometry WipeoutWorld(Input& i){std::vector<WorldTriangle> triangles;QueryMetadata metadata;metadata.island_flags=3;const auto count=i.Word();for(unsigned k=0;k<count;++k){std::array<Vec3,3> vertices;for(auto& v:vertices)v={i.Float(),i.Float(),i.Float()};const auto fatness=i.Float();const auto edges=i.Floats<3>();const auto flags=i.Word();const ContactMaterial material{i.Float(),i.Float(),i.Float()};const auto tag=i.Word(),surface=i.Word();triangles.push_back({TriangleFromVolume(vertices,fatness,edges,flags),material,tag});metadata.packed_surfaces.push_back(std::uint16_t(surface));}if(count){QueryMesh mesh;mesh.triangle_range={0,count};mesh.local_bounds={{-100,-100,-100},{100,100,100}};mesh.matching_group=-1;mesh.rejection_flags=0xffffffffu;mesh.geometry=77;mesh.pool=QueryPool::Ground;metadata.meshes.push_back(mesh);}const char* error=nullptr;auto world=WorldGeometry::WithQueryMetadata(std::move(triangles),std::move(metadata),error);if(!world)std::abort();return std::move(*world);}
}
int main(int argc,char** argv){
 if(argc==5&&std::string_view(argv[4])=="--settings-only"){SettingsDatabase d;PhysicsSkeletons b;std::string e;if(!d.Load(File(argv[1]),e)||!b.Load(File(argv[2]),argv[3],e))return 2;const auto* def=b.Find("PHYS_TPOSE");if(!def)return 2;WipeoutPhysicalRuntime w;Output o;const bool ok=w.Load(d,*def,e);o.Status(ok,e);if(ok)WipeoutSettingsOut(o,w);for(auto v:o.words)for(unsigned n=0;n<4;++n)std::cout.put(char(v>>(n*8)));return 0;}
// GENERATED_NATIVE_OWNER_INITIALIZATION
 Input i{{std::istreambuf_iterator<char>(std::cin),{}},0};Output o;const auto count=i.Word();o.Word(count);
 for(unsigned c=0;c<count;++c){
// GENERATED_NATIVE_OWNER_CONSTRUCTION
 WipeoutPhysicalRuntime w;AirStateSettings air_settings;if(!w.Load(data,*definition,error)||!checks.Load(data,error)||!air_settings.Load(data,error)){std::cerr<<error;return 2;}
 auto globals=TeleportGlobals(evaluator,0,error);const auto rows=i.Word();o.Word(rows);
 auto frame=[&](){return WipeoutPhysicalOwners{p,*owner,ground,life,a,*ik,anim,*input,checks,air_settings,globals};};
 auto snapshot=[&]{o.Word(3);Block(o,[&]{TeleportSnapshot(o,*owner,ground,gr,controller,life.manual_drag_2724,elapsed,animated,wobble,hand,air,*sair,foot,wipeout,grab,p,a,*ik,*input,anim,collision,teleported,actions);});Block(o,[&]{WipeoutOwnerOut(o,w);});Block(o,[&]{WipeoutSettingsOut(o,w);});};snapshot();
 for(unsigned r=0;r<rows;++r){const auto op=i.Word();o.Word(op);bool okay=true;std::vector<std::uint32_t> extra;error.clear();switch(op){
// GENERATED_NATIVE_PACKET_RESET_CASES
 case 10:okay=w.Enter(frame(),error);break;
 case 11:w.Exit(frame());break;
 case 12:owner->toolkit=BoardToolkit::FromBoard(p.board,owner->processed.flags_2468,owner->processed.scalar_2612,Decode(owner->processed.vectors_464_480_496_512_528[0]),gr.retained_board_normal);gr.retained_board_normal=owner->toolkit->filtered_normal;break;
 case 13:okay=w.Advance(frame(),error);break;
 case 14:{Output e;ObserveWipeoutOutput(e,w.Fill(frame()));extra=std::move(e.words);break;}
 case 17:w.PostPhysics(frame());break;
 case 18:owner->toolkit.reset();break;
 case 21:w.state=ReadWipeoutState(i);break;
 case 22:{const auto pose=i.Word();globals=TeleportGlobals(evaluator,pose,error);anim.extra.wipeout_control=i.Floats<2>();anim.extra.wipeout_gesture=i.Floats<2>();break;}
 case 24:{const auto part=i.Word(),value=i.Word();extra.push_back(std::uint32_t(ik->bone_indices[part]));ik->bone_indices[part]=value;break;}
 case 31:p.world=WipeoutWorld(i);break;
 case 34:okay=p.riding.StartWheelQueries(p.board,p.world,error)&&p.riding.FinishWheelQueries(error);if(okay)p.riding.FinishPostPhysics(p.board,p.board_wiping_out,owner->processed.flags_2468,owner->processed.timestep_2604);break;
 case 35:{const auto request=i.Word();controller.override_enabled=i.Word()!=0;okay=w.ragdoll.Request(controller,request,p.skeleton,p.skeleton_joints,p.skeleton_collision,error);break;}
 case 36:w.ragdoll.RestoreNormal(p.skeleton,p.skeleton_joints,p.skeleton_collision,p.collision_feedback);break;
 case 37:{const auto part=i.Word();const auto velocity=i.Floats<3>();p.skeleton.BodiesMut()[part].rates.linear_velocity={velocity[0],velocity[1],velocity[2]};break;}
 case 38:{const auto reason=i.Word();wipeout.Request(reason,i.Float());break;}
 case 39:{const auto v=i.Floats<3>();for(auto& part:p.skeleton.BodiesMut()){part.rates.position.x+=v[0];part.rates.position.y+=v[1];part.rates.position.z+=v[2];}p.skeleton.PublishPhysicalRecord(p.DeckFrame());break;}
 default:return 2;}
 collision=Collision(p);o.Status(okay,error);o.Word(std::uint32_t(extra.size()));for(auto v:extra)o.Word(v);snapshot();
 }
 }if(i.at!=i.data.size())return 2;for(auto v:o.words)for(unsigned n=0;n<4;++n)std::cout.put(char(v>>(n*8)));
}
#pragma clang diagnostic pop

// Actual Session APIs; every frame, state, body, marker query and pose is live.
#include "GameplaySession.h"
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-function"
#include "gameplay_session_helpers.inc"
#pragma clang diagnostic pop
#include "gameplay_session_controller.inc"
namespace {
std::string SessionText(Input& i){const auto n=i.Word();std::string s;for(std::uint32_t k=0;k<n;++k)s+=char(i.Word());return s;}
XboxState SessionXbox(Input& i){XboxState s;s.buttons=std::uint16_t(i.Word());for(auto& x:s.triggers)x=std::uint8_t(i.Word());for(auto& x:s.left)x=std::int16_t(i.Word());for(auto& x:s.right)x=std::int16_t(i.Word());return s;}
DeviceSample SessionSample(Input& i){const auto kind=i.Word();if(kind==0){DevicePacket p;p.number=i.Word();p.state=SessionXbox(i);p.subtype=std::uint8_t(i.Word());return p;}return DeviceError{DeviceError::Kind(kind-1),i.Word()};}
GameplayWorldSnapshot SessionWorld(Input& i){GameplayWorldSnapshot s;const auto n=i.Word();for(std::uint32_t k=0;k<n;++k){std::array<Vec3,3> t;for(auto& p:t){const auto x=i.Floats<3>();p={x[0],x[1],x[2]};}s.triangles.push_back(t);}const auto r=i.Word();for(std::uint32_t k=0;k<r;++k){std::vector<std::array<float,3>> points;const auto n=i.Word();for(std::uint32_t j=0;j<n;++j)points.push_back(i.Floats<3>());s.rails.push_back(std::move(points));}return s;}
void SessionMarkerOut(Output& o,const SessionMarkerRuntime& s){
 o.Word(bool(s.marker));if(s.marker){const auto& m=*s.marker;o.Matrix(m.transform);o.Word(m.on_board);o.Word(m.foot_forward);o.Wide(m.generation);}
 o.Float(s.hold.elapsed);o.Word(s.hold.fired);o.Word(s.hold.tail);o.Wide(s.generation);o.Wide(s.last_batch);o.Word(s.visible);o.Word(s.can_place);o.Word(s.can_return);o.Word(s.blocked_until_release);o.Float(s.progress);std::uint64_t time;std::memcpy(&time,&s.ui_time,8);o.Wide(time);o.Float(s.validation.slope);o.Float(s.validation.max_drop);o.Float(s.validation.clearance_length);o.Float(s.validation.clearance_radius);
}
void SessionSnapshot(Output& o,GameplaySession& s,std::uint32_t generation){
 auto& g=*s.gameplay;o.Word(6);
 Block(o,[&]{const auto pose=s.Pose();o.Matrix(pose.root);o.Word(std::uint32_t(pose.bones.size()));for(const auto& m:pose.bones)o.Matrix(m);o.Word(std::uint32_t(pose.names.size()));for(const auto& name:pose.names)TextOut(o,name);o.Word(bool(pose.camera));if(pose.camera){const auto& f=*pose.camera;o.Floats(std::array<float,3>{f.position[0],f.position[1],f.position[2]});for(const auto& c:f.basis.columns)o.Floats(c);o.Float(f.field_of_view_degrees);}const auto& v=pose.velocity;o.Floats(std::array<float,3>{v.x,v.y,v.z});o.Wide(pose.tick);TextOut(o,pose.state);const auto& score=g.scoring.session.holder.State().snapshot;o.Floats(std::array<float,3>{score.completed_lines+score.line,score.last_reward,g.animation_input.fields.balance});TextOut(o,g.scoring.CurrentTrick());o.Float(s.Period());});
 Block(o,[&]{std::string error;std::vector<Mat4> pose;const bool okay=s.ReferencePose(pose,error);o.Status(okay,error);if(okay){o.Word(std::uint32_t(pose.size()));for(const auto& m:pose)o.Matrix(m);}});
 Block(o,[&]{SessionMarkerOut(o,s.markers);});
 Block(o,[&]{GameplayWorldInputObserver::Controller(o,s.input);});
 Block(o,[&]{o.Float(s.Elapsed());o.Word(generation);});
 Block(o,[&]{GameplaySnapshot(o,g);});
}
}
int main(int argc,char** argv){
 if(argc!=2)return 2;std::string error;std::shared_ptr<const GameplayResources> resources;if(!LoadGameplayResources(argv[1],resources,error)){std::cerr<<error<<'\n';return 2;}
 Input i;i.data.assign(std::istreambuf_iterator<char>(std::cin),{});Output o;const auto count=i.Word();o.Word(count);
 for(std::uint32_t c=0;c<count;++c){
  const auto world=SessionWorld(i);const auto spawn=i.Floats<3>();const auto heading=i.Float();const auto rows=i.Word();o.Word(rows);std::unique_ptr<GameplaySession> s;const bool loaded=GameplaySession::Create(resources,world,{spawn[0],spawn[1],spawn[2]},heading,s,error);o.Status(loaded,error);if(!loaded){if(rows)return 2;continue;}
  std::uint32_t generation=0;SessionSnapshot(o,*s,generation);
  for(std::uint32_t n=0;n<rows;++n){const auto op=i.Word();o.Word(op);bool okay=true;error.clear();switch(op){
   case 0:{const auto p=i.Floats<3>();const auto angle=i.Float();const auto next=i.Word();okay=s->Activate({p[0],p[1],p[2]},angle,error);if(okay)generation=next;break;}
   case 1:okay=s->Tick(SessionXbox(i),error);break;
   case 2:{const auto dt=i.Float();std::array<DeviceSample,4> samples;for(auto& x:samples)x=SessionSample(i);s->Collect(samples,dt);break;}
   case 3:okay=s->Advance(error);break;
   case 4:s->SuspendInput();break;
   case 5:{const auto dt=i.Float();const auto raw=SessionXbox(i);okay=s->Step(raw,dt,error);break;}
   case 6:{const auto name=SessionText(i);const auto goofy=i.Word()!=0;const auto trucks=i.Float();okay=s->Configure(name,goofy,trucks,error);break;}
   case 7:{const auto v=i.Floats<4>();okay=s->Tune(v[0],v[1],v[2],v[3],error);break;}
   case 8:{const auto v=i.Floats<3>();s->Launch({v[0],v[1],v[2]});break;}
   case 9:s->SetAspectRatio(i.Float());break;
   case 10:{const auto source=SessionWorld(i);std::optional<PreparedGameplayWorld> next;okay=BuildGameplayWorld(source,s->gameplay->physical->settings.board.floor_material,next,error);if(okay)okay=s->InstallCollision(std::move(*next),error);break;}
   case 11:break;
   default:return 2;
  }o.Status(okay,error);SessionSnapshot(o,*s,generation);}
 }
 if(i.at!=i.data.size())return 2;for(const auto w:o.words)for(unsigned n=0;n<4;++n)std::cout.put(char(w>>(n*8)));return std::cout?0:2;
}

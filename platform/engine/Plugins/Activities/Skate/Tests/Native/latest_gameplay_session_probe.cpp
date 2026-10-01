// SPDX-License-Identifier: Apache-2.0
// Latest pinned Session APIs; every frame, state, body, marker query and pose is live.
// The seventh block reads authoritative retained owners; the leaf footer calls the actual helper.
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
void LatestQueryOut(Output &o, const AirTrajectoryQueryResult &r) {
  o.Floats(r.contact_position);
  o.Floats(r.contact_normal);
  o.Floats(r.landing_normal);
  o.Float(r.contact_time);
  o.Matrix(r.contact_transform);
  o.Word(std::uint32_t(r.contact_frame));
  o.Word(r.surface);
  o.Word(r.geometry);
}
void LatestLaunchOut(Output &o, const AirLaunchInfo &v) {
  o.Matrix(v.reckoning_transform);
  o.Matrix(v.reckoning_inverse);
  for (auto a :
       {v.start_velocity, v.com_velocity, v.skeleton_vector_160,
        v.skeleton_vector_176, v.board_position, v.animation_com_position,
        v.start_position_override, v.board_position_override})
    o.Floats(a);
  o.Floats(std::array<float, 3>{v.cone_angle_x, v.cone_angle_z, v.timestep});
  o.Word(v.player_jumped);
  o.Word(v.use_position_override);
  o.Word(v.trajectory_count);
}
void LatestTrajectoryOwnerOut(Output &o, const AirTrajectoryRuntime &a) {
  const auto &s = a.selector;
  for (bool v :
       {s.Pending(), s.Valid(), s.JustChanged(), s.AllPredictionsMissed(),
        s.GrindLockedToMiddle(), s.AdjustedOnVert()})
    o.Word(v);
  o.Word(s.Pass());
  o.Word(s.SelectedIndex() ? std::uint32_t(*s.SelectedIndex()) : 0xffffffffu);
  o.Word(s.LaunchInfo().has_value());
  if (s.LaunchInfo())
    LatestLaunchOut(o, *s.LaunchInfo());
  o.Word(std::uint32_t(s.Requests().size()));
  for (const auto &r : s.Requests()) {
    TrajectoryOut(o, r.trajectory);
    o.Floats(std::array<float, 3>{r.radius, r.start_error, r.end_error});
  }
  o.Word(s.Selection().has_value());
  if (s.Selection()) {
    const auto &v = *s.Selection();
    o.Word(std::uint32_t(v.candidate_index));
    LatestQueryOut(o, v.prediction.result);
    TrajectoryOut(o, v.prediction.request.trajectory);
    o.Floats(std::array<float, 3>{v.prediction.request.radius,
                                  v.prediction.request.start_error,
                                  v.prediction.request.end_error});
    for (auto x : {v.start_velocity, v.landing_normal, v.collision_velocity,
                   v.collision_position})
      o.Floats(x);
    TrajectoryOut(o, v.com_trajectory);
    o.Word(v.surface_category);
    o.Word(v.wall_ride);
    o.Word(v.grind.has_value());
  }
  o.Word(a.PendingResults().has_value());
  if (a.PendingResults()) {
    o.Word(std::uint32_t(a.PendingResults()->size()));
    for (const auto &r : *a.PendingResults())
      LatestQueryOut(o, r);
  }
  o.Word(bool(a.GrindWorld()));
  o.Word(std::uint32_t(a.NearbyGrinds().size()));
  for (auto v : a.NearbyGrinds())
    o.Word(std::uint32_t(v));
}
void SessionSnapshot(Output& o,GameplaySession& s,std::uint32_t generation){
 auto& g=*s.gameplay;o.Word(7);
 Block(o,[&]{const auto pose=s.Pose();o.Matrix(pose.root);o.Word(std::uint32_t(pose.bones.size()));for(const auto& m:pose.bones)o.Matrix(m);o.Word(std::uint32_t(pose.names.size()));for(const auto& name:pose.names)TextOut(o,name);o.Word(bool(pose.camera));if(pose.camera){const auto& f=*pose.camera;o.Floats(std::array<float,3>{f.position[0],f.position[1],f.position[2]});for(const auto& c:f.basis.columns)o.Floats(c);o.Float(f.field_of_view_degrees);}const auto& v=pose.velocity;o.Floats(std::array<float,3>{v.x,v.y,v.z});o.Wide(pose.tick);TextOut(o,pose.state);const auto& score=g.scoring.session.holder.State().snapshot;o.Floats(std::array<float,3>{score.completed_lines+score.line,score.last_reward,g.animation_input.fields.balance});TextOut(o,g.scoring.CurrentTrick());o.Float(s.Period());});
 Block(o,[&]{std::string error;std::vector<Mat4> pose;const bool okay=s.ReferencePose(pose,error);o.Status(okay,error);if(okay){o.Word(std::uint32_t(pose.size()));for(const auto& m:pose)o.Matrix(m);}});
 Block(o,[&]{SessionMarkerOut(o,s.markers);});
 Block(o,[&]{GameplayWorldInputObserver::Controller(o,s.input);});
 Block(o,[&]{o.Float(s.Elapsed());o.Word(generation);});
 Block(o,[&]{GameplaySnapshot(o,g);});
 Block(o,[&]{
  o.Word(g.physical->transfer.has_value());if(g.physical->transfer)o.Word(*g.physical->transfer);o.Float(g.trajectory.vert_assist);
  o.Wide(g.physical->ticks);o.Word(std::uint32_t(g.player_state->Current()));const auto& p=g.input->processed;
  o.Word(p.state_2504);o.Word(p.state_2508);o.Float(p.transition_2636);
  for(auto w:p.vectors_464_480_496_512_528[0])o.Word(w);for(auto w:p.vectors_400_416[0])o.Word(w);
  const auto& v=g.physical->board.Bodies()[std::size_t(BoardBodyId::Deck)].rates.linear_velocity;o.Floats(std::array<float,3>{v.x,v.y,v.z});
  LatestTrajectoryOwnerOut(o,g.trajectory);
 });
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
   case 7:{const auto v=i.Floats<5>();okay=s->Tune(v[0],v[1],v[2],v[3],v[4],error);break;}
   case 8:{const auto v=i.Floats<3>();s->Launch({v[0],v[1],v[2]});break;}
   case 9:s->SetAspectRatio(i.Float());break;
   case 10:{const auto source=SessionWorld(i);std::optional<PreparedGameplayWorld> next;okay=BuildGameplayWorld(source,s->gameplay->physical->settings.board.floor_material,next,error);if(okay)okay=s->InstallCollision(std::move(*next),error);break;}
   case 11:break;
   default:return 2;
  }o.Status(okay,error);SessionSnapshot(o,*s,generation);}
 }
 const auto leaves=i.Word();o.Word(leaves);for(std::uint32_t n=0;n<leaves;++n){const auto normal=i.Floats<4>(),velocity=i.Floats<4>();const float direction=i.Float(),assist=i.Float();const auto result=AirTrajectoryVertDeparture(normal,velocity,direction,assist);o.Floats(result.first);o.Floats(result.second);}
 if(i.at!=i.data.size())return 2;for(const auto w:o.words)for(unsigned n=0;n<4;++n)std::cout.put(char(w>>(n*8)));return std::cout?0:2;
}

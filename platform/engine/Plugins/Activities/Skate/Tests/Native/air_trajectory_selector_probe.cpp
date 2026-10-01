// SPDX-License-Identifier: Apache-2.0
#include "AirTrajectorySelector.h"
#include "AirTrajectorySelectorSettings.h"
#include "AirTrajectorySelectorMath.h"
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <numeric>
using namespace atelier::skate;
namespace M=atelier::skate::air_trajectory_detail;
namespace {
std::vector<std::uint32_t> input,output;std::size_t cursor=0;
std::uint32_t Word(){if(cursor==input.size())std::abort();return input[cursor++];}
float Float(){const auto w=Word();float f;std::memcpy(&f,&w,4);return f;}
Vec4 Vector(){Vec4 v;for(auto& f:v)f=Float();return v;}
Mat4 Matrix(){Mat4 m;for(auto& v:m)v=Vector();return m;}
void Out(std::uint32_t w){output.push_back(w);}
void Out(float f){std::uint32_t w;std::memcpy(&w,&f,4);Out(w);}
void Out(Vec4 v){for(auto f:v)Out(f);}
void Out(Mat4 m){for(auto v:m)Out(v);}
void Status(bool ok,const std::string& e){Out(std::uint32_t(ok));Out(std::uint32_t(e.size()));for(unsigned char c:e)Out(std::uint32_t(c));}
template<class T,class F>void Optional(const std::optional<T>& v,F emit){Out(std::uint32_t(v.has_value()));if(v)emit(*v);}
void OptionalVector(const std::optional<Vec4>& v){Optional(v,[](Vec4 x){Out(x);});}
void OptionalFloat(const std::optional<float>& v){Optional(v,[](float x){Out(x);});}
void Traj(AirTrajectory t){Out(t.position);Out(t.velocity);Out(t.acceleration);Out(t.scalar_48);}
AirTrajectory ReadTrajectory(){auto p=Vector(),v=Vector(),a=Vector();return {p,v,a,Float()};}
void Request(AirTrajectoryQueryRequest q){Traj(q.trajectory);Out(q.radius);Out(q.start_error);Out(q.end_error);}
AirTrajectoryQueryRequest ReadRequest(){auto t=ReadTrajectory();const float r=Float(),a=Float(),b=Float();return {t,r,a,b};}
void Result(AirTrajectoryQueryResult v){Out(v.contact_position);Out(v.contact_normal);Out(v.landing_normal);Out(v.contact_time);Out(v.contact_transform);Out(std::uint32_t(v.contact_frame));Out(v.surface);Out(v.geometry);}
void Prediction(AirTrajectoryPrediction v){Result(v.result);Request(v.request);}
void Edge(PlayerGrindPrimitive v){Out(v.start);Out(v.end);Out(std::uint32_t(v.owner));Out(std::uint32_t(v.owner>>32));}
void Orientation(GrindAirLandingOrientation v){Out(v.kind);Out(std::uint32_t(v.garbage));Out(v.boardslide_dir);Out(v.tipslide_dir);Out(v.backslash_dir);Out(v.high_side);}
void Target(AirTrajectoryGrindTarget v){Edge(v.edge);Out(std::uint32_t(v.provider_index));Out(v.primitive_flags);Orientation(v.orientation);Out(v.point);Out(v.vertical_normal);}
void GrindCandidate(AirTrajectoryGrindCandidate v){Out(v.point);Out(v.trajectory_point);Out(v.direction);Out(v.approach);Out(v.distance);Out(v.time);Out(v.angle);Out(std::uint32_t(v.frame));Out(std::uint32_t(v.primitive));}
void Candidate(const AirTrajectoryCandidate& c){Prediction(c.prediction);Out(c.start_velocity);Out(c.normal);Out(c.collision_velocity);Out(c.collision_position);Out(c.score);Out(c.wall_score);Out(std::uint32_t(c.wall_ride));Optional(c.grind,[](auto v){Target(v);});}
void LaunchInfo(const AirLaunchInfo& v){Out(v.reckoning_transform);Out(v.reckoning_inverse);Out(v.start_velocity);Out(v.com_velocity);Out(v.skeleton_vector_160);Out(v.skeleton_vector_176);Out(v.board_position);Out(v.animation_com_position);Out(v.start_position_override);Out(v.board_position_override);Out(v.cone_angle_x);Out(v.cone_angle_z);Out(v.timestep);Out(std::uint32_t(v.player_jumped));Out(std::uint32_t(v.use_position_override));Out(std::uint32_t(v.trajectory_count));}
AirLaunchInfo ReadLaunch(){AirLaunchInfo v;v.reckoning_transform=Matrix();v.reckoning_inverse=Matrix();v.start_velocity=Vector();v.com_velocity=Vector();v.skeleton_vector_160=Vector();v.skeleton_vector_176=Vector();v.board_position=Vector();v.animation_com_position=Vector();v.start_position_override=Vector();v.board_position_override=Vector();v.cone_angle_x=Float();v.cone_angle_z=Float();v.timestep=Float();v.player_jumped=Word()!=0;v.use_position_override=Word()!=0;v.trajectory_count=static_cast<std::uint16_t>(Word());return v;}
AirSelectorInput ReadSelectorInput(){AirSelectorInput v;v.gravity=Vector();v.ground_normal=Vector();v.contact_position=Vector();v.heading_direction=Vector();v.reference_up=Vector();v.board_vertical_velocity=Float();v.directional_input=Float();v.previous_physics_state=Word();v.flags_2472=Word();v.flags_2476=Word();v.offboard_flags_1776=Word();v.grind_lock_distance=Float();return v;}
template<std::size_t N>void Graph(PointGraph<N> p){for(auto x:p.x)Out(x);for(auto y:p.y)Out(y);}
PointGraph<8> ReadGraph(){PointGraph<8> g;for(auto& x:g.x)x=Float();for(auto& y:g.y)y=Float();return g;}
void Settings(const AirTrajectorySelectorSettings& s){
    Out(s.cone_x);
    Out(s.cone_z);
    Out(s.trajectory_max_time);
    Out(s.trajectory_max_drop);
    Out(s.trajectory_error_start);
    Out(s.trajectory_error_end);
    Out(s.speed_factor_min);
    Out(s.speed_factor_max);
    Graph(s.cone_angle_z_vs_speed);
    Out(s.cone_x_second_pass);
    Out(s.cone_z_second_pass);
    Graph(s.landing_time_bonus);
    Graph(s.landing_com_scalar_vs_slope);
    Graph(s.landing_force_scalar);
    Graph(s.grind_penalty_vs_distance);
    Out(s.score_middle_bonus);
    Out(s.score_landing_force);
    Out(s.score_landing_direction);
    Out(s.score_transition);
    Out(s.surface_unrideable_score);
    Out(s.surface_dont_align_score);
    Out(s.natural_air_off_verts_scalar);
    Out(s.minimum_valid_time);
    Out(s.minimum_time_after_apex);
    Out(s.minimum_normal_delta_second_pass);
    Out(s.maximum_trajectory_adjust);
    Out(s.wall_ride_test_distance);
    Out(s.wall_ride_minimum_height);
    Out(s.wall_ride_angle_allow_landing);
    Out(s.wall_ride_height_score);
    Graph(s.wall_ride_boost);
    Out(s.wall_ride_normal_dot_limit);
    Graph(s.displacement_vs_speed);
    Graph(s.displacement_vs_ground_normal);
    Out(s.trajectory_radius);
    Out(s.trajectory_displacement);
    Out(std::uint32_t(s.minimum_trajectory_frames));
    Out(s.vert_jump_align_factor);
    Out(s.vert_jump_align_max_ground_normal_y);
    Out(s.vert_jump_align_min_direction_y);
    Out(s.vert_jump_align_max_angle);
}
void Batch(const AirTrajectoryLaunchBatch& b){Out(std::uint32_t(b.requests.size()));for(auto q:b.requests)Request(q);Out(std::uint32_t(b.velocities.size()));for(auto v:b.velocities)Out(v);Out(b.origin);Out(b.board_position);Out(b.local_board_position);Out(b.local_com_position);Out(b.com_displacement);}
void Selection(const AirTrajectorySelection& v){Out(std::uint32_t(v.candidate_index));Prediction(v.prediction);Out(v.start_velocity);Out(v.landing_normal);Out(v.collision_velocity);Out(v.collision_position);Traj(v.com_trajectory);Out(v.surface_category);Out(std::uint32_t(v.wall_ride));Optional(v.grind,[](auto t){Target(t);});}
void Observe(const AirTrajectorySelector& s){Optional(s.LaunchInfo(),[](const auto& v){LaunchInfo(v);});Optional(s.Batch(),[](const auto& b){Batch(b);});Out(std::uint32_t(s.Candidates().size()));for(const auto& c:s.Candidates())Candidate(c);Optional(s.Selection(),[](const auto& v){Selection(v);});Optional(s.SelectedIndex(),[](auto v){Out(std::uint32_t(v));});Out(std::uint32_t(s.GrindLockedToMiddle()));OptionalVector(s.GrindNormal());Out(std::uint32_t(s.Pass()));Out(std::uint32_t(s.AdjustedOnVert()));Out(std::uint32_t(s.Pending()));Out(std::uint32_t(s.Valid()));Out(std::uint32_t(s.JustChanged()));Out(std::uint32_t(s.AllPredictionsMissed()));OptionalVector(s.SuggestedNormal());}
WorldGeometry ReadWorld(){std::vector<WorldTriangle> triangles;QueryMetadata metadata;const auto n=Word();for(unsigned i=0;i<n;++i){std::array<Vec3,3> vertices;for(auto& v:vertices){const float x=Float(),y=Float(),z=Float();v={x,y,z};}const float fat=Float();const auto flags=Word(),tag=Word(),surface=Word();triangles.push_back({TriangleFromVolume(vertices,fat,{1,1,1},flags),{},tag});metadata.packed_surfaces.push_back(static_cast<std::uint16_t>(surface));}if(n)metadata.meshes.push_back({{0,n},{},{},{{-100,-100,-100},{100,100,100}},-1,0,0,QueryPool::Ground});const char* e=nullptr;auto w=WorldGeometry::WithQueryMetadata(std::move(triangles),std::move(metadata),e);if(!w)std::abort();return std::move(*w);}
std::vector<PlayerGrindPrimitive> ReadEdges(){std::vector<PlayerGrindPrimitive> e;const auto n=Word();for(unsigned i=0;i<n;++i){auto a=Vector(),b=Vector();const auto lo=Word(),hi=Word();e.push_back({a,b,std::uint64_t(lo)|(std::uint64_t(hi)<<32)});}return e;}
struct WorldQueries:AirTrajectoryWorldQueries{const WorldGeometry& world;explicit WorldQueries(const WorldGeometry& w):world(w){}bool Line(Vec4 a,Vec4 b,float r,std::optional<AirTrajectorySurfaceHit>& h,std::string& e)override{return AirTrajectoryWorldLine(world,a,b,r,h,e);}bool Nearby(Vec4 c,float r,std::vector<std::array<Vec4,3>>& t,std::string& e)override{return AirTrajectoryNearbyTriangles(world,c,r,t,e);}};
AirTrajectoryPrediction QueryPrediction(const WorldGeometry& world,AirTrajectoryQueryRequest q){WorldQueries queries(world);auto result=AirTrajectoryQueryResult::Miss();std::string e;const bool ok=QueryAirTrajectory(q,queries,result,e);Status(ok,e);Result(result);return {result,q};}
AirTrajectoryGrindAssistLimits ReadLimits(){AirTrajectoryGrindAssistLimits v;v.lock_distance=Float();v.max_speed_squared_ledge=Float();v.max_speed_squared_rail=Float();v.max_downward_speed=Float();for(auto& f:v.ledge_scalars)f=Float();v.tip_scalar=Float();v.maximum_adjust_angle=Float();for(auto& f:v.deck_dimensions)f=Float();return v;}
struct SurfaceQueries:PlayerGrindSurfaceQueries{const WorldGeometry& world;explicit SurfaceQueries(const WorldGeometry& w):world(w){}bool Query(std::size_t i,PlayerGrindProbe p,std::optional<PlayerGrindProbeHit>& h,std::string& e)override{return PlayerGrindSurfaceProbe(world,{17,0xffffffff},i,p,h,e);}};
struct Evaluator:AirTrajectorySelectionServices{
 const WorldGeometry& world;const std::vector<PlayerGrindPrimitive>& edges;AirTrajectoryGrindAssistLimits limits;PointGraph<8> height;Vec4 board,body;float padding,maximum,velocity_scalar,max_angle,score,penalty_domain,truck_distance;std::uint32_t failure=0,calls=0;std::vector<std::uint32_t> trace;
 Evaluator(const WorldGeometry& w,const std::vector<PlayerGrindPrimitive>& e):world(w),edges(e),limits(ReadLimits()),height(ReadGraph()),board(Vector()),body(Vector()),padding(Float()),maximum(Float()),velocity_scalar(Float()),max_angle(Float()),score(Float()),penalty_domain(Float()),truck_distance(Float()){}
 void Trace(std::uint32_t kind){trace.push_back(kind);}
 void CapturePrediction(const AirTrajectoryPrediction& p){const auto mark=output.size();Prediction(p);trace.insert(trace.end(),output.begin()+static_cast<std::ptrdiff_t>(mark),output.end());output.resize(mark);}
 bool EvaluateGrind(AirTrajectoryPrediction& p,bool middle,AirTrajectoryGrindEvaluation& result,std::string& error)override{
  ++calls;Trace(1);Trace(std::uint32_t(middle));CapturePrediction(p);
  if(failure==1||(failure==4&&calls==2)){error="Explicit grind producer failure";CapturePrediction(p);return false;}
  AirTrajectoryGrindEvaluation e{std::nullopt,0,1000,std::nullopt,penalty_domain};std::vector<std::size_t> indices(edges.size());std::iota(indices.begin(),indices.end(),0);indices=AirTrajectoryBoxFilter(indices,edges,board);std::vector<AirTrajectoryGrindCandidate> candidates;
  for(auto i:indices){const auto c=ConsiderAirTrajectoryGrindPrimitive(p,edges[i],i,padding);if(c){e.distance=VectorMin(e.distance,c->distance);candidates.push_back(*c);}}
  if(middle)while(const auto c=TakeBestAirTrajectoryGrind(candidates,limits.lock_distance,height)){
   const auto edge=edges[c->primitive];const PlayerGrindSurfaceInput query{edge.start,edge.end,c->point,std::nullopt,truck_distance};if(!PreparePlayerGrindSurface(query))continue;SurfaceQueries queries(world);PlayerGrindSurface surface{};if(!InvestigatePlayerGrindSurface(query,queries,surface,error)){CapturePrediction(p);return false;}
   GrindAirLandingOrientation orientation{};Vec4 support{};UpdatePlayerGrindLandingOrientation(&surface,board,c->point,support,orientation);
   const auto correction=AdmitAirTrajectoryGrindDisplacement(p,*c,edge,p.CollisionVelocity(),body,{orientation.kind,orientation.high_side},limits,e.effective_lock_distance);if(!correction)continue;
   const auto reference=p.request.trajectory.velocity;ApplyAirTrajectoryGrindTarget(p,*c,*correction,support,reference,maximum,velocity_scalar,max_angle);
   auto vertical=M::Cross(M::Cross(c->direction,M::Up),c->direction);if(vertical[1]<0)vertical=M::Scale(vertical,-1);vertical=M::Length(vertical)>M::Bits(0x358637bd)?M::Normalize(vertical):M::Up;
   e.target=AirTrajectoryGrindTarget{edge,c->primitive,0x40000000u|std::uint32_t(c->primitive),orientation,c->point,vertical};e.score=score;break;
  }
  CapturePrediction(p);if(failure==2){error="Explicit grind failure after prediction mutation";return false;}result=e;return true;
 }
 bool Line(Vec4 a,Vec4 b,float r,std::optional<AirTrajectorySurfaceHit>& h,std::string& e)override{Trace(2);const auto mark=output.size();Out(a);Out(b);Out(r);trace.insert(trace.end(),output.begin()+static_cast<std::ptrdiff_t>(mark),output.end());output.resize(mark);if(failure==3){e="Explicit wall line producer failure";return false;}return AirTrajectoryWorldLine(world,a,b,r,h,e);}
 void ObserveTrace(){Out(std::uint32_t(trace.size()));for(auto w:trace)Out(w);trace.clear();calls=0;}
};
AirTrajectorySelectorSettings Variant(AirTrajectorySelectorSettings s){const auto mode=Word();if(mode&1){s.minimum_trajectory_frames=0;s.minimum_valid_time=0;s.minimum_normal_delta_second_pass=0;}if(mode&2){s.vert_jump_align_max_ground_normal_y=2;s.vert_jump_align_min_direction_y=-2;s.vert_jump_align_factor=.5f;}if(mode&4){s.score_middle_bonus=0;s.wall_ride_minimum_height=0;s.wall_ride_angle_allow_landing=100;s.wall_ride_normal_dot_limit=1;}if(mode&8){s.minimum_trajectory_frames=100000;}return s;}
}
int main(int argc,char** argv){if(argc!=2)return 2;std::ifstream settings_file(argv[1],std::ios::binary);std::vector<std::uint8_t> settings_bytes(std::istreambuf_iterator<char>(settings_file),{});SettingsDatabase database;std::string error;if(!database.Load(settings_bytes,error))return 2;AirTrajectorySelectorSettings stock{};const bool loaded=LoadAirTrajectorySelectorSettings(database,stock,error);Status(loaded,error);if(loaded)Settings(stock);
 std::vector<unsigned char> bytes(std::istreambuf_iterator<char>(std::cin),{});if(bytes.size()%4)return 2;for(std::size_t at=0;at<bytes.size();at+=4)input.push_back(std::uint32_t(bytes[at])|(std::uint32_t(bytes[at+1])<<8)|(std::uint32_t(bytes[at+2])<<16)|(std::uint32_t(bytes[at+3])<<24));const auto count=Word();if(!loaded&&count!=0)return 2;
 for(unsigned index=0;index<count;++index){auto world=ReadWorld();auto edges=ReadEdges();const auto op=Word();const auto s=Variant(stock);Out(index);Out(op);const auto mark=output.size();Out(0u);
 if(op==0){auto info=ReadLaunch();const auto in=ReadSelectorInput();Out(std::uint32_t(AdjustAirTrajectoryLaunchVelocity(info,in,s)));LaunchInfo(info);Batch(BuildAirTrajectoryLaunchBatch(info,in,s));}
 else if(op==1){const auto takeoff=Vector();const auto n=Word();std::vector<std::size_t> indices;for(unsigned i=0;i<n;++i)indices.push_back(Word());const auto result=AirTrajectoryBoxFilter(indices,edges,takeoff);Out(std::uint32_t(result.size()));for(auto i:result)Out(std::uint32_t(i));}
 else if(op==2){const auto t=ReadTrajectory();const auto p=Vector(),n=Vector();OptionalFloat(AirTrajectoryDescendingPlaneTime(t,p,n));}
 else if(op==3){const auto p=QueryPrediction(world,ReadRequest());const float padding=Float(),difficulty=Float();const auto height=ReadGraph();std::vector<AirTrajectoryGrindCandidate> cs;for(std::size_t i=0;i<edges.size();++i){const auto c=ConsiderAirTrajectoryGrindPrimitive(p,edges[i],i,padding);Optional(c,[](auto v){GrindCandidate(v);});if(c)cs.push_back(*c);}Out(std::uint32_t(cs.size()));while(const auto c=TakeBestAirTrajectoryGrind(cs,difficulty,height))GrindCandidate(*c);Out(std::uint32_t(cs.size()));}
 else if(op==4){Evaluator services(world,edges);AirTrajectorySelector selector;const auto n=Word();Out(n);Observe(selector);for(unsigned i=0;i<n;++i){const auto command=Word();Out(command);error.clear();bool value=true,ok=true;if(command==0){const auto info=ReadLaunch();const auto in=ReadSelectorInput();ok=selector.Launch(info,in,s,value,error);}else if(command==1||command==5){const auto in=ReadSelectorInput();services.failure=Word();std::vector<AirTrajectoryQueryResult> results;for(const auto& request:selector.Requests()){WorldQueries q(world);auto result=AirTrajectoryQueryResult::Miss();std::string e;if(!QueryAirTrajectory(request,q,result,e))std::abort();results.push_back(result);}if(command==5)results.push_back(AirTrajectoryQueryResult::Miss());ok=selector.CompleteBatch(results,in,s,services,value,error);}else if(command==2)value=selector.UpdateWithoutCompletion();else if(command==3)selector.CancelPending();else if(command==4)selector.Reset();else std::abort();Status(ok,error);Out(std::uint32_t(value));Observe(selector);services.ObserveTrace();}}
 else if(op==5){auto info=ReadLaunch();const auto in=ReadSelectorInput();const auto pass=Word(),adjusted=Word();Evaluator services(world,edges);services.failure=Word();auto batch=BuildAirTrajectoryLaunchBatch(info,in,s);std::vector<AirTrajectoryCandidate> cs;for(auto request:batch.requests){const auto p=QueryPrediction(world,request);cs.push_back({p,{.137f,.317f,.731f,.517f},{.17f,.31f,.73f,.51f},{.73f,.13f,.17f,.31f},{.31f,.73f,.51f,.17f},.317f,.731f,true,std::nullopt});}bool missed=true;const bool ok=ScoreAirTrajectoryCandidates(cs.data(),cs.size(),static_cast<std::uint16_t>(pass),adjusted!=0,in,s,services,missed,error);Status(ok,error);Out(std::uint32_t(missed));Out(std::uint32_t(cs.size()));for(const auto& c:cs)Candidate(c);services.ObserveTrace();}
 else std::abort();output[mark]=std::uint32_t(output.size()-mark-1);
 }if(cursor!=input.size())return 2;for(auto w:output)for(unsigned n=0;n<4;++n)std::cout.put(static_cast<char>(w>>(8*n)));
}

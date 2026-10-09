#include "AirTrajectoryRuntime.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace {
std::vector<std::uint32_t> input, output;
std::size_t cursor = 0;
std::uint32_t Word() { if (cursor == input.size()) std::abort(); return input[cursor++]; }
float Float() { const auto w = Word(); float v; std::memcpy(&v, &w, 4); return v; }
Vec4 Vector() { Vec4 v; for (auto &x : v) x = Float(); return v; }
void Out(std::uint32_t w) { output.push_back(w); }
void Out(float f) { std::uint32_t w; std::memcpy(&w, &f, 4); Out(w); }
void Out(Vec4 v) { for (auto f : v) Out(f); }
void Out(const Mat4 &m) { for (auto v : m) Out(v); }
void Status(bool okay, const std::string &error) {
  Out(std::uint32_t(okay)); Out(std::uint32_t(error.size()));
  for (unsigned char c : error) Out(std::uint32_t(c));
}
template<class T> void Result(const T &v) {
  Out(v.contact_position); Out(v.contact_normal); Out(v.landing_normal);
  Out(v.contact_time); Out(v.contact_transform);
  Out(std::uint32_t(v.contact_frame)); Out(v.surface); Out(v.geometry);
}
void Hit(const std::optional<AirTrajectorySurfaceHit> &v) {
  Out(std::uint32_t(v.has_value()));
  if (v) { Out(v->position); Out(v->normal); Out(v->transform); Out(v->surface); Out(v->geometry); }
}
void Triangles(const std::vector<std::array<Vec4,3>> &v) {
  Out(std::uint32_t(v.size())); for (const auto &t : v) for (auto p : t) Out(p);
}
AirTrajectory Trajectory() { const auto p = Vector(), v = Vector(), a = Vector(); return {p,v,a,Float()}; }
AirTrajectoryQueryRequest Request() { auto t = Trajectory(); const float r = Float(), a = Float(), b = Float(); return {t,r,a,b}; }
WorldGeometry World() {
  std::vector<WorldTriangle> triangles; const auto count = Word();
  for (unsigned n=0;n<count;++n) {
    std::array<Vec3,3> vertices;
    for (auto &v : vertices) { const float x=Float(),y=Float(),z=Float(); v={x,y,z}; }
    const float fatness=Float(); const auto flags=Word(),tag=Word();
    triangles.push_back({TriangleFromVolume(vertices,fatness,{1,1,1},flags),{},tag});
  }
  return WorldGeometry(std::move(triangles));
}
struct Queries final : AirTrajectoryWorldQueries {
  const WorldGeometry &world;
  std::uint32_t failure;
  std::vector<std::uint32_t> trace;
  Queries(const WorldGeometry &w, std::uint32_t f):world(w),failure(f) {}
  void Add(Vec4 v) { for (float f : v) {std::uint32_t w; std::memcpy(&w,&f,4);trace.push_back(w);} }
  void Add(float f) {std::uint32_t w;std::memcpy(&w,&f,4);trace.push_back(w);}
  bool Line(Vec4 start,Vec4 end,float radius,std::optional<AirTrajectorySurfaceHit>&v,std::string&e) override {
    trace.push_back(1); Add(start);Add(end);Add(radius);
    if (failure==1) {e="Explicit line producer failure";return false;}
    return AirTrajectoryWorldLine(world,start,end,radius,v,e);
  }
  bool Nearby(Vec4 center,float radius,std::vector<std::array<Vec4,3>>&v,std::string&e) override {
    trace.push_back(2);Add(center);Add(radius);
    if (failure==2) {e="Explicit nearby producer failure";return false;}
    return AirTrajectoryNearbyTriangles(world,center,radius,v,e);
  }
};
} // namespace
int main() {
  std::vector<unsigned char> bytes(std::istreambuf_iterator<char>(std::cin),{});
  if (bytes.size()%4) return 2;
  for(std::size_t at=0;at<bytes.size();at+=4) input.push_back(std::uint32_t(bytes[at])|(std::uint32_t(bytes[at+1])<<8)|(std::uint32_t(bytes[at+2])<<16)|(std::uint32_t(bytes[at+3])<<24));
  const auto count=Word();
  for(unsigned index=0;index<count;++index) {
    auto world=World(); const auto op=Word(); Out(index);Out(op);const auto mark=output.size();Out(0u);std::string error;
    if(op==0||op==4) {
      const auto request=Request();const auto failure=Word();Queries queries(world,failure);auto result=AirTrajectoryQueryResult::Miss();result.contact_time=17;
      const bool okay=QueryAirTrajectory(request,queries,result,error);Status(okay,error);Result(result);Out(std::uint32_t(queries.trace.size()));for(auto w:queries.trace)Out(w);
    } else if(op==1) {
      const auto start=Vector(),end=Vector();const float radius=Float();std::optional<AirTrajectorySurfaceHit> hit;const bool okay=AirTrajectoryWorldLine(world,start,end,radius,hit,error);Status(okay,error);Hit(hit);
    } else if(op==2) {
      const auto center=Vector();const float radius=Float();std::vector<std::array<Vec4,3>> triangles;const bool okay=AirTrajectoryNearbyTriangles(world,center,radius,triangles,error);Status(okay,error);Triangles(triangles);
    } else if(op==3) {
      const auto trajectory=Trajectory();const float time=Float();Out(AirTrajectoryPositionAt(trajectory,time));Out(AirTrajectoryVelocityAt(trajectory,time));const auto apex=AirTrajectoryHighestPosition(trajectory);Out(apex.first);Out(apex.second);
    } else if(op==5) {
      const auto request=Request();auto result=AirTrajectoryQueryResult::Miss();result.contact_time=17;const bool okay=AirTrajectoryRuntime::Query(world,request,result,error);Status(okay,error);Result(result);
      AirTrajectoryRuntime runtime;PlantTrajectoryQueryResult plant{result.contact_position,result.contact_normal,result.landing_normal,result.contact_time,result.contact_transform,result.contact_frame,result.surface,result.geometry};
      const bool plant_okay=runtime.Query(world,request.trajectory,request.radius,request.start_error,request.end_error,plant,error);Status(plant_okay,error);Result(plant);
    } else std::abort();
    output[mark]=std::uint32_t(output.size()-mark-1);
  }
  if(cursor!=input.size())return 2;
  for(auto w:output)for(unsigned n=0;n<4;++n)std::cout.put(static_cast<char>(w>>(8*n)));
}

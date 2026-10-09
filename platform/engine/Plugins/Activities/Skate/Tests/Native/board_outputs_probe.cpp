#include "BoardGround.h"
#include "BoardMotionOutput.h"
#include "BoardProbes.h"
#include "BoardToolkit.h"
#include "DeckGeometry.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
using namespace atelier::skate;
namespace {
std::vector<std::uint32_t> out;
std::uint32_t Word(){char b[4];if(!std::cin.read(b,4))std::exit(2);return std::uint32_t(static_cast<unsigned char>(b[0]))|(std::uint32_t(static_cast<unsigned char>(b[1]))<<8)|(std::uint32_t(static_cast<unsigned char>(b[2]))<<16)|(std::uint32_t(static_cast<unsigned char>(b[3]))<<24);}
float Float(){const auto w=Word();float v;std::memcpy(&v,&w,4);return v;}
Vec3 Vector(){return {Float(),Float(),Float()};}
Vec4 Four(){return {Float(),Float(),Float(),Float()};}
Mat4 Matrix(){Mat4 m;for(auto& c:m)c=Four();return m;}
AffineTransform Transform(){Basis3 b;for(auto& c:b.columns)for(auto& v:c)v=Float();return {b,Vector()};}
void Out(std::uint32_t w){out.push_back(w);}
void Out(float v){std::uint32_t w;std::memcpy(&w,&v,4);Out(w);}
void Out(bool v){Out(std::uint32_t(v));}
void Out(Vec3 v){Out(v.x);Out(v.y);Out(v.z);}
template<class T,std::size_t N>void Out(const std::array<T,N>& a){for(const auto& v:a)Out(v);}
void State(const WheelLineState& w,const BoardGroundState& g){
 Out(w.normals);Out(w.distances);Out(w.physics_surfaces);Out(w.minimum_distance);
 for(const auto& c:g.parts){Out(c.in_contact);Out(c.normal);Out(c.point);Out(c.relative_velocity);}
 Out(g.previous_velocities);Out(g.accelerations);Out(g.closing_velocity);Out(g.maximum_closing_speed);Out(g.opposing_contact);Out(g.surface_twelve_height);Out(g.collision_flags);
 Out(g.overall_normal);Out(g.wheel_normal);Out(g.valid_wheel_normals);Out(std::uint32_t(g.part_contact_count));Out(std::uint32_t(g.wheel_contact_count));Out(g.time_without_wheel_contact);Out(g.wheel_angular_drag);
}
void State(const BoardProbeState& p){Out(p.start);Out(p.point);Out(p.normal);Out(p.surface_tag);Out(p.hit);}
void State(const BoardToolkit& t){Out(t.deck);Out(t.effective);Out(t.inverse_effective);Out(t.side);Out(t.up);Out(t.forward);Out(t.horizontal_forward);Out(t.transverse_up);Out(t.forward_velocity);Out(t.travel_direction);Out(t.filtered_normal);Out(t.absolute_speed);Out(t.control_sign);Out(t.total_mass);}
void Line(WheelLine line){Out(line.start);Out(line.end);}
}
int main(){
 const auto cases=Word();for(std::uint32_t c=0;c<cases;++c){const auto op=Word();Out(c);Out(op);const auto size=out.size();Out(0u);
 if(op==0){WheelLineState w;BoardGroundState g;
  if(Word()){for(auto& v:w.normals)v=Vector();for(auto& v:w.distances)v=Float();for(auto& v:w.physics_surfaces)v=Word();w.minimum_distance=Float();for(auto& v:g.previous_velocities)v=Vector();g.wheel_normal=Vector();g.collision_flags=Word();g.time_without_wheel_contact=Float();}
  const auto n=Word();Out(n);State(w,g);for(std::uint32_t j=0;j<n;++j){const auto command=Word();
   if(command==0){std::array<std::optional<WheelLineHit>,4> hits;for(auto& h:hits)if(Word()){const float fraction=Float();const auto normal=Vector();h=WheelLineHit{fraction,normal,Word()};}w.Publish(hits);}
   else if(command==1){std::vector<BoardContactReport> reports;const auto r=Word();for(std::uint32_t k=0;k<r;++k){BoardContactReport x{};x.part=static_cast<BoardBodyId>(Word());x.other=CollisionBody::StaticWorld();x.normal=Vector();x.position=Vector();x.relative_linear_velocity=Vector();x.other_surface=static_cast<std::uint16_t>(Word());reports.push_back(x);}const auto up=Vector();const auto angle=Float();const bool wipe=Word()!=0;g.Update(reports,w,up,angle,wipe);}
   else if(command==2){std::array<Vec3,7> velocities;for(auto& v:velocities)v=Vector();g.SampleAccelerations(velocities,Float());}
   else if(command==3)g.AdvanceContactTime(Float());else if(command==4)g=BoardGroundState{};else return 2;State(w,g);
  }
 }else if(op==1){BoardProbeState p;const auto n=Word();Out(n);State(p);for(std::uint32_t j=0;j<n;++j){switch(Word()){case 0:p.Start(Vector());break;case 1:{std::optional<BoardProbeHit> h;if(Word()){const auto point=Vector(),normal=Vector();h=BoardProbeHit{point,normal,Word()};}p.Publish(h);break;}case 2:p.Disable();break;default:return 2;}State(p);Line(DeckProbe(Vector()));const auto state=Word();const auto normal=Vector(),up=Vector(),deck=Vector();const auto line=WallProbe({state,normal,up,deck,Float()});Out(bool(line));if(line)Line(*line);}
 }else if(op==2){const auto matrix=Matrix();const auto n=Word();std::vector<float> masses;for(std::uint32_t j=0;j<n;++j)masses.push_back(Float());const auto flags=Word();const auto speed=Float();const auto normal=Four(),retained=Four();State(BoardToolkit::Calculate(matrix,masses,flags,speed,normal,retained));
 }else if(op==3){const auto authored=AuthoredBodyTransforms(AuthoredTransformInputs::Stock());const auto sim=SimulationStep::Fixed60Hz(0,.001f,{0,-9.81f,0});BoardRuntime b(DefaultSkateboardMassProperties(),authored,Transform(),sim,BoardMotion::Active);const auto n=Word();Out(n);for(std::uint32_t j=0;j<n;++j){b.SetTransform(Transform());b.BodiesMut()[6].rates.linear_velocity=Vector();b.BodiesMut()[6].rates.angular_velocity=Vector();const auto up=Vector();const auto flags=Word();const auto speed=Float();const auto normal=Four(),retained=Four();for(const auto line:WheelLines(b,up))Line(line);const auto m=BoardMotionOutput::FromBoard(b,up,flags);Out(m.angular_velocity);Out(m.linear_velocity);Out(m.ground_velocity);Out(m.speed);Out(m.ground_speed);Out(m.forward_speed);Out(m.effective_basis.columns);State(BoardToolkit::FromBoard(b,flags,speed,normal,retained));}
 }else return 2;out[size]=std::uint32_t(out.size()-size-1);}
 if(std::cin.peek()!=std::char_traits<char>::eof())return 2;for(auto w:out)for(unsigned i=0;i<4;++i)std::cout.put(char(w>>(8*i)));
}

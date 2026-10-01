// SPDX-License-Identifier: Apache-2.0
#include "ReckoningFrames.h"
#include "RidingAngles.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>
using namespace atelier::skate;
namespace {
std::vector<std::uint32_t> out;
std::uint32_t Word(){char b[4];if(!std::cin.read(b,4))std::exit(2);return std::uint32_t(static_cast<unsigned char>(b[0]))|(std::uint32_t(static_cast<unsigned char>(b[1]))<<8)|(std::uint32_t(static_cast<unsigned char>(b[2]))<<16)|(std::uint32_t(static_cast<unsigned char>(b[3]))<<24);}
float Float(){const auto w=Word();float v;std::memcpy(&v,&w,4);return v;}
Vec3 Three(){return {Float(),Float(),Float()};}
Vec4 Four(){return {Float(),Float(),Float(),Float()};}
Mat4 Matrix(){Mat4 m;for(auto& c:m)c=Four();return m;}
PointGraph<8> Curve(){PointGraph<8> c;for(auto& v:c.x)v=Float();for(auto& v:c.y)v=Float();return c;}
void Out(std::uint32_t w){out.push_back(w);}
void Out(float v){std::uint32_t w;std::memcpy(&w,&v,4);Out(w);}
template<class T,std::size_t N>void Out(const std::array<T,N>& a){for(const auto& v:a)Out(v);}
void State(const ReckoningFrames& r){Out(r.ground);Out(r.system);Out(r.unflipped);Out(r.inverse_system);Out(r.body_flip);Out(r.heading);Out(r.target_lean_angle);Out(r.lateral_tilt);}
}
int main(){const auto cases=Word();for(std::uint32_t c=0;c<cases;++c){const auto op=Word();Out(c);Out(op);const auto size=out.size();Out(0u);
 if(op==0){const auto a=Three(),b=Three(),axis=Three();Out(RidingSignedAngle(a,b,axis));}
 else if(op==1){ReckoningFrames r;if(Word()){r.ground=Matrix();r.system=Matrix();r.unflipped=Matrix();r.inverse_system=Matrix();r.body_flip=Matrix();r.heading=Four();r.target_lean_angle=Float();r.lateral_tilt=Four();}
  const auto angle_curve=Curve(),up_curve=Curve();const auto n=Word();Out(n);State(r);
  for(std::uint32_t j=0;j<n;++j){switch(Word()){case 0:{const auto up=Four(),normal=Four();r.CalculateTransform(up,normal);break;}case 1:{const auto up=Four(),dynamic_up=Four();r.CalculateDynamicLean(up,dynamic_up);break;}case 2:r.CalculateTilt(Word()!=0,angle_curve,up_curve);break;case 3:r.body_flip=Matrix();break;case 4:r.ground[3]=Four();break;case 5:r.system[3]=Four();break;case 6:r=ReckoningFrames{};break;default:return 2;}State(r);}
 }else return 2;out[size]=std::uint32_t(out.size()-size-1);}
 if(std::cin.peek()!=std::char_traits<char>::eof())return 2;for(auto w:out)for(unsigned i=0;i<4;++i)std::cout.put(char(w>>(8*i)));
}

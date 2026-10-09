#include "DriveFrames.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
using namespace atelier::skate;
namespace
{
std::uint32_t Word(){char b[4];if(!std::cin.read(b,4))std::exit(2);return std::uint32_t(static_cast<unsigned char>(b[0]))|(std::uint32_t(static_cast<unsigned char>(b[1]))<<8)|(std::uint32_t(static_cast<unsigned char>(b[2]))<<16)|(std::uint32_t(static_cast<unsigned char>(b[3]))<<24);}
float Float(){const auto w=Word();float v;std::memcpy(&v,&w,4);return v;}
Vec3 Vector(){const float x=Float(),y=Float(),z=Float();return {x,y,z};}
Basis3 Basis(){Basis3 b;for(auto& c:b.columns)for(auto& v:c)v=Float();return b;}
AffineTransform Frame(){const auto b=Basis();return {b,Vector()};}
void Out(std::uint32_t w){const char b[4]={char(w),char(w>>8),char(w>>16),char(w>>24)};std::cout.write(b,4);}
void Out(float v){std::uint32_t w;std::memcpy(&w,&v,4);Out(w);}
template<class T,std::size_t N>void Out(const std::array<T,N>& values){for(const auto& v:values)Out(v);}
void Out(Vec3 v){Out(v.x);Out(v.y);Out(v.z);}
void Out(AffineTransform f){Out(f.basis.columns);Out(f.translation);}
void Out(DriveFrames d){for(const auto& f:{d.body_a,d.body_b}){Out(f.orientation);Out(f.translation);}const auto raw=PackDriveFrames(d);for(const auto& f:{raw.body_a,raw.body_b}){Out(f.quaternion_lanes);Out(f.translation_lanes);}}
}
int main()
{
    const auto count=Word();for(std::uint32_t n=0;n<count;++n)
    {
        const auto op=Word();
        if(op==0)
        {
            const bool stock=Word()!=0;AuthoredTransformInputs a{Float(),Float(),Float(),Float(),Float()};TruckTransformInputs t{Float(),Float(),Float(),Float(),Float()};
            if(stock){a=AuthoredTransformInputs::Stock();t=TruckTransformInputs::Stock();}
            for(const auto& f:AuthoredBodyTransforms(a))Out(f);Out(AuthoredBodyPoseRecords(a));const auto trucks=CalculateTruckTransforms(t);
            for(const auto& f:trucks)Out(f);for(const auto& f:trucks)Out(SetDriveFrames2({},f));
        }
        else if(op==1){const auto parent=Frame();const auto child=Frame();Out(SetDriveFrames2(parent,child));}
        else if(op==2)Out(QuaternionFromBasis(Basis()));
        else if(op==3){for(const auto& f:DefaultLiveBodyTransforms())Out(f);for(const auto& q:DefaultLiveBodyOrientations())Out(q);for(const auto& d:DefaultTruckDriveFrames())Out(d);for(const auto& d:DefaultWheelDriveFrames())Out(d);}
        else return 2;
    }
    return std::cin.peek()==std::char_traits<char>::eof()?0:2;
}

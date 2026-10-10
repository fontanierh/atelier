#include "DeckAngularCorrections.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>
using namespace atelier::skate;
namespace
{
std::vector<std::uint32_t> out;
std::uint32_t Word(){char b[4];if(!std::cin.read(b,4))std::exit(2);return std::uint32_t(static_cast<unsigned char>(b[0]))|(std::uint32_t(static_cast<unsigned char>(b[1]))<<8)|(std::uint32_t(static_cast<unsigned char>(b[2]))<<16)|(std::uint32_t(static_cast<unsigned char>(b[3]))<<24);}
float Float(){auto w=Word();float x;std::memcpy(&x,&w,4);return x;}
Vec3 Vector(){return {Float(),Float(),Float()};}
Basis3 Basis(){Basis3 b;for(auto& c:b.columns)for(auto& x:c)x=Float();return b;}
BodyRates Body(){BodyRates b;for(auto& x:b.orientation)x=Float();b.basis=Basis();b.world_inverse_inertia=Basis();b.position=Vector();b.linear_velocity=Vector();b.angular_velocity=Vector();b.force_acceleration=Vector();b.torque_acceleration=Vector();b.kinetic_energy=Float();b.cool_down=Word();return b;}
void Out(std::uint32_t w){out.push_back(w);}
void Out(float x){std::uint32_t w;std::memcpy(&w,&x,4);Out(w);}
void Out(Vec3 v){Out(v.x);Out(v.y);Out(v.z);}
void Out(Basis3 b){for(auto c:b.columns)for(auto x:c)Out(x);}
void Out(BodyRates b){for(auto x:b.orientation)Out(x);Out(b.basis);Out(b.world_inverse_inertia);Out(b.position);Out(b.linear_velocity);Out(b.angular_velocity);Out(b.force_acceleration);Out(b.torque_acceleration);Out(b.kinetic_energy);Out(b.cool_down);}
}
int main()
{
    const auto count=Word();for(std::uint32_t index=0;index<count;++index)
    {
        auto b=Body();const auto n=Word();Out(index);Out(n);const auto mark=out.size();Out(0u);const auto start=out.size();Out(b);
        for(std::uint32_t j=0;j<n;++j)
        {
            const auto op=Word();Out(op);switch(op)
            {
            case 0:ApplyDeckAxisDisplacement(b,Vector());break;case 1:ApplyDeckLimitedDisplacement(b,Vector());break;
            case 2:ApplyDeckAngularDisplacement(b,Vector());break;case 3:ApplyGroundBodyTorque(b);break;
            case 4:b.angular_velocity=Vector();break;case 5:b.torque_acceleration=Vector();b.cool_down=Word();break;
            case 6:b.world_inverse_inertia=Basis();break;case 7:b.basis=Basis();break;default:return 2;
            }Out(b);
        }out[mark]=static_cast<std::uint32_t>(out.size()-start);
    }
    if(std::cin.peek()!=std::char_traits<char>::eof())return 2;
    for(auto w:out){const char b[4]={char(w),char(w>>8),char(w>>16),char(w>>24)};std::cout.write(b,4);}
}

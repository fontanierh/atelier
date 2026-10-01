// SPDX-License-Identifier: Apache-2.0
#include "RevertRuntime.h"
#include "RidingAngles.h"
#include "StockSettingsReader.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
Vec3 Xyz(Vec4 v) {return {v[0],v[1],v[2]};}
float Dot(Vec4 a,Vec4 b) {return std::fma(a[2],b[2],std::fma(a[1],b[1],a[0]*b[0]));}
}
bool RevertRuntime::Load(const SettingsDatabase& data,std::string& error)
{
    constexpr std::string_view category="Hash_018E8A2E5028AB3F";
    StockSettingsReader reader(data);std::vector<std::uint32_t> a,b;
    if(!reader.Words(category,"default","Hash_DAA990E803A782A1",20,a,error)
        ||!reader.Words(category,"default","Hash_3387562E9BEA0AF6",12,b,error))return false;
    RevertRuntime value;
    for(std::size_t i=0;i<8;++i){value.speed.x[i]=Float(a[4+i]);value.speed.y[i]=Float(a[12+i]);}
    for(std::size_t i=0;i<4;++i){value.tolerance.x[i]=Float(b[4+i]);value.tolerance.y[i]=Float(b[8+i]);}
    if(!reader.Float(category,"default","Hash_0E5B939FD4ECDBAA",value.gain,error)
        ||!reader.Float(category,"default","Hash_6BF6544475D2A5AD",value.delay,error)
        ||!reader.Float(category,"default","Hash_035D9805EB9E2EE2",value.duration,error))return false;
    *this=std::move(value);return true;
}
Vec4 RevertRuntime::Correction(Vec4 forward,Vec4 normal,Vec4 angular)
{
    if(!captured)return {};
    Vec4 desired;for(std::size_t i=0;i<4;++i)desired[i]=forward[i]*travel_sign;
    // Preserve the original self-scaled projections, including the fourth
    // lane. These are deliberately not conventional plane projections.
    const auto project=[&](Vec4 v){const auto d=Dot(v,normal);for(auto& x:v)x=x-x*d;return v;};
    const auto from=project(velocity),to=project(desired);
    if(Dot(from,from)*Dot(to,to)<=Float(0x37800000))return {};
    const auto normalize=[](Vec4 v){const auto length=std::sqrt(Dot(v,v));for(auto& x:v)x=x/length;return v;};
    auto angle=RidingSignedAngle(Xyz(normalize(from)),Xyz(normalize(to)),Xyz(normal));
    if(angle>=Float(0x40490fdb))angle-=Float(0x40c90fdb);
    if(angle*direction>0)angle-=direction*Float(0x40c90fdb);
    const auto target=speed.Evaluate(std::fabs(angle))*direction;
    if(std::fabs(angle)<tolerance.Evaluate(normal[1])*Float(0x3c8efa35)||std::fabs(angle)>4.5f)active=false;
    const auto current=Dot(angular,normal);
    const auto correction=current*target>0&&std::fabs(current)>std::fabs(target)?0.0f:(target-current)*gain;
    for(auto& component:normal)component=component*correction;
    return normal;
}
}

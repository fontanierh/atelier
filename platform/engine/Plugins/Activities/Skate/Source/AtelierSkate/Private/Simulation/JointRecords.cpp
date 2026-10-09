#include "JointRecords.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
float Float(std::uint32_t w){float f;std::memcpy(&f,&w,4);return f;}
std::uint32_t Word(float f){std::uint32_t w;std::memcpy(&w,&f,4);return w;}
std::array<std::uint32_t,20> Frames(DriveFrames frames,Quat linear_b)
{
    const auto raw=PackDriveFrames(frames);std::array<std::uint32_t,20> words{};
    for(std::size_t i=0;i<4;++i)
    {
        words[i]=raw.body_a.quaternion_lanes[i];words[4+i]=raw.body_a.translation_lanes[i];
        words[8+i]=raw.body_b.quaternion_lanes[i];words[12+i]=raw.body_b.translation_lanes[i];words[16+i]=Word(linear_b[i]);
    }
    return words;
}
}
JointSettings JointSettings::Stock(){return {Float(0x42ac3333),Float(0x41600000),Float(0x49742400)};}
std::array<JointRecord,6> JointRecords(JointSettings s)
{
    const float radians=Float(0x3c8efa35),frequency=Float(0x426fffff);
    const float angle=s.truck_twist_angle_degrees*radians;
    std::array<std::uint32_t,16> truck{},wheel{};
    truck[8]=Word((s.truck_twist_limit_degrees*radians)*frequency);truck[11]=Word(angle);
    truck[12]=Word(1.0f);truck[13]=Word(SinCos(angle).second);truck[14]=0;truck[15]=1;
    wheel[9]=Word((s.wheel_swing_limit_degrees*radians)*frequency);wheel[12]=Word(1.0f);wheel[13]=Word(1.0f);wheel[14]=3;
    const auto trucks=DefaultTruckDriveFrames();const auto trig=SinCos(Float(0x3fc90fdb));
    const auto q=QuaternionFromBasis({{{{1,0,0},{0,trig.second,trig.first},{0,-trig.first,trig.second}}}});
    const float offset=AuthoredTransformInputs::Stock().wheel_x_distance;
    const auto positive=Frames({{q,{}},{q,{0,0,offset}}},q),negative=Frames({{q,{}},{q,{0,0,-offset}}},q);
    using B=BoardBodyId;
    return {{{B::Deck,B::FrontTruck,truck,Frames(trucks[0],trucks[0].body_b.orientation)},
        {B::Deck,B::BackTruck,truck,Frames(trucks[1],trucks[1].body_b.orientation)},
        {B::FrontTruck,B::RightFrontWheel,wheel,positive},{B::FrontTruck,B::LeftFrontWheel,wheel,negative},
        {B::BackTruck,B::RightBackWheel,wheel,positive},{B::BackTruck,B::LeftBackWheel,wheel,negative}}};
}
std::array<JointRecord,6> DefaultJointRecords(){return JointRecords(JointSettings::Stock());}
}

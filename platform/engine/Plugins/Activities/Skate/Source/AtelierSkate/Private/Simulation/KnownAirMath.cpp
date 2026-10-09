#include "KnownAirPrivate.h"
#include "RidingAngles.h"
#include <cstring>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::known_air
{
float Bits(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
float Select(float test,float nonnegative,float negative){return test>=0?nonnegative:negative;}
Vec4 Add(Vec4 a,Vec4 b){for (std::size_t i=0;i<4;++i) a[i]+=b[i];return a;}
Vec4 Sub(Vec4 a,Vec4 b){for (std::size_t i=0;i<4;++i) a[i]-=b[i];return a;}
Vec4 Scale(Vec4 a,float scalar){for (auto& value:a) value*=scalar;return a;}
Vec4 Cross(Vec4 a,Vec4 b)
{return {std::fma(-a[2],b[1],a[1]*b[2]),std::fma(-a[0],b[2],a[2]*b[0]),std::fma(-a[1],b[0],a[0]*b[1]),std::fma(-a[3],b[3],a[3]*b[3])};}
std::pair<Vec4,float> Normalize(Vec4 v)
{
    const auto square=Dot3(v,v);const auto inverse=InverseLengthSquared(square,2);const auto length=square==0?0:square*inverse;
    return {length>Bits(0x358637bd)?Scale(v,inverse):Vec4{},length};
}
Vec4 Rotate(const Mat4& matrix,Vec4 v)
{
    Vec4 out{};for (std::size_t i=0;i<4;++i) out[i]=std::fma(matrix[2][i],v[2],std::fma(matrix[1][i],v[1],matrix[0][i]*v[0]));return out;
}
Vec4 TransformPoint(const Mat4& matrix,Vec4 v)
{
    Vec4 out{};for (std::size_t i=0;i<4;++i) out[i]=std::fma(matrix[2][i],v[2],std::fma(matrix[1][i],v[1],std::fma(matrix[0][i],v[0],matrix[3][i])));return out;
}
float Signed(Vec4 a,Vec4 b,Vec4 axis)
{
    if (!(Dot3(a,a)*Dot3(b,b)>Bits(0x37800000))) return 0;
    a=Sub(a,Scale(axis,Dot3(axis,a)));b=Sub(b,Scale(axis,Dot3(axis,b)));
    return RidingSignedAngle({a[0],a[1],a[2]},{b[0],b[1],b[2]},{axis[0],axis[1],axis[2]});
}
float Wrap(float angle)
{
    const auto pi=Bits(0x40490fdb),tau=Bits(0x40c90fdb);
    if (angle<-pi||!(angle<pi))
    {
        const auto value=angle*Bits(0x3e22f983);std::int32_t n;
        if (std::isnan(value)) n=0;
        else if (value>=2147483648.0f) n=std::numeric_limits<std::int32_t>::max();
        else if (value<=-2147483648.0f) n=std::numeric_limits<std::int32_t>::min();
        else n=static_cast<std::int32_t>(value);
        angle=std::fma(-static_cast<float>(n),tau,angle);
        if (!(angle<pi)) angle-=tau;else if (angle<-pi) angle+=tau;
    }
    return angle;
}
RestoreVelocityGeometry RestoreGeometry(Vec4 v,Vec4 normal)
{
    const auto tangent=Sub(v,Scale(normal,Dot3(normal,v)));const auto downhill=Cross(normal,Cross(normal,{0,1,0,0}));
    return {tangent,normal[1],Dot3(Normalize(downhill).first,Normalize(tangent).first)};
}
KnownAirTrajectory Trajectory(AirTrajectory t)
{
    std::uint32_t word;std::memcpy(&word,&t.scalar_48,4);return {t.position,t.velocity,t.acceleration,t.scalar_48,word,word,word};
}
AirTrajectory Actual(const KnownAirTrajectory& t){return {t.position,t.velocity,t.acceleration,t.scalar_48};}
Vec4 Position(const KnownAirTrajectory& t,float time)
{
    const auto square=time*time;Vec4 out{};
    for (std::size_t i=0;i<4;++i) {const auto linear=std::fma(t.velocity[i],time,t.position[i]);const auto half=t.acceleration[i]*0.5f;out[i]=std::fma(half,square,linear);}return out;
}
Vec4 Velocity(const KnownAirTrajectory& t,float time)
{Vec4 out{};for (std::size_t i=0;i<4;++i) out[i]=std::fma(t.acceleration[i],time,t.velocity[i]);return out;}
std::int32_t WrappingAdd(std::int32_t value,std::uint32_t increment)
{std::uint32_t word;std::memcpy(&word,&value,4);word+=increment;std::memcpy(&value,&word,4);return value;}
}

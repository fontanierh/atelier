#include "RigidBody.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#pragma clang fp contract(off)

namespace atelier::skate
{
namespace
{
float FromBits(std::uint32_t bits) { float value; std::memcpy(&value,&bits,4); return value; }
std::uint32_t Bits(float value) { std::uint32_t bits; std::memcpy(&bits,&value,4); return bits; }
Vec4 Splat(float value) { return {value,value,value,value}; }
Vec4 Load(const std::uint32_t* words) { return {FromBits(words[0]),FromBits(words[1]),FromBits(words[2]),FromBits(words[3])}; }
void StoreXYZ(std::uint32_t* words,const Vec4& value) { for (unsigned i=0;i<3;++i) words[i]=Bits(value[i]); }
Vec4 Perm(const Vec4& value,std::array<unsigned,4> indices)
{ return {value[indices[0]],value[indices[1]],value[indices[2]],value[indices[3]]}; }
Vec4 Mul(const Vec4& a,const Vec4& b) { Vec4 v; for (unsigned i=0;i<4;++i) v[i]=a[i]*b[i]; return v; }
Vec4 Add(const Vec4& a,const Vec4& b) { Vec4 v; for (unsigned i=0;i<4;++i) v[i]=a[i]+b[i]; return v; }
Vec4 Sub(const Vec4& a,const Vec4& b) { Vec4 v; for (unsigned i=0;i<4;++i) v[i]=a[i]-b[i]; return v; }
Vec4 Madd(const Vec4& a,const Vec4& b,const Vec4& c)
{ Vec4 v; for (unsigned i=0;i<4;++i) v[i]=std::fma(a[i],b[i],c[i]); return v; }
Vec4 Nmsub(const Vec4& a,const Vec4& b,const Vec4& c)
{ Vec4 v; for (unsigned i=0;i<4;++i) v[i]=std::fma(-a[i],b[i],c[i]); return v; }
float RefinedRsqrt(float value)
{
    float estimate=ReciprocalSquareRootEstimate(value);
    for (unsigned i=0;i<2;++i)
    {
        const float square=estimate*estimate;
        const float half_estimate=estimate*0.5f;
        const float residual=std::fma(-value,square,1.0f);
        estimate=std::fma(half_estimate,residual,estimate);
    }
    return estimate;
}
Vec4 Orientation(const Vec4& q,const Vec4& rotation)
{
    const auto cross=Perm(Nmsub(Perm(rotation,{1,2,0,3}),q,Mul(rotation,Perm(q,{1,2,0,3}))),{1,2,0,3});
    auto increment=Mul(Madd(rotation,Splat(q[3]),cross),Splat(0.5f));
    increment[3]=Dot3(rotation,q)*-0.5f;
    const auto candidate=Add(q,increment);
    return Mul(candidate,Splat(RefinedRsqrt(Dot4(candidate,candidate))));
}
std::array<Vec4,3> QuaternionBasis(const Vec4& q)
{
    const auto s=Mul(q,Splat(FromBits(0x3fb504f3)));
    const auto d=Nmsub(s,s,Splat(0.5f));
    const auto diagonal=Add(d,Perm(d,{1,2,0,0}));
    const auto products=Mul(s,Perm(s,{1,2,0,0}));
    const auto w_products=Mul(Splat(s[3]),Perm(s,{2,0,1,0}));
    const auto plus=Add(products,w_products),minus=Sub(products,w_products);
    return {{{diagonal[1],plus[0],minus[2],0}, {minus[0],diagonal[2],plus[1],0}, {plus[2],minus[1],diagonal[0],0}}};
}
std::pair<Vec4,Vec4> InverseInertia(const std::array<Vec4,3>& basis,const std::array<std::uint32_t,3>& tensor)
{
    const auto& ri=basis[0]; const auto& up=basis[1]; const auto& at=basis[2];
    const auto r=Mul(ri,Splat(FromBits(tensor[0]))),u=Mul(up,Splat(FromBits(tensor[1]))),a=Mul(at,Splat(FromBits(tensor[2])));
    const auto full=Madd(a,Splat(at[0]),Madd(r,Splat(ri[0]),Mul(u,Splat(up[0]))));
    const auto p=[](const Vec4& v){return Perm(v,{2,1,1,3});};
    const auto s=[](const Vec4& v){return Perm(v,{2,1,2,3});};
    return {full,Madd(p(at),s(a),Madd(p(ri),s(r),Mul(p(up),s(u))))};
}
std::pair<Vec4,float> Cap(const Vec4& value,float maximum)
{
    const float squared=Dot3(value,value),maximum_squared=maximum*maximum;
    if (squared>maximum_squared)
    {
        const float ratio=maximum_squared/squared;
        const float root=ratio*RefinedRsqrt(ratio);
        const float scale=ratio==0.0f ? 0.0f : root;
        return {Mul(value,Splat(scale)),maximum_squared};
    }
    return {value,squared};
}
Basis3 Unpack(Vec3 full,Vec3 split)
{ Basis3 result; result.columns={{{full.x,full.y,full.z},{full.y,split.y,split.z},{full.z,split.z,split.x}}};return result; }
Vec3 MultiplyBasis(Basis3 basis,Vec3 v)
{
    const auto lane=[&](unsigned i){return std::fma(basis.columns[2][i],v.z,std::fma(basis.columns[1][i],v.y,basis.columns[0][i]*v.x));};
    return {lane(0),lane(1),lane(2)};
}
}
SimulationStep SimulationStep::Fixed60Hz(std::uint32_t cool_down,float minimum_energy,Vec3 gravity)
{
    const float time_step=FromBits(0x3c888889);
    return {time_step,1.0f/time_step,cool_down,minimum_energy,gravity};
}
DynamicUpdateResult DynamicUpdatePacked(std::array<std::uint32_t,44>& body,
    const std::array<std::uint32_t,10>& inertia,SimulationStep simulation,std::array<std::uint32_t,16>& reactions)
{
    const auto dt=Splat(simulation.time_step);
    const auto linear=Madd(Madd(Load(body.data()+36),dt,Load(body.data()+8)),dt,Load(reactions.data()));
    const auto angular=Madd(Madd(Load(body.data()+40),dt,Load(body.data()+12)),dt,Load(reactions.data()+8));
    StoreXYZ(body.data()+4,Add(Add(Load(body.data()+4),Load(reactions.data()+4)),linear));
    const auto rotation=Add(angular,Load(reactions.data()+12));
    const auto q=Orientation(Load(body.data()),rotation);
    for (unsigned i=0;i<4;++i) body[i]=Bits(q[i]);
    const auto basis=QuaternionBasis(q);
    for (unsigned i=0;i<3;++i) StoreXYZ(body.data()+16+i*4,basis[i]);
    const auto tensor=InverseInertia(basis,{inertia[0],inertia[1],inertia[2]});
    StoreXYZ(body.data()+28,tensor.first); StoreXYZ(body.data()+32,tensor.second);
    const auto rate=[&](std::uint32_t drag){const float difference=simulation.frequency-FromBits(drag);return difference>0.0f?difference:0.0f;};
    const auto omega=Cap(Mul(angular,Splat(rate(inertia[9]))),FromBits(inertia[7]));
    const auto velocity=Cap(Mul(linear,Splat(rate(inertia[8]))),FromBits(inertia[6]));
    const float factor=FromBits(inertia[5])*FromBits(body[31]);
    const float energy=std::fma(factor,omega.second,velocity.second);
    // Unordered comparisons and wrapping cooldown arithmetic are intentional.
    if (!(energy<simulation.minimum_energy)) body[43]=0;
    else
    {
        const auto cooldown=!(energy>FromBits(body[39])) ? body[43]+std::uint32_t(1) : body[43];
        body[43]=std::min(cooldown,simulation.cool_down);
    }
    body[39]=Bits(energy);
    StoreXYZ(body.data()+8,velocity.first); StoreXYZ(body.data()+12,omega.first);
    reactions.fill(0);
    const auto gravity=simulation.gravity_acceleration;
    StoreXYZ(body.data()+36,{gravity.x,gravity.y,gravity.z,0});
    StoreXYZ(body.data()+40,{0,0,0,0});
    return {{rotation[0],rotation[1],rotation[2]},velocity.second,omega.second};
}
BodyRateStep IntegrateBodyRates(BodyRates body,InertiaDynamics inertia,SimulationStep simulation,ReactionCorrections reactions)
{
    std::array<std::uint32_t,44> words{};
    for (unsigned i=0;i<4;++i) words[i]=Bits(body.orientation[i]);
    const auto store=[&](unsigned offset,Vec3 v){StoreXYZ(words.data()+offset,{v.x,v.y,v.z,0});};
    store(4,body.position);store(8,body.linear_velocity);store(12,body.angular_velocity);
    store(36,body.force_acceleration);store(40,body.torque_acceleration);
    words[31]=Bits(inertia.inverse_mass);words[39]=Bits(body.kinetic_energy);words[43]=body.cool_down;
    const std::array<std::uint32_t,10> native_inertia{Bits(inertia.inverse_tensor.x),Bits(inertia.inverse_tensor.y),Bits(inertia.inverse_tensor.z),0,
        Bits(inertia.inverse_mass),Bits(inertia.spherical),Bits(inertia.maximum_linear_velocity),Bits(inertia.maximum_angular_velocity),Bits(inertia.linear_drag),Bits(inertia.angular_drag)};
    std::array<std::uint32_t,16> corrections{};
    const std::array<Vec3,4> values{reactions.linear_displacement,reactions.position_displacement,reactions.angular_displacement,reactions.orientation_displacement};
    for (unsigned i=0;i<4;++i) StoreXYZ(corrections.data()+i*4,{values[i].x,values[i].y,values[i].z,0});
    const auto result=DynamicUpdatePacked(words,native_inertia,simulation,corrections);
    const auto vector=[&](unsigned offset){return Vec3{FromBits(words[offset]),FromBits(words[offset+1]),FromBits(words[offset+2])};};
    for (unsigned i=0;i<4;++i) body.orientation[i]=FromBits(words[i]);
    body.position=vector(4);body.linear_velocity=vector(8);body.angular_velocity=vector(12);
    body.force_acceleration=vector(36);body.torque_acceleration=vector(40);body.kinetic_energy=FromBits(words[39]);body.cool_down=words[43];
    for (unsigned i=0;i<3;++i) for (unsigned j=0;j<3;++j) body.basis.columns[i][j]=FromBits(words[16+i*4+j]);
    body.world_inverse_inertia=Unpack(vector(28),vector(32));
    return {body,{result.orientation_displacement[0],result.orientation_displacement[1],result.orientation_displacement[2]},result.linear_speed_squared,result.angular_speed_squared};
}
Quat IntegrateOrientation(Quat orientation,Vec3 displacement)
{ return Orientation(orientation,{displacement.x,displacement.y,displacement.z,0}); }
Basis3 BasisFromQuaternion(Quat orientation)
{
    const auto columns=QuaternionBasis(orientation);Basis3 result{};
    for (unsigned i=0;i<3;++i) for (unsigned j=0;j<3;++j) result.columns[i][j]=columns[i][j];
    return result;
}
Basis3 WorldInverseInertia(Basis3 basis,Vec3 tensor)
{
    std::array<Vec4,3> columns{};
    for (unsigned i=0;i<3;++i) for (unsigned j=0;j<3;++j) columns[i][j]=basis.columns[i][j];
    const auto values=InverseInertia(columns,{Bits(tensor.x),Bits(tensor.y),Bits(tensor.z)});
    return Unpack({values.first[0],values.first[1],values.first[2]},{values.second[0],values.second[1],values.second[2]});
}
PackedWorldInverseInertia PackWorldInverseInertia(Basis3 tensor)
{
    return {{tensor.columns[0][0],tensor.columns[1][0],tensor.columns[2][0]},
            {tensor.columns[2][2],tensor.columns[1][1],tensor.columns[2][1]}};
}
Vec3 MultiplyPackedWorldInverseInertia(PackedWorldInverseInertia tensor,Vec3 vector)
{
    return {tensor.full.x*vector.x+tensor.full.y*vector.y+tensor.full.z*vector.z,
            tensor.full.y*vector.x+tensor.split.y*vector.y+tensor.split.z*vector.z,
            tensor.full.z*vector.x+tensor.split.z*vector.y+tensor.split.x*vector.z};
}
ForceAccumulator AccumulatePointForce(ForceAccumulator accumulator,Vec3 force,Vec3 point,Basis3 deck,float inverse_mass,Basis3 inertia)
{
    accumulator.force_acceleration.x+=force.x*inverse_mass;
    accumulator.force_acceleration.y+=force.y*inverse_mass;
    accumulator.force_acceleration.z+=force.z*inverse_mass;
    const auto arm=MultiplyBasis(deck,point);
    const Vec3 torque{std::fma(-arm.z,force.y,arm.y*force.z),std::fma(-arm.x,force.z,arm.z*force.x),std::fma(-arm.y,force.x,arm.x*force.y)};
    const auto angular=MultiplyBasis(inertia,torque);
    accumulator.torque_acceleration.x+=angular.x;accumulator.torque_acceleration.y+=angular.y;accumulator.torque_acceleration.z+=angular.z;
    accumulator.cool_down=0;return accumulator;
}
}

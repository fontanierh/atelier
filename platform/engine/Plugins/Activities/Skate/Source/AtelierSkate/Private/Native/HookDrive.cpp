// SPDX-License-Identifier: Apache-2.0
#include "HookDrive.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Scalar(std::uint32_t bits) {float v;std::memcpy(&v,&bits,4);return v;}
std::uint32_t Word(float v) {std::uint32_t bits;std::memcpy(&bits,&v,4);return bits;}
Vec4 Add(Vec4 a,Vec4 b) {return {a[0]+b[0],a[1]+b[1],a[2]+b[2],a[3]+b[3]};}
Vec4 Sub(Vec4 a,Vec4 b) {return {a[0]-b[0],a[1]-b[1],a[2]-b[2],a[3]-b[3]};}
Vec4 Mul(Vec4 a,Vec4 b) {return {a[0]*b[0],a[1]*b[1],a[2]*b[2],a[3]*b[3]};}
std::array<std::uint32_t,4> Convert(const std::array<std::uint32_t,12>& basis)
{
    const Vec4 ri={Scalar(basis[0]),Scalar(basis[1]),Scalar(basis[2]),Scalar(basis[3])};
    const Vec4 up={Scalar(basis[4]),Scalar(basis[5]),Scalar(basis[6]),Scalar(basis[7])};
    const Vec4 at={Scalar(basis[8]),Scalar(basis[9]),Scalar(basis[10]),Scalar(basis[11])};
    const Vec4 rx={ri[0],ri[0],-ri[0],-ri[0]},uy={up[1],-up[1],up[1],-up[1]},az={at[2],-at[2],-at[2],at[2]};
    const Vec4 first=Add(rx,uy),d=Add(first,Add(az,{1,1,1,1}));Vec4 inverse;
    for (unsigned i=0;i<4;++i) inverse[i]=InverseLengthSquared(d[i],2);
    const Vec4 roots=Mul(d,inverse),halves=Mul({.5f,.5f,.5f,.5f},inverse),a={up[2],at[0],ri[1],.5f},b={at[1],ri[2],up[0],0};
    const Vec4 minus=Sub(a,b),plus=Add(a,b);
    const Vec4 y=Mul({plus[2],minus[3],plus[0],minus[1]},{halves[2],roots[2],halves[2],halves[2]});
    const Vec4 z=Mul({plus[1],plus[0],minus[3],minus[2]},{halves[3],halves[3],roots[3],halves[3]});
    const Vec4 x=Mul({minus[3],plus[2],plus[1],minus[0]},{roots[1],halves[1],halves[1],halves[1]});
    const Vec4 w=Mul(minus,{halves[0],halves[0],halves[0],roots[0]});
    const Vec4 yz=up[1]>at[2] ? y:z,xyz=ri[0]>up[1] && ri[0]>at[2] ? x:yz;
    const Vec4 selected=first[0]+at[2]>0.0f ? w:xyz;
    return {Word(selected[0]),Word(selected[1]),Word(selected[2]),Word(selected[3])};
}
std::array<std::uint32_t,4> Soft(float spring,std::uint32_t strength)
{return {Word(spring),Word((spring*InverseLengthSquared(spring,2))*2.0f),strength,1};}
void Put(std::array<std::uint32_t,8>& dynamics,unsigned offset,const std::array<std::uint32_t,4>& words)
{for (unsigned i=0;i<4;++i) dynamics[offset+i]=words[i];}
}
void SetChildAngularFrame(std::array<std::uint32_t,16>& frames,const std::array<std::uint32_t,12>& basis)
{const auto q=Convert(basis);for (unsigned i=0;i<4;++i) frames[i]=q[i];}
void SetParentAngularFrame(std::array<std::uint32_t,16>& frames,const std::array<std::uint32_t,12>& basis)
{const auto q=Convert(basis);for (unsigned i=0;i<4;++i) frames[8+i]=q[i];}
HookDriveState HookDriveState::Initial()
{
    HookDriveState state;constexpr std::array<std::uint32_t,12> identity={0x3f800000,0,0,0,0,0x3f800000,0,0,0,0,0x3f800000,0};
    SetChildAngularFrame(state.frames,identity);SetParentAngularFrame(state.frames,identity);state.DisableLinear();state.DisableAngular();return state;
}
void HookDriveState::EnableAnimationSoft(std::uint8_t& animated)
{animated=1;Put(dynamics,0,Soft(5000,0x44e0fffe));EnableAngularSoft();}
void HookDriveState::EnableAngularSoft() {Put(dynamics,4,Soft(20000,0x470c9fff));}
void HookDriveState::EnableAngularOnly(std::uint8_t& animated) {animated=1;EnableAngularSoft();DisableLinear();}
void HookDriveState::DisableAnimation(std::uint8_t& animated) {animated=0;DisableLinear();DisableAngular();}
void HookDriveState::DisableLinear() {Put(dynamics,0,{0,0,0,2});}
void HookDriveState::DisableAngular() {Put(dynamics,4,{0,0,0,2});}
DriveDynamics HookDriveState::SolverDynamics() const
{
    auto params=[&](unsigned offset){return DriveParams{Scalar(dynamics[offset]),Scalar(dynamics[offset+1]),Scalar(dynamics[offset+2]),
        dynamics[offset+3]==1 ? DriveType::Soft:dynamics[offset+3]==2 ? DriveType::Hard:DriveType::None};};
    return {params(0),params(4)};
}
}

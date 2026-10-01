// SPDX-License-Identifier: Apache-2.0
#include "PlayerGrindSurface.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float F(std::uint32_t w){float f;std::memcpy(&f,&w,4);return f;}
Vec4 Add(Vec4 a,Vec4 b){Vec4 r;for(std::size_t i=0;i<4;++i)r[i]=a[i]+b[i];return r;}
Vec4 Sub(Vec4 a,Vec4 b){Vec4 r;for(std::size_t i=0;i<4;++i)r[i]=a[i]-b[i];return r;}
Vec4 Scale4(Vec4 a,float s){for(auto& v:a)v*=s;return a;}
Vec4 Madd4(Vec4 a,float s,Vec4 b){Vec4 r;for(std::size_t i=0;i<4;++i)r[i]=std::fma(a[i],s,b[i]);return r;}
Vec4 Negate(Vec4 a){for(auto& f:a){std::uint32_t w;std::memcpy(&w,&f,4);w^=0x80000000;std::memcpy(&f,&w,4);}return a;}
constexpr Vec4 Up{0,1,0,0};
Vec4 Normalize(Vec4 a,bool retain=false)
{
    const float q=Dot3(a,a),inverse=InverseLengthSquared(q,2),length=q==0 ? 0.0f : q*inverse;
    return length>F(0x358637bd) ? Scale4(a,inverse) : retain ? a : Vec4{};
}
bool IsCurb(const std::optional<PlayerGrindProbeHit>& a,const std::optional<PlayerGrindProbeHit>& b,Vec4 up,Vec4 center)
{
    if(!a||!b)return false;if(!(Dot3(up,a->normal)>0.99f&&Dot3(up,b->normal)>0.99f))return false;
    const float ah=Dot3(Sub(a->position,center),up),bh=Dot3(Sub(b->position,center),up);
    const float high=ah>=bh ? ah : bh,low=ah>=bh ? bh : ah;
    return high>-.035f&&high<.035f&&low>-.24f&&low<-.2f;
}
bool OptionalNormal(PlayerGrindProbeHit hit,Vec4 center,Vec4 direction)
{
    const float component=Dot3(hit.normal,Normalize(direction));const Vec4 projected=component>0 ? Sub(hit.normal,Scale4(direction,component)) : hit.normal;
    const auto normal=Normalize(projected);if(!(F(0x3f666666)>normal[1]))return false;
    auto offset=Sub(hit.position,center);offset[1]=0;return Dot3(offset,normal)>0;
}
std::pair<std::uint32_t,std::uint32_t> Unpack(std::uint32_t packed){return {packed&0x7f,(packed>>7)&0x1f};}
std::pair<std::uint32_t,std::uint32_t> SurfaceInfo(PlayerGrindGeometryKind kind,bool curb,const std::array<std::optional<PlayerGrindProbeHit>,7>& hits)
{
    if(curb)return {4,2};if(kind==PlayerGrindGeometryKind::ThinRail)return {hits[4] ? hits[4]->packed_surface&0x7f : 11,4};
    for(std::size_t pair:{std::size_t(0),std::size_t(2)})
    {
        const auto selected=hits[pair]&&hits[pair+1] ? (hits[pair]->position[1]>hits[pair+1]->position[1] ? hits[pair] : hits[pair+1]) : hits[pair] ? hits[pair] : hits[pair+1];
        if(selected)return Unpack(selected->packed_surface);
    }
    return hits[4] ? Unpack(hits[4]->packed_surface) : std::pair<std::uint32_t,std::uint32_t>{3,1};
}
PlayerGrindSurface NotSubmitted(PlayerGrindSurfaceInput input)
{
    const Vec4 x{1,0,0,0},z{0,0,1,0};return {input.reference,{Madd4(x,input.deck_center_to_truck,input.reference),Sub(input.reference,Scale4(x,input.deck_center_to_truck))},z,z,z,{0,0},PlayerGrindGeometryKind::Impossible,3,1,PlayerGrindSurface::Invalid,PlayerGrindTiltedNormal(z,z,{0,0})};
}
}
Vec4 PlayerGrindRotate(Vec4 axis,Vec4 value,float angle)
{
    const auto sc=SinCos(angle*.5f);const auto q=Scale4(axis,sc.first);
    return Madd4(Cross3(q,Madd4(value,sc.second,Cross3(q,value))),2.0f,value);
}
Vec4 PlayerGrindTiltedNormal(Vec4 direction,Vec4 up,std::array<float,2> limits)
{
    const float lo=limits[0],hi=limits[1],pi=F(0x40490fdb);float angle;
    if(lo<hi){if(lo<pi&&hi>pi)return up;angle=std::abs(pi-lo)<std::abs(pi-hi) ? lo : hi;}
    else angle=(hi+lo)*.5f;
    return PlayerGrindRotate(direction,Scale4(up,-1),angle);
}
std::optional<PlayerGrindInvestigation> PreparePlayerGrindSurface(PlayerGrindSurfaceInput input)
{
    const auto delta=Sub(input.end,input.start),raw_up=Cross3(delta,Cross3(Up,delta));const float up_length=Length3(raw_up);
    const auto up=Normalize(raw_up,true),direction=Normalize(delta,true);if(up_length<F(0x3727c5ac))return std::nullopt;
    const auto projected=Madd4(direction,Dot3(Sub(input.reference,input.start),direction),input.start);
    const auto center=Sub(input.reference,Sub(input.reference,projected)),side=Cross3(up,direction);
    const auto short_up=Scale4(up,F(0x3d23d70a)),near_side=Scale4(side,F(0x3db851ec)),far_side=Scale4(side,input.deck_center_to_truck);
    const auto far_up=Scale4(up,input.deck_center_to_truck*F(0x3f87ae14)),raised=Scale4(up,F(0x3db851ec));
    const auto line=[](Vec4 at,Vec4 half,float radius){return PlayerGrindProbe{Add(at,half),Sub(at,half),radius};};
    std::vector<PlayerGrindProbe> probes{line(Add(center,near_side),short_up,0),line(Sub(center,near_side),short_up,0),line(Add(center,far_side),far_up,0),line(Sub(center,far_side),far_up,0),line(center,short_up,0),line(Add(center,raised),near_side,F(0x3a83126f))};
    if(input.optional_probe)probes.push_back({*input.optional_probe,Add(*input.optional_probe,{0,-6,0,0}),0});
    return PlayerGrindInvestigation{center,up,direction,std::move(probes)};
}
PlayerGrindSurface ResolvePlayerGrindSurface(const PlayerGrindInvestigation& plan,const std::array<std::optional<PlayerGrindProbeHit>,7>& hits,std::uint32_t previous)
{
    const auto h6=plan.probes.size()==7 ? hits[6] : std::nullopt;const bool blocked=(hits[0]&&hits[1])||bool(hits[5]);
    const auto kind=blocked ? PlayerGrindGeometryKind::Impossible : hits[0] ? (hits[2]&&hits[2]->fraction<F(0x3f266666) ? PlayerGrindGeometryKind::Ledge : PlayerGrindGeometryKind::FatRail) : hits[1] ? (hits[3]&&hits[3]->fraction<F(0x3f266666) ? PlayerGrindGeometryKind::Ledge : PlayerGrindGeometryKind::FatRail) : PlayerGrindGeometryKind::ThinRail;
    auto side=Cross3(Up,plan.direction);side=Scale4(side,InverseLengthSquared(Dot3(side,side),2));
    const auto high_side=!blocked&&!hits[0]&&hits[1] ? Scale4(side,-1) : side;
    const bool curb=kind==PlayerGrindGeometryKind::Ledge&&IsCurb(hits[2],hits[3],plan.upmost_normal,plan.center);
    const bool stair=(hits[0]&&(hits[0]->packed_surface&0xf80)==0x400)||(hits[1]&&(hits[1]->packed_surface&0xf80)==0x400);
    const bool optional_normal=h6&&OptionalNormal(*h6,plan.center,plan.direction),optional_drop=!h6||!(h6->position[1]-plan.center[1]>-1.0f);
    auto flags=previous&~(PlayerGrindSurface::Invalid|PlayerGrindSurface::Curb|PlayerGrindSurface::Stair|PlayerGrindSurface::OptionalNormalTest|PlayerGrindSurface::OptionalDropTest);
    if(blocked)flags|=PlayerGrindSurface::BlockedCrossSection;if(curb)flags|=PlayerGrindSurface::Curb;if(stair)flags|=PlayerGrindSurface::Stair;if(optional_normal)flags|=PlayerGrindSurface::OptionalNormalTest;if(optional_drop)flags|=PlayerGrindSurface::OptionalDropTest;
    const auto materials=SurfaceInfo(kind,curb,hits);
    const std::array<Vec4,2> far_points{hits[2] ? hits[2]->position : plan.probes[2].end,hits[3] ? hits[3]->position : plan.probes[3].end};
    const auto negative_up=Scale4(plan.upmost_normal,-1);std::array<float,2> angles;
    for(std::size_t i=0;i<2;++i){const auto delta=Sub(far_points[i],plan.center);const auto unit=Scale4(delta,RefinedReciprocal(Length3(delta),2));angles[i]=Acos(VectorMin(VectorMax(Dot3(negative_up,unit),-1.0f),1.0f));}
    const float half_pi=F(0x3fc90fdb),clearance=F(0x3e8efa35);const std::array<float,2> limits{(angles[0]+half_pi)+clearance,((F(0x40c90fdb)-angles[1])-half_pi)-clearance};
    return {plan.center,far_points,plan.upmost_normal,plan.direction,high_side,limits,kind,materials.first,materials.second,flags,PlayerGrindTiltedNormal(plan.direction,plan.upmost_normal,limits)};
}
bool InvestigatePlayerGrindSurface(PlayerGrindSurfaceInput input,PlayerGrindSurfaceQueries& queries,PlayerGrindSurface& result,std::string& error)
{
    const auto plan=PreparePlayerGrindSurface(input);if(!plan){result=NotSubmitted(input);error.clear();return true;}
    std::array<std::optional<PlayerGrindProbeHit>,7> hits;for(std::size_t i=0;i<plan->probes.size();++i)if(!queries.Query(i,plan->probes[i],hits[i],error))return false;
    result=ResolvePlayerGrindSurface(*plan,hits,0);error.clear();return true;
}
void UpdatePlayerGrindLandingOrientation(const PlayerGrindSurface* surface,Vec4 takeoff,Vec4 position,Vec4& up,GrindAirLandingOrientation& out)
{
    if(!surface){out.kind=3;out.garbage=true;return;}
    if((surface->flags&PlayerGrindSurface::Invalid)!=0){const Vec4 x{1,0,0,0};up=Up;out.kind=0;out.garbage=true;out.boardslide_dir=x;out.tipslide_dir=x;out.backslash_dir=Negate(x);out.high_side=x;return;}
    up=PlayerGrindTiltedNormal(surface->direction,surface->upmost_normal,surface->normal_limits);out.kind=std::uint32_t(surface->kind);out.garbage=false;out.high_side=surface->high_side;
    const auto side=Cross3(surface->upmost_normal,surface->direction);const float tipslide=F(0x3eb2b8c3);
    if(surface->kind==PlayerGrindGeometryKind::ThinRail)
    {
        out.boardslide_dir=side;const auto oriented=Dot3(side,Sub(takeoff,position))>0 ? side : Negate(side);const auto axis=Cross3(oriented,surface->upmost_normal);
        out.tipslide_dir=PlayerGrindRotate(axis,oriented,tipslide);out.backslash_dir=PlayerGrindRotate(axis,oriented,F(0x401a25c2));
    }
    else
    {
        const auto axis=Cross3(side,surface->upmost_normal);out.boardslide_dir=surface->kind==PlayerGrindGeometryKind::FatRail ? side : Cross3(up,surface->direction);
        const float sign=Dot3(side,surface->high_side)>0 ? 1.0f : -1.0f;
        out.backslash_dir=PlayerGrindRotate(Scale4(axis,sign),Scale4(side,sign),F(0x3f3ba866));out.tipslide_dir=PlayerGrindRotate(Scale4(axis,-sign),Scale4(side,-sign),tipslide);
    }
}
}

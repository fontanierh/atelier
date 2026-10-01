// SPDX-License-Identifier: Apache-2.0
#include "GroundHangGeometry.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Word(std::uint32_t word) {float v;std::memcpy(&v,&word,4);return v;}
Vec3 HangAdd(Vec3 a,Vec3 b) {return {a.x+b.x,a.y+b.y,a.z+b.z};}
Vec3 HangCross(Vec3 a,Vec3 b)
{return {std::fma(-a.z,b.y,a.y*b.z),std::fma(-a.x,b.z,a.z*b.x),std::fma(-a.y,b.x,a.x*b.y)};}
std::pair<Vec3,float> NormalizeOrRetain(Vec3 v)
{
    const float square=Dot3(v,v),inverse=InverseLengthSquared(square,2),length=square==0?0:square*inverse;
    return {length>Word(0x358637bd)?Scale(v,inverse):v,length};
}
}
std::optional<std::array<HangLine,6>> GroundHangLines(HangGeometryInput input,float deck_center_to_truck)
{
    const auto delta=Subtract(input.edge_end,input.edge_start);
    const auto first=HangCross({0,1,0},delta),raw_up=HangCross(delta,first);
    const auto normalized=NormalizeOrRetain(raw_up);
    const auto direction=NormalizeOrRetain(delta).first;
    if (normalized.second<Word(0x3727c5ac)) return std::nullopt;
    const auto up=normalized.first;
    const float projected=Dot3(Subtract(input.reference_point,input.edge_start),direction);
    const Vec3 on_edge{std::fma(direction.x,projected,input.edge_start.x),std::fma(direction.y,projected,input.edge_start.y),std::fma(direction.z,projected,input.edge_start.z)};
    const auto centre=Subtract(input.reference_point,Subtract(input.reference_point,on_edge));
    const auto side=HangCross(up,direction),short_up=Scale(up,.04f),near_side=Scale(side,.09f);
    const auto far_side=Scale(side,deck_center_to_truck),far_up=Scale(up,deck_center_to_truck*Word(0x3f87ae14)),last_up=Scale(up,.09f);
    const auto line=[](Vec3 c,Vec3 v,float radius) {return HangLine{HangAdd(c,v),Subtract(c,v),radius};};
    return std::array<HangLine,6>{line(HangAdd(centre,near_side),short_up,0),line(Subtract(centre,near_side),short_up,0),
        line(HangAdd(centre,far_side),far_up,0),line(Subtract(centre,far_side),far_up,0),line(centre,short_up,0),line(HangAdd(centre,last_up),near_side,.001f)};
}
bool GroundHungClassification(const std::array<std::optional<float>,6>& hits)
{
    if ((hits[0]&&hits[1])||hits[4]) return false;
    const auto short_hit=[](const std::optional<float>& v) {return v&&*v<.65f;};
    const std::uint32_t kind=hits[0]?(short_hit(hits[2])?2:1):hits[1]?(short_hit(hits[3])?2:1):0;
    return kind!=2;
}
bool DetectGroundHungGeometry(const WorldGeometry& world,HangGeometryInput input,float distance,bool& output,std::string& error)
{
    const auto lines=GroundHangLines(input,distance);
    if (!lines) {output=false;return true;}
    std::array<std::optional<float>,6> fractions;
    for (std::size_t i=0;i<lines->size();++i)
    {
        const auto line=(*lines)[i];const auto result=world.QuerySweptLine(line.start,line.end,line.radius);
        if (result.error) {error=result.error;return false;}
        if (result.hit) fractions[i]=result.hit->geometry.fraction;
    }
    output=GroundHungClassification(fractions);return true;
}
}

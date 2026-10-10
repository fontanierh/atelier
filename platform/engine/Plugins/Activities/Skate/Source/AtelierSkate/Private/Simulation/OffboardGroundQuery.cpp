#include "OffboardGroundQueryMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
OffboardGroundFrame OffboardGroundQueryFrame(const Mat4& f){const auto xyz=[](Vec4 v){return Vec3{v[0],v[1],v[2]};};return {xyz(f[0]),xyz(f[1]),xyz(f[2]),xyz(f[3])};}
Mat4 OffboardGroundSimulationFrame(OffboardGroundFrame f){const auto lanes=[](Vec3 v){return Vec4{v.x,v.y,v.z,0};};return {lanes(f.right),lanes(f.up),lanes(f.forward),lanes(f.position)};}
OffboardGroundEdgeSearch SearchOffboardGroundEdges(OffboardGroundFrame frame,OffboardGroundContext context,Vec3 state,std::uint32_t flags)
{
    using namespace offboard_ground_query;const auto narrow=(flags&0x08000000)!=0||!(Dot(state,state)>=1);
    const auto center=narrow?Fma(frame.forward,.75f,frame.position):frame.position;
    const auto extent=Fma(Abs(frame.forward),.75f,Fma(Abs(frame.up),.2f,Mul(Abs(frame.right),.5f)));
    return {Sub(center,extent),Add(center,extent),frame,context,narrow};
}
Vec3 ClosestOffboardGroundEdgePoint(Vec3 point,OffboardGroundEdge edge)
{
    using namespace offboard_ground_query;auto d=Sub(edge.end,edge.start);const auto length=Length(d);if(length>Bits(0x37800000))d=Mul(d,Reciprocal(length));
    const auto t=VectorMax(VectorMin(Dot(d,Sub(point,edge.start)),length),0);return Fma(d,t,edge.start);
}
std::optional<OffboardGroundEdgeSelection> SelectOffboardGroundEdge(OffboardGroundEdgeSearch search,const std::vector<OffboardGroundEdge>& candidates)
{
    using namespace offboard_ground_query;float best_vertical=.2f,best_horizontal=1.5f;std::optional<OffboardGroundEdgeSelection> selected;
    for(std::size_t n=0;n<std::min<std::size_t>(40,candidates.size());++n)
    {
        const auto edge=candidates[n];const auto closest=ClosestOffboardGroundEdgePoint(search.frame.position,edge),delta=Sub(closest,search.frame.position);
        if(search.narrow_forward&&0>Dot(search.frame.forward,delta))continue;
        const auto vertical=Dot(search.frame.up,delta),horizontal=Length(Sub(delta,Mul(search.frame.up,vertical)));
        if(!(std::abs(vertical)>=best_vertical)&&!(horizontal>=best_horizontal)){best_vertical=std::abs(vertical);best_horizontal=horizontal;selected=OffboardGroundEdgeSelection{edge,closest};}
    }
    return selected;
}
std::optional<OffboardGroundPacket> PrepareOffboardGroundPacket(OffboardGroundFrame frame,OffboardGroundContext context,OffboardGroundEdgeSelection selected,float offset)
{
    using namespace offboard_ground_query;const auto edge=selected.edge;const auto closest=selected.closest;
    const auto reverse=Unit(Sub(edge.start,edge.end),frame.right),forward=Unit(Sub(frame.forward,Mul(reverse,Dot(reverse,frame.forward))),frame.forward);
    const auto seventh=Fma(forward,.2f,closest),delta=Sub(edge.end,edge.start),raw_up=Cross(delta,Cross({0,1,0},delta));
    const auto up=Unit(raw_up,raw_up),tangent=Unit(delta,delta);if(Bits(0x3727c5ac)>Length(raw_up))return std::nullopt;
    const auto projection=Fma(tangent,Dot(Sub(closest,edge.start),tangent),edge.start),center=Sub(closest,Sub(closest,projection));
    const auto side=Cross(up,tangent),short_up=Mul(up,.04f),near=Mul(side,.09f),far=Mul(side,offset),far_up=Mul(up,offset*Bits(0x3f87ae14));
    const auto line=[](Vec3 c,Vec3 d,float radius){return OffboardGroundLine{offboard_ground_query::Add(c,d),offboard_ground_query::Sub(c,d),radius};};
    return OffboardGroundPacket{context,center,up,tangent,{line(Add(center,near),short_up,0),line(Sub(center,near),short_up,0),line(Add(center,far),far_up,0),line(Sub(center,far),far_up,0),line(center,short_up,0),line(Add(center,Mul(up,.09f)),near,.001f),OffboardGroundLine{seventh,Add(seventh,{0,-6,0}),0}}};
}
}

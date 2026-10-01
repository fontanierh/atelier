// SPDX-License-Identifier: Apache-2.0
#include "OffboardAirMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec4 LedgeClosest(Vec4 point,OffboardGroundEdge edge)
{
    using namespace offboard_air_math;const auto start=Lanes(edge.start);auto delta=Sub(Lanes(edge.end),start);const auto n=Length(delta);
    if(n>Bits(0x37800000))delta=Mul(delta,Reciprocal(n));return Madd(delta,VectorMax(VectorMin(Dot(delta,Sub(point,start)),n),0),start);
}
float LedgeAngle(Vec4 a,Vec4 b,Vec4 up)
{
    using namespace offboard_air_math;if(!(Dot(a,a)*Dot(b,b)>Bits(0x37800000)))return 0;
    a=Sub(a,Mul(up,Dot(up,a)));b=Sub(b,Mul(up,Dot(up,b)));const auto aa=Dot(a,a),bb=Dot(b,b);
    if(!(aa>.0001f&&bb>.0001f))return 0;a=Mul(a,Inverse(aa,1));b=Mul(b,Inverse(bb,1));
    const auto value=Acos(VectorMin(VectorMax(Dot(a,b),-1),1)),angle=Dot(Cross(a,b),up)<0?Bits(0x40c90fdb)-value:value;
    return std::abs(WrapAngle(angle));
}
}
std::optional<OffboardGroundEdgeSearch> SearchOffboardAirLedge(OffboardAirCandidate c,OffboardAirPrediction p,OffboardAirContext context)
{
    using namespace offboard_air_math;if(!Valid(p.result)||p.result.contact_frame<16)return std::nullopt;
    const auto collision=p.CollisionPosition();const auto apex=AirTrajectoryHighestPosition(c.trajectory).first;Vec4 min{},max{};
    for(std::size_t n=0;n<4;++n){min[n]=VectorMin(collision[n],apex[n])-2;max[n]=VectorMax(collision[n],apex[n])+2;}
    OffboardGroundFrame frame;frame.position=XYZ(c.trajectory.position);return OffboardGroundEdgeSearch{XYZ(min),XYZ(max),frame,{context.selection_flags_2948,context.matching_group_2952},false};
}
std::vector<OffboardGroundEdge> FilterOffboardAirLedges(const std::vector<OffboardGroundEdge>& edges,Vec4 reference)
{
    using namespace offboard_air_math;std::vector<Vec4> directions;for(const auto& e:edges)directions.push_back(Unit(Sub(Lanes(e.end),Lanes(e.start))));
    std::vector<OffboardGroundEdge> result;
    for(std::size_t i=0;i<edges.size();++i)
    {
        const auto edge=edges[i];const auto start=Lanes(edge.start),midpoint=Mul(Add(start,Lanes(edge.end)),.5f);bool keep=true;
        for(std::size_t j=0;j<edges.size();++j)
        {
            if(i==j)continue;const auto other=edges[j];const auto parallel=Cross(directions[i],directions[j]);if(!(Dot(parallel,parallel)<.0001f))continue;
            const auto delta=Sub(Lanes(other.start),start),off=Sub(delta,Mul(directions[j],Dot(directions[j],delta)));const auto distance=Dot(off,off);
            if(!(distance>.0001f&&distance<.010000001f))continue;const auto from_mid=Sub(Lanes(other.start),midpoint);
            if(!(Dot(from_mid,Sub(Lanes(other.end),midpoint))<0))continue;
            const auto other_point=Add(midpoint,Sub(from_mid,Mul(directions[j],Dot(directions[j],from_mid)))),a=Sub(midpoint,reference),b=Sub(other_point,reference);
            const auto normal=UnitOr(Cross(directions[i],Cross(Up,directions[i])),{});const auto height=Dot(delta,normal);
            if((height>-.02f&&Dot(a,a)>Dot(b,b))||height>.02f){keep=false;break;}
        }
        if(keep){result.push_back(edge);if(result.size()==40)break;}
    }
    return result;
}
std::optional<float> OffboardAirLedgePlaneTime(AirTrajectory t,Vec4 point,Vec4 normal)
{
    using namespace offboard_air_math;const auto a=Dot(normal,Mul(t.acceleration,.5f)),b=Dot(normal,t.velocity),c=Dot(normal,t.position)-Dot(point,normal);
    const auto discriminant=b*b-(4*a)*c;if(discriminant<0)return std::nullopt;const auto denominator=Reciprocal(2*a);
    if(discriminant>0){const auto root=discriminant*Inverse(discriminant);return VectorMax(denominator*(-b+root),denominator*(-b-root));}
    const auto time=denominator*(-b);return time>0?std::optional<float>{time}:std::nullopt;
}
void OffboardAirLedgeAdjustment::Apply(OffboardAirCandidate& c) const
{
    using namespace offboard_air_math;c.trajectory=lowered_trajectory;c.trajectory.position=Add(c.trajectory.position,{0,radius,0,0});
    const auto delta=Sub(Lanes(edge.end),Lanes(edge.start));c.normal_64=UnitOr(Cross(delta,Cross(Up,delta)),Up);
    c.contact_position_96=point;c.landing_frame_116=landing_frame;c.contact_velocity_80=AirTrajectoryVelocityAt(lowered_trajectory,float(landing_frame)*Step());c.special_121=true;
}
std::optional<OffboardAirLedgeAdjustment> ChooseOffboardAirLedge(OffboardAirCandidate candidate,OffboardAirPrediction prediction,OffboardAirContext context,float radius,const std::vector<OffboardGroundEdge>& edges)
{
    using namespace offboard_air_math;if(!Valid(prediction.result)||prediction.result.contact_frame<16)return std::nullopt;
    const auto t=candidate.trajectory;auto lowered=t;lowered.position=Add(t.position,{0,-radius,0,0});std::optional<OffboardAirLedgeAdjustment> best;
    for(const auto& edge:edges)
    {
        const auto delta=Sub(Lanes(edge.end),Lanes(edge.start)),normal=UnitOr(Cross(delta,Cross(Up,delta)),Up);
        const auto time=OffboardAirLedgePlaneTime(t,Lanes(edge.start),normal);if(!time)continue;
        const auto intersection=AirTrajectoryPositionAt(t,*time),point=LedgeClosest(intersection,edge);if(!(normal[1]>.71f))continue;
        const auto horizontal=Flat(Sub(point,lowered.position));const auto distance=Length(horizontal);if(!(distance>.3f))continue;
        const auto direction=Mul(horizontal,1/distance);if(!(Dot(direction,UnitOr(Flat(context.forward_224),{}))>.71f))continue;
        const auto frame=Integer(*time*59.999996f);auto adjusted=lowered;Adjust(adjusted,frame,Sub(point,intersection),10);
        const auto velocity_delta=Sub(adjusted.velocity,t.velocity);const auto height=point[1]-prediction.result.contact_position[1];
        if(!(height>-.05f&&Dot(velocity_delta,velocity_delta)<2.25f))continue;const auto near_height=height<.05f;const float maximum=near_height?10:40;
        if(near_height&&!(Dot(direction,UnitOr(Flat(delta),{}))>=.71f))continue;
        if(!(LedgeAngle(adjusted.velocity,t.velocity,context.up_544)<maximum*Bits(0x3c8efa35)))continue;
        if(best&&best->point[1]>point[1])continue;best=OffboardAirLedgeAdjustment{edge,point,adjusted,frame,radius};
    }
    return best;
}
std::optional<std::array<OffboardGroundLine,6>> OffboardAirLedgeLines(OffboardAirLedgeAdjustment adjustment,float half)
{
    using namespace offboard_air_math;const auto edge=adjustment.edge;const auto delta=Sub(Lanes(edge.end),Lanes(edge.start)),raw_up=Cross(delta,Cross(Up,delta));
    if(.00001f>Length(raw_up))return std::nullopt;const auto up=UnitOr(raw_up,raw_up),tangent=UnitOr(delta,delta),start=Lanes(edge.start);
    const auto projection=Madd(tangent,Dot(Sub(adjustment.point,start),tangent),start),center=Sub(adjustment.point,Sub(adjustment.point,projection));
    const auto side=Cross(up,tangent),near=Mul(side,.09f),far=Mul(side,half),short_up=Mul(up,.04f),far_up=Mul(up,half*Bits(0x3f87ae14));
    const auto line=[](Vec4 c,Vec4 d,float radius){return OffboardGroundLine{XYZ(Add(c,d)),XYZ(Sub(c,d)),radius};};
    return std::array<OffboardGroundLine,6>{{line(Add(center,near),short_up,0),line(Sub(center,near),short_up,0),line(Add(center,far),far_up,0),line(Sub(center,far),far_up,0),line(center,short_up,0),line(Add(center,Mul(up,.09f)),near,.001f)}};
}
bool ConsumeOffboardAirLedgeLines(std::size_t count,std::string& error)
{if(count!=6){error="BipedAir ledge completion requires exactly six lines";return false;}error.clear();return true;}
}

// SPDX-License-Identifier: Apache-2.0
#include "OffboardGrabMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
bool QualifyGrabRecord(const OffboardGrabRecord& r,Vec4 position,const Mat4& bounds_frame,Vec4 extents,float margin,float angle_a,float angle_b)
{
    using namespace offboard_grab_math;const auto length=GrabRecordScalar(r,176);if(margin>length*.5f)margin=length*.5f;
    const auto distance=VectorMin(VectorMax(NearestPolylineDistance(r,position),margin),length-margin);const auto point=PolylineAtDistance(r,distance);const auto endpoints=GrabRecordEndpoints(r);const auto direction=Sub(endpoints[0],endpoints[1]),forward=bounds_frame[2];
    const auto facing=std::abs(Dot(Unit(Flat(forward)),Unit(Flat(direction))));const auto side=Unit(Cross({0,1,0,0},direction)),approach=GrabRecordVector(r,96);const auto approach_side=Dot(side,approach);
    if(std::abs(approach_side)<=.1f||Dot(forward,side)*approach_side>=0||!(facing<.8f))return false;
    const auto reach=Flat(Sub(point,position));if(!(Dot(reach,reach)>0))return false;auto opposite=approach;for(auto& v:opposite)v=-v;if(!(angle_a>Angle(reach,opposite)))return false;
    auto step=length*.5f;if(step>Bits(0x3c23d70a))step=Bits(0x3c23d70a);const auto next_distance=distance+step>length?distance-step:distance+step;const auto tangent=Sub(PolylineAtDistance(r,next_distance),point),horizontal=Flat(tangent);if(!(Dot(horizontal,horizontal)>Bits(0x37800000)))return false;
    const auto turns=Angle(tangent,horizontal)*Bits(0x3e22f983),fraction=turns-std::floor(turns);auto slope=std::abs((fraction-(fraction>.5f?1.0f:0.0f))*Bits(0x40c90fdb));if(slope>Bits(0x3fc90fdb))slope=Bits(0x40490fdb)-slope;if(!(angle_b>slope))return false;
    const auto local=InversePoint(bounds_frame,point);for(unsigned n=0;n<3;++n)if(!(local[n]>=-extents[n]&&local[n]<=extents[n]))return false;return true;
}
std::optional<OffboardGrabRecord> BestGrabSpline(const std::vector<OffboardGrabRecord>& records,Vec4 position)
{
    using namespace offboard_grab_math;auto distance=Bits(0x47c34ff3);std::optional<OffboardGrabRecord> best;
    for(const auto& r:records)
    {
        const auto endpoints=GrabRecordEndpoints(r);const auto delta=Sub(ClosestGrabPoint(position,endpoints),position),direction=Unit(Flat(Sub(endpoints[0],endpoints[1]))),approach=Unit(Flat(delta));
        const auto eligible=delta[1]>Bits(0xbf19999a)&&delta[1]<Bits(0x3f19999a)&&std::abs(Dot(direction,approach))<Bits(0x3f4ccccd);const auto candidate=Dot(delta,delta);
        if(!(candidate>=distance)){distance=candidate;best=eligible?std::optional<OffboardGrabRecord>{r}:std::nullopt;}
    }
    return best;
}
}

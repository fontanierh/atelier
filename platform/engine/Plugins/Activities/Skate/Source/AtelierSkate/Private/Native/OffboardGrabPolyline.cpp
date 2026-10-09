#include "OffboardGrabMath.h"
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
Vec4 ClosestGrabPoint(Vec4 position,std::array<Vec4,2> endpoints)
{
    using namespace offboard_grab_math;auto direction=Sub(endpoints[1],endpoints[0]);const auto length=Length(direction);if(length>Bits(0x37800000))direction=Mul(direction,QualifyReciprocal(length));const auto along=VectorMax(VectorMin(Dot(direction,Sub(position,endpoints[0])),length),0);return Madd(direction,along,endpoints[0]);
}
namespace offboard_grab_math
{
float NearestPolylineDistance(const OffboardGrabRecord& r,Vec4 world)
{
    const auto& points=r.geometry->points;const auto count=points.size();if(count<=1)return 0;const auto local=InversePoint(Frame(r),world);const bool reverse=Reversed(r);auto a=points[reverse?count-1:0];float accumulated=0,best=std::numeric_limits<float>::max(),distance=0;
    for(std::size_t n=1;n<count;++n)
    {
        const auto b=points[reverse?count-1-n:n],near=ClosestGrabPoint(local,{a,b}),error=Sub(local,near);const auto square=Dot(error,error);
        if(best>square){best=square;const auto partial=Sub(near,a);distance=Dot(partial,partial)==0?0:accumulated+Length(partial);}
        const auto segment=Sub(b,a);accumulated=Dot(segment,segment)==0?0:accumulated+Length(segment);a=b;
    }
    return distance;
}
Vec4 PolylineAtDistance(const OffboardGrabRecord& r,float distance)
{
    const auto endpoints=GrabRecordEndpoints(r);const auto& points=r.geometry->points;const auto count=points.size();if(count<=1||0>=distance)return endpoints[0];const bool reverse=Reversed(r);auto a=points[reverse?count-1:0];float accumulated=0;
    for(std::size_t n=1;n<count;++n)
    {
        const auto b=points[reverse?count-1-n:n],direction=Sub(b,a);const auto length=Length(direction);accumulated+=length;
        if(accumulated>distance){if(0>=length)return Point(Frame(r),b);const auto remaining=QualifyReciprocal(length)*(accumulated-distance);return Point(Frame(r),Sub(b,Mul(direction,remaining)));}a=b;
    }
    return endpoints[1];
}
}
}

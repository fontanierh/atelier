#include "GeometrySweep.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
float MinimumReciprocal() { const std::uint32_t word=0x00200000; float value; std::memcpy(&value,&word,4); return value; }
Vec3 Add(Vec3 a, Vec3 b) { return {a.x+b.x,a.y+b.y,a.z+b.z}; }
float L1(Vec3 v) { return (std::fabs(v.y)+std::fabs(v.z))+std::fabs(v.x); }
struct Fraction
{
    float numerator,denominator;
    float Value() const { return numerator/denominator; }
    bool Before(Fraction other) const { return numerator*other.denominator < other.numerator*denominator; }
};
enum class RootKind { Away, Miss, Hit };
struct Root { RootKind kind; Fraction fraction{0.0f,1.0f}; };
Root SphereRoot(Vec3 start, Vec3 delta, Vec3 center, float radius)
{
    const Vec3 toward_center=Subtract(center,start);
    const float radius_squared=radius*radius;
    if (Dot3(toward_center,toward_center) < radius_squared) return {RootKind::Hit,{0.0f,1.0f}};
    const float approach=Dot3(toward_center,delta);
    if (!(approach > 0.0f)) return {RootKind::Away};
    const float delta_squared=Dot3(delta,delta);
    const Vec3 perpendicular=Cross3(toward_center,delta);
    const float discriminant=std::fma(delta_squared,radius_squared,-Dot3(perpendicular,perpendicular));
    if (discriminant < 0.0f) return {RootKind::Miss};
    const float overrun=approach-delta_squared;
    if (overrun > 0.0f && overrun*overrun > discriminant) return {RootKind::Miss};
    return {RootKind::Hit,{approach-std::sqrt(discriminant),delta_squared}};
}
Root CylinderRoot(Vec3 start, Vec3 delta, Vec3 origin, Vec3 edge, float radius)
{
    const Vec3 perpendicular=Cross3(Subtract(origin,start),edge);
    const float distance_squared=Dot3(perpendicular,perpendicular);
    const float radius_squared=(Dot3(edge,edge)*radius)*radius;
    if (distance_squared < radius_squared) return {RootKind::Hit,{0.0f,1.0f}};
    const Vec3 delta_perpendicular=Cross3(delta,edge);
    const float approach=Dot3(perpendicular,delta_perpendicular);
    if (!(approach > 0.0f)) return {RootKind::Away};
    const float delta_squared=Dot3(delta_perpendicular,delta_perpendicular);
    const float residual=std::fma(approach,approach,-(delta_squared*distance_squared));
    const float discriminant=std::fma(delta_squared,radius_squared,residual);
    if (discriminant < 0.0f) return {RootKind::Miss};
    const float overrun=approach-delta_squared;
    if (!(overrun < 0.0f) && !(overrun*overrun < discriminant)) return {RootKind::Miss};
    return {RootKind::Hit,{approach-std::sqrt(discriminant),delta_squared}};
}
bool Replaces(const std::optional<Fraction>& hit, Fraction candidate)
{
    return candidate.denominator > MinimumReciprocal() && candidate.numerator > 0.0f
        && (!hit || !hit->Before(candidate));
}
void AdvanceFraction(TriangleLineHit& result, float fraction)
{
    result.fraction=std::fma(1.0f-result.fraction,fraction,result.fraction);
}
bool Walk(TriangleLineHit& result, Vec3 start, Vec3 delta, const std::array<Vec3,3>& vertices,
          const ClosestTrianglePoint& closest, float radius)
{
    auto region=closest.region;
    Vec3 vertex=closest.point;
    for (unsigned iteration=0;iteration<5;++iteration)
    {
        float fraction;
        if (region<=2)
        {
            const Root root=SphereRoot(start,delta,vertex,radius);
            if (root.kind==RootKind::Away) return false;
            std::optional<Fraction> hit=root.kind==RootKind::Hit ? std::optional<Fraction>(root.fraction) : std::nullopt;
            const std::array<Vec3,2> adjacent=region==0 ? std::array<Vec3,2>{Subtract(vertices[1],vertices[0]),Subtract(vertices[2],vertices[0])}
                : region==1 ? std::array<Vec3,2>{Subtract(vertices[0],vertices[1]),Subtract(vertices[2],vertices[1])}
                : std::array<Vec3,2>{Subtract(vertices[0],vertices[2]),Subtract(vertices[1],vertices[2])};
            auto next_region=region;
            for (unsigned index=0;index<2;++index)
            {
                const Fraction candidate={Dot3(Subtract(vertex,start),adjacent[index]),Dot3(delta,adjacent[index])};
                if (Replaces(hit,candidate))
                {
                    hit=candidate;
                    next_region=(region+(index==0 ? 6u:9u))/2u;
                }
            }
            if (!hit) return false;
            fraction=hit->Value();
            if (next_region<=2)
            {
                AdvanceFraction(result,fraction);
                result.position=Madd(delta,fraction,start);
                result.normal=Scale(Subtract(result.position,vertex),RefinedReciprocal(radius,2));
                result.volume_parameter={region==1 ? 1.0f:0.0f,region==2 ? 1.0f:0.0f,0.0f};
                return true;
            }
            region=next_region;
        }
        else
        {
            const Vec3 origin=region==5 ? vertices[1]:vertices[0];
            const Vec3 edge=region==3 ? Subtract(vertices[1],vertices[0])
                : region==4 ? Subtract(vertices[2],vertices[0]) : Subtract(vertices[2],vertices[1]);
            vertex=origin;
            const Root root=CylinderRoot(start,delta,origin,edge,radius);
            if (root.kind==RootKind::Away) return false;
            std::optional<Fraction> hit=root.kind==RootKind::Hit ? std::optional<Fraction>(root.fraction) : std::nullopt;
            const Vec3 end=Add(origin,edge);
            const Fraction forward={Dot3(Subtract(end,start),edge),Dot3(delta,edge)};
            const Fraction backward={Dot3(Subtract(start,origin),edge),-forward.denominator};
            if (Replaces(hit,forward))
            {
                hit=forward; vertex=end; region/=2;
            }
            else if (Replaces(hit,backward))
            {
                hit=backward; region=(region-3)/2;
            }
            if (!hit) return false;
            fraction=hit->Value();
            if (region>2)
            {
                AdvanceFraction(result,fraction);
                result.position=Madd(delta,fraction,start);
                const float along_edge=Dot3(Subtract(result.position,origin),edge)*(1.0f/Dot3(edge,edge));
                const Vec3 nearest=Madd(edge,along_edge,origin);
                result.normal=Scale(Subtract(result.position,nearest),RefinedReciprocal(radius,2));
                result.volume_parameter=region==3 ? std::array<float,3>{along_edge,0.0f,0.0f}
                    : region==4 ? std::array<float,3>{0.0f,along_edge,0.0f} : std::array<float,3>{1.0f-along_edge,along_edge,0.0f};
                return true;
            }
        }
        AdvanceFraction(result,fraction);
        start=Madd(delta,fraction,start);
        delta=Scale(delta,1.0f-fraction);
        if (fraction > 1.0f) return false;
    }
    // The simulation success after the fifth transition leaves the output payload alone.
    return true;
}
bool Sweep(TriangleLineHit& result, Vec3 start, Vec3 delta, const std::array<Vec3,3>& vertices, float radius)
{
    result.fraction=0.0f;
    const Vec3 a=vertices[0],b=vertices[1],c=vertices[2],ab=Subtract(b,a),ac=Subtract(c,a);
    Vec3 from_a=Subtract(start,a);
    const Vec3 cross_ac=Cross3(delta,ac);
    float determinant=Dot3(ab,cross_ac),side=1.0f;
    if (determinant < 0.0f) { side=-1.0f; determinant=-determinant; }
    if (Dot3(result.normal,from_a)*side < -radius) return false;
    const float u=Dot3(from_a,cross_ac)*side,u_margin=L1(cross_ac)*radius;
    if (u < -u_margin || u > u_margin+determinant) return false;
    const Vec3 cross_ab=Cross3(ab,delta);
    const float v=Dot3(from_a,cross_ab)*side,v_margin=L1(cross_ab)*radius;
    if (v < -v_margin || v > v_margin+determinant || v+u > (u_margin+v_margin)+determinant) return false;
    if (determinant > MinimumReciprocal())
    {
        const Vec3 offset=Subtract(from_a,Scale(result.normal,side*radius));
        const float distance=-(Dot3(offset,Cross3(ac,ab))*side);
        if (distance > determinant) return false;
        if (!(distance < 0.0f))
        {
            const float inverse=1.0f/determinant;
            result.fraction=inverse*distance;
            const float face_u=Dot3(offset,cross_ac)*side;
            if (!(face_u < 0.0f) && !(face_u > determinant))
            {
                const float face_v=Dot3(offset,cross_ab)*side;
                if (!(face_v < 0.0f) && !(face_v+face_u > determinant))
                {
                    result.position=Madd(delta,result.fraction,start);
                    result.normal=Scale(result.normal,side);
                    result.volume_parameter={inverse*face_u,inverse*face_v,0.0f};
                    return true;
                }
            }
            from_a=Madd(delta,result.fraction,from_a);
            delta=Scale(delta,1.0f-result.fraction);
        }
    }
    start=Add(from_a,a);
    const ClosestTrianglePoint feature=ClosestPointOnTriangle(start,vertices);
    const Vec3 separation=Subtract(start,feature.point);
    const float squared=Dot3(separation,separation),penetration=std::fma(radius,radius,-squared);
    if (penetration > 0.0f)
    {
        result.position=start;
        if (squared > 0.0f) result.normal=Scale(separation,InverseLengthSquared(squared,1));
        result.volume_parameter={feature.u,feature.v,penetration};
        return true;
    }
    if (feature.region==6)
    {
        result.position=start;
        if (determinant < 0.0f) result.normal=Scale(result.normal,-1.0f);
        result.volume_parameter={feature.u,feature.v,0.0f};
        return true;
    }
    return Walk(result,start,delta,vertices,feature,radius);
}
}
bool TriangleSegment(TriangleLineHit& result, Vec3 start, Vec3 direction,
                     const std::array<Vec3,3>& vertices, float line_radius, float triangle_fatness)
{
    const float radius=line_radius+triangle_fatness;
    if (radius==0.0f)
    {
        const auto hit=ThinTriangleSegment(start,direction,vertices);
        if (!hit) return false;
        result=*hit; return true;
    }
    const Vec3 normal=Cross3(Subtract(vertices[0],vertices[1]),Subtract(vertices[0],vertices[2]));
    result.normal=Normalize3(normal,2);
    if (!Sweep(result,start,direction,vertices,radius)) return false;
    result.position=Subtract(result.position,Scale(result.normal,line_radius));
    return true;
}
}

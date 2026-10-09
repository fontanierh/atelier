#include "GeometryTriangleFixup.h"
#include <cassert>
#include <cstdlib>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
float Scalar(std::uint32_t word) { float value;std::memcpy(&value,&word,4);return value; }
double Scalar64(std::uint64_t word) { double value;std::memcpy(&value,&word,8);return value; }
Vec3 Neg(Vec3 value) { return {-value.x,-value.y,-value.z}; }
Vec3 Normalize(Vec3 value,unsigned refinements) { return Scale(value,InverseLengthSquared(Dot3(value,value),refinements)); }
bool Convex(const TriangleFeature& triangle,std::size_t edge) { return triangle.flags&(0x20u<<edge); }
bool Disabled(const TriangleFeature& triangle,std::size_t vertex) { return triangle.flags&(0x200u<<vertex); }
bool EdgeCosTest(Vec3 edge,Vec3 face,Vec3 normal,float cosine,bool convex,bool two_sided)
{
    if (Dot3(normal,Cross3(edge,face))<0.0f) return true;
    if (!convex && !two_sided) return false;
    const Vec3 projected=Normalize(Subtract(normal,Scale(edge,Dot3(normal,edge))),2);
    return Dot3(projected,convex ? face:Neg(face))>=cosine;
}
void Bend(Vec3& normal,ContactPair* contacts,std::size_t count,Vec3 direction,bool reverse)
{
    normal=reverse ? Neg(direction):direction;
    for (std::size_t i=0;i<count;++i)
    {
        auto& pair=contacts[i];
        if (reverse) pair.b=Madd(direction,Dot3(Subtract(pair.b,pair.a),direction),pair.a);
        else pair.a=Madd(direction,Dot3(Subtract(pair.a,pair.b),direction),pair.b);
    }
}
bool OneSidedEdge(const TriangleFeature& t,std::size_t edge,float projection,Vec3& normal,
                  ContactPair* contacts,std::size_t count,TriangleFixup settings)
{
    const float cosine=t.edge_cosines[edge];
    // Rust rounds cosine-1 in f32 before its original f64 near-flat comparison.
    if (Convex(t,edge) || (settings.is_object && std::fabs(static_cast<double>(cosine-1.0f))<Scalar64(0x3ee4f8b588e368f1)))
        return projection+settings.convexity_epsilon>=cosine;
    if (cosine>settings.edge_cos_bend_normal_threshold || cosine<=Scalar(0x3a83126f)) return false;
    const float squared=1.0f-cosine*cosine;
    const float threshold=squared==0.0f ? 0.0f:squared*InverseLengthSquared(squared,2);
    if (projection>threshold) {Bend(normal,contacts,count,t.normal,settings.reverse);return true;}
    return false;
}
}
TriangleRegion ClassifyTriangleFeature(const TriangleFeature& triangle,Vec3 direction)
{
    const float a=Dot3(direction,triangle.edges[0]),b=Dot3(direction,triangle.edges[1]),c=Dot3(direction,triangle.edges[2]);
    const float t=Scalar(0x3d4ccccd);
    if (a>t && b<-t) return TriangleRegion::Vertex2;
    if (b>t && c<-t) return TriangleRegion::Vertex1;
    if (c>t && a<-t) return TriangleRegion::Vertex0;
    if (a>-c && -b>=a) return TriangleRegion::Edge2;
    if (b>-a && -c>=b) return TriangleRegion::Edge1;
    if (c>-b && -a>=c) return TriangleRegion::Edge0;
    return TriangleRegion::Face;
}
bool FixUpTriangle(const TriangleFeature& triangle,Vec3& normal,ContactPair* contacts,std::size_t count,TriangleFixup settings)
{
    if (count>16) {assert(false && "Triangle contact capacity exceeded");std::abort();}
    const Vec3 toward=settings.reverse ? Neg(normal):normal;const float projection=Dot3(toward,triangle.normal);
    const float face_tolerance=Scalar(0x3f7ff62b);
    const auto region=std::fabs(projection)<face_tolerance
        ? ClassifyTriangleFeature(triangle,Normalize(Subtract(toward,Scale(triangle.normal,projection)),2)):TriangleRegion::Face;
    const bool one_sided=triangle.flags&0x10u;
    int edge=-1,vertex=-1;
    switch (region)
    {
    case TriangleRegion::Edge0:edge=0;break;
    case TriangleRegion::Edge1:edge=1;break;
    case TriangleRegion::Edge2:edge=2;break;
    case TriangleRegion::Vertex0:vertex=0;break;
    case TriangleRegion::Vertex1:vertex=1;break;
    case TriangleRegion::Vertex2:vertex=2;break;
    case TriangleRegion::Face:break;
    }
    if (!(triangle.flags&0x100u))
    {
        if (region==TriangleRegion::Face) return !one_sided || projection>0.0f;
        if (one_sided)
        {
            if (projection>face_tolerance) return true;
            if (projection<0.0f) return false;
        }
        else if (std::fabs(projection)>face_tolerance) return true;
        return edge>=0 ? Convex(triangle,edge):!Disabled(triangle,vertex);
    }
    if (region==TriangleRegion::Face) return !one_sided || projection>0.0f;
    if (edge>=0)
    {
        if (!one_sided) return (Convex(triangle,edge) ? projection:-projection)>=triangle.edge_cosines[edge];
        return OneSidedEdge(triangle,edge,projection,normal,contacts,count,settings);
    }
    const std::size_t first=(static_cast<std::size_t>(vertex)+2)%3,second=vertex;
    if (!one_sided)
    {
        if (Disabled(triangle,vertex)) return false;
        for (auto i:{first,second})
            if (!EdgeCosTest(Neg(triangle.edges[2-i]),triangle.normal,toward,triangle.edge_cosines[i],Convex(triangle,i),true)) return false;
        return true;
    }
    const bool disabled=Disabled(triangle,vertex) && !settings.is_object;
    if (projection>0.0f && disabled)
    {
        const bool convex_first=Convex(triangle,first),convex_second=Convex(triangle,second);
        if (convex_first==convex_second) return false;
        const std::size_t selected=convex_first ? second:first;const float cosine=triangle.edge_cosines[selected];
        if (!(cosine<=Scalar(0x3f7851ec) && cosine>Scalar(0x3a83126f))) return false;
        const Vec3 direction=triangle.edges[2-(selected==second ? first:second)];
        Bend(normal,contacts,count,Normalize(Cross3(Cross3(direction,toward),direction),1),settings.reverse);return true;
    }
    if (disabled) return false;
    for (auto i:{first,second})
        if (!EdgeCosTest(Neg(triangle.edges[2-i]),triangle.normal,toward,triangle.edge_cosines[i],Convex(triangle,i),false)) return false;
    return true;
}
}

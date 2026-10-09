#include "Geometry.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
float Word(std::uint32_t word) { float value; std::memcpy(&value,&word,4); return value; }
}
ClosestTrianglePoint ClosestPointOnTriangle(Vec3 point, const std::array<Vec3,3>& vertices)
{
    const Vec3 origin=vertices[0],edge_b=Subtract(vertices[1],origin),edge_c=Subtract(vertices[2],origin);
    const Vec3 toward_origin=Subtract(origin,point);
    const float bb=Dot3(edge_b,edge_b),cc=Dot3(edge_c,edge_c),bc=Dot3(edge_b,edge_c);
    const float bp=Dot3(edge_b,toward_origin),cp=Dot3(edge_c,toward_origin);
    const float determinant=std::fma(cc,bb,-(bc*bc));
    // Negate the coefficients before multiplying, as the original vector code
    // does. A folded FNMUL negates the product and changes a NaN payload's sign.
    // Volatile intermediates preserve this order without changing finite math.
    const volatile float negative_cc=-cc,negative_bb=-bb;
    const float un=std::fma(cp,bc,bp*negative_cc),vn=std::fma(bp,bc,cp*negative_bb);
    const float opposite=std::fma(-bc,2.0f,bb)+cc;
    unsigned feature;
    if (determinant < Word(0x00200000))
        feature=bb > cc ? (bb > opposite ? 0:2) : cc > opposite ? 1:2;
    else if (un+vn > determinant)
        feature=un < 0.0f ? (cp+cc < bp+bc ? 1:2) : vn < 0.0f ? (bp+bb < cp+bc ? 0:2) : 2;
    else if (un < 0.0f) feature=-cp > 0.0f ? 1:0;
    else if (vn < 0.0f) feature=-bp > 0.0f ? 0:1;
    else feature=3;
    float u,v;
    std::uint32_t region;
    if (feature==0)
    {
        if (!(bp < 0.0f)) { u=0.0f; v=0.0f; region=0; }
        else if (!(-bp < bb)) { u=1.0f; v=0.0f; region=1; }
        else { u=-(bp/bb); v=0.0f; region=3; }
    }
    else if (feature==1)
    {
        if (!(cp < 0.0f)) { u=0.0f; v=0.0f; region=0; }
        else if (!(-cp < cc)) { u=0.0f; v=1.0f; region=2; }
        else { u=0.0f; v=-(cp/cc); region=4; }
    }
    else if (feature==2)
    {
        const float numerator=((cp+cc)-bc)-bp;
        if (!(numerator > 0.0f)) { u=0.0f; v=1.0f; region=2; }
        else if (!(numerator < opposite)) { u=1.0f; v=0.0f; region=1; }
        else { u=numerator/opposite; v=1.0f-u; region=5; }
    }
    else
    {
        const float inverse=1.0f/determinant;
        u=inverse*un; v=inverse*vn; region=6;
    }
    return {Madd(edge_c,v,Madd(edge_b,u,origin)),region,u,v};
}
std::optional<TriangleLineHit> ThinTriangleSegment(Vec3 start, Vec3 direction, const std::array<Vec3,3>& vertices)
{
    const Vec3 a=vertices[0],b=vertices[1],c=vertices[2],ac=Subtract(c,a),ab=Subtract(b,a);
    Vec3 perpendicular=Cross3(direction,ac);
    const float determinant=Dot3(ab,perpendicular);
    if (!(determinant > Word(0x322bcc77))) return std::nullopt;
    const Vec3 from_a=Subtract(start,a);
    const float lower=determinant*Word(0xb727c5ac),upper=determinant-lower;
    const float u=Dot3(from_a,perpendicular);
    if (u < lower || u > upper) return std::nullopt;
    perpendicular=Cross3(from_a,ab);
    const float v=Dot3(direction,perpendicular);
    if (v < lower || v+u > upper) return std::nullopt;
    const float distance=Dot3(ac,perpendicular);
    if (distance < lower || distance > upper) return std::nullopt;
    const float inverse=1.0f/determinant,fraction=distance*inverse;
    const Vec3 normal=Cross3(Subtract(a,b),Subtract(a,c));
    return TriangleLineHit{Madd(direction,fraction,start),Normalize3(normal,2),fraction,{u*inverse,v*inverse,0.0f}};
}
float SampleShakeBezier(const Mat4& points, float input)
{
    const Mat4 basis={{{-1.0f,3.0f,-3.0f,1.0f},{3.0f,-6.0f,3.0f,0.0f},
                      {-3.0f,3.0f,0.0f,0.0f},{1.0f,0.0f,0.0f,0.0f}}};
    Mat4 coefficients{};
    for (unsigned row=0;row<4;++row) for (unsigned lane=0;lane<4;++lane)
        coefficients[row][lane]=std::fma(points[3][lane],basis[row][3],std::fma(points[2][lane],basis[row][2],
            std::fma(points[1][lane],basis[row][1],points[0][lane]*basis[row][0])));
    float t=0.5f;
    for (unsigned iteration=0;iteration<10;++iteration)
    {
        const float square=t*t;
        const auto evaluate=[&](const Vec4& powers,unsigned lane) {
            return std::fma(coefficients[3][lane],powers[3],std::fma(coefficients[2][lane],powers[2],
                std::fma(coefficients[1][lane],powers[1],coefficients[0][lane]*powers[0])));
        };
        const Vec4 powers={square*t,square,t,1.0f};
        const float value=evaluate(powers,0),result=evaluate(powers,1);
        const float derivative=evaluate(Vec4{square*3.0f,t*2.0f,1.0f,0.0f},0),residual=input-value;
        if (iteration==9 || !(std::fabs(residual) > Word(0x3c23d70a) && std::fabs(derivative) > Word(0x34000000))) return result;
        t=residual/derivative+t;
    }
    return 0.0f; // The tenth iteration always returns above.
}
}

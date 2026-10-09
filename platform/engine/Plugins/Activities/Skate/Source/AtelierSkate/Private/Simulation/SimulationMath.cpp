#include "SimulationMath.h"
#if defined(__x86_64__) || defined(_M_X64)
#include <xmmintrin.h>
#endif
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
float Word(std::uint32_t word) { float value; std::memcpy(&value,&word,4); return value; }
float QuietOperand(float value)
{
    std::uint32_t word; std::memcpy(&word,&value,4);
    if ((word&0x7f800000u)==0x7f800000u && (word&0x007fffffu)!=0)
        word|=0x00400000u;
    std::memcpy(&value,&word,4); return value;
}
#if defined(__GNUC__)
__attribute__((noinline))
#elif defined(_MSC_VER)
__declspec(noinline)
#endif
float OrderedFma(float multiplier, float multiplicand, float addend)
{
    return std::fma(multiplier,multiplicand,addend);
}
#if defined(__GNUC__)
__attribute__((noinline))
#elif defined(_MSC_VER)
__declspec(noinline)
#endif
float OrderedMultiply(float multiplier, float multiplicand)
{
    return multiplier*multiplicand;
}
#if defined(__GNUC__)
__attribute__((noinline))
#elif defined(_MSC_VER)
__declspec(noinline)
#endif
float NegatedProduct(float multiplier, float multiplicand)
{
    return -(multiplier*multiplicand);
}
float RoundTiesEven(float value)
{
    const float magnitude=std::fabs(value);
    if (!(magnitude < 8388608.0f)) return value;
    const float floor=std::floor(magnitude);
    const float fraction=magnitude-floor;
    const float rounded=fraction < 0.5f ? floor : fraction > 0.5f ? floor+1.0f
        : std::fmod(floor,2.0f) == 0.0f ? floor : floor+1.0f;
    return std::copysign(rounded,value);
}
float ReducedAngle(float angle)
{
    const float turns=RoundTiesEven(angle*Word(0x3e22f983));
    return std::fma(-Word(0x40c90fdb),turns,angle);
}
float AtanReciprocal(float value)
{
    const float initial=ReciprocalEstimate(value);
    const float first=std::fma(initial,std::fma(-value,initial,1.0f),initial);
    const float second=std::fma(first,std::fma(-value,first,1.0f),first);
    return std::isnan(first) ? initial : second;
}
}
float Dot3(const Vec4& a, const Vec4& b) { return (a[0]*b[0]+a[1]*b[1])+a[2]*b[2]; }
float Dot4(const Vec4& a, const Vec4& b) { return Dot3(a,b)+a[3]*b[3]; }
float Dot3(Vec3 a, Vec3 b) { return (a.x*b.x+a.y*b.y)+a.z*b.z; }
float ReciprocalEstimate(float value) { return 1.0f/value; }
float ReciprocalSquareRootEstimate(float value) { return 1.0f/std::sqrt(value); }
float RefinedReciprocal(float value, unsigned refinements)
{
    float inverse = ReciprocalEstimate(value);
    for (unsigned i=0; i<refinements; ++i)
    {
        const float error = std::fma(-inverse,value,1.0f);
        inverse = std::fma(inverse,error,inverse);
    }
    return inverse;
}
bool FlushDenormalsToZero()
{
#if defined(__aarch64__) && (defined(__clang__) || defined(__GNUC__))
    std::uint64_t control;
    __asm__ volatile("mrs %0, fpcr" : "=r"(control));
    control |= std::uint64_t(1) << 24;
    __asm__ volatile("msr fpcr, %0" : : "r"(control));
    return true;
#elif defined(__x86_64__) || defined(_M_X64)
    _mm_setcsr(_mm_getcsr() | 0x8040);
    return true;
#else
    return false;
#endif
}
float InverseLengthSquared(float value, unsigned refinements)
{
    float inverse = ReciprocalSquareRootEstimate(value);
    for (unsigned i=0; i<refinements; ++i)
        inverse = std::fma(inverse*0.5f,std::fma(-value,inverse*inverse,1.0f),inverse);
    return inverse;
}
// Rust min/max quiet each input before the min-number instruction. Applying
// fmin directly to a signaling NaN would lose a finite counterpart on arm64.
float VectorMin(float a, float b) { return std::fmin(QuietOperand(a),QuietOperand(b)); }
float VectorMax(float a, float b) { return std::fmax(QuietOperand(a),QuietOperand(b)); }
float Length3(const Vec4& value)
{
    const float squared = Dot3(value,value);
    const float result = squared*InverseLengthSquared(squared,2);
    return squared == 0.0f ? 0.0f : result;
}
float Length3(Vec3 value) { return Length3(Vec4{value.x,value.y,value.z,0.0f}); }
Vec4 Normalize3(const Vec4& value, unsigned refinements)
{
    const float inverse=InverseLengthSquared(Dot3(value,value),refinements);
    return {value[0]*inverse,value[1]*inverse,value[2]*inverse,value[3]*inverse};
}
Vec4 Normalize4(const Vec4& value, unsigned refinements)
{
    const float inverse=InverseLengthSquared(Dot4(value,value),refinements);
    return {value[0]*inverse,value[1]*inverse,value[2]*inverse,value[3]*inverse};
}
Vec3 Normalize3(Vec3 value, unsigned refinements) { return Scale(value,InverseLengthSquared(Dot3(value,value),refinements)); }
Vec4 Cross3(const Vec4& a, const Vec4& b)
{
    // An arm64 FMSUB negates its first multiplier before NaN propagation.
    // Clang may commute the multipliers when folding unary minus into FMSUB,
    // changing which NaN sign flips. Keep the normal finite path efficient;
    // the nonfinite path passes the already-negated first operand to FMADD.
    bool finite=true;
    for (unsigned lane=0;lane<4;++lane) finite=finite && std::isfinite(a[lane]) && std::isfinite(b[lane]);
    if (!finite)
        return {OrderedFma(-a[2],b[1],a[1]*b[2]),OrderedFma(-a[0],b[2],a[2]*b[0]),
                OrderedFma(-a[1],b[0],a[0]*b[1]),OrderedFma(-a[3],b[3],a[3]*b[3])};
    return {std::fma(-a[2],b[1],a[1]*b[2]),std::fma(-a[0],b[2],a[2]*b[0]),
            std::fma(-a[1],b[0],a[0]*b[1]),std::fma(-a[3],b[3],a[3]*b[3])};
}
Vec3 Cross3(Vec3 a, Vec3 b)
{
    if (!(std::isfinite(a.x) && std::isfinite(a.y) && std::isfinite(a.z)
          && std::isfinite(b.x) && std::isfinite(b.y) && std::isfinite(b.z)))
        return {OrderedFma(-a.z,b.y,a.y*b.z),OrderedFma(-a.x,b.z,a.z*b.x),OrderedFma(-a.y,b.x,a.x*b.y)};
    return {std::fma(-a.z,b.y,a.y*b.z),std::fma(-a.x,b.z,a.z*b.x),std::fma(-a.y,b.x,a.x*b.y)};
}
Vec3 Madd(Vec3 a, float b, Vec3 c) { return {std::fma(a.x,b,c.x),std::fma(a.y,b,c.y),std::fma(a.z,b,c.z)}; }
Vec3 Scale(Vec3 a, float b) { return {a.x*b,a.y*b,a.z*b}; }
Vec3 Subtract(Vec3 a, Vec3 b) { return {a.x-b.x,a.y-b.y,a.z-b.z}; }
Vec4 LimitLength3(const Vec4& value, float limit)
{
    const float magnitude=Length3(value);
    if (!(magnitude >= Word(0x37800000))) return value;
    const float capped=limit-magnitude >= 0.0f ? magnitude : limit;
    const float inverse=RefinedReciprocal(magnitude,2);
    return {(value[0]*capped)*inverse,(value[1]*capped)*inverse,(value[2]*capped)*inverse,(value[3]*capped)*inverse};
}
std::pair<float,float> SinCos(float angle)
{
    const float x=ReducedAngle(angle);
    const float x2=x*x, x3=x2*x, x4=x2*x2, x5=x3*x2, x6=x3*x3;
    const float x7=x4*x3, x8=x4*x4, x9=x5*x4, x10=x5*x5;
    const float x11=x6*x5, x12=x6*x6, x13=x7*x6, x15=x8*x7;
    const float x14=x7*x7, x16=x8*x8, x17=x9*x8, x19=x10*x9;
    const float x18=x9*x9, x21=x11*x10, x20=x10*x10, x23=x12*x11, x22=x11*x11;
    float sine=std::fma(Word(0xbe2aaaab),x3,x);
    sine=std::fma(Word(0x3c088889),x5,sine);
    sine=std::fma(x7,Word(0xb9500d01),sine);
    const float odd[]={x9,x11,x13,x15,x17,x19,x21,x23};
    const std::uint32_t odd_coeff[]={0x3638ef1d,0xb2d7322b,0x2f309231,0xab573f9f,0x274a963c,0xa317a4da,0x1eb8dc78,0x9a3b0da1};
    for (unsigned i=0;i<8;++i) sine=std::fma(Word(odd_coeff[i]),odd[i],sine);
    float cosine=std::fma(-0.5f,x2,1.0f);
    const float even[]={x4,x6,x8,x10,x12,x14,x16,x18,x20,x22};
    const std::uint32_t even_coeff[]={0x3d2aaaab,0xbab60b61,0x37d00d01,0xb493f27e,0x310f76c8,0xad49cba5,0x29573f9f,0xa53413c3,0x20f2a15d,0x9c8671cb};
    for (unsigned i=0;i<10;++i) cosine=std::fma(Word(even_coeff[i]),even[i],cosine);
    return {sine,cosine};
}
float Sin(float angle)
{
    const float x=ReducedAngle(angle), x2=x*x;
    float power=x*x2, result=x;
    const std::uint32_t coefficients[]={0xbe2aaaab,0x3c088889,0xb9500d01,0x3638ef1d,0xb2d7322b,
        0x2f309231,0xab573f9f,0x274a963c,0xa317a4da,0x1eb8dc78,0x9a3b0da1};
    for (auto coefficient:coefficients)
    {
        result=std::fma(Word(coefficient),power,result);
        power*=x2;
    }
    return result;
}
float Cos(float angle)
{
    const float x=ReducedAngle(angle), x2=x*x, x4=x2*x2, x6=x4*x2, x8=x4*x4;
    const float x10=x6*x4, x12=x6*x6, x14=x8*x6, x16=x8*x8, x18=x10*x8;
    const float x22=x12*x10, x20=x10*x10;
    float value=std::fma(-0.5f,x2,1.0f);
    const float powers[]={x4,x6,x8,x10,x12,x14,x16,x18,x20,x22};
    const std::uint32_t coefficients[]={0x3d2aaaab,0xbab60b61,0x37d00d01,0xb493f27e,0x310f76c8,
        0xad49cba5,0x29573f9f,0xa53413c3,0x20f2a15d,0x9c8671cb};
    for (unsigned i=0;i<10;++i) value=std::fma(Word(coefficients[i]),powers[i],value);
    return value;
}
float Asin(float value)
{
    const float a=std::fabs(value), cube=(value*value)*a;
    float p0=std::fma(Word(0x400b1889),a,Word(0xc0d1360e));
    float p1=std::fma(Word(0x3e663246),a,Word(0xbf983f2f));
    float p2=std::fma(Word(0xbed65553),a,Word(0x408980bd));
    float p3=std::fma(Word(0xbd6dd42d),a,Word(0x3f1dd7b6));
    p0=std::fma(p0,a,Word(0x40af6ad8)); p1=std::fma(p1,a,Word(0x3fb58485));
    p2=std::fma(p2,a,Word(0xc08f6ad9)); p3=std::fma(p3,a,Word(0xbfaf4418));
    const float left=std::fma(p1,cube,p0), right=std::fma(p3,cube,p2);
    const float radicand=Word(0x3f800001)-a;
    float r=ReciprocalSquareRootEstimate(radicand);
    const float correction=std::fma(-(radicand*0.5f),r*r,0.5f);
    r=std::fma(r,correction,r);
    const float residual=std::fma(-a,value,value)*right;
    return std::fma(residual,r,value*left);
}
float Acos(float value) { return (Word(0x40490fdb)*0.5f)-Asin(value); }
float Atan(float value)
{
    const float absolute=std::fabs(value);
    const bool invert=absolute > 1.0f;
    const float reduced=invert ? AtanReciprocal(absolute) : absolute;
    const bool transform=reduced > Word(0x3e8930a3);
    const float offset=transform ? (invert ? Word(0x3f860a92) : Word(0x3f060a92))
        : invert ? Word(0x3fc90fdb) : 0.0f;
    const float transformed=(std::fma(reduced,Word(0x3f3b67af),reduced)-1.0f)
        *AtanReciprocal(reduced+Word(0x3fddb3d7));
    const float t=transform ? transformed : reduced, square=t*t;
    float numerator=std::fma(square,Word(0xbf566bd7),Word(0xc107e9fb));
    numerator=std::fma(square,numerator,Word(0xc1a40bfe));
    numerator=std::fma(square,numerator,Word(0xc15b0533));
    float denominator=std::fma(square,square+Word(0x4170624f),Word(0x426e5052));
    denominator=std::fma(square,denominator,Word(0x42ac5090));
    denominator=std::fma(square,denominator,Word(0x422443e6));
    const float polynomial=std::fma(t,(numerator*square)*AtanReciprocal(denominator),t);
    float result=Word(0x39800000) > std::fabs(t) ? t : polynomial;
    result=(invert ? -result : result)+offset;
    result=value < 0.0f ? -result : result;
    result=value > Word(0x7e800000) ? Word(0x3fc90fdb) : result;
    return -Word(0x7e800000) > value ? -Word(0x3fc90fdb) : result;
}
Quat QuaternionMultiply(const Quat& a, const Quat& b)
{
    const Vec3 cross=Cross3(Vec3{a[0],a[1],a[2]},Vec3{b[0],b[1],b[2]});
    return {std::fma(a[0],b[3],std::fma(b[0],a[3],cross.x)),
            std::fma(a[1],b[3],std::fma(b[1],a[3],cross.y)),
            std::fma(a[2],b[3],std::fma(b[2],a[3],cross.z)),a[3]*b[3]-Dot3(a,b)};
}
std::array<float,3> QuaternionRotate(const Quat& q, const std::array<float,3>& v)
{
    const Vec3 first=Cross3(Vec3{q[0],q[1],q[2]},Vec3{v[0],v[1],v[2]});
    const Vec3 second=Cross3(Vec3{q[0],q[1],q[2]},Vec3{
        std::fma(q[3],v[0],first.x),std::fma(q[3],v[1],first.y),std::fma(q[3],v[2],first.z)});
    return {std::fma(2.0f,second.x,v[0]),std::fma(2.0f,second.y,v[1]),std::fma(2.0f,second.z,v[2])};
}
Quat QuaternionBlend(const Quat& first, const Quat& second, float weight)
{
    const bool positive=Dot4(first,second) > 0.0f;
    Quat rotation{};
    for (unsigned lane=0;lane<4;++lane)
        rotation[lane]=std::fma(positive ? second[lane]-first[lane] : -(second[lane]+first[lane]),weight,first[lane]);
    return Normalize4(rotation,2);
}
Mat4 SqtToMatrix(const Sqt& input)
{
    const float x=input.rotation[0],y=input.rotation[1],z=input.rotation[2],w=input.rotation[3];
    const float sx=input.scale[0],sy=input.scale[1],sz=input.scale[2];
    const float xx=x*x,yy=y*y,zz=z*z,xy=x*y,wz=w*z,xz=x*z,wy=w*y,yz=y*z,wx=w*x;
    return {{{std::fma(-(yy+zz),2.0f,1.0f)*sx,((xy+wz)*2.0f)*sx,((xz-wy)*2.0f)*sx,0.0f},
             {((xy-wz)*2.0f)*sy,std::fma(-(xx+zz),2.0f,1.0f)*sy,((yz+wx)*2.0f)*sy,0.0f},
             {((xz+wy)*2.0f)*sz,((yz-wx)*2.0f)*sz,std::fma(-(xx+yy),2.0f,1.0f)*sz,0.0f},
             {input.translation[0],input.translation[1],input.translation[2],1.0f}}};
}
Mat4 ConcatenateAffine(const Mat4& local, const Mat4& parent)
{
    Mat4 result=local;
    for (unsigned row=0;row<4;++row) for (unsigned lane=0;lane<4;++lane)
    {
        const float first=row==3 ? std::fma(parent[0][lane],local[row][0],parent[3][lane]) : parent[0][lane]*local[row][0];
        const float second=std::fma(parent[1][lane],local[row][1],first);
        result[row][lane]=std::fma(parent[2][lane],local[row][2],second);
    }
    return result;
}
Mat4 InverseAffine(const Mat4& frame)
{
    const std::array<Vec4,3> cofactors={Cross3(frame[1],frame[2]),Cross3(frame[2],frame[0]),Cross3(frame[0],frame[1])};
    const float inverse=RefinedReciprocal(Dot3(frame[0],cofactors[0]),2);
    Mat4 result{};
    for (unsigned column=0;column<3;++column)
        result[column]={cofactors[0][column]*inverse,cofactors[1][column]*inverse,cofactors[2][column]*inverse,cofactors[1][column]*inverse};
    bool finite=true;
    for (unsigned column=0;column<3;++column) for (float lane:result[column]) finite=finite && std::isfinite(lane);
    if (!finite)
    {
        // Rust's arm64 inverse kernel folds its first translation product to
        // FNMUL, then reuses the separately sign-flipped X value for the other
        // lanes. Folding those FMULs to FNMUL changes a singular result's NaN
        // sign. Preserve this operation structure without changing finite math.
        const float negative_x=-frame[3][0];
        for (unsigned lane=0;lane<4;++lane)
        {
            const float x=lane==0 ? NegatedProduct(frame[3][0],result[0][lane]) : OrderedMultiply(negative_x,result[0][lane]);
            const float y=OrderedFma(-frame[3][1],result[1][lane],x);
            result[3][lane]=OrderedFma(-frame[3][2],result[2][lane],y);
        }
        return result;
    }
    for (unsigned lane=0;lane<4;++lane)
    {
        const float x=-frame[3][0]*result[0][lane];
        const float y=std::fma(-frame[3][1],result[1][lane],x);
        result[3][lane]=std::fma(-frame[3][2],result[2][lane],y);
    }
    return result;
}
std::pair<Vec4,float> RotationAxisAngle(const Mat4& rotation)
{
    const Vec4 skew={rotation[1][2]-rotation[2][1],rotation[2][0]-rotation[0][2],rotation[0][1]-rotation[1][0],0.0f};
    const float sine_twice=Length3(skew),cosine_twice=((rotation[0][0]+rotation[1][1])+rotation[2][2])-1.0f;
    Vec4 axis{};
    if (sine_twice > 0.0f)
    {
        const float inverse=RefinedReciprocal(sine_twice,2)*1.0f;
        for (unsigned lane=0;lane<4;++lane) axis[lane]=skew[lane]*inverse;
    }
    const float ratio=std::fma(sine_twice,RefinedReciprocal(cosine_twice,1),0.0f);
    float angle=Atan(ratio);
    if (cosine_twice < 0.0f) angle+=std::copysign(Word(0x40490fdb),sine_twice);
    if (cosine_twice == 0.0f) angle=std::copysign(Word(0x3fc90fdb),sine_twice);
    if (sine_twice <= Word(0x00200000) && cosine_twice <= 0.0f)
    {
        const unsigned selected=rotation[0][0] > rotation[1][1] ? (rotation[0][0] > rotation[2][2] ? 0:2)
            : rotation[1][1] > rotation[2][2] ? 1:2;
        for (unsigned lane=0;lane<3;++lane)
        {
            const float diagonal=1.0f+rotation[selected][selected];
            axis[lane]=lane==selected ? diagonal*diagonal : rotation[selected][lane]+rotation[lane][selected];
        }
        axis[3]=axis[0];
        axis=Normalize3(axis);
    }
    return {axis,angle};
}
Mat4 AxisRotation(const Vec4& axis, float angle)
{
    const auto sc=SinCos(angle);
    const float sine=sc.first,cosine=sc.second,complement=1.0f-cosine;
    const float x=axis[0],y=axis[1],z=axis[2],sx=sine*x,sy=sine*y,sz=sine*z;
    const float tx=complement*x,ty=complement*y,tz=complement*z;
    const float xx=std::fma(tx,x,cosine),yy=std::fma(ty,y,cosine),zz=std::fma(tz,z,cosine);
    const float xy_positive=std::fma(tx,y,sz),xy_negative=ty*x-sz;
    const float xz_positive=std::fma(tz,x,sy),xz_negative=tx*z-sy;
    const float yz_positive=std::fma(ty,z,sx),yz_negative=tz*y-sx;
    return {{{xx,xy_positive,xz_negative,xx},{xy_negative,yy,yz_positive,xy_negative},
             {xz_positive,yz_negative,zz,xz_positive},{0.0f,0.0f,0.0f,0.0f}}};
}
std::pair<Mat4,float> InterpolateMatrix(const Mat4& a, const Mat4& b, float weight)
{
    if (weight >= 1.0f) return {b,0.0f};
    const Mat4 identity={{{1.0f,0.0f,0.0f,0.0f},{0.0f,1.0f,0.0f,0.0f},
                         {0.0f,0.0f,1.0f,0.0f},{0.0f,0.0f,0.0f,0.0f}}};
    Mat4 relative=identity;
    for (unsigned column=0;column<3;++column) for (unsigned lane=0;lane<4;++lane)
    {
        const float x=a[0][column]*b[0][lane];
        const float y=std::fma(a[1][column],b[1][lane],x);
        relative[column][lane]=std::fma(a[2][column],b[2][lane],y);
    }
    const auto axis_angle=RotationAxisAngle(relative);
    const float angle=axis_angle.second;
    if (weight <= 0.0f) return {a,angle};
    Mat4 output=identity;
    if (angle < Word(0x3d0efa35))
    {
        for (unsigned column=0;column<3;++column)
        {
            Vec4 value{};
            for (unsigned lane=0;lane<4;++lane) value[lane]=std::fma(b[column][lane]-a[column][lane],weight,a[column][lane]);
            output[column]=Normalize3(value);
        }
    }
    else
    {
        const Mat4 rotation=AxisRotation(axis_angle.first,angle*weight);
        for (unsigned column=0;column<3;++column) for (unsigned lane=0;lane<4;++lane)
        {
            const float x=a[column][0]*rotation[0][lane];
            const float y=std::fma(a[column][1],rotation[1][lane],x);
            output[column][lane]=std::fma(a[column][2],rotation[2][lane],y);
        }
    }
    for (unsigned lane=0;lane<4;++lane) output[3][lane]=std::fma(b[3][lane]-a[3][lane],weight,a[3][lane]);
    return {output,angle-angle*weight};
}
Mat4 InterpolateAffine(const Mat4& a, const Mat4& b, float weight)
{
    Vec4 translation{};
    for (unsigned lane=0;lane<4;++lane) translation[lane]=std::fma(a[3][lane],1.0f-weight,b[3][lane]*weight);
    Mat4 output=InterpolateMatrix(a,b,weight).first;
    output[3]=translation;
    return output;
}
}

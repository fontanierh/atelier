#include "BoardPose.h"
#include "HookDrive.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Scalar(std::uint32_t bits) {float v;std::memcpy(&v,&bits,4);return v;}
std::uint32_t Word(float v) {std::uint32_t bits;std::memcpy(&bits,&v,4);return bits;}
Vec4 Load(const std::uint32_t* p) {return {Scalar(p[0]),Scalar(p[1]),Scalar(p[2]),Scalar(p[3])};}
Mat4 Matrix(PoseMatrix input) {Mat4 m;for (unsigned i=0;i<4;++i) m[i]=Load(input.data()+i*4);return m;}
PoseMatrix Words(Mat4 matrix) {PoseMatrix p;for (unsigned i=0;i<16;++i) p[i]=Word(matrix[i/4][i%4]);return p;}
Vec4 Broadcast(float v) {return {v,v,v,v};}
Vec4 Sub(Vec4 a,Vec4 b) {return {a[0]-b[0],a[1]-b[1],a[2]-b[2],a[3]-b[3]};}
Vec4 Mul(Vec4 a,Vec4 b) {return {a[0]*b[0],a[1]*b[1],a[2]*b[2],a[3]*b[3]};}
Vec4 Madd4(Vec4 a,Vec4 b,Vec4 c) {return {std::fma(a[0],b[0],c[0]),std::fma(a[1],b[1],c[1]),std::fma(a[2],b[2],c[2]),std::fma(a[3],b[3],c[3])};}
Vec4 Perm(Vec4 a,std::array<std::size_t,4> p) {return {a[p[0]],a[p[1]],a[p[2]],a[p[3]]};}
Vec4 Normalize(Vec4 v,bool four=false) {return Mul(v,Broadcast(InverseLengthSquared(four ? Dot4(v,v):Dot3(v,v),2)));}
Mat4 Compose(Mat4 a,Mat4 b)
{
    Mat4 out;
    for (unsigned i=0;i<4;++i)
    {
        const Vec4 first=i==3 ? Madd4(Broadcast(b[i][0]),a[0],a[3]):Mul(Broadcast(b[i][0]),a[0]);
        out[i]=Madd4(Broadcast(b[i][2]),a[2],Madd4(Broadcast(b[i][1]),a[1],first));
    }
    return out;
}
Mat4 InverseRigid(Mat4 m)
{
    Mat4 out{};for (unsigned i=0;i<3;++i) out[i]={m[0][i],m[1][i],m[2][i],0};
    const Vec4 negative=Sub({},m[3]);out[3]=Madd4(Broadcast(negative[0]),out[0],Madd4(Broadcast(negative[1]),out[1],Mul(Broadcast(negative[2]),out[2])));return out;
}
Quat Quaternion(Mat4 m)
{
    std::array<std::uint32_t,12> basis;for (unsigned i=0;i<12;++i) basis[i]=Word(m[i/4][i%4]);
    PoseMatrix frames{};SetChildAngularFrame(frames,basis);return Normalize(Load(frames.data()),true);
}
void StoreXyz(std::uint32_t* p,Vec4 v) {for (unsigned i=0;i<3;++i) p[i]=Word(v[i]);}
}
PoseMatrix OrthonormalizeRotation(PoseMatrix input)
{
    const auto original=Matrix(input);auto out=original;
    for (int axis=2;axis>=0;--axis)
    {
        Vec4 residual=original[axis];
        for (int other=2;other>axis;--other) residual=Sub(residual,Mul(out[other],Broadcast(Dot3(out[other],original[axis]))));
        out[axis]=Normalize(residual);
    }
    return Words(out);
}
PoseMatrix OrthonormalizePartBasis(PoseMatrix input)
{
    auto m=Matrix(input);std::array<float,3> squares,magnitudes;
    for (unsigned i=0;i<3;++i) squares[i]=Dot3(m[i],m[i]);
    for (unsigned i=0;i<3;++i) {const float root=squares[i]*InverseLengthSquared(squares[i],2);magnitudes[i]=squares[i]==0.0f ? 0.0f:root;}
    for (unsigned i=0;i<3;++i) m[i]=Mul(m[i],Broadcast(InverseLengthSquared(squares[i],2)));
    unsigned u,v,w;
    if (!(magnitudes[0]>0.0f)) {u=1;v=2;w=0;}
    else if (!(magnitudes[1]>0.0f)) {u=2;v=0;w=1;}
    else if (!(magnitudes[2]>0.0f)) {u=0;v=1;w=2;}
    else
    {
        const float ca=std::fabs(Dot3(m[2],m[0])),bc=std::fabs(Dot3(m[1],m[2])),ab=std::fabs(Dot3(m[0],m[1]));
        if (ca>bc) {if (ab>bc) {u=1;v=2;w=0;} else {u=0;v=1;w=2;}}
        else if (ab>ca) {u=2;v=0;w=1;} else {u=0;v=1;w=2;}
    }
    m[w]=Normalize(Cross3(m[u],m[v]));m[v]=Normalize(Cross3(m[w],m[u]));return Words(m);
}
PoseMatrix PartTransform(const PartPose& part)
{
    if (!part.body) return part.transform;const auto& body=*part.body;
    const Mat4 m={Load(body.data()+16),Load(body.data()+20),Load(body.data()+24),Load(body.data()+4)};
    return Words(part.local_mass_frame ? Compose(m,Matrix(*part.local_mass_frame)):m);
}
void SetPartTransform(PartPose& part,PoseMatrix requested)
{
    if (part.body)
    {
        auto& body=*part.body;const auto raw=part.local_mass_frame ? Words(Compose(Matrix(requested),InverseRigid(Matrix(*part.local_mass_frame)))):requested;
        const auto m=Matrix(OrthonormalizePartBasis(raw));
        for (unsigned i=0;i<4;++i) StoreXyz(body.data()+(i==3 ? 4:16+i*4),m[i]);
        const auto q=Quaternion(m);for (unsigned i=0;i<4;++i) body[i]=Word(q[i]);
        if (part.inertia)
        {
            const auto& inertia=*part.inertia;const auto ri=m[0],up=m[1],at=m[2];
            const auto r=Mul(ri,Broadcast(Scalar(inertia[0]))),u=Mul(up,Broadcast(Scalar(inertia[1]))),a=Mul(at,Broadcast(Scalar(inertia[2])));
            const auto full=Madd4(a,Broadcast(at[0]),Madd4(r,Broadcast(ri[0]),Mul(u,Broadcast(up[0]))));
            auto p=[](Vec4 v){return Perm(v,{2,1,1,3});};auto s=[](Vec4 v){return Perm(v,{2,1,2,3});};
            const auto split=Madd4(p(at),s(a),Madd4(p(ri),s(r),Mul(p(up),s(u))));
            StoreXyz(body.data()+28,full);StoreXyz(body.data()+32,split);body[31]=inertia[4];
        }
    }
    part.transform=requested;
}
void SetBoardTransform(std::array<PartPose,7>& parts,PartPose& hook,PoseMatrix requested)
{
    const auto old_deck=Matrix(PartTransform(parts[6]));const auto normalized=OrthonormalizeRotation(requested);
    const auto delta=Compose(Matrix(normalized),InverseRigid(old_deck));SetPartTransform(parts[6],normalized);
    for (unsigned i=0;i<6;++i) SetPartTransform(parts[i],OrthonormalizeRotation(Words(Compose(delta,Matrix(PartTransform(parts[i]))))));
    SetPartTransform(hook,requested);
}
}

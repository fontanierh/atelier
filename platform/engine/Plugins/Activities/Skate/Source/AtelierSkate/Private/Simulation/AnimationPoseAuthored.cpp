#include "AnimationPose.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
// Authored matrix conversion follows glam 0.32.1's arm64 arithmetic, including
// pairwise SIMD dot sums and unfused products. The simulation ACS math stays separate.
// Algebra adapted from glam (MIT OR Apache-2.0), https://github.com/bitshifter/glam-rs.
// The following permission notice accompanies the adapted glam algebra:
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
// of the Software, and to permit persons to whom the Software is furnished to do
// so, subject to the following conditions: The above copyright notice and this
// permission notice shall be included in all copies or substantial portions of
// the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
// EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
// MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO
// EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES
// OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
// ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
// DEALINGS IN THE SOFTWARE.
namespace atelier::skate
{
namespace
{
float Dot(const Vec4& a,const Vec4& b) {return (a[0]*b[0]+a[1]*b[1])+(a[2]*b[2]+a[3]*b[3]);}
float Determinant(const Mat4& m)
{
    const auto a2323=m[2][2]*m[3][3]-m[2][3]*m[3][2],a1323=m[2][1]*m[3][3]-m[2][3]*m[3][1],a1223=m[2][1]*m[3][2]-m[2][2]*m[3][1];
    const auto a0323=m[2][0]*m[3][3]-m[2][3]*m[3][0],a0223=m[2][0]*m[3][2]-m[2][2]*m[3][0],a0123=m[2][0]*m[3][1]-m[2][1]*m[3][0];
    return m[0][0]*(m[1][1]*a2323-m[1][2]*a1323+m[1][3]*a1223)-m[0][1]*(m[1][0]*a2323-m[1][2]*a0323+m[1][3]*a0223)+m[0][2]*(m[1][0]*a1323-m[1][1]*a0323+m[1][3]*a0123)-m[0][3]*(m[1][0]*a1223-m[1][1]*a0223+m[1][2]*a0123);
}
Quat RotationAxes(const Mat4& m)
{
    const auto m00=m[0][0],m01=m[0][1],m02=m[0][2],m10=m[1][0],m11=m[1][1],m12=m[1][2],m20=m[2][0],m21=m[2][1],m22=m[2][2];
    if (m22<=0) {const auto dif=m11-m00,om=1.0f-m22;if (dif<=0) {const auto four=om-dif,inv=0.5f/std::sqrt(four);return {four*inv,(m01+m10)*inv,(m02+m20)*inv,(m12-m21)*inv};}const auto four=om+dif,inv=0.5f/std::sqrt(four);return {(m01+m10)*inv,four*inv,(m12+m21)*inv,(m20-m02)*inv};}
    const auto sum=m11+m00,op=1.0f+m22;if (sum<=0) {const auto four=op-sum,inv=0.5f/std::sqrt(four);return {(m02+m20)*inv,(m12+m21)*inv,four*inv,(m01-m10)*inv};}const auto four=op+sum,inv=0.5f/std::sqrt(four);return {(m12-m21)*inv,(m20-m02)*inv,(m01-m10)*inv,four*inv};
}
Sqt Decompose(const Mat4& m)
{
    const auto det=Determinant(m);Sqt out;out.scale={std::sqrt(Dot(m[0],m[0]))*(std::isnan(det)?det:std::copysign(1.0f,det)),std::sqrt(Dot(m[1],m[1])),std::sqrt(Dot(m[2],m[2])),1};
    auto axes=m;for (std::size_t c=0;c<3;++c) {const auto inverse=1.0f/out.scale[c];for (auto& value:axes[c]) value*=inverse;}out.rotation=RotationAxes(axes);out.translation=m[3];return out;
}
Mat4 Matrix(Sqt s)
{
    const auto x=s.rotation[0],y=s.rotation[1],z=s.rotation[2],w=s.rotation[3];const auto x2=x+x,y2=y+y,z2=z+z;
    const auto xx=x*x2,xy=x*y2,xz=x*z2,yy=y*y2,yz=y*z2,zz=z*z2,wx=w*x2,wy=w*y2,wz=w*z2;
    Mat4 out{{{1.0f-(yy+zz),xy+wz,xz-wy,0},{xy-wz,1.0f-(xx+zz),yz+wx,0},{xz+wy,yz-wx,1.0f-(xx+yy),0},{s.translation[0],s.translation[1],s.translation[2],1}}};
    for (std::size_t c=0;c<3;++c) for (auto& value:out[c]) value*=s.scale[c];return out;
}
Mat4 Product(const Mat4& a,const Mat4& b)
{
    Mat4 out{};for (std::size_t c=0;c<4;++c) for (std::size_t r=0;r<4;++r) {auto v=a[0][r]*b[c][0];v=v+a[1][r]*b[c][1];v=v+a[2][r]*b[c][2];out[c][r]=v+a[3][r]*b[c][3];}return out;
}
Mat4 Inverse(const Mat4& m)
{
    const float m00=m[0][0],m01=m[0][1],m02=m[0][2],m03=m[0][3],m10=m[1][0],m11=m[1][1],m12=m[1][2],m13=m[1][3],m20=m[2][0],m21=m[2][1],m22=m[2][2],m23=m[2][3],m30=m[3][0],m31=m[3][1],m32=m[3][2],m33=m[3][3];
    const auto c00=m22*m33-m32*m23,c02=m12*m33-m32*m13,c03=m12*m23-m22*m13,c04=m21*m33-m31*m23,c06=m11*m33-m31*m13,c07=m11*m23-m21*m13,c08=m21*m32-m31*m22,c10=m11*m32-m31*m12,c11=m11*m22-m21*m12,c12=m20*m33-m30*m23,c14=m10*m33-m30*m13,c15=m10*m23-m20*m13,c16=m20*m32-m30*m22,c18=m10*m32-m30*m12,c19=m10*m22-m20*m12,c20=m20*m31-m30*m21,c22=m10*m31-m30*m11,c23=m10*m21-m20*m11;
    const Vec4 f0{c00,c00,c02,c03},f1{c04,c04,c06,c07},f2{c08,c08,c10,c11},f3{c12,c12,c14,c15},f4{c16,c16,c18,c19},f5{c20,c20,c22,c23},v0{m10,m00,m00,m00},v1{m11,m01,m01,m01},v2{m12,m02,m02,m02},v3{m13,m03,m03,m03};
    Mat4 out;for (std::size_t i=0;i<4;++i) {const auto sign=i%2? -1.0f:1.0f;out[0][i]=((v1[i]*f0[i]-v2[i]*f1[i])+v3[i]*f2[i])*sign;out[1][i]=((v0[i]*f0[i]-v2[i]*f3[i])+v3[i]*f4[i])*(-sign);out[2][i]=((v0[i]*f1[i]-v1[i]*f3[i])+v3[i]*f5[i])*sign;out[3][i]=((v0[i]*f2[i]-v1[i]*f4[i])+v2[i]*f5[i])*(-sign);}
    const Vec4 row{out[0][0],out[1][0],out[2][0],out[3][0]};const auto reciprocal=1.0f/Dot(m[0],row);for (auto& column:out) for (auto& value:column) value*=reciprocal;return out;
}
Quat Multiply(const Quat& a,const Quat& b)
{
    const Vec4 bx{b[3],-b[2],b[1],-b[0]},by{b[2],b[3],-b[0],-b[1]},bz{-b[1],b[0],b[3],-b[2]};Quat q;
    for (std::size_t i=0;i<4;++i) q[i]=(a[3]*b[i]+a[0]*bx[i])+(a[1]*by[i]+a[2]*bz[i]);return q;
}
std::array<float,3> Rotate(const Quat& q,const std::array<float,3>& v)
{
    const Vec4 b{q[0],q[1],q[2],0},a{v[0],v[1],v[2],0};const auto first=q[3]*q[3]-Dot(b,b),second=Dot(a,b)*2.0f,third=q[3]*2.0f;
    const std::array<float,3> cross{b[1]*v[2]-b[2]*v[1],b[2]*v[0]-b[0]*v[2],b[0]*v[1]-b[1]*v[0]};std::array<float,3> out{};
    for (std::size_t i=0;i<3;++i) out[i]=(v[i]*first+b[i]*second)+cross[i]*third;return out;
}
SampleWords RemoveReference(const Mat4& local,Sqt reference)
{
    auto s=Decompose(local);const Quat inverse{-reference.rotation[0],-reference.rotation[1],-reference.rotation[2],reference.rotation[3]};
    const auto translation=Rotate(inverse,{s.translation[0]-reference.translation[0],s.translation[1]-reference.translation[1],s.translation[2]-reference.translation[2]});
    auto rotation=Multiply(inverse,s.rotation);const auto norm=1.0f/std::sqrt(Dot(rotation,rotation));for (auto& f:rotation) f*=norm;
    const std::array<float,10> values{s.scale[0]/reference.scale[0],s.scale[1]/reference.scale[1],s.scale[2]/reference.scale[2],rotation[0],rotation[1],rotation[2],rotation[3],translation[0],translation[1],translation[2]};SampleWords out;for (std::size_t i=0;i<10;++i) std::memcpy(&out[i],&values[i],4);return out;
}
bool ValidMatrix(const Mat4& m)
{
    const auto s=Decompose(m);for (const auto& c:m) for (auto f:c) if (!std::isfinite(f)) return false;
    if (Determinant(m)<=0||std::min({s.scale[0],s.scale[1],s.scale[2]})<0.9f||std::max({s.scale[0],s.scale[1],s.scale[2]})>1.1f) return false;
    for (auto f:s.rotation) if (!std::isfinite(f)) return false;
    return !(std::fabs(m[3][3]-1.0f)>0.001f||std::fabs(m[0][3])+std::fabs(m[1][3])+std::fabs(m[2][3])>0.001f);
}
}
bool BakeAuthoredAnimationClips(const AuthoredAnimationDocument& d,const AnimationPoseFrames& frames,AnimationClipReplacements& output,std::string& error)
{
    std::vector<std::string> names;for (const auto& b:frames.rig.bones) names.push_back(b.name);
    if (d.version!=1||d.bone_names!=names||d.clips.size()>32) {error="Authored clip format or skeleton mismatch";return false;}
    const auto* bind=frames.NamedPose("RIG_TPOSE",error);if (!bind) return false;
    auto index=[&](std::string_view n,std::size_t& out) {const auto i=std::find(names.begin(),names.end(),n);if (i==names.end()) {error="Missing "+std::string(n);return false;}out=std::size_t(i-names.begin());return true;};
    std::size_t hips=0,board=0;std::array<std::pair<std::size_t,std::size_t>,4> helpers{};
    if (!index("HIPS",hips)||!index("SKATEBOARD_ROOT",board)) return false;
    const std::array<std::pair<const char*,const char*>,4> hn{{{"RIGHTTOEBASE_REPARENTED","RIGHTTOEBASE"},{"LEFTTOEBASE_REPARENTED","LEFTTOEBASE"},{"RIGHTHAND_REPARENTED","RIGHTHAND"},{"LEFTHAND_REPARENTED","LEFTHAND"}}};
    for (std::size_t i=0;i<4;++i) if (!index(hn[i].first,helpers[i].first)||!index(hn[i].second,helpers[i].second)) return false;
    AnimationClipReplacements baked;
    for (const auto& item:d.clips)
    {
        const auto& name=item.first;const auto& authored=item.second;
        if (name!="R_ANTIC_OLLIE_N_0_INTO"&&name!="R_ANTIC_OLLIE_N_0_CYC"&&name!="R_ANTIC_360SHUVIT_N_0_CYC"&&name!="360FLIP_D_HIGH_G"&&name!="360FLIP_D_HIGH_A"&&name!="360FLIP_D_LOW_G"&&name!="360FLIP_D_LOW_A") {error="Unsupported authored slot "+name;return false;}
        const auto* stock=frames.Clip(name,error);if (!stock) return false;float fps;std::memcpy(&fps,&stock->fps_bits,4);
        if (authored.fps!=fps||authored.frames.size()!=stock->frame_count) {error=name+": timing differs from stock slot";return false;}
        AnimationClipReplacement clip;clip.stock=frames.clips.find(stock->name)->second;
        for (std::size_t f=0;f<stock->frame_count;++f)
        {
            const auto& absolute=authored.frames[f];if (absolute.size()!=names.size()) {error=name+": missing bones";return false;}
            for (const auto& matrix:absolute) if (!ValidMatrix(matrix)) {error=name+": invalid joint matrix";return false;}
            auto globals=absolute;std::vector<SampleWords> row;for (std::size_t b=0;b<stock->bone_count;++b) row.push_back(stock->Sample(std::uint32_t(f),std::uint32_t(b)));
            const Mat4 identity{{{1,0,0,0},{0,1,0,0},{0,0,1,0},{0,0,0,1}}};std::vector<Mat4> stock_globals(row.size(),identity);
            for (std::size_t b=1;b<row.size();++b) {const auto p=frames.rig.bones[b].parent;const auto local=Matrix(AddAnimationPose(DecodeSampleWords(row[b]),DecodeSampleWords(bind->samples[b]),true));stock_globals[b]=p>0?Product(stock_globals[std::size_t(p)],local):local;}
            auto helper_min=helpers[0].first;for (const auto& h:helpers) helper_min=std::min(helper_min,h.first);for (auto b=board;b<helper_min;++b) globals[b]=stock_globals[b];
            for (const auto& h:helpers) globals[h.first]=globals[h.second];
            const auto apply=[&](std::size_t b) {const auto p=frames.rig.bones[b].parent;const auto local=p>0?Product(Inverse(globals[std::size_t(p)]),globals[b]):globals[b];row[b]=RemoveReference(local,DecodeSampleWords(bind->samples[b]));};
            for (auto b=hips;b<board;++b) apply(b);for (const auto& h:helpers) apply(h.first);clip.frames.push_back(std::move(row));
        }baked.emplace(name,std::move(clip));
    }output=std::move(baked);error.clear();return true;
}
}

#include "NetworkProxies.h"
#include "WorldGeometry.h"
#include <cstdlib>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
// Glam 0.32.1 algebra below uses true sqrt/reciprocal and unfused arm64 order.
// Adapted from glam (MIT OR Apache-2.0), https://github.com/bitshifter/glam-rs.
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
float DotGlam(Vec3 a,Vec3 b){return (a.x*b.x+a.y*b.y)+a.z*b.z;}
float DotGlam(Vec4 a,Vec4 b){return (a[0]*b[0]+a[1]*b[1])+(a[2]*b[2]+a[3]*b[3]);}
Vec3 Add(Vec3 a,Vec3 b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
Vec3 Sub(Vec3 a,Vec3 b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
float Length(Vec3 v){return std::sqrt(DotGlam(v,v));}
Quat Normalize(Quat q){const float inverse=1.0f/std::sqrt(DotGlam(q,q));for(auto& v:q)v*=inverse;return q;}
Basis3 Basis(Quat q)
{
    const float x=q[0],y=q[1],z=q[2],w=q[3],x2=x+x,y2=y+y,z2=z+z;
    const float xx=x*x2,xy=x*y2,xz=x*z2,yy=y*y2,yz=y*z2,zz=z*z2,wx=w*x2,wy=w*y2,wz=w*z2;
    Basis3 b;b.columns={{{1.0f-(yy+zz),xy+wz,xz-wy},{xy-wz,1.0f-(xx+zz),yz+wx},{xz+wy,yz-wx,1.0f-(xx+yy)}}};return b;
}
NetworkBodyPose BodyPose(const BodySnapshot& b){return {b.rates.position,Normalize(b.rates.orientation)};}
Mat4 Matrix(NetworkBodyPose p)
{
    const auto basis=Basis(Normalize(p.orientation));Mat4 m;
    for(unsigned i=0;i<3;++i)m[i]={basis.columns[i][0],basis.columns[i][1],basis.columns[i][2],0.0f};
    m[3]={p.position.x,p.position.y,p.position.z,1.0f};return m;
}
Mat4 Inverse(const Mat4& m)
{
    const float m00=m[0][0],m01=m[0][1],m02=m[0][2],m03=m[0][3],m10=m[1][0],m11=m[1][1],m12=m[1][2],m13=m[1][3],m20=m[2][0],m21=m[2][1],m22=m[2][2],m23=m[2][3],m30=m[3][0],m31=m[3][1],m32=m[3][2],m33=m[3][3];
    const auto c00=m22*m33-m32*m23,c02=m12*m33-m32*m13,c03=m12*m23-m22*m13,c04=m21*m33-m31*m23,c06=m11*m33-m31*m13,c07=m11*m23-m21*m13,c08=m21*m32-m31*m22,c10=m11*m32-m31*m12,c11=m11*m22-m21*m12,c12=m20*m33-m30*m23,c14=m10*m33-m30*m13,c15=m10*m23-m20*m13,c16=m20*m32-m30*m22,c18=m10*m32-m30*m12,c19=m10*m22-m20*m12,c20=m20*m31-m30*m21,c22=m10*m31-m30*m11,c23=m10*m21-m20*m11;
    const Vec4 f0{c00,c00,c02,c03},f1{c04,c04,c06,c07},f2{c08,c08,c10,c11},f3{c12,c12,c14,c15},f4{c16,c16,c18,c19},f5{c20,c20,c22,c23},v0{m10,m00,m00,m00},v1{m11,m01,m01,m01},v2{m12,m02,m02,m02},v3{m13,m03,m03,m03};
    Mat4 out;for(unsigned i=0;i<4;++i){const float sign=i%2?-1.0f:1.0f;out[0][i]=((v1[i]*f0[i]-v2[i]*f1[i])+v3[i]*f2[i])*sign;out[1][i]=((v0[i]*f0[i]-v2[i]*f3[i])+v3[i]*f4[i])*(-sign);out[2][i]=((v0[i]*f1[i]-v1[i]*f3[i])+v3[i]*f5[i])*sign;out[3][i]=((v0[i]*f2[i]-v1[i]*f4[i])+v2[i]*f5[i])*(-sign);}
    const Vec4 row{out[0][0],out[1][0],out[2][0],out[3][0]};const float reciprocal=1.0f/DotGlam(m[0],row);
    for(auto& column:out)for(auto& v:column)v*=reciprocal;return out;
}
Vec3 Direction(const Mat4& m,Vec3 v)
{
    const float x=m[0][0]*v.x,y=m[0][1]*v.x,z=m[0][2]*v.x;
    return {m[2][0]*v.z+(m[1][0]*v.y+x),m[2][1]*v.z+(m[1][1]*v.y+y),m[2][2]*v.z+(m[1][2]*v.y+z)};
}
Vec3 Point(const Mat4& m,Vec3 v)
{const auto d=Direction(m,v);return {m[3][0]+d.x,m[3][1]+d.y,m[3][2]+d.z};}
ContactPrimitive Transform(const ContactPrimitive& shape,const Mat4& m)
{
    if(const auto* s=std::get_if<Sphere>(&shape))return Sphere{Point(m,s->center),s->radius};
    if(const auto* c=std::get_if<Capsule>(&shape))return Capsule{Point(m,c->center),Direction(m,c->axis),c->half_length,c->radius};
    if(const auto* box=std::get_if<RoundedBox>(&shape))
    {
        Basis3 basis;for(unsigned c=0;c<3;++c)
        {
            const auto v=box->basis.columns[c];
            for(unsigned r=0;r<3;++r)basis.columns[c][r]=(m[0][r]*v[0]+m[1][r]*v[1])+m[2][r]*v[2];
        }
        return RoundedBox{Point(m,box->center),basis,box->half_extents,box->radius};
    }
    const auto& t=std::get<Triangle>(shape);std::array<Vec3,3> vertices;for(unsigned i=0;i<3;++i)vertices[i]=Point(m,t.vertices[i]);
    return TriangleFromVolume(vertices,t.fatness,{-1.0f,-1.0f,-1.0f},0);
}
const BodySnapshot& Template(const NetworkProxyContext& context,std::size_t i)
{return i<7?context.board[i]:context.skeleton[i-7];}
}
NetworkCollisionSchema NetworkCollisionSchema::FromWorldVolumes(const std::vector<BoardWorldVolume>& world,
    const std::array<BodySnapshot,7>& board,const std::array<BodySnapshot,26>& skeleton,std::uint64_t fingerprint)
{
    NetworkCollisionSchema schema;schema.fingerprint=fingerprint;
    for(auto volume:world)
    {
        const auto body=CollisionBody::FromContactId(volume.body_contact_id);std::size_t index;
        if(body.kind==CollisionBody::Kind::Board && body.index<7)index=body.index;
        else if(body.kind==CollisionBody::Kind::Attached && body.index<26)index=body.index+7;
        else std::abort();
        const auto& state=index<7?board[index]:skeleton[index-7];volume.primitive=Transform(volume.primitive,Inverse(Matrix(BodyPose(state))));
        schema.volumes.emplace_back(index,volume);
    }
    return schema;
}
std::pair<Vec3,float> RemotePrimitiveBounds(const ContactPrimitive& primitive)
{
    if(const auto* s=std::get_if<Sphere>(&primitive))return {s->center,s->radius};
    if(const auto* c=std::get_if<Capsule>(&primitive))return {c->center,c->half_length+c->radius};
    if(const auto* b=std::get_if<RoundedBox>(&primitive))return {b->center,Length(b->half_extents)+b->radius};
    const auto& t=std::get<Triangle>(primitive);const auto sum=Add(Add(t.vertices[0],t.vertices[1]),t.vertices[2]);
    const Vec3 center{sum.x/3.0f,sum.y/3.0f,sum.z/3.0f};float radius=0.0f;
    for(const auto vertex:t.vertices)radius=std::fmax(radius,Length(Sub(vertex,center)));
    return {center,radius+t.fatness};
}
void NetworkProxies::Append(const NetworkBodyState& frame,const NetworkCollisionSchema& schema,const NetworkProxyContext& context,float age)
{
    bool nearby=false;
    for(const auto& wire:frame.bodies)
    {
        for(std::size_t i=0;i<33;++i){const auto delta=Sub(wire.pose.position,Template(context,i).rates.position);if(DotGlam(delta,delta)<64.0f){nearby=true;break;}}
        if(nearby)break;
    }
    if(!nearby)return;
    const auto base=26+context.target_count+bodies.size(),body_start=bodies.size();
    for(std::size_t i=0;i<33 && i<frame.bodies.size();++i)
    {
        auto b=Template(context,i);const auto& wire=frame.bodies[i];
        if(i<7)b.inertia=context.board_masses[i].dynamics;
        else
        {
            const auto& part=context.definition.parts[i-7];const bool ragdoll=(frame.enabled&(std::uint64_t(1)<<63)) && i-7>=1 && i-7<24;
            b.inertia=ragdoll?part.ragdoll.dynamics:part.animated.dynamics;
            b.inertia.inverse_mass=ragdoll?part.inverse_mass_ragdoll:part.inverse_mass_animated;
        }
        const auto q=Normalize(wire.pose.orientation);b.rates.orientation=q;b.rates.basis=Basis(q);
        b.rates.world_inverse_inertia=WorldInverseInertia(b.rates.basis,b.inertia.inverse_tensor);
        b.rates.position=Add(wire.pose.position,{wire.velocity.x*age,wire.velocity.y*age,wire.velocity.z*age});
        b.rates.linear_velocity=wire.velocity;b.rates.angular_velocity=wire.angular;
        b.rates.force_acceleration={};b.rates.torque_acceleration={};b.state_flags=4;bodies.push_back(b);
    }
    for(const auto& entry:schema.volumes)
    {
        const auto i=entry.first;if(i>=64)std::abort();if(!(frame.enabled&(std::uint64_t(1)<<i)))continue;
        if(body_start+i>=bodies.size())std::abort();const auto& b=bodies[body_start+i];
        auto v=entry.second;v.body_contact_id=CollisionBody::Attached(base+i).ContactId();v.primitive=Transform(v.primitive,Matrix(BodyPose(b)));v.linear_velocity=b.rates.linear_velocity;volumes.push_back(v);
    }
}
std::size_t AppendRemoteContacts(std::vector<BoardCollision>& contacts,const std::vector<BoardWorldVolume>& board,
    const std::vector<BoardWorldVolume>& rider,const std::vector<BoardWorldVolume>& remote)
{
    const auto before=contacts.size();
    for(const auto* local:{&board,&rider})for(const auto& a:*local)for(const auto& b:remote)
    {
        const auto [ac,ar]=RemotePrimitiveBounds(a.primitive);const auto [bc,br]=RemotePrimitiveBounds(b.primitive);
        const auto delta=Sub(ac,bc);const float radius=(ar+br)+0.05f;
        if(DotGlam(delta,delta)<=radius*radius)AppendPrimitivePairContacts(contacts,a,b);
    }
    return contacts.size()-before;
}
}

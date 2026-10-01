// SPDX-License-Identifier: Apache-2.0
#include "WorldPrimitiveContact.h"
#include "WorldGeometry.h"
#include "PrimitiveGeometry.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
float Scalar(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
Vec4 Lanes(Vec3 value,float w) {return {value.x,value.y,value.z,w};}
Vec3 Xyz(Vec4 value) {return {value[0],value[1],value[2]};}
Vec4 Load(const std::uint32_t* words) {return {Scalar(words[0]),Scalar(words[1]),Scalar(words[2]),Scalar(words[3])};}
void Store(std::uint32_t* output,Vec4 value) {for (unsigned i=0;i<4;++i) output[i]=primitive_geometry::Word(value[i]);}
Vec4 Scale4(Vec4 value,float scalar) {return {value[0]*scalar,value[1]*scalar,value[2]*scalar,value[3]*scalar};}
Vec4 Sub(Vec4 a,Vec4 b) {return {a[0]-b[0],a[1]-b[1],a[2]-b[2],a[3]-b[3]};}
Vec4 Madd4(Vec4 a,float scalar,Vec4 b)
{return {std::fma(a[0],scalar,b[0]),std::fma(a[1],scalar,b[1]),std::fma(a[2],scalar,b[2]),std::fma(a[3],scalar,b[3])};}
DirectionWords Flip(DirectionWords direction) {for (auto& word:direction) word^=0x80000000u;return direction;}
}
float WorldSeparationLimit(Vec3 velocity,Vec3 triangle_normal,float padding,float maximum)
{
    const Vec3 negative={-triangle_normal.x,-triangle_normal.y,-triangle_normal.z};
    const float approach=Dot3(negative,Scale(velocity,Scalar(0x3c888889)));
    const float positive=-approach>=0.0f ? 0.0f:approach,limited=maximum-positive>=0.0f ? positive:maximum;
    return limited+padding;
}
Triangle TransformTriangleVolume(const std::array<Vec3,3>& vertices,float fatness,const std::array<float,3>& edge_cosines,
                                 std::uint32_t volume_flags,const AffineTransform& transform)
{
    const auto local=TriangleFromVolume(vertices,fatness,edge_cosines,volume_flags);std::array<Vec4,3> axes;
    for (unsigned i=0;i<3;++i) {const auto& c=transform.basis.columns[i];axes[i]={c[0],c[1],c[2],0};}
    std::array<Vec3,3> world;
    for (unsigned i=0;i<3;++i)
    {
        const auto v=vertices[i];world[i]=Xyz(Madd4(axes[2],v.z,Madd4(axes[1],v.y,Madd4(axes[0],v.x,Lanes(transform.translation,1)))));
    }
    const auto n=local.feature.normal;const auto normal=Xyz(Madd4(axes[2],n.z,Madd4(axes[1],n.y,Scale4(axes[0],n.x))));
    auto result=TriangleFromVolume(world,fatness,edge_cosines,volume_flags);result.feature.normal=normal;return result;
}
std::optional<PrimitiveContactManifold> PrimitiveTriangleWorldContacts(const ContactPrimitive& primitive,const Triangle& triangle,
                                                                     Vec3 velocity,WorldContactSettings settings)
{
    const float limit=WorldSeparationLimit(velocity,triangle.feature.normal,settings.volume_padding,settings.maximum_separating_distance);
    const auto [a,a_kind]=primitive_geometry::Pack(primitive);const auto [b,b_kind]=primitive_geometry::Pack(ContactPrimitive{triangle});
    auto best=a_kind==PrimitiveKind::Box ? primitive_geometry::TriangleBox(b,a):BestSeparatingDirection(a,a_kind,b,b_kind);
    if (a_kind==PrimitiveKind::Box) best.second=Flip(best.second);
    const float separation=Scalar(best.first[0]),fat_a=Scalar(a[32]),fat_b=Scalar(b[32]);
    if (separation>(fat_b+limit)+fat_a) return std::nullopt;
    auto feature_a=primitive_geometry::Maximum(a,a_kind,1,best.second),feature_b=primitive_geometry::Maximum(b,b_kind,0,Flip(best.second));FeaturePrism prism{};
    if (!FindFeatureIntersectionPrism(prism,feature_a,feature_b,best.second)) return std::nullopt;
    PrimitiveContactManifold result;result.count=prism[132];Vec4 normal=Load(best.second.data());
    if (result.count==1)
    {
        const auto delta=Sub(Load(prism.data()+64),Load(prism.data()));const float squared=Dot3(delta,delta),inverse=InverseLengthSquared(squared,2);
        const float length=squared==0.0f ? 0.0f:squared*inverse;
        if (length>Scalar(0x34000000)) {Store(prism.data()+128,Scale4(delta,inverse));prism[133]=1;}
    }
    if (prism[133])
    {
        DirectionWords direction;for (unsigned i=0;i<4;++i) direction[i]=prism[128+i];ProjectionInterval ai{},bi{};
        ProjectDirection(a,a_kind,direction,ai);ProjectDirection(b,b_kind,direction,bi);
        const float forward=Scalar(ai[0])-Scalar(bi[4]),reverse=Scalar(bi[0])-Scalar(ai[4]);const bool flip=forward>reverse;
        if ((flip ? forward:reverse)>=separation) normal=Load((flip ? Flip(direction):direction).data());
    }
    for (std::size_t i=0;i<result.count;++i) result.points[i]={Xyz(Load(prism.data()+i*4)),Xyz(Load(prism.data()+64+i*4))};
    Vec3 pair_normal=Xyz(normal);
    if (!FixUpTriangle(triangle.feature,pair_normal,result.points.data(),result.count,
        {true,settings.edge_cos_bend_normal_threshold,settings.convexity_epsilon,settings.is_object})) return std::nullopt;
    const Vec3 a_offset=Scale(pair_normal,fat_a),b_offset=Scale(pair_normal,fat_b);
    for (std::size_t i=0;i<result.count;++i)
    {
        auto& pair=result.points[i];pair.a={pair.a.x+a_offset.x,pair.a.y+a_offset.y,pair.a.z+a_offset.z};pair.b=Subtract(pair.b,b_offset);
    }
    result.normal={-pair_normal.x,-pair_normal.y,-pair_normal.z};return result;
}
}

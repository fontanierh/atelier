// SPDX-License-Identifier: Apache-2.0
#include "WorldPrimitiveContact.h"
#include "WorldGeometry.h"
#include "GeometryPrism.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
float Scalar(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
std::uint32_t Word(float value) {std::uint32_t word;std::memcpy(&word,&value,4);return word;}
Vec4 Lanes(Vec3 value,float w) {return {value.x,value.y,value.z,w};}
Vec3 Xyz(Vec4 value) {return {value[0],value[1],value[2]};}
Vec4 Load(const std::uint32_t* words) {return {Scalar(words[0]),Scalar(words[1]),Scalar(words[2]),Scalar(words[3])};}
DirectionWords Words(Vec4 value) {return {Word(value[0]),Word(value[1]),Word(value[2]),Word(value[3])};}
void Store(std::uint32_t* output,Vec4 value) {for (unsigned i=0;i<4;++i) output[i]=Word(value[i]);}
Vec4 Scale4(Vec4 value,float scalar) {return {value[0]*scalar,value[1]*scalar,value[2]*scalar,value[3]*scalar};}
Vec4 Sub(Vec4 a,Vec4 b) {return {a[0]-b[0],a[1]-b[1],a[2]-b[2],a[3]-b[3]};}
Vec4 Madd4(Vec4 a,float scalar,Vec4 b)
{return {std::fma(a[0],scalar,b[0]),std::fma(a[1],scalar,b[1]),std::fma(a[2],scalar,b[2]),std::fma(a[3],scalar,b[3])};}
std::pair<GpRecord,PrimitiveKind> Pack(const ContactPrimitive& primitive)
{
    GpRecord gp{};PrimitiveKind kind;float radius;std::uint32_t counts,id;
    if (const auto* sphere=std::get_if<Sphere>(&primitive))
    {
        Store(gp.data(),Lanes(sphere->center,1));kind=PrimitiveKind::Sphere;radius=sphere->radius;counts=0;id=1;
    }
    else if (const auto* capsule=std::get_if<Capsule>(&primitive))
    {
        Store(gp.data(),Lanes(capsule->center,1));Store(gp.data()+16,Lanes(capsule->axis,0));gp[28]=Word(capsule->half_length);
        kind=PrimitiveKind::Capsule;radius=capsule->radius;counts=0x00010000;id=2;
    }
    else if (const auto* triangle=std::get_if<Triangle>(&primitive))
    {
        Store(gp.data(),Lanes(triangle->vertices[0],1));Store(gp.data()+4,Lanes(triangle->feature.normal,0));
        Store(gp.data()+8,Lanes(triangle->vertices[1],1));Store(gp.data()+12,Lanes(triangle->vertices[2],1));
        for (unsigned i=0;i<3;++i)
        {
            Store(gp.data()+16+i*4,Lanes(triangle->feature.edges[i],0));gp[28+i]=Word(triangle->edge_lengths[i]);
            gp[38+i]=Word(triangle->feature.edge_cosines[i]);
        }
        gp[37]=triangle->feature.flags;kind=PrimitiveKind::Triangle;radius=triangle->fatness;counts=0x01030000;id=3;
    }
    else
    {
        const auto& box=std::get<RoundedBox>(primitive);Store(gp.data(),Lanes(box.center,1));
        const std::array<float,3> half={box.half_extents.x,box.half_extents.y,box.half_extents.z};
        for (unsigned i=0;i<3;++i)
        {
            const auto& v=box.basis.columns[i];const Vec4 axis={v[0],v[1],v[2],0};
            Store(gp.data()+4+i*4,axis);Store(gp.data()+16+i*4,axis);gp[28+i]=Word(half[i]);
        }
        kind=PrimitiveKind::Box;radius=box.radius;counts=0x03030000;id=4;
    }
    gp[32]=Word(radius);gp[35]=counts;gp[36]=id;return {gp,kind};
}
MaximumFeature Maximum(const GpRecord& gp,PrimitiveKind kind,std::uint32_t mode,DirectionWords direction)
{
    MaximumFeature feature{};
    switch (kind)
    {
    case PrimitiveKind::Sphere:for (unsigned i=0;i<4;++i) feature[136+i]=gp[i];break;
    case PrimitiveKind::Capsule:{FeatureSegment scratch{};CapsuleMaximumFeature(gp,direction,feature,scratch);break;}
    case PrimitiveKind::Triangle:TriangleMaximumFeature(gp,mode,direction,feature);break;
    case PrimitiveKind::Box:BoxMaximumFeature(gp,mode,direction,feature,{});break;
    }
    return feature;
}
std::pair<DirectionWords,DirectionWords> TriangleBox(const GpRecord& triangle,const GpRecord& box)
{
    std::array<Vec4,13> axes{};axes[0]=Load(triangle.data()+4);
    for (unsigned i=0;i<3;++i) axes[1+i]=Load(box.data()+12-i*4);
    for (unsigned edge=0;edge<3;++edge)
        for (unsigned box_edge=0;box_edge<3;++box_edge)
        {
            const auto axis=Cross3(Load(triangle.data()+16+edge*4),Load(box.data()+16+box_edge*4));
            axes[4+edge*3+box_edge]=Scale4(axis,InverseLengthSquared(Dot3(axis,axis),1));
        }
    std::array<Vec4,3> scaled_box;
    for (unsigned i=0;i<3;++i) scaled_box[i]=Scale4(Load(box.data()+4+i*4),Scalar(box[28+i]));
    auto minimum=[](float a,float b){return a<b ? a:b;};auto maximum=[](float a,float b){return a>b ? a:b;};
    float best=0,selected_sign=1;Vec4 selected=axes[0];
    for (unsigned index=0;index<13;++index)
    {
        const auto& axis=axes[index];const float p0=Dot3(Load(triangle.data()),axis),p1=Dot3(Load(triangle.data()+8),axis),p2=Dot3(Load(triangle.data()+12),axis);
        const float low=minimum(p0,minimum(p1,p2)),high=maximum(p0,maximum(p1,p2)),center=Dot3(Load(box.data()),axis);
        const float e0=std::fabs(Dot3(scaled_box[0],axis)),e1=std::fabs(Dot3(scaled_box[1],axis)),e2=std::fabs(Dot3(scaled_box[2],axis));
        const float radius=(e0+e1)+e2,forward=low-(center+radius),reverse=(center-radius)-high;
        const bool flip=forward>reverse;const float separation=flip ? forward:reverse,sign=flip ? -1.0f:1.0f;
        if (!index || separation>best) {best=separation;selected=axis;selected_sign=sign;}
    }
    return {DirectionWords{Word(best),Word(best),Word(best),Word(best)},Words(Scale4(selected,selected_sign))};
}
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
    const auto [a,a_kind]=Pack(primitive);const auto [b,b_kind]=Pack(ContactPrimitive{triangle});
    auto best=a_kind==PrimitiveKind::Box ? TriangleBox(b,a):BestSeparatingDirection(a,a_kind,b,b_kind);
    if (a_kind==PrimitiveKind::Box) best.second=Flip(best.second);
    const float separation=Scalar(best.first[0]),fat_a=Scalar(a[32]),fat_b=Scalar(b[32]);
    if (separation>(fat_b+limit)+fat_a) return std::nullopt;
    auto feature_a=Maximum(a,a_kind,1,best.second),feature_b=Maximum(b,b_kind,0,Flip(best.second));FeaturePrism prism{};
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

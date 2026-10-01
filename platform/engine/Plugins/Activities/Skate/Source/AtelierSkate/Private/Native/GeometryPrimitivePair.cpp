// SPDX-License-Identifier: Apache-2.0
#include "GeometryPrimitivePair.h"
#include "PrimitiveGeometry.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
using namespace primitive_geometry;
Vec3 Xyz(Vec4 v){return {v[0],v[1],v[2]};}
Vec4 Sub(Vec4 a,Vec4 b){return {a[0]-b[0],a[1]-b[1],a[2]-b[2],a[3]-b[3]};}
DirectionWords Flip(DirectionWords direction){for(auto& word:direction)word^=0x80000000u;return direction;}
std::pair<DirectionWords,DirectionWords> BoxBox(const GpRecord& a,const GpRecord& b)
{
    std::array<Vec4,16> axes{};
    for(unsigned i=0;i<3;++i){axes[i]=Load(a.data()+12-i*4);axes[3+i]=Load(b.data()+12-i*4);}
    for(unsigned edge_a=0;edge_a<3;++edge_a)for(unsigned edge_b=0;edge_b<3;++edge_b)
    {
        const auto axis=Cross3(Load(a.data()+16+edge_a*4),Load(b.data()+16+edge_b*4));
        // This entry uses the raw estimate; the triangle/box entry refines once.
        axes[6+edge_a*3+edge_b]=Scale4(axis,ReciprocalSquareRootEstimate(Dot3(axis,axis)));
    }
    axes[15]=axes[14];std::array<Vec4,3> scaled_a,scaled_b;
    for(unsigned i=0;i<3;++i){scaled_a[i]=Scale4(Load(a.data()+4+i*4),Scalar(a[28+i]));scaled_b[i]=Scale4(Load(b.data()+4+i*4),Scalar(b[28+i]));}
    float best=0,selected_sign=1;Vec4 selected=axes[0];
    for(unsigned index=0;index<16;++index)
    {
        const auto& axis=axes[index];const float ac=Dot3(Load(a.data()),axis),bc=Dot3(Load(b.data()),axis);
        const float a0=std::fabs(Dot3(scaled_a[0],axis)),a1=std::fabs(Dot3(scaled_a[1],axis)),a2=std::fabs(Dot3(scaled_a[2],axis));
        const float b0=std::fabs(Dot3(scaled_b[0],axis)),b1=std::fabs(Dot3(scaled_b[1],axis)),b2=std::fabs(Dot3(scaled_b[2],axis));
        const float ar=(a0+a1)+a2,br=(b0+b1)+b2,forward=(ac-ar)-(bc+br),reverse=(bc-br)-(ac+ar);
        const bool flip=forward>reverse;const float separation=flip ? forward:reverse,sign=flip ? -1.0f:1.0f;
        if(!index || separation>best){best=separation;selected=axis;selected_sign=sign;}
    }
    return {DirectionWords{Word(best),Word(best),Word(best),Word(best)},Words(Scale4(selected,selected_sign))};
}
std::pair<DirectionWords,DirectionWords> SeparatingDirection(const GpRecord& a,PrimitiveKind ak,const GpRecord& b,PrimitiveKind bk)
{
    if(ak==PrimitiveKind::Sphere && bk==PrimitiveKind::Sphere)
    {
        const auto delta=Sub(Load(b.data()),Load(a.data()));const float square=Dot3(delta,delta),inverse=InverseLengthSquared(square,2);
        const float length=square==0.0f ? 0.0f:square*inverse;
        return {DirectionWords{Word(length),Word(length),Word(length),Word(length)},Words(Scale4(delta,inverse))};
    }
    if(ak==PrimitiveKind::Box && bk==PrimitiveKind::Box)return BoxBox(a,b);
    if(ak==PrimitiveKind::Triangle && bk==PrimitiveKind::Box)return TriangleBox(a,b);
    if(ak==PrimitiveKind::Box && bk==PrimitiveKind::Triangle){auto result=TriangleBox(b,a);result.second=Flip(result.second);return result;}
    return BestSeparatingDirection(a,ak,b,bk);
}
}
PrimitivePairSettings PrimitivePairSettings::SkaterSelfCollision()
{return {primitive_geometry::Scalar(0x3d4ccccd),primitive_geometry::Scalar(0x3d4ccccd),0,
    primitive_geometry::Scalar(0x3f7fbe77),primitive_geometry::Scalar(0x3c23d70a)};}
std::optional<PrimitiveContactManifold> PrimitivePairContacts(const ContactPrimitive& primitive_a,const ContactPrimitive& primitive_b,PrimitivePairSettings settings)
{
    using namespace primitive_geometry;
    const auto [a,ak]=Pack(primitive_a);const auto [b,bk]=Pack(primitive_b);const auto best=SeparatingDirection(a,ak,b,bk);
    const float separation=Scalar(best.first[0]),limit=(settings.padding_b+settings.padding_a)+settings.additional_padding;
    const float fat_a=Scalar(a[32]),fat_b=Scalar(b[32]);if(separation>(fat_b+limit)+fat_a)return std::nullopt;
    auto feature_a=Maximum(a,ak,1,best.second),feature_b=Maximum(b,bk,0,Flip(best.second));FeaturePrism prism{};
    if(!FindFeatureIntersectionPrism(prism,feature_a,feature_b,best.second))return std::nullopt;
    PrimitiveContactManifold result;result.count=prism[132];Vec4 normal=Load(best.second.data());
    if(result.count==1)
    {
        const auto delta=Sub(Load(prism.data()+64),Load(prism.data()));const float square=Dot3(delta,delta),inverse=InverseLengthSquared(square,2);
        const float length=square==0.0f ? 0.0f:square*inverse;
        if(length>Scalar(0x34000000)){Store(prism.data()+128,Scale4(delta,inverse));prism[133]=1;}
    }
    if(prism[133])
    {
        DirectionWords direction;for(unsigned i=0;i<4;++i)direction[i]=prism[128+i];ProjectionInterval ia{},ib{};
        ProjectDirection(a,ak,direction,ia);ProjectDirection(b,bk,direction,ib);
        const float forward=Scalar(ia[0])-Scalar(ib[4]),reverse=Scalar(ib[0])-Scalar(ia[4]);const bool flip=forward>reverse;
        if((flip ? forward:reverse)>=separation)normal=Load((flip ? Flip(direction):direction).data());
    }
    for(std::size_t i=0;i<result.count;++i)result.points[i]={Xyz(Load(prism.data()+4*i)),Xyz(Load(prism.data()+64+4*i))};
    Vec3 pair_normal=Xyz(normal);
    const std::array<const ContactPrimitive*,2> primitives{{&primitive_a,&primitive_b}};
    for(std::size_t i=0;i<2;++i)if(const auto* triangle=std::get_if<Triangle>(primitives[i]))
        if(!FixUpTriangle(triangle->feature,pair_normal,result.points.data(),result.count,
            {i==1,settings.edge_cos_bend_normal_threshold,settings.convexity_epsilon,false}))return std::nullopt;
    const auto direction=Lanes(pair_normal,normal[3]),oa=Scale4(direction,fat_a),ob=Scale4(direction,fat_b);
    for(std::size_t i=0;i<result.count;++i)
    {
        auto& point=result.points[i];point.a={point.a.x+oa[0],point.a.y+oa[1],point.a.z+oa[2]};
        point.b={point.b.x-ob[0],point.b.y-ob[1],point.b.z-ob[2]};
    }
    result.normal={-pair_normal.x,-pair_normal.y,-pair_normal.z};return result;
}
}

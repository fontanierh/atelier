// SPDX-License-Identifier: Apache-2.0
#pragma once
// Shared original GP packing, feature selection and triangle/box SAT expressions.
// These helpers are internal to the typed geometry queries.
#include "GeometryPrism.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::primitive_geometry
{
inline float Scalar(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
inline std::uint32_t Word(float value) {std::uint32_t word;std::memcpy(&word,&value,4);return word;}
inline Vec4 Lanes(Vec3 value,float w) {return {value.x,value.y,value.z,w};}
inline Vec4 Load(const std::uint32_t* words) {return {Scalar(words[0]),Scalar(words[1]),Scalar(words[2]),Scalar(words[3])};}
inline DirectionWords Words(Vec4 value) {return {Word(value[0]),Word(value[1]),Word(value[2]),Word(value[3])};}
inline void Store(std::uint32_t* output,Vec4 value) {for (unsigned i=0;i<4;++i) output[i]=Word(value[i]);}
inline Vec4 Scale4(Vec4 value,float scalar) {return {value[0]*scalar,value[1]*scalar,value[2]*scalar,value[3]*scalar};}
inline std::pair<GpRecord,PrimitiveKind> Pack(const ContactPrimitive& primitive)
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
inline MaximumFeature Maximum(const GpRecord& gp,PrimitiveKind kind,std::uint32_t mode,DirectionWords direction)
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
inline std::pair<DirectionWords,DirectionWords> TriangleBox(const GpRecord& triangle,const GpRecord& box)
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
}

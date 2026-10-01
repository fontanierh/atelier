// SPDX-License-Identifier: Apache-2.0
#include "BodyMass.h"
#include <cmath>
#include <cstring>
#pragma clang fp contract(off)
namespace atelier::skate
{
namespace
{
float Word(std::uint32_t bits){float v;std::memcpy(&v,&bits,4);return v;}
// This ordered subtraction also preserves unordered and signed-zero selection.
float GreaterExtent(float left,float right){return left-right>=0.0f?left:right;}
PrimitiveMass RoundedBox(Vec3 half,float radius)
{
    const float largest=GreaterExtent(half.x,GreaterExtent(half.y,half.z));
    const float floor=GreaterExtent((largest+radius)*0.05f,Word(0x33d6bf95))-radius;
    const float x=GreaterExtent(half.x,floor),y=GreaterExtent(half.y,floor),z=GreaterExtent(half.z,floor);
    const float radius_moment=(radius*radius)*0.5f,x_squared=x*x,y_squared=y*y,z_squared=z*z;
    const float xy_radius=(x+y)*radius,yz_radius=(y+z)*radius,xz_radius=(x+z)*radius;
    const float mx=std::fma(std::fma(yz_radius,2.0f,z_squared)+y_squared,Word(0x3eaaaaab),radius_moment);
    const float my=std::fma(std::fma(xz_radius,2.0f,x_squared)+z_squared,Word(0x3eaaaaab),radius_moment);
    const float mz=std::fma(std::fma(xy_radius,2.0f,x_squared)+y_squared,Word(0x3eaaaaab),radius_moment);
    const float rounded_edges=(((std::fma(radius,Word(0x3f2aaaab),x)+y)+z)*radius)*Word(0x40c90fdb);
    const float face_products=std::fma(y+z,x,y*z),box_volume=((x*y)*z)*8.0f;
    return {{mx,my,mz},std::fma(std::fma(face_products,8.0f,rounded_edges),radius,box_volume)};
}
}
std::optional<PrimitiveMass> ComputePrimitiveMass(MassShape shape)
{
    switch(shape.kind)
    {
    case MassShapeKind::Unsupported:return std::nullopt;
    case MassShapeKind::Sphere:
    {
        const float radius=GreaterExtent(shape.radius,Word(0x33d6bf95)),squared=radius*radius,moment=squared*0.4f;
        return PrimitiveMass{{moment,moment,moment},(squared*radius)*Word(0x40860a92)};
    }
    case MassShapeKind::Capsule:
    {
        const float length_squared=shape.half_length*shape.half_length;
        const float radius=GreaterExtent(GreaterExtent(shape.radius,Word(0x33d6bf95)),shape.half_length*0.05f);
        const float numerator=std::fma(std::fma(std::fma(radius,1.6f,shape.half_length*0.75f),radius,length_squared*4.0f),radius,length_squared*shape.half_length);
        const float denominator=std::fma(radius,4.0f,shape.half_length*3.0f),transverse=numerator/denominator,axial=(radius*radius)*0.4f;
        return PrimitiveMass{{transverse,transverse,axial},((std::fma(radius,Word(0x3faaaaab),shape.half_length*2.0f)*radius)*radius)*Word(0x40490fdb)};
    }
    case MassShapeKind::RoundedBox:return RoundedBox(shape.half_extents,shape.radius);
    case MassShapeKind::Cylinder:
    {
        const float radius=shape.radius+shape.padding,half_length=shape.half_length+shape.padding,squared=radius*radius;
        const float transverse=std::fma(half_length*half_length,4.0f,squared*3.0f)*Word(0x3daaaaab);
        return PrimitiveMass{{transverse,transverse,squared*0.5f},((half_length*radius)*radius)*Word(0x40c90fdb)};
    }
    }
    return std::nullopt;
}
}

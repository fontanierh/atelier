// SPDX-License-Identifier: Apache-2.0
#include "SkeletonBodyDefinition.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
std::optional<BodyMassProperties> MassProperties(MassShape shape,std::optional<HatGeometry> hat,float mass,std::string& error)
{
    const float unbounded=Float(0x7f7fffff);
    if(hat)
    {
        MassShape cylinder;cylinder.kind=MassShapeKind::Cylinder;cylinder.radius=hat->radius;cylinder.half_length=hat->half_length;
        const auto hat_mass=ComputePrimitiveMass(cylinder);
        if(!hat_mass){error="Invalid skeleton hat primitive";return std::nullopt;}
        auto moments=MassMoments::FromPrimitive(*hat_mass);moments.Transform(hat->basis,hat->translation);
        const auto head_mass=ComputePrimitiveMass(shape);
        if(!head_mass){error="Invalid head primitive";return std::nullopt;}
        moments.Add(MassMoments::FromPrimitive(*head_mass));
        auto properties=ComputeAggregateMassProperties(moments,mass,unbounded,0);properties.local_mass_frame={};return properties;
    }
    const auto properties=ComputePrimitiveMassProperties({shape,mass},unbounded,0);
    if(!properties)error="Invalid skeleton primitive";
    return properties;
}
void AdjustInertia(BodyMassProperties& properties,std::uint32_t kind,float factor)
{
    auto& d=properties.dynamics;
    if(kind==1)
    {
        const float reciprocal=RefinedReciprocal(factor,2);
        d.inverse_tensor={d.inverse_tensor.x*reciprocal,d.inverse_tensor.y*reciprocal,d.inverse_tensor.z*reciprocal};
        const float xy=d.inverse_tensor.x<d.inverse_tensor.y ? d.inverse_tensor.x:d.inverse_tensor.y;
        const float xyz=xy<d.inverse_tensor.z ? xy:d.inverse_tensor.z;d.spherical=1.0f/xyz;
    }
    else if(kind==2)
    {
        const float reciprocal=1.0f/(factor*3.0f);
        const float value=((d.inverse_tensor.x+d.inverse_tensor.y)+d.inverse_tensor.z)*reciprocal;
        d.inverse_tensor={value,value,value};d.spherical=1.0f/value;
    }
}
}
HatGeometry HatGeometry::FromOffsets(float radius,float thickness,Vec3 angles,Vec3 translation)
{
    const auto x=SinCos(angles.x),y=SinCos(angles.y),z=SinCos(angles.z);
    const float sx=x.first,cx=x.second,sy=y.first,cy=y.second,sz=z.first,cz=z.second;
    const float cxsz=cx*sz,sxsz=sx*sz,sxcz=sx*cz,cxcz=cx*cz;
    Basis3 basis;basis.columns={{{cy*cz,cy*sz,-sy},
        {sy*sxcz-cxsz,std::fma(sy,sxsz,cxcz),cy*sx},
        {std::fma(sy,cxcz,sxsz),sy*cxsz-sxcz,cy*cx}}};
    return {radius,thickness*0.5f,basis,translation};
}
std::optional<SkeletonBodyDefinition> SkeletonBodyDefinition::Build(
    std::array<Vec3,SkeletonAnimationPartCount> sizes,
    std::array<BoneSettings,SkeletonAnimationPartCount> bones,
    SkeletonBodySettings settings,std::optional<HatGeometry> hat,std::string& error)
{
    SkeletonBodyDefinition result;result.bones=bones;
    for(std::size_t i=0;i<SkeletonAnimationPartCount;++i)
    {
        const auto b=bones[i];const auto size=sizes[i];MassShape shape;
        if(i==0){shape.kind=MassShapeKind::Capsule;shape.radius=settings.root_radius;shape.half_length=settings.root_half_length;}
        else if((i==1 && hat) || b.volume_type==1)
        {
            const float x=size.x*0.5f,y=size.y*0.5f;
            shape.kind=MassShapeKind::Sphere;shape.radius=(x-y>=0.0f ? x:y)*b.volume_scalar;
        }
        else if(b.volume_type==0)
        {
            const float scalar=b.volume_scalar*0.5f;shape.kind=MassShapeKind::RoundedBox;
            shape.half_extents={size.x*scalar,size.y*scalar,size.z*scalar};
        }
        else if(b.volume_type==2)
        {
            const float radius=(size.x*settings.capsule_radius_scalar)*0.5f;
            const float length=size.z*0.5f-radius;shape.kind=MassShapeKind::Capsule;
            shape.radius=b.volume_scalar*radius;
            shape.half_length=(((-length>=0.0f) ? 0.0f:length)*settings.capsule_length_scalar)*b.volume_scalar;
        }
        else {error="Unresolved non-root skeleton volume type";return std::nullopt;}
        const float base_mass=i==0 ? Float(0x3a83126f):settings.density*((size.x*size.y)*size.z);
        const auto head_hat=i==1 ? hat:std::nullopt;
        const float animated_mass=b.mass_factor*base_mass,ragdoll_mass=b.ragdoll_mass_factor*base_mass;
        auto animated=MassProperties(shape,head_hat,animated_mass,error);if(!animated)return std::nullopt;
        const auto ragdoll=MassProperties(shape,head_hat,ragdoll_mass,error);if(!ragdoll)return std::nullopt;
        AdjustInertia(*animated,settings.inertia_multiply_type,settings.inertia_factor);
        result.parts[i]={shape,head_hat,*animated,*ragdoll,1.0f/animated_mass,settings.ragdoll_inverse_mass_factor/ragdoll_mass};
    }
    constexpr std::array<std::array<std::uint32_t,3>,2> extra{{{0x3e6b851f,0x3dcccccd,0x3dcccccd},{0x3eb851ec,0x3e851eb8,0x3c23d70a}}};
    for(std::size_t i=0;i<extra.size();++i)
    {
        MassShape shape;shape.kind=MassShapeKind::Capsule;shape.radius=Float(extra[i][0]);shape.half_length=Float(extra[i][1]);
        const float mass=Float(extra[i][2]);auto properties=MassProperties(shape,std::nullopt,mass,error);if(!properties)return std::nullopt;
        properties->dynamics.maximum_linear_velocity=Float(0x41efffff);
        properties->dynamics.maximum_angular_velocity=Float(0x41efffff);AdjustInertia(*properties,1,5.0f);
        result.parts[SkeletonAnimationPartCount+i]={shape,std::nullopt,*properties,*properties,1.0f/mass,1.0f/mass};
    }
    std::array<std::uint32_t,SkeletonAnimationPartCount> shapes;
    for(std::size_t i=0;i<shapes.size();++i)shapes[i]=bones[i].volume_type;
    result.animation_masses=SkeletonAnimationMasses::FromBoneData(sizes,shapes,hat.has_value());error.clear();return result;
}
}

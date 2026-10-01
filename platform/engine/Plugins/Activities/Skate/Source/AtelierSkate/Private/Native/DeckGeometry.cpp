// SPDX-License-Identifier: Apache-2.0
#include "DeckGeometry.h"
#include <cstring>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
AffineTransform Translated(Vec3 translation){AffineTransform frame;frame.translation=translation;return frame;}
DeckChild FanTriangle(std::pair<float,float> previous,std::pair<float,float> next,
    std::pair<float,float> slope,float width,float length,float center_z,float fatness,bool front,bool enabled)
{
    const auto point=[=](std::pair<float,float> arc)
    {
        const float along_end=arc.first*length;
        const float elevation=front?along_end:-along_end;
        return Vec3{arc.second*width,slope.first*elevation,std::fma(along_end,slope.second,center_z)};
    };
    return {DeckTriangle{{Vec3{0,0,center_z},point(previous),point(next)},fatness,{1,-1,1},0x3e2},{},enabled};
}
}
DeckGeometrySettings DeckGeometrySettings::Stock()
{
    return {Float(0x3e75c28f),Float(0x3f170a3d),Float(0x3c75c28f),Float(0x3e28f5c3),
        Float(0x41500000),Float(0x41480000),5,true,true};
}
DeckGeometry::DeckGeometry(DeckGeometrySettings settings)
{
    const float half_width=settings.width*0.5f,half_length=settings.mid_length*0.5f,
        half_thickness=settings.thickness*0.5f,radius=half_thickness*Float(0x3f666666);
    children.push_back({DeckRoundedBox{{half_width-radius,half_thickness-radius,half_length-radius},radius},
        {},settings.enable_deck_volume_collisions});
    const float half_delta=(-half_length-half_length)*0.5f;
    const float capsule_half_length=Length3(Vec3{0,0,half_delta});
    const float capsule_center_z=half_length+half_delta,arc_width=half_width-half_thickness;
    for(float x:{arc_width,half_thickness-half_width})
        children.push_back({DeckCapsule{half_thickness,capsule_half_length},
            Translated({x,0,capsule_center_z}),settings.enable_end_volume_collisions});
    for(float z:{Float(0x3e70a3d7),Float(0xbe70a3d7)})
        children.push_back({DeckSphere{0.035f},Translated({0,Float(0xbca3d70a),z}),true});
    const float back_angle=settings.back_end_angle_degrees*Float(0x3c8efa35);
    const float front_angle=settings.front_end_angle_degrees*Float(0x3c8efa35);
    const std::pair<float,float> back_slope{Sin(back_angle),Cos(back_angle)},front_slope{Sin(front_angle),Cos(front_angle)};
    const float end_length=settings.back_end_size-half_thickness;
    std::pair<float,float> previous_back{Sin(0),Cos(0)},previous_front=previous_back;
    for(std::int64_t segment=1;segment<=settings.end_capsule_count;++segment)
    {
        const float back_arc=(static_cast<float>(segment)*Float(0xc0490fdb))/static_cast<float>(settings.end_capsule_count);
        const std::pair<float,float> next_back{Sin(back_arc),Cos(back_arc)};
        children.push_back(FanTriangle(previous_back,next_back,back_slope,arc_width,end_length,-half_length,
            half_thickness,false,settings.enable_deck_volume_collisions));
        previous_back=next_back;
        const float front_arc=(static_cast<float>(segment)*Float(0x40490fdb))/static_cast<float>(settings.end_capsule_count);
        const std::pair<float,float> next_front{Sin(front_arc),Cos(front_arc)};
        children.push_back(FanTriangle(previous_front,next_front,front_slope,arc_width,end_length,half_length,
            half_thickness,true,settings.enable_deck_volume_collisions));
        previous_front=next_front;
    }
}
MassMoments DeckGeometry::ComputeMassMoments() const
{
    MassMoments total;
    for(const auto& child:children)total.Add(child.ComputeMassMoments());
    // The original aggregate applies its identity volume transform after adding
    // all children, including those whose collision-enable flag is clear.
    total.Transform(AffineTransform{}.basis,{});
    return total;
}
MassMoments DeckChild::ComputeMassMoments() const
{
    MassShape primitive;AffineTransform frame=transform;
    if(const auto* box=std::get_if<DeckRoundedBox>(&shape))
    {primitive.kind=MassShapeKind::RoundedBox;primitive.half_extents=box->half_extents;primitive.radius=box->radius;}
    else if(const auto* capsule=std::get_if<DeckCapsule>(&shape))
    {primitive.kind=MassShapeKind::Capsule;primitive.radius=capsule->radius;primitive.half_length=capsule->half_length;}
    else if(const auto* sphere=std::get_if<DeckSphere>(&shape))
    {primitive.kind=MassShapeKind::Sphere;primitive.radius=sphere->radius;}
    else
    {
        const auto& triangle=std::get<DeckTriangle>(shape);
        const auto axis=[&](float Vec3::* member)
        {
            const float a=triangle.vertices[0].*member,b=triangle.vertices[1].*member,c=triangle.vertices[2].*member;
            const float low=VectorMin(a,VectorMin(b,c))-triangle.fatness;
            const float high=VectorMax(a,VectorMax(b,c))+triangle.fatness;
            const float half=(high-low)*0.5f;
            return std::pair<float,float>{half,low+half};
        };
        const auto x=axis(&Vec3::x),y=axis(&Vec3::y),z=axis(&Vec3::z);
        primitive.kind=MassShapeKind::RoundedBox;primitive.radius=0;primitive.half_extents={x.first,y.first,z.first};
        // Triangle mass uses its fat AABB, ignoring the authored child transform.
        frame=Translated({x.second,y.second,z.second});
    }
    auto moments=MassMoments::FromPrimitive(*ComputePrimitiveMass(primitive));
    moments.Transform(frame.basis,frame.translation);return moments;
}
BodyMassProperties DeckMassProperties(const DeckGeometry& geometry,float mass,float angular_drag)
{
    auto properties=ComputeAggregateMassProperties(geometry.ComputeMassMoments(),mass,Float(0x7f7fffff),angular_drag);
    properties.local_mass_frame={};return properties;
}
BodyMassProperties StockDeckMassProperties()
{
    return DeckMassProperties(DeckGeometry(DeckGeometrySettings::Stock()),6.0f,Float(0x3ee66666)*Float(0x426fffff));
}
std::array<BodyMassProperties,7> DefaultSkateboardMassProperties()
{
    return {WheelMassProperties(WheelMassSettings::Stock()),WheelMassProperties(WheelMassSettings::Stock()),
        WheelMassProperties(WheelMassSettings::Stock()),WheelMassProperties(WheelMassSettings::Stock()),
        TruckMassProperties(TruckMassSettings::Stock()),TruckMassProperties(TruckMassSettings::Stock()),StockDeckMassProperties()};
}
}

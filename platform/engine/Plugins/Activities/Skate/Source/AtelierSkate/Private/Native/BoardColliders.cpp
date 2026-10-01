// SPDX-License-Identifier: Apache-2.0
#include "BoardColliders.h"
#include <cstdlib>
#include <cstring>
#include <type_traits>

namespace atelier::skate
{
namespace
{
AffineTransform Compose(AffineTransform parent,AffineTransform child)
{
    AffineTransform world;
    for(std::size_t axis=0;axis<3;++axis)
        for(std::size_t row=0;row<3;++row)
        {
            const auto& c=child.basis.columns[axis];
            world.basis.columns[axis][row]=std::fma(c[2],parent.basis.columns[2][row],
                std::fma(c[1],parent.basis.columns[1][row],c[0]*parent.basis.columns[0][row]));
        }
    const std::array<float,3> origin{parent.translation.x,parent.translation.y,parent.translation.z};
    const auto component=[&](std::size_t row)
    {return std::fma(child.translation.z,parent.basis.columns[2][row],std::fma(child.translation.y,parent.basis.columns[1][row],
        std::fma(child.translation.x,parent.basis.columns[0][row],origin[row])));};
    world.translation={component(0),component(1),component(2)};return world;
}
Capsule MakeCapsule(AffineTransform pose,float radius,float half_length)
{
    const auto z=pose.basis.columns[2];return {pose.translation,{z[0],z[1],z[2]},half_length,radius};
}
}
std::vector<BoardWorldVolume> BoardWorldVolumes(const BoardRuntime& board,const BoardCollisionSettings& settings)
{
    const auto poses=board.PartTransforms();std::vector<BoardWorldVolume> volumes;
    for(std::size_t id=0;id<BoardBodyCount;++id)
    {
        const auto& body=board.Bodies()[id];if(body.state_flags==1)continue;
        const auto pose=poses[id];
        const auto add=[&](ContactPrimitive primitive,ContactMaterial material)
        {volumes.push_back({static_cast<std::uint32_t>(id),std::move(primitive),body.rates.linear_velocity,material});};
        if(id==static_cast<std::size_t>(BoardBodyId::Deck))
        {
            for(const auto& child:settings.deck_geometry.children)
            {
                if(!child.collision_enabled)continue;
                const auto world=Compose(pose,child.transform);
                const ContactPrimitive primitive=std::visit([&](const auto& shape)->ContactPrimitive
                {
                    using T=std::decay_t<decltype(shape)>;
                    if constexpr(std::is_same_v<T,DeckSphere>)return Sphere{world.translation,shape.radius};
                    else if constexpr(std::is_same_v<T,DeckCapsule>)return MakeCapsule(world,shape.radius,shape.half_length);
                    else if constexpr(std::is_same_v<T,DeckRoundedBox>)return RoundedBox{world.translation,world.basis,shape.half_extents,shape.radius};
                    else return TransformTriangleVolume(shape.vertices,shape.fatness,shape.edge_cosines,shape.volume_flags,world);
                },child.shape);
                add(primitive,settings.deck_material);
            }
        }
        else if(id==static_cast<std::size_t>(BoardBodyId::FrontTruck) || id==static_cast<std::size_t>(BoardBodyId::BackTruck))
        {
            if(settings.truck_collisions)
            {
                const auto& shape=settings.truck_shape;
                if(shape.kind!=MassShapeKind::Capsule)std::abort();
                add(MakeCapsule(pose,shape.radius,shape.half_length),settings.truck_material);
            }
        }
        else add(Sphere{pose.translation,settings.wheel_radius},settings.wheel_material);
    }
    return volumes;
}
const std::vector<BoardCollision>& BoardWorldContacts::Query(const WorldGeometry& world,
    const std::vector<BoardWorldVolume>& volumes,WorldContactSettings query,ContactRetentionSettings retention)
{
    const auto& seeds=producer_.QueryPrimitives(world,volumes,query,retention);contacts_.clear();contacts_.reserve(seeds.size());
    for(const auto& seed:seeds)
    {
        const auto f=[&](std::size_t i){float value;std::memcpy(&value,&seed[i],4);return value;};
        const auto v=[&](std::size_t i)->Vec3{return {f(i),f(i+1),f(i+2)};};
        contacts_.push_back({CollisionBody::FromContactId(seed[3]),CollisionBody::StaticWorld(),
            {v(0),v(4),v(8),f(11),f(15),f(19),seed[23]}});
    }
    return contacts_;
}
}

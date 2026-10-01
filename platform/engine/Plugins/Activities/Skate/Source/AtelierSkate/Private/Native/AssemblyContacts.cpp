// SPDX-License-Identifier: Apache-2.0
#include "AssemblyContacts.h"
#include "GeometryPrimitivePair.h"
#include <algorithm>
#include <cstdlib>
namespace atelier::skate
{
namespace
{
bool Allowed(std::uint32_t a,std::uint32_t b)
{
    constexpr std::array<std::uint32_t,21> allowed{{0x1876fd,0,0x120001,1,0x79d1,0x1079e1,0x1079f1,0x279f1,0x1676f0,0x7101,0x5101,
        0x1008f0,0x1d77f1,0x233f1,0xa57f1,0,0x1000,0x6184,0x1100,0x5001,0x1965}};
    return a<21 && b<21 && (allowed[a]&(1u<<b))!=0;
}
std::size_t Part(const BoardWorldVolume& volume)
{const auto body=CollisionBody::FromContactId(volume.body_contact_id);if(body.kind!=CollisionBody::Kind::Attached || body.index>=SkeletonPartCount)std::abort();return body.index;}
}
bool AppendAssemblyContacts(std::vector<BoardCollision>& contacts,const std::vector<BoardWorldVolume>& board,
    const std::vector<BoardWorldVolume>& rider,std::uint32_t board_group,const SkeletonCollisionMode& collision,std::string& error)
{
    if(board_group>=21 || collision.assembly_group>=21 || std::any_of(collision.parts.begin(),collision.parts.end(),[](const SkeletonPartCollision& part){return part.part_group>=21;}))
    {error="Skater collision group is outside the original21x21 table";return false;}
    if(Allowed(board_group,collision.assembly_group))for(const auto& a:board)for(const auto& b:rider)
    {const auto part=Part(b);if(Allowed(board_group,collision.parts[part].part_group))AppendPrimitivePairContacts(contacts,a,b);}
    for(const auto& a:rider)
    {
        const auto pa=Part(a);for(const auto& b:rider){const auto pb=Part(b);if(pa!=pb && !collision.self_culling[pa][pb])AppendPrimitivePairContacts(contacts,a,b);}
    }
    error.clear();return true;
}
void AppendPrimitivePairContacts(std::vector<BoardCollision>& contacts,const BoardWorldVolume& a,const BoardWorldVolume& b)
{
    const auto manifold=PrimitivePairContacts(a.primitive,b.primitive,PrimitivePairSettings::SkaterSelfCollision());if(!manifold)return;
    const auto material=CombineContactMaterials(a.material,b.material);
    for(std::size_t i=0;i<manifold->count;++i)
    {
        const auto& p=manifold->points[i];contacts.push_back({CollisionBody::FromContactId(a.body_contact_id),CollisionBody::FromContactId(b.body_contact_id),
            {p.a,p.b,manifold->normal,material.restitution,material.static_friction,material.dynamic_friction,0}});
    }
}
}

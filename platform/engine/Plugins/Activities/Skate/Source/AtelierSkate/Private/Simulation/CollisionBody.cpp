#include "CollisionBody.h"
#include <cstdlib>
#include <limits>

namespace atelier::skate
{
std::uint32_t CollisionBody::ContactId() const
{
    if(kind==Kind::StaticWorld)return 0xffffffffu;
    if(kind==Kind::Board){if(index>=BoardBodyCount)std::abort();return static_cast<std::uint32_t>(index);}
    if(index>std::numeric_limits<std::uint32_t>::max()-AttachedReactionBase)std::abort();
    return static_cast<std::uint32_t>(AttachedReactionBase+index);
}
CollisionBody CollisionBody::FromContactId(std::uint32_t id)
{
    if(id==0xffffffffu)return StaticWorld();
    if(id<BoardBodyCount)return Board(static_cast<BoardBodyId>(id));
    if(id<AttachedReactionBase)std::abort();
    return Attached(id-AttachedReactionBase);
}
}

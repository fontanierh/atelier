// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "BoardTypes.h"

namespace atelier::skate
{
constexpr std::size_t AttachedReactionBase=BoardBodyCount+1;
struct CollisionBody
{
    enum class Kind { Board,Attached,StaticWorld };
    Kind kind=Kind::StaticWorld;
    std::size_t index=0;
    static CollisionBody Board(BoardBodyId id){return {Kind::Board,static_cast<std::size_t>(id)};}
    static CollisionBody Attached(std::size_t index){return {Kind::Attached,index};}
    static CollisionBody StaticWorld(){return {};}
    std::uint32_t ContactId() const;
    static CollisionBody FromContactId(std::uint32_t id);
    bool operator==(CollisionBody other) const {return kind==other.kind && index==other.index;}
};
}

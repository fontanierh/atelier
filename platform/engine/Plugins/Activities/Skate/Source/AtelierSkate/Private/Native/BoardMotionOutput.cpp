// SPDX-License-Identifier: Apache-2.0
#include "BoardMotionOutput.h"
namespace atelier::skate
{
BoardMotionOutput BoardMotionOutput::FromBoard(const BoardRuntime& board,Vec3 normal,std::uint32_t flags)
{
    const auto& deck=board.Bodies()[static_cast<std::size_t>(BoardBodyId::Deck)].rates;
    auto basis=board.PartTransforms()[static_cast<std::size_t>(BoardBodyId::Deck)].basis;
    if(flags&0x00100000u)
        for(const std::size_t axis:{0,2})for(auto& lane:basis.columns[axis])lane=-lane;
    const auto ground=Subtract(deck.linear_velocity,Scale(normal,Dot3(deck.linear_velocity,normal)));
    const auto z=basis.columns[2];
    return {deck.angular_velocity,deck.linear_velocity,ground,Length3(deck.linear_velocity),Length3(ground),
        Dot3(deck.linear_velocity,Vec3{z[0],z[1],z[2]}),basis};
}
}

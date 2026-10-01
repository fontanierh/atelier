// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "SkeletonColliders.h"
#include "BoardStep.h"
namespace atelier::skate
{
bool AppendAssemblyContacts(std::vector<BoardCollision>& contacts,const std::vector<BoardWorldVolume>& board,
    const std::vector<BoardWorldVolume>& rider,std::uint32_t board_group,const SkeletonCollisionMode&,std::string& error);
void AppendPrimitivePairContacts(std::vector<BoardCollision>& contacts,const BoardWorldVolume& a,const BoardWorldVolume& b);
}

#pragma once
#include "BoardPossession.h"
#include "BoardAssembly.h"
namespace atelier::skate
{
void AppendBoardPossessionDrives(const BoardPossessionState&,BodySnapshot deck,
    const std::array<BodySnapshot,2>& hands,std::size_t deck_reaction,
    std::array<std::size_t,2> hand_reactions,float time_step,std::vector<DriveRows>& rows);
}

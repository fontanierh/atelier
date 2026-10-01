// SPDX-License-Identifier: Apache-2.0
#include "BoardPossessionManager.h"
namespace atelier::skate
{
void BoardPossessionManager::Reset(){*this=BoardPossessionManager{};}
void BoardPossessionManager::Enter(std::uint32_t previous,std::uint32_t current,BoardManagerSkeletonReset skeleton)
{
    if(previous!=500 && previous!=501 && previous!=502){Reset();skeleton.values_468={};skeleton.values_484={};skeleton.words_500={};skeleton.enabled_464=false;}
    flags_304_to_307[0]=current==502;
}
}

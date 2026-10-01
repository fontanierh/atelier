// SPDX-License-Identifier: Apache-2.0
#include "PlayerStateRegistry.h"
#include <iostream>
using namespace atelier::skate;
namespace {void Word(std::uint32_t word){for(unsigned byte=0;byte<4;++byte)std::cout.put(char(word>>(byte*8)));}}
int main()
{
    const PlayerStateRegistry registry;
    for(auto id:PhysicalStates)
    {
        const auto capability=registry.Capability(id);
        Word(std::uint32_t(capability.id));Word(capability.supported);Word(capability.has_enter);Word(capability.has_exit);
    }
    for(auto current:PhysicalStates)for(auto requested:PhysicalStates)
    {Word(std::uint32_t(current));Word(std::uint32_t(requested));Word(registry.CanTransition(current,requested));}
    return std::cout?0:2;
}

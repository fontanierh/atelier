// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "PlayerGrindInputWorld.h"
#include <memory>
namespace atelier::skate
{
// Already transformed native Y-up metres, in the exported mesh's authored
// triangle and rail order. Construction runs independently of a live session.
struct GameplayWorldSnapshot
{
    std::vector<std::array<Vec3,3>> triangles;
    std::vector<std::vector<std::array<float,3>>> rails;
};
struct PreparedGameplayWorld
{
    WorldGeometry collision;
    std::shared_ptr<const PlayerGrindStaticProvider> grind;
    // Contact-producer state, owned separately from the geometry in C++.
    bool imported_floor_seams=false;
};
bool BuildGameplayWorld(const GameplayWorldSnapshot&,ContactMaterial,
    std::optional<PreparedGameplayWorld>& output,std::string& error);
}

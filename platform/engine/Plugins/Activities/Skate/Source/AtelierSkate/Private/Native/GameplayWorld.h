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
    // Empty arrays retain the original stock material and packed surface zero.
    // A null material entry also uses the caller's stock fallback. The packed
    // surface is source data: low7 material bits, bits7..11 physics category.
    std::vector<std::optional<ContactMaterial>> triangle_materials;
    std::vector<std::uint16_t> triangle_surfaces;
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

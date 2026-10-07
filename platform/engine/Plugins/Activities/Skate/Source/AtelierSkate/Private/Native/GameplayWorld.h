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
    // Per triangle (or empty for none): the packed surface, physics surface << 7 | sound surface (GroundSurfaceRuntime).
    std::vector<std::uint16_t> surfaces;
    // Imported two-sided sheets retain both collision faces, but their
    // coincident backs are not adjoining bends. Off by default so construction
    // of the recovered host/reference corpus remains bit-exact.
    bool exclude_coincident_backfaces=false;
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

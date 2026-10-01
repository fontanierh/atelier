// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "WorldGeometry.h"
#include <string>
namespace atelier::skate
{
struct PlayerSceneProbe {Vec4 start,end;float radius;};
struct PlayerSceneProbeHit
{
    TriangleLineHit geometry;
    std::uint16_t packed_surface;
    std::size_t mesh_index;
    AffineTransform support_frame;
};
// Exact physics/offboard/contact_queries.rs query. Unlike other world line
// policies, this uses authored pool/group order, transforms and triangle fatness.
// The prior output remains intact on missing/invalid query metadata.
bool QueryPlayerSceneProbe(const WorldGeometry&,PlayerSceneProbe,std::uint32_t matching_id,
    std::optional<PlayerSceneProbeHit>& output,std::string& error);
}

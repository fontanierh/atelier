#pragma once
#include "OffboardGroundGeometry.h"
namespace atelier::skate
{
struct OffboardGroundEdgeSegment{OffboardGroundEdge edge;Bounds local_bounds;};
struct OffboardGroundEdgeBody{OffboardGroundFrame local_to_world;Bounds local_bounds;std::vector<OffboardGroundEdgeSegment> segments;};
struct OffboardGroundAlternateRecord{bool enabled;std::array<std::optional<std::pair<const OffboardGroundEdgeBody*,std::int32_t>>,2> choices;};
struct OffboardGroundIndexedBody{std::uint32_t id;bool disabled;const OffboardGroundEdgeBody* body;};
struct OffboardGroundEdgeSources
{
    const std::vector<OffboardGroundEdgeBody>& dynamic;
    const std::vector<OffboardGroundEdgeBody>& vehicles;
    const std::vector<OffboardGroundAlternateRecord>& alternates;
    const std::vector<OffboardGroundIndexedBody>& indexed;
    bool use_alternate;
};
// Ephemeral borrowed view of the canonical authored world and live edge views.
// Provider arrays are explicit; the scene supplies no fallback geometry.
class OffboardGroundScene
{
public:
    static std::optional<OffboardGroundScene> Create(const WorldGeometry&,OffboardGroundEdgeSources,std::string& error);
    std::vector<OffboardGroundEdge> EdgeCandidates(OffboardGroundEdgeSearch) const;
    bool QueryLines(const OffboardGroundPacket&,std::array<std::optional<OffboardGroundLineHit>,7>&,std::string& error) const;
private:
    OffboardGroundScene(const WorldGeometry& world,const QueryMetadata& metadata,OffboardGroundEdgeSources sources)
        :world_(&world),metadata_(&metadata),sources_(sources){}
    const WorldGeometry* world_;const QueryMetadata* metadata_;OffboardGroundEdgeSources sources_;
};
}

// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "OffboardContactToolkit.h"

namespace atelier::skate
{
// A scene borrows the current authored world. Query results themselves are
// retained by the toolkit; no scene is retained across terrain replacement.
class OffboardStaticScene final : public OffboardContactScene
{
public:
    static std::optional<OffboardStaticScene> Create(const WorldGeometry&,std::string& error);
    bool Execute(const OffboardQueryBatch&,OffboardQueryResults&,std::string& error) const override;
    bool Lines(const std::vector<OffboardLineProbe>&,std::int32_t matching_group,
               std::vector<std::optional<OffboardLineHit>>&,std::string& error) const;
    bool Trajectory(AirTrajectoryQueryRequest,std::int32_t matching_group,std::uint32_t mesh_reject_mask,
                    AirTrajectoryQueryResult&,std::string& error) const;
    // These operations retain mesh/triangle order and the reference's capacity.
    // Nearby intentionally does not apply the trajectory mesh rejection mask.
    bool Line(QueryPool,OffboardLineProbe,std::int32_t matching_group,std::uint32_t mesh_reject_mask,
              std::optional<OffboardLineHit>&,std::string& error) const;
    bool Nearby(QueryPool,Vec4 center,float radius,std::int32_t matching_group,
                std::vector<std::array<Vec4,3>>&,std::string& error) const;
private:
    OffboardStaticScene(const WorldGeometry& world,const QueryMetadata& metadata)
        :world_(&world),metadata_(&metadata){}
    std::vector<QueryPool> Pools() const;
    std::vector<std::array<Vec4,2>> Edges(const OffboardQueryBatch&) const;
    const WorldGeometry* world_;const QueryMetadata* metadata_;
};
}

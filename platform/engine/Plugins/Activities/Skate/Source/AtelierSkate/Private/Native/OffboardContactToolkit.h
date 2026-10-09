#pragma once
#include "AirTrajectoryQuery.h"
#include "SkeletonPoseFrames.h"
namespace atelier::skate
{
struct OffboardToolkitInput
{Vec4 position,forward,up,right,velocity,animation_up,animation_right;};
struct OffboardLineProbe {Vec4 start,end;float radius;};
struct OffboardProbeDescriptor
{OffboardLineProbe line;std::size_t forward_index;std::optional<std::size_t> reverse_index;};
struct OffboardQueryBatch
{
    OffboardToolkitInput input;std::int32_t matching_group;std::uint32_t mesh_reject_mask;
    std::array<AirTrajectoryQueryRequest,3> trajectories;std::vector<OffboardLineProbe> lines;
    std::vector<OffboardProbeDescriptor> secondary,primary;
};
struct OffboardProbeLayout
{
    std::array<OffboardLineProbe,3> trajectories;std::vector<OffboardProbeDescriptor> secondary,primary;
    static OffboardProbeLayout Stock();OffboardQueryBatch Prepare(OffboardToolkitInput,std::int32_t matching_group) const;
};
struct OffboardLineHit
{Vec4 position,normal;float fraction;std::uint16_t surface;Mat4 mesh_frame;std::uint32_t geometry;};
struct OffboardQueryResults
{std::array<AirTrajectoryQueryResult,3> trajectories;std::vector<std::optional<OffboardLineHit>> lines;std::vector<std::array<Vec4,2>> edges;};
class OffboardContactScene
{
public:
    virtual ~OffboardContactScene()=default;
    virtual bool Execute(const OffboardQueryBatch&,OffboardQueryResults&,std::string& error) const=0;
};
struct OffboardContactPrefix
{
    Vec4 position{},normal{0,1,0,0};Mat4 support_frame=SkeletonIdentity;
    Vec4 target_position{},target_normal{0,1,0,0},edge_position{},edge_normal{};
    float scalar_160=0;std::uint32_t kind_164=0;float distance_168=1.0e10f,distance_172=1.0e10f;
    std::uint32_t flags_176=0,support_180=0;
    void ConsumeSupport(OffboardToolkitInput,const std::array<AirTrajectoryQueryResult,3>&,std::uint32_t candidate_flags);
};
struct OffboardContactSample
{Vec4 position,normal;float forward_distance,height;std::uint32_t flags;float sort_distance;};
struct OffboardContactSamples
{
    std::vector<OffboardContactSample> ground,other;std::size_t original_ground_count=0;
    bool Insert(OffboardToolkitInput,Vec4 position,Vec4 normal,std::uint32_t category,float sort_override,std::uint32_t provenance);
};
struct OffboardContactCandidate
{
    Vec4 position{},normal{0,1,0,0},direction{};std::uint32_t flags=0;float low=0,high=0,order=0;
    std::int32_t segment=0;std::uint32_t kind=0;
};
struct OffboardContactHistory
{std::uint32_t accepted=0;std::array<std::uint32_t,3> samples{};std::size_t cursor=0;void Classify(OffboardContactPrefix&,Vec4 direction);};
struct OffboardCollectedContacts
{OffboardQueryBatch batch;OffboardQueryResults results;OffboardContactPrefix prefix;OffboardContactSamples samples;};
class OffboardContactToolkit
{
public:
    // Each query result is retained by value. The world/scene lifetime does not
    // extend across input boundaries or terrain replacements.
    OffboardProbeLayout layout=OffboardProbeLayout::Stock();
    std::optional<std::pair<OffboardQueryBatch,OffboardQueryResults>> pending;
    std::uint32_t readiness=0;OffboardContactPrefix prefix;OffboardContactCandidate candidate;OffboardContactHistory history;
    void BeginInput();void ResetHistory();
    bool Submit(OffboardToolkitInput,std::int32_t matching_group,const OffboardContactScene&,std::string& error);
    std::optional<OffboardCollectedContacts> Refresh();
};
Vec4 OffboardTriangleNormal(const std::array<Vec4,3>& vertices);
}

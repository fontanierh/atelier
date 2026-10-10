#pragma once
#include "GeometryTypes.h"
#include <vector>

namespace atelier::skate
{
enum class PrimitiveKind { Sphere,Capsule,Triangle,Box };
using GpRecord=std::array<std::uint32_t,48>;
using DirectionWords=std::array<std::uint32_t,4>;
using ProjectionInterval=std::array<std::uint32_t,12>;
using FeatureSegment=std::array<std::uint32_t,16>;
using MaximumFeature=std::array<std::uint32_t,144>;
using SeparatingAxes=std::array<DirectionWords,16>;

// Both projection callbacks retain interval words8..12. Batch box projection
// scales axes before the dot, while its single-direction callback scales after.
void ProjectDirection(const GpRecord& gp,PrimitiveKind kind,DirectionWords direction,ProjectionInterval& output);
void ProjectDirections(const GpRecord& gp,PrimitiveKind kind,const std::vector<DirectionWords>& directions,
                       std::vector<ProjectionInterval>& output);
std::size_t SeparatingAxisCandidates(const GpRecord& a,const GpRecord& b,SeparatingAxes& output);
std::pair<DirectionWords,DirectionWords> BestSeparatingDirection(const GpRecord& a,PrimitiveKind a_kind,
                                                               const GpRecord& b,PrimitiveKind b_kind);
void InitializeFeatureSegment(FeatureSegment& output,DirectionWords origin,DirectionWords end);
void CapsuleMaximumFeature(const GpRecord& gp,DirectionWords direction,MaximumFeature& output,FeatureSegment& scratch);
void TriangleMaximumFeature(const GpRecord& gp,std::uint32_t mode,DirectionWords direction,MaximumFeature& output);
void BoxMaximumFeature(const GpRecord& gp,std::uint32_t mode,DirectionWords direction,MaximumFeature& output,
                       DirectionWords incoming_edge_plane);
void BuildFeatureEdgePlanes(MaximumFeature& feature,std::uint32_t mode,DirectionWords direction);
}

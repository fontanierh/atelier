// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GeometryFeatures.h"

namespace atelier::skate
{
using FeaturePrism=std::array<std::uint32_t,136>;
std::uint32_t ClosestFeatureSegment(const FeatureSegment& segment,DirectionWords& point);
std::uint32_t IntersectPointFace(FeaturePrism& output,MaximumFeature& face,const MaximumFeature& point,
                               DirectionWords normal,bool face_is_a);
std::uint32_t ClampPointToFeature(const MaximumFeature& face,DirectionWords normal,DirectionWords& point);
std::uint32_t ClipSegmentToFeature(const MaximumFeature& face,const MaximumFeature& segment,DirectionWords normal,
                                  std::array<std::uint32_t,2>& interval,std::array<std::uint32_t,8>& outside);
std::uint32_t IntersectFeatureSegments(FeaturePrism& output,MaximumFeature& a,MaximumFeature& b,
                                     DirectionWords normal,bool a_is_first);
std::uint32_t IntersectSegmentFace(FeaturePrism& output,MaximumFeature& face,MaximumFeature& segment,
                                 DirectionWords normal,bool face_is_a);
std::uint32_t IntersectFeatureCornerEdge(FeaturePrism& output,MaximumFeature& a,MaximumFeature& b,
                                       std::size_t corner,std::size_t edge,bool a_is_first);
std::uint32_t FindFeatureIntersectionPrism(FeaturePrism& output,MaximumFeature& a,MaximumFeature& b,DirectionWords normal);
}

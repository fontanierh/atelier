#pragma once
#include "SkeletonCollisionFeedback.h"
#include "BoardStep.h"
namespace atelier::skate
{
struct SkeletonReportOwners
{
    const std::array<BodySnapshot,BoardBodyCount>& board;
    // Skeleton bodies, targets, then external proxies in original registration order.
    const std::vector<const BodySnapshot*>& attached;
    std::size_t local_attached_count;
    std::uint32_t board_group,skeleton_group;
};
void CollectSkeletonContactReports(std::vector<SkeletonContactReport>& output,
    const std::vector<ContactConstraint>& contacts,const SkeletonReportOwners&,float frequency);
}

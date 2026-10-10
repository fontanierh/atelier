#pragma once
#include "AirReckoning.h"
#include "WipeoutSettings.h"
#include "WipeoutRequests.h"
namespace atelier::skate
{
// Borrow completed physical feedback from the same player and solved frame.
// maximum_pose_error remains unavailable until the actual feedback producer.
struct WipeoutObservations
{
    const ProcessedPhysicsInput& processed;
    const BoardGroundState& board;
    const SkeletonCollisionFeedback& collision;
    Mat4 deck,input_board,world_to_animation;
    Vec4 pose_error;
    std::optional<float> maximum_pose_error;
    std::uint32_t jump_fix_frames;
    const AirReckoningState& air;
    float system_up_y;
    bool grind_locked_to_middle;
    std::optional<Vec4> grind_normal;
    bool Frame(WipeoutFrame&,std::string& error) const;
};
WipeoutRequestInput WipeoutRequestsFromProcessed(const ProcessedPhysicsInput&);
}

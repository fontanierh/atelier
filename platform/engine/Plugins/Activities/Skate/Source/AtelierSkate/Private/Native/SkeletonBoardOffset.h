#pragma once
#include "SkeletonPoseFrames.h"
namespace atelier::skate
{
struct SkateboardOffset
{
    Mat4 transform=SkeletonIdentity;
    float orientation_frames=0,height_frames=0;
    bool orientation_refreshed=false,height_refreshed=false;
    void RefreshTransform(Mat4);
    void RefreshHeight(float height,float frames);
    void Update(Mat4& board_pose,std::array<Mat4,4>& targets);
};
}

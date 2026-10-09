#pragma once
#include "DriveFrames.h"
#include "SkeletonPoseFrames.h"
namespace atelier::skate
{
DriveFrames BoneDriveFrames(const Mat4& child_animation,const Mat4& inverse_child,const Mat4& inverse_parent);
DriveFrames PrepareBoneDriveFrames(DriveFrames frames);
}

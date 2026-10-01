// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "DriveFrames.h"
namespace atelier::skate
{
std::array<AffineTransform,2> SteeringTruckTransforms(std::array<AffineTransform,2> base,std::array<float,2> targets);
std::array<DriveFrames,2> SteeringDriveFrames(std::array<AffineTransform,2> base,std::array<float,2> targets);
}

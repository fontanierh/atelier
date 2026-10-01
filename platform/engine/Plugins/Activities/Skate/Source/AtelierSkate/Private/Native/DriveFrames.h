// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GeometryTypes.h"

namespace atelier::skate
{
struct AuthoredTransformInputs
{
    float deck_mid_length,wheel_x_distance,truck_z_position_front,truck_z_position_back,truck_y_position;
    static AuthoredTransformInputs Stock();
};
struct TruckTransformInputs
{
    float deck_mid_length,truck_z_position_front,truck_z_position_back,truck_y_position,truck_rotation_axis_angle_degrees;
    static TruckTransformInputs Stock();
};
struct DriveFrame { Quat orientation{0,0,0,1};Vec3 translation{}; };
struct DriveFrames { DriveFrame body_a{},body_b{}; };
struct DriveFrameRaw { std::array<std::uint32_t,4> quaternion_lanes{},translation_lanes{}; };
struct DriveFramesRaw { DriveFrameRaw body_a{},body_b{}; };
std::array<AffineTransform,7> AuthoredBodyTransforms(AuthoredTransformInputs input);
std::array<std::array<std::uint32_t,16>,7> AuthoredBodyPoseRecords(AuthoredTransformInputs input);
std::array<AffineTransform,2> CalculateTruckTransforms(TruckTransformInputs input);
Quat QuaternionFromBasis(Basis3 basis);
DriveFrames SetDriveFrames2(AffineTransform parent_world,AffineTransform child_world);
DriveFramesRaw PackDriveFrames(DriveFrames frames);
std::array<AffineTransform,7> DefaultLiveBodyTransforms();
std::array<Quat,7> DefaultLiveBodyOrientations();
std::array<DriveFrames,2> DefaultTruckDriveFrames();
std::array<DriveFrames,4> DefaultWheelDriveFrames();
}

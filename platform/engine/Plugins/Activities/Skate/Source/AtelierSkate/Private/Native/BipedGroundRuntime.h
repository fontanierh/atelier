// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "BipedRuntimeOwners.h"
#include "BipedGroundLifecycle.h"
namespace atelier::skate
{
class BipedGroundRuntime
{
public:
    OffboardController controller;
    std::optional<BipedGroundResult> result;
    BipedGroundState state;
    OffboardContactPrefix contact;
    std::optional<OffboardGroundAdjustment> geometry_adjustment;
    BipedSkeletonState skeleton_state;
    OffboardGroundGeometry geometry;
    PointGraph<8> movement_vs_stick_angle,turn_vs_stick_angle;
    OffboardAirLaunchSettings air_launch;
    BipedGroundCollisionSettings collision_settings;
    OffboardBoardSettings grab_settings;
    static std::optional<BipedGroundRuntime> Load(const SettingsDatabase&,const AnimationMetadata&,std::string& error);
    void Reset(OffboardContactToolkit&);
    void EnterCore(BipedGroundEntryInput,std::uint32_t current_state,Mat4 previous_frame,OffboardContactToolkit&);
    bool Enter(BipedRuntimeOwners,std::string& error);void Exit(OffboardContactToolkit&);
    BipedGroundResult Run(const BipedGroundJob&);
    // ContactSnapshot is captured by the frame's PreState before Refresh.
    // A successful update returns the seven vectors submitted by that frame.
    bool Update(BipedRuntimeOwners,BipedGroundContactSnapshot,OffboardToolkitInput&,std::string& error);
    bool SubmitGeometry(BipedRuntimeOwners,std::string& error);
    void PostPhysics(BipedRuntimeOwners,const WipeoutFrame& actual_frame);
    bool Fill(BipedRuntimeOwners,BipedStatePublication&,std::string& error) const;
    bool PrepareAir(const OffboardAirLaunchInput&,float elapsed_2664,Vec4 skeleton_point_10960,
        std::optional<OffboardAirLaunchPacket>&,std::string& error);
private:
    explicit BipedGroundRuntime(OffboardSettings settings);
    bool UpdateSkeleton(BipedRuntimeOwners,Mat4 animation_frame,Vec4 centre_of_mass,std::string& error);
    void UpdatePossession(BipedRuntimeOwners);
    void SyncGrab(BipedRuntimeOwners);
};
}

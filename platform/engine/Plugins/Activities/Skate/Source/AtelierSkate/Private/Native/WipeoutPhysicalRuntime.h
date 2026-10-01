// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "WipeoutPhysicalSettings.h"
#include "WipeoutRagdoll.h"
#include "WipeoutPrediction.h"
#include "WipeoutContactResponse.h"
#include "WipeoutRuntime.h"
#include "PlayerInputRuntime.h"
#include "GroundPhaseRuntime.h"
#include "SkeletonInputRuntime.h"
#include "AirStateSettings.h"
namespace atelier::skate
{
struct WipeoutPhysicalOwners
{
    PhysicalSimulationRuntime& physical;
    PlayerInputRuntime& input;
    GroundStateRuntime& ground;
    GroundPhaseLifecycle& life;
    AnimatedSkeleton& animated;
    FootIk& ik;
    PhysicsAnimationInput& animation_input;
    SkeletonInputRuntime& skeleton_input;
    WipeoutRuntime& wipeout;
    const AirStateSettings& air_settings;
    const std::vector<Mat4>& globals;
};
class WipeoutPhysicalRuntime
{
public:
    WipeoutRagdollSetup ragdoll;
    WipeoutPhysicalState state;
    WipeoutPhysicalSettings settings;
    WipeoutDriveSettings drives;
    std::array<WipeoutControlProfile,5> profiles;
    WipeoutContactResponse contact;
    WipeoutPrediction prediction;
    // canonical_physical is the same bank-validated PHYS_TPOSE constructor
    // record used by the live body; no second skeleton/history is constructed.
    bool Load(const SettingsDatabase&,const PhysicsSkeleton& canonical_physical,std::string& error);
    bool Enter(WipeoutPhysicalOwners,std::string& error);
    void Exit(WipeoutPhysicalOwners);
    bool Advance(WipeoutPhysicalOwners,std::string& error);
    void PostPhysics(WipeoutPhysicalOwners);
    WipeoutPhysicalOutput Fill(WipeoutPhysicalOwners) const;
private:
    bool UpdateContact(WipeoutPhysicalOwners,bool actual_contact,Vec4 com_velocity,Vec4 effective_axis,std::array<float,2> controls,std::string&);
    bool UpdateSkeleton(WipeoutPhysicalOwners,float start,float end,float controlled,float extra,bool skip_targets,float& residual,std::string&);
};
}

#pragma once
#include "BipedFeet.h"
#include "GroundPhaseRuntime.h"
#include "LandingDeck.h"
#include "OffboardAirSelector.h"
#include "OffboardGrabRuntime.h"
#include "SkeletonBiped.h"
#include "WipeoutRuntime.h"
namespace atelier::skate
{
// The coordinator supplies the same owners used by input, Ground, Air,
// animation and shared solve. None of these histories is copied by Biped.
struct BipedRuntimeOwners
{
    PhysicalSimulationRuntime& physical;
    ProcessedPhysicsInput& processed;
    PhysicalPlayerInput& publication;
    const std::optional<BoardToolkit>& toolkit;
    AnimatedSkeleton& animated;FootIk& ik;PhysicsAnimationInput& animation_input;
    SkeletonInputRuntime& skeleton_input;SkeletonAir& skeleton_air;
    const std::vector<Mat4>& hierarchy;
    GroundStateRuntime& ground;GroundPhaseLifecycle& life;
    const AirStateSettings& air_settings;AirReckoning& air_reckoning;WipeoutRuntime& wipeout;
    OffboardContactToolkit& contact;OffboardAirSelector& selector;
    BoardPossessionManager& feet;LandingDeck& landing;OffboardGrabRuntime& grab;
    SkeletonInputOwners SkeletonOwners() const{return {physical,animated,ik,animation_input};}
};
SkeletonInputCollision BipedRuntimeCollision(const PhysicalSimulationRuntime&);
OffboardAirContext BipedRuntimeAirContext(const ProcessedPhysicsInput&);
Vec4 BipedRuntimeGravity(const PhysicalSimulationRuntime&);
Mat4 EffectiveBipedAirFrame(Mat4,std::uint32_t flags_2476);
bool BipedRuntimeLaunchInput(BipedRuntimeOwners,std::optional<OffboardDepartureGeometry>,
    const char* missing_toolkit,OffboardAirLaunchInput&,std::string& error);
}

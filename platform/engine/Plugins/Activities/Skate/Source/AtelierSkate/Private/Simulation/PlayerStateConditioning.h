#pragma once
#include "FilteredState.h"
#include "LandingQuality.h"
#include "PlayerStateLifecycle.h"
#include "KnownAirTypes.h"
#include "GrindRuntime.h"
#include "AnimationPublication.h"
namespace atelier::skate
{
// Only source conditioner history lives here. Physical/input/animation/grind
// histories and the selected state remain in their canonical borrowed owners.
class PlayerStateConditioning
{
public:
    FilteredState filtered;
    std::optional<FilteredStateOutput> filtered_output;
    LandingQualitySettings landing_settings;
    LandingQualityOutput landing_quality;
    bool Load(const SettingsDatabase&,std::string& error);
    void ResetFilteredForTeleport();
    // Run after all selected-state Fill writes and before Wipeout/Teleport
    // output tails. Ground output and KnownAir state are actual owner records.
    bool Publish(GrindRuntime&,GrindRuntimeOwners,const PhysicalPlayerStateLifecycle&,
        const std::optional<PhysicsGroundOutput>& completed_ground_output,
        const KnownAirState&,const PhysicsPosePacket& actual_animation_packet,std::string& error);
    // Original animation_phase::publish_feedback landing/capability prefix.
    // Complete animation feedback is a separate canonical producer.
    void PublishLandingQuality(const PhysicalSimulationRuntime&,PlayerInputRuntime&,const AirReckoning&);
};
struct ConditionerCapabilityContext
{
    bool in_front_end,hall_of_meat_enabled,challenge_query_active,challenge_configuration_enabled;
    std::uint32_t Capabilities() const;
};
}

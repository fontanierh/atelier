#pragma once
#include "AnimationPublication.h"
#include "PlayerInputTypes.h"
#include "Settings.h"
namespace atelier::skate
{
struct AnimationProfile
{
    float maximum_ground_angle_degrees=0,skitch_transition_time=0,truck_tightness=0,wheel_hardness=0;
    std::uint32_t physics_mode=0;
    bool prevent_manual_respawn=false;
    std::uint8_t ignore_respawn_reset_button=0;
    bool force_braking=false,suppress_transition=false;
    std::optional<std::array<std::uint32_t,4>> gesture_selections;
    bool suppress_up_gesture=false,gesture_force_brake_bypass=false;
    bool Load(const SettingsDatabase&,std::string_view mode,std::string& error);
};
struct AnimationExternalReset {RawMatrix transform{};std::uint8_t byte64=0;};
// Entire actual host animation_phase_packet.rs storage and publication. The
// inactive external-provider fields reproduce explicit pinned host constants.
class AnimationPhaseOutput
{
public:
    AnimationPhaseOutput();
    AnimationAdditionalResetFields reset;
    void Publish(const PhysicsPosePacket&,const AnimationProfile&,std::uint32_t actor_flags);
    void PublishExternalReset(AnimationExternalReset);
    AnimationInputPacket Packet() const;
    const AnimationPacketFields& Publication() const {return publication_;}
    const ExternalPhysicsInput& External() const {return external_;}
    std::uint8_t Mirrored() const {return mirrored_;}
    std::uint8_t WeightForwards() const {return weight_forwards_;}
    std::uint32_t Flags() const {return flags_;}
private:
    AnimationPacketFields publication_{};
    ExternalPhysicsInput external_{};
    std::uint8_t mirrored_=0,weight_forwards_=0;
    std::uint32_t flags_=0;
};
}

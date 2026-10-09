#pragma once
#include "GroundBoard.h"
#include "GroundTorqueSettings.h"
#include "GeometryTypes.h"
#include "TrainerTuning.h"
#include <memory>
namespace atelier::skate
{
struct GroundSettings
{
    SteeringSettings steering;
    SpeedWobbleSettings wobble;
    GroundPropulsionSettings propulsion;
    GroundForceSettings force;
    SpeedModelSettings speed;
    GroundTorqueSettings torque;
    ManualSettings manual;
    ManualMode manual_mode;
    LinearDragSettings drag;
    float collision_duration,collision_scale,contact_force_time;
    ContactMaterial wheel_material;
    float foot_force_offset,push_target_multiplier,absorption_front,absorption_rear;
    float surface_braking_factor,wobble_activation,wobble_amplitude;
    bool Load(const SettingsDatabase&,std::string_view mode,std::string_view surface,std::string&);
    GroundSettings Tuned(TrainerTuning) const;
    GroundBoardSettings Board() const;
};
class GroundProfiles
{
public:
    bool Load(const SettingsDatabase&,std::string&);
    std::shared_ptr<const GroundSettings> Select(std::uint32_t mode,std::uint32_t surface,std::string&) const;
private:
    std::array<std::array<std::shared_ptr<const GroundSettings>,5>,5> profiles_{};
};
}

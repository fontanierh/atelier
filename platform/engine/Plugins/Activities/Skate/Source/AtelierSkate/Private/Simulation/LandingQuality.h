#pragma once
#include "SimulationMath.h"
#include "Settings.h"
namespace atelier::skate
{
struct LandingQualitySettings
{
    PointGraph<4> twist_spin,side_speed;
    bool Load(const SettingsDatabase&,std::string& error);
};
struct LandingQualityInput
{
    std::uint32_t previous_filtered_state,filtered_state;
    Vec4 ground_normal,deck_velocity;
    bool flipped;
    Vec4 reckoning_forward;
    float air_spin;
};
struct LandingQualityOutput
{
    float landing_adjust_80=0,sideways_speed_84=0,forward_speed_88=0,spin_92=0;
    std::uint32_t landing_type_96=0;
    bool landing_data_167=false;
    // The core preserves all fields on nonlanding frames. The host separately
    // resets this record before each completed-output publication.
    void Update(LandingQualityInput,const LandingQualitySettings&);
};
}

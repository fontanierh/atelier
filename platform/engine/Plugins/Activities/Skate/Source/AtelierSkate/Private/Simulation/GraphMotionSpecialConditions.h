#pragma once
#include "GraphConditions.h"
#include "Settings.h"
namespace atelier::skate
{
struct MotionGraphGrindConditionInputs
{
    bool filtered_grinding_80;
    std::uint32_t blunting_136,approach_268,trick_out_240;
    bool air_grind_443;
    float air_time_184;
    bool dropping_in_324;
};
struct MotionGraphLandingInputs {float height,spin;std::uint32_t kind;float last_good_landing_velocity;};
struct MotionGraphWipeoutConditionInputs
{
    bool over_599;
    float collision_time_144,no_support_time_548;
    std::uint32_t profile_148;
    bool below_surface_82;
    std::optional<float> orientation_y;
    float hips_right_angle_496,hips_up_angle_500;
};
struct MotionGraphPrelandingInputs
{
    bool air_444;
    float air_normal_144_y,animation_16_x,com_velocity_y;
    bool offboard_316,offboard_319;
    float offboard_time_32;
    bool air_437;
    float air_normal_36,air_remaining_184,animation_height_72;
};
struct MotionGraphPrelandingConditionSettings
{
    float override_x,override_velocity_y;
    bool Load(const SettingsDatabase&,std::string& error);
};
bool MotionGraphOverridePrelanding(const MotionGraphPrelandingInputs&,const MotionGraphPrelandingConditionSettings&);
struct MotionSpecialConditionContext
{
    const std::optional<MotionGraphGrindConditionInputs>& grind;
    const std::optional<MotionGraphLandingInputs>& landing;
    const std::optional<MotionGraphWipeoutConditionInputs>& wipeout;
    const std::optional<MotionGraphPrelandingInputs>& prelanding;
    const MotionGraphPrelandingConditionSettings& prelanding_settings;
};
struct GraphMotionSpecialCondition
{
    enum class Kind {Unsupported,GrindBlunting,GrindApproach,GrindTrickOut,LandingIntoGrind,DroppingIn,LandingType,TiltForPreland,
        DoneWipingOut,WipeoutTimeToLand,WipeoutTimeSinceContact,GestureType,InWater};
    Kind kind=Kind::Unsupported;
    NumericCondition numeric;
    std::uint32_t value=0;
    bool Evaluate(const MotionSpecialConditionContext&,bool& result,std::string& error) const;
};
bool ParseGraphMotionSpecialCondition(const GraphAttributes&,GraphMotionSpecialCondition&,bool& recognized,std::string& error);
}

#pragma once
#include "InputIntentions.h"
#include "Settings.h"
#include "AnimationPhysical.h"

namespace atelier::skate
{
struct AnimationAutoPumpSettings
{
    PointGraph<4> maximum_crouch;
    float sufficient_crouch,standing_threshold,rise_speed,pump_speed,potential_threshold,potential_blend;
    float intent_magnitude_start,intent_angle_region,crouch_time,crouch_speed;
};
struct AnimationCrouchingSettings
{
    PointGraph<8> maximum_height,absorption_upforce,pump_maxspeed;
    float minimum_height,maximum_ratio,maximum_delta_delta,maximum_delta,input_blend;
    float pump_vertical_speed,maximum_crouch_from_deck,skateboard_damping,maximum_force,maximum_ground_force,absorption_factor;
    AnimationAutoPumpSettings auto_pump;
};
struct AnimationCrouchingIntents
{
    std::optional<float> auto_pump_angle,auto_pump_magnitude,crouch,hard_turn_crouch,manual;
    bool motion_flag_108=false;
};
struct AnimationCrouchingOutput {float height;bool new_auto_pump,player_controlled_pump;};
struct AnimationCrouchingState
{
    float absorbed_velocity=0,filtered_input=0,fraction=0,delta_fraction=0;
    bool player_pumping=false;
    float auto_fraction=0;
    std::uint32_t auto_state=0;
    float auto_time=0,previous_angle=0,previous_magnitude=0,filtered_potential=0,pump_idle_time=0.5f;
    static AnimationCrouchingState Begin(const AnimationCrouchingPhysical&,const AnimationCrouchingSettings&);
    AnimationCrouchingOutput Update(const AnimationCrouchingPhysical&,AnimationCrouchingIntents,float dt,const AnimationCrouchingSettings&);
};
struct AnimationBodyTiltSettings {PointGraph<4> body_spin_factor;float ground_velocity,ground_acceleration,air_velocity,air_acceleration;};
struct AnimationBodyTiltState
{
    float value=0,velocity=0;
    bool was_enabled=false;
    void Disable() {was_enabled=false;}
    std::optional<float> Update(bool enabled,bool mirrored,const AnimationBodyTiltPhysical&,const AnimationBodyTiltSettings&);
};
struct AnimationFakieSettings {float high_speed,low_speed,slowly_backwards_seconds,after_teleport_seconds;};
struct AnimationFakieState
{
    float slowly_backwards=0,after_teleport=0;
    std::optional<bool> Update(const AnimationFakiePhysical&,float dt,AnimationFakieSettings);
};
struct AnimationPumpSettings {PointGraph<8> amplify;float input_blend,maximum_physics_pump,new_pump_threshold,blend_in,blend_out;};
struct AnimationPumpUpdate {std::optional<std::size_t> start;std::optional<std::pair<std::size_t,float>> influence;};
struct AnimationPumpState
{
    float value=0,filtered=0;
    std::optional<std::size_t> channel;
    float peak=0;
    AnimationPumpUpdate Update(float physics_pump,std::array<bool,5> occupied,const AnimationPumpSettings&);
};
struct AnimationGroundAccelerationSettings {float scale_x_acc,min_bump_mag;};
struct AnimationGroundAccelerationInput {Mat4 deck,ground;Vec4 world_acceleration;};
struct AnimationGroundAccelerationOutput {Vec4 acceleration;bool bumped;};
Vec4 ConditionAnimationGroundAcceleration(AnimationGroundAccelerationInput);
bool AnimationIsBumped(Vec4 acceleration,AnimationGroundAccelerationSettings);
AnimationGroundAccelerationOutput PublishAnimationGroundAcceleration(AnimationGroundAccelerationInput,AnimationGroundAccelerationSettings);
// Actual completed BoardMotion/Pumping/SpeedWobble/Reckoning inputs. Producer
// identity remains explicit; animation never estimates these from a pose.
struct AnimationBoardFeedback {float speed,forward_speed,ground_speed,linear_velocity_y;};
struct AnimationPumpingFeedback {float pumping,absorption,ground_normal_absorption,minimum_crouch,deck_angle_absorption,pump_acceleration;};
struct AnimationReckoningFeedback {Vec3 system_position,system_up,board_position;float target_lean_angle;};
struct AnimationControlFeedback {std::uint32_t processed_flags;float turn;bool animation_mirrored;};
AnimationPhysicalFeedback PublishPhysicalAnimationFeedback(TurnConditionerState&,const TurnConditionerSettings&,
    AnimationBoardFeedback,AnimationPumpingFeedback,float speed_wobble_36,AnimationReckoningFeedback,
    AnimationControlFeedback,AnimationGroundAccelerationOutput);
bool LoadAnimationCrouchingSettings(const SettingsDatabase&,AnimationCrouchingSettings&,std::string& error);
bool LoadAnimationBodyTiltSettings(const SettingsDatabase&,AnimationBodyTiltSettings&,std::string& error);
bool LoadAnimationPumpSettings(const SettingsDatabase&,AnimationPumpSettings&,std::string& error);
bool LoadAnimationTurningSettings(const SettingsDatabase&,SetTurningSettings&,std::string& error);
bool LoadAnimationTurnFeedbackSettings(const SettingsDatabase&,TurnConditionerSettings&,std::string& error);
bool LoadAnimationGroundAccelerationSettings(const SettingsDatabase&,AnimationGroundAccelerationSettings&,std::string& error);
}

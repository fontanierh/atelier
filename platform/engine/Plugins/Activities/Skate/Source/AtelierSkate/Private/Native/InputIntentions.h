#pragma once
#include "Input.h"
#include "Intents.h"
#include "NativeMath.h"
#include <functional>
#include <string_view>

namespace atelier::skate
{
struct ControllerIntent { std::string_view name; float value; };
struct PushPreferences { bool automatic_push_enabled = false, automatic_push_right = false; };
struct SteeringIntentions { std::optional<float> turn, hard_turn, hard_turn_crouch; };
SteeringIntentions ProduceSteering(std::array<float,2> left, std::uint32_t actor_flags);
std::vector<ControllerIntent> ProduceRiding(const DerivedControllerInput&, std::uint32_t actor_flags, PushPreferences);
std::vector<ControllerIntent> ProduceAnticipation(const DerivedControllerInput&);
std::vector<ControllerIntent> ProduceManual(const DerivedControllerInput&, std::uint32_t actor_flags);
std::vector<ControllerIntent> ProduceTrick(const DerivedControllerInput&);
std::vector<ControllerIntent> ProduceGrind(const DerivedControllerInput&);
std::vector<ControllerIntent> ProduceWipeout(const DerivedControllerInput&, std::uint32_t actor_flags, std::uint32_t physical_flags);
std::vector<ControllerIntent> ProduceOffboardDiscrete(const DerivedControllerInput&, std::uint32_t actor_flags, bool air_reckoning_active);
struct OffboardAnalogObservation { Vec4 effective_skeleton_z; std::optional<Vec4> biped_correction; };
std::array<ControllerIntent,4> ProduceOffboardAnalog(const DerivedControllerInput&, OffboardAnalogObservation);
struct BodyFlipSettings { float gesture_window = 0, takeoff_window = 0; };
struct BodyFlipState
{
    float gesture_time = 0, takeoff_time = 0;
    std::optional<std::size_t> selected;
    void Begin(BodyFlipSettings);
    std::optional<std::size_t> Update(std::array<bool,2> present, std::uint32_t category, float dt, BodyFlipSettings);
};
struct TurnRemap
{
    PointGraph<16> magnitude, angle;
    float angle_offset = 0;
    Vec4 Apply(std::array<float,2> input) const;
};
struct TurnConditionerSettings
{
    std::array<std::array<float,4>,3> filter_coefficients;
    PointGraph<8> input_curve, quickness_curve, speed_curve;
    PointGraph<4> smoothing_curve;
    std::array<float,13> parameters;
};
struct TurnConditionerState
{
    std::array<float,8> history;
    std::array<std::array<float,9>,3> filters;
    void ResetHistory();
};
struct TurnConditionerInput
{
    float body_160, body_176, bundle_36_field_160, bundle_32_field_264;
    std::uint8_t animation_152, animation_156;
};
std::array<float,8> UpdateTurnConditioner(TurnConditionerState&, TurnConditionerInput, const TurnConditionerSettings&);
struct SlideLatch
{
    std::array<std::uint32_t,5> words{};
    bool CapturedFakie() const { return (words[4]&0x80000000) != 0; }
    bool CandidateEnabled() const { return (words[4]&0x40000000) != 0; }
    void SetCandidateEnabled(bool);
    float Elapsed(bool right) const;
    bool Start(bool right) const { return (words[right ? 3 : 1]&0x80000000) != 0; }
    bool End(bool right) const { return (words[right ? 3 : 1]&0x40000000) != 0; }
    void SetStart(bool right, bool value);
    void SetEnd(bool right, bool value);
    void AdvanceElapsed(bool right, float dt);
    void BeginSlide(bool fakie);
    void Grab(bool authored_right);
    bool ShouldLeave(bool authored_right) const { return End(authored_right != CapturedFakie()); }
    void Reset();
};
struct SetTurningState { float elapsed = 0, smoothed = 0; std::uint32_t mode = 2; void Enter(); };
struct SetTurningSettings
{
    std::array<TurnRemap,2> remaps;
    PointGraph<8> speed_tuck, blend;
    float speed_threshold, maximum_delta, override_turn;
};
struct SetTurningPhysical { float field_32, field_36, field_52, field_56, field_60, body_168; };
struct SetTurningIntents { std::optional<float> fakie_turn, mode_0_slide, mode_1_slide; };
enum class TurningAttribute { Angle, Direction, Quickness, Speed, Holding, Turn, Slide };
void UpdateSetTurning(SetTurningState&, SlideLatch&, SetTurningPhysical, Stance, float dt,
    const SetTurningSettings&, SetTurningIntents, const std::function<void(TurningAttribute,float)>& emit);
struct PowerSlidingState { float elapsed = 0, previous_right = 0, previous_left = 0; std::uint32_t flags = 0; };
struct PowerSlidingSettings
{
    float minimum_speed, minimum_slide_time;
    PointGraph<4> stop_time, speed_response, angle_response;
};
struct PowerSlidingInput
{
    std::uint32_t category;
    float speed;
    std::optional<float> right_slide, left_slide;
    bool right_query, left_query;
    float graph_scalar;
};
struct PowerSlidingAlignmentInput { Vec4 velocity, basis; std::uint8_t flipped; };
float PowerSlidingAlignment(std::optional<PowerSlidingAlignmentInput>);
void UpdatePowerSliding(PowerSlidingState&, SlideLatch&, PowerSlidingInput, const PowerSlidingSettings&, const std::function<float()>& clock);
struct AnimationPacketFields
{
    std::uint8_t stance_byte;
    float timestep, scalar_10388;
    std::array<std::uint8_t,3> flags_10375_10496_10784;
    std::array<std::uint32_t,4> vector_10480;
    std::array<std::array<std::uint32_t,4>,4> matrix_10704;
    std::uint8_t byte_10768;
    float truck_tightness, scalar_10792;
    std::uint8_t flag_10371;
};
struct ProcessedPacketFields
{
    std::uint32_t flags_2468, flags_2476;
    float timestep, scalar_2668;
    std::array<std::uint32_t,4> vector_1520;
    std::array<std::array<std::uint32_t,4>,4> matrix_1536;
    std::uint8_t byte_1600;
    float truck_tightness, scalar_2764;
};
void PublishAnimationPacket(const AnimationPacketFields&, ProcessedPacketFields&);
}

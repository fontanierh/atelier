// SPDX-License-Identifier: Apache-2.0
#include "RidingAnimation.h"
#include "SkaterAnimation.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace
{
struct Input:detail::DataReader
{
    explicit Input(const std::vector<std::uint8_t>& bytes):DataReader{bytes} {at=8;}
    bool Bool() {return Word()!=0;}
    Vec4 Vector() {Vec4 v;for (auto& f:v) f=Float();return v;}
    Vec3 Position() {return {Float(),Float(),Float()};}
    std::optional<float> Optional() {return Bool()?std::optional<float>(Float()):std::nullopt;}
    Mat4 Matrix() {Mat4 m;for (auto& c:m) c=Vector();return m;}
    template<std::size_t N> PointGraph<N> Curve() {PointGraph<N> p;for (auto& f:p.x) f=Float();for (auto& f:p.y) f=Float();return p;}
    AnimationCrouchingSettings CrouchSettings()
    {
        AnimationCrouchingSettings s;s.maximum_height=Curve<8>();s.absorption_upforce=Curve<8>();s.pump_maxspeed=Curve<8>();
        s.minimum_height=Float();s.maximum_ratio=Float();s.maximum_delta_delta=Float();s.maximum_delta=Float();s.input_blend=Float();s.pump_vertical_speed=Float();s.maximum_crouch_from_deck=Float();s.skateboard_damping=Float();s.maximum_force=Float();s.maximum_ground_force=Float();s.absorption_factor=Float();
        s.auto_pump={Curve<4>(),Float(),Float(),Float(),Float(),Float(),Float(),Float(),Float(),Float(),Float()};return s;
    }
    AnimationCrouchingPhysical CrouchPhysical() {return {Float(),Float(),Float(),Float(),Float(),Float(),Float(),Float()};}
    AnimationCrouchingIntents CrouchIntents() {return {Optional(),Optional(),Optional(),Optional(),Optional(),Bool()};}
    AnimationBodyTiltSettings TiltSettings() {return {Curve<4>(),Float(),Float(),Float(),Float()};}
    AnimationFakieSettings FakieSettings() {return {Float(),Float(),Float(),Float()};}
    AnimationFakiePhysical FakiePhysical() {return {Word(),Word(),Bool(),Vector(),Vector(),Vector(),Float()};}
    AnimationPumpSettings PumpSettings() {return {Curve<8>(),Float(),Float(),Float(),Float(),Float()};}
};
void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) std::cout.put(char(v>>(8*i)));}
void Float(float v) {std::uint32_t word;std::memcpy(&word,&v,4);Word(word);}
void Optional(std::optional<float> v) {Word(bool(v));if (v) Float(*v);}
template<std::size_t N> void Curve(const PointGraph<N>& p) {for (const auto f:p.x) Float(f);for (const auto f:p.y) Float(f);}
void Settings(const AnimationCrouchingSettings& s)
{
    Curve(s.maximum_height);Curve(s.absorption_upforce);Curve(s.pump_maxspeed);
    for (const auto f:{s.minimum_height,s.maximum_ratio,s.maximum_delta_delta,s.maximum_delta,s.input_blend,s.pump_vertical_speed,s.maximum_crouch_from_deck,s.skateboard_damping,s.maximum_force,s.maximum_ground_force,s.absorption_factor}) Float(f);
    const auto& a=s.auto_pump;Curve(a.maximum_crouch);for (const auto f:{a.sufficient_crouch,a.standing_threshold,a.rise_speed,a.pump_speed,a.potential_threshold,a.potential_blend,a.intent_magnitude_start,a.intent_angle_region,a.crouch_time,a.crouch_speed}) Float(f);
}
void Settings(const AnimationBodyTiltSettings& s) {Curve(s.body_spin_factor);for (const auto f:{s.ground_velocity,s.ground_acceleration,s.air_velocity,s.air_acceleration}) Float(f);}
void Settings(const AnimationPumpSettings& s) {Curve(s.amplify);for (const auto f:{s.input_blend,s.maximum_physics_pump,s.new_pump_threshold,s.blend_in,s.blend_out}) Float(f);}
void Settings(const SetTurningSettings& s) {for (const auto& remap:s.remaps) {Curve(remap.magnitude);Curve(remap.angle);Float(remap.angle_offset);}Curve(s.speed_tuck);Curve(s.blend);Float(s.speed_threshold);Float(s.maximum_delta);Float(s.override_turn);}
void Settings(const TurnConditionerSettings& s) {for (const auto& c:s.filter_coefficients) for (const auto f:c) Float(f);Curve(s.input_curve);Curve(s.quickness_curve);Curve(s.speed_curve);Curve(s.smoothing_curve);for (const auto f:s.parameters) Float(f);}
std::vector<std::uint8_t> File(const char* path) {std::ifstream f(path,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
}
int main(int argc,char** argv)
{
    if (argc!=2) return 2;SettingsDatabase data;std::string error;if (!data.Load(File(argv[1]),error)) {std::cerr<<error;return 2;}
    AnimationCrouchingSettings stock_crouch;AnimationBodyTiltSettings stock_tilt;AnimationPumpSettings stock_pump;SetTurningSettings stock_turn;TurnConditionerSettings stock_feedback;AnimationGroundAccelerationSettings stock_ground;
    if (!LoadAnimationCrouchingSettings(data,stock_crouch,error)||!LoadAnimationBodyTiltSettings(data,stock_tilt,error)||!LoadAnimationPumpSettings(data,stock_pump,error)||!LoadAnimationTurningSettings(data,stock_turn,error)||!LoadAnimationTurnFeedbackSettings(data,stock_feedback,error)||!LoadAnimationGroundAccelerationSettings(data,stock_ground,error)) {std::cerr<<error;return 2;}
    const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input input(bytes);const auto count=input.Word();
    for (std::uint32_t i=0;i<count;++i)
    {
        switch (input.Word())
        {
        case 0:Settings(stock_crouch);Settings(stock_tilt);Settings(stock_pump);Settings(stock_turn);Settings(stock_feedback);Float(stock_ground.scale_x_acc);Float(stock_ground.min_bump_mag);break;
        case 1:
        {
            const auto settings=input.Bool()?stock_crouch:input.CrouchSettings();const auto physical=input.CrouchPhysical();auto state=AnimationCrouchingState::Begin(physical,settings);Float(state.fraction);const auto steps=input.Word();
            for (std::uint32_t j=0;j<steps;++j) {const auto p=input.CrouchPhysical();const auto intents=input.CrouchIntents();const auto result=state.Update(p,intents,input.Float(),settings);Float(result.height);Word(result.new_auto_pump);Word(result.player_controlled_pump);Float(state.fraction);}break;
        }
        case 2:
        {
            const auto settings=input.Bool()?stock_tilt:input.TiltSettings();AnimationBodyTiltState state;const auto steps=input.Word();
            for (std::uint32_t j=0;j<steps;++j) {const auto action=input.Word();if (action==2) {state.Disable();Optional(std::nullopt);}else {const bool mirrored=input.Bool();const AnimationBodyTiltPhysical p{input.Float(),input.Float(),input.Word()};Optional(state.Update(action!=0,mirrored,p,settings));}}break;
        }
        case 3:
        {
            const auto settings=input.FakieSettings();AnimationFakieState state;const auto steps=input.Word();for (std::uint32_t j=0;j<steps;++j) {const auto p=input.FakiePhysical();const auto result=state.Update(p,input.Float(),settings);Word(bool(result));if (result) Word(*result);}break;
        }
        case 4:
        {
            const auto settings=input.Bool()?stock_pump:input.PumpSettings();AnimationPumpState state;const auto steps=input.Word();
            for (std::uint32_t j=0;j<steps;++j) {const auto pump=input.Float();std::array<bool,5> occupied;for (auto& b:occupied) b=input.Bool();const auto result=state.Update(pump,occupied,settings);Word(bool(result.start));if (result.start) Word(std::uint32_t(*result.start));Word(bool(result.influence));if (result.influence) {Word(std::uint32_t(result.influence->first));Float(result.influence->second);}}break;
        }
        case 5:
        {
            const AnimationGroundAccelerationSettings settings{input.Float(),input.Float()};const AnimationGroundAccelerationInput p{input.Matrix(),input.Matrix(),input.Vector()};const auto result=PublishAnimationGroundAcceleration(p,settings);for (const auto f:result.acceleration) Float(f);Word(result.bumped);break;
        }
        case 6:
        {
            TurnConditionerState state;for (auto& f:state.history) f=input.Float();for (auto& c:state.filters) for (auto& f:c) f=input.Float();const auto steps=input.Word();
            for (std::uint32_t j=0;j<steps;++j)
            {
                const AnimationBoardFeedback board{input.Float(),input.Float(),input.Float(),input.Float()};const AnimationPumpingFeedback pump{input.Float(),input.Float(),input.Float(),input.Float(),input.Float(),input.Float()};const auto wobble=input.Float();const AnimationReckoningFeedback reckoning{input.Position(),input.Position(),input.Position(),input.Float()};const AnimationControlFeedback controls{input.Word(),input.Float(),input.Bool()};const AnimationGroundAccelerationOutput acceleration{input.Vector(),input.Bool()};
                const auto out=PublishPhysicalAnimationFeedback(state,stock_feedback,board,pump,wobble,reckoning,controls,acceleration);const auto& t=out.turning;for (const auto f:{t.field_32,t.field_36,t.field_52,t.field_56,t.field_60,t.body_168}) Float(f);const auto& c=out.crouching;for (const auto f:{c.body_84,c.body_164,c.body_188,c.force_516,c.ground_force_520,c.minimum_crouch_528,c.deck_angle_532,c.animation_height_72}) Float(f);Float(out.pumping_acceleration);for (const auto f:out.ground_acceleration) Float(f);Word(out.bumped);for (const auto f:out.conditioned_turn) Float(f);for (const auto f:state.history) Float(f);for (const auto& filter:state.filters) for (const auto f:filter) Float(f);
            }break;
        }
        default:return 2;
        }
    }
    if (!input.ok||input.Remaining()!=0) return 2;return std::cout?0:2;
}

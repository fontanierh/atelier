#include "GroundControlSettings.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
using namespace atelier::skate;
namespace
{
std::vector<std::uint8_t> File(const std::string& name) {std::ifstream f(name,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
struct Output
{
    std::vector<std::uint8_t> bytes;
    void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) bytes.push_back(std::uint8_t(v>>(8*i)));}
    void Float(float v) {std::uint32_t word;std::memcpy(&word,&v,4);Word(word);}
    void String(std::string_view text) {Word(std::uint32_t(text.size()));bytes.insert(bytes.end(),text.begin(),text.end());}
    void Curve(const PointGraph<8>& value) {for (auto v:value.x) Float(v);for (auto v:value.y) Float(v);}
    void Settings(const ManualSettings& s) {Curve(s.noise_vs_speed);for (auto v:{s.torque_scale_without_contact,s.torque_bleed_without_contact,s.start_torque_scale,s.procedural_noise_scale,s.procedural_noise_frequency,s.powerslide.proportional,s.powerslide.integral,s.powerslide.derivative,s.manual.proportional,s.manual.integral,s.manual.derivative,s.maximum_tilt_degrees,s.maximum_angle_error,s.derivative_limit,s.brake_tilt_degrees,s.animation_noise_scale}) Float(v);}
    void Settings(const ManualMode& s) {Float(s.correction_angular_speed_threshold);Word(s.corrective_force_enabled);}
    void Settings(const GroundPropulsionSettings& s) {for (auto v:{s.braking.input_force,s.braking.override_force,s.braking.minimum_speed,s.maximum_pushable_speed,s.mode_speed_changes[0],s.mode_speed_changes[1]}) Float(v);}
    void Settings(const LinearDragSettings& s) {for (auto v:{s.brake_speed,s.balance_speed,s.comparison_threshold,s.balance_drag}) Float(v);}
    void Settings(const SpeedModelSettings& s) {for (auto v:{s.negative_gain,s.maximum_gravity_acceleration,s.gravity,s.positive_gain,s.coffin_acceleration,s.speed_error_bound}) Float(v);Curve(s.surface_friction);for (auto v:{s.manual_acceleration,s.negative_manual_angle_limit,s.manual_angle_limit,s.no_input_delay}) Float(v);Curve(s.no_input_friction);Curve(s.manual_friction);Word(s.override_enabled);Float(s.override_speed);for (auto v:s.normal_threshold) Float(v);for (auto v:s.override_direction_threshold) Float(v);}
    void Settings(const WallRideSettings& s) {Curve(s.anti_gravity_vs_time);for (auto v:{s.max_dot_floor_wall,s.foot_force_time,s.auto_jump_height,s.max_time,s.velocity_time_to_consider,s.auto_jump_y_down_scalar,s.auto_jump_force}) Float(v);}
};
}
int main(int argc,char** argv)
{
    if (argc!=2) return 2;const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};detail::DataReader input{bytes};input.at=0;const auto count=input.Word();std::map<std::uint32_t,SettingsDatabase> fixtures;Output output;
    for (std::uint32_t index=0;index<count;++index)
    {
        const auto op=input.Word(),fixture=input.Word();const auto mode=input.String(),surface=input.String();const auto surface_id=input.Word();if (!input.ok) return 2;
        auto found=fixtures.find(fixture);std::string error;if (found==fixtures.end()) {SettingsDatabase data;if (!data.Load(File(std::string(argv[1])+"/"+std::to_string(fixture)+"/settings.simulation"),error)) {std::cerr<<error;return 2;}found=fixtures.emplace(fixture,std::move(data)).first;}
        const auto& data=found->second;bool ok=false;Output payload;
        switch (op)
        {
            case 0:{ManualSettings s{};ok=LoadGroundManualSettings(data,s,error);if (ok) payload.Settings(s);break;}
            case 1:{ManualMode s{};ok=LoadGroundManualMode(data,mode,s,error);if (ok) payload.Settings(s);break;}
            case 2:{GroundPropulsionSettings s{};ok=LoadGroundPropulsionSettings(data,mode,s,error);if (ok) payload.Settings(s);break;}
            case 3:{LinearDragSettings s{};ok=LoadGroundLinearDragSettings(data,s,error);if (ok) payload.Settings(s);break;}
            case 4:{SpeedModelSettings s{};ok=LoadGroundSpeedModelSettings(data,mode,surface,s,error);if (ok) payload.Settings(s);break;}
            case 5:{WallRideSettings s{};ok=LoadGroundWallRideSettings(data,s,error);if (ok) payload.Settings(s);break;}
            case 6:{std::string_view key;ok=GroundSurfaceKey(surface_id,key,error);if (ok) payload.String(key);break;}
            default:return 2;
        }
        output.Word(index);output.Word(op);output.Word(ok);if (ok) output.bytes.insert(output.bytes.end(),payload.bytes.begin(),payload.bytes.end());else output.String(error);
    }
    if (!input.ok||input.at!=bytes.size()) return 2;std::cout.write(reinterpret_cast<const char*>(output.bytes.data()),std::streamsize(output.bytes.size()));
}

#include "SlideStateSettings.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
using namespace atelier::skate;
namespace
{
struct Output
{
    std::vector<std::uint8_t> bytes;
    void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) bytes.push_back(std::uint8_t(v>>(8*i)));}
    void Float(float v) {std::uint32_t word;std::memcpy(&word,&v,4);Word(word);}
    void String(std::string_view v) {Word(std::uint32_t(v.size()));bytes.insert(bytes.end(),v.begin(),v.end());}
    void Curve(const PointGraph<8>& v) {for (auto x:v.x) Float(x);for (auto y:v.y) Float(y);}
    void Settings(const SlideStateSettings& s)
    {
        for (const auto* c:{&s.settings.input_remap,&s.settings.remap_vs_speed,&s.settings.force_vs_angle,&s.settings.force_vs_speed}) Curve(*c);
        for (auto v:{s.settings.softest_wheel_force,s.settings.softest_wheel_spin,s.settings.angular_force,s.settings.force_y_offset}) Float(v);
        for (const auto& p:s.surfaces) {Curve(p.surface.speed_to_force);for (auto v:{p.surface.yaw_strength,p.surface.yaw_damping,p.material.static_friction,p.material.dynamic_friction,p.material.restitution}) Float(v);}
        Float(s.manual_scalar);
    }
};
}
int main(int argc,char** argv)
{
    if (argc!=2) return 2;const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};detail::DataReader input{bytes};input.at=0;const auto count=input.Word();Output output;
    for (std::uint32_t index=0;index<count;++index)
    {
        const auto fixture=input.Word();std::ifstream file(std::string(argv[1])+"/"+std::to_string(fixture)+"/settings.simulation",std::ios::binary);const std::vector<std::uint8_t> packed{std::istreambuf_iterator<char>(file),{}};SettingsDatabase data;std::string error;if (!data.Load(packed,error)) {std::cerr<<error;return 2;}
        SlideStateSettings s{};s.settings.angular_force=.137f;s.surfaces[2].material.dynamic_friction=.731f;s.surfaces[4].surface.speed_to_force.y[7]=-.317f;s.manual_scalar=-.113f;Output before;before.Settings(s);
        const auto ok=s.Load(data,error);output.Word(index);output.Word(ok);if (ok) output.Settings(s);else {output.String(error);Output after;after.Settings(s);output.Word(before.bytes==after.bytes);}
    }
    if (!input.ok||input.at!=bytes.size()) return 2;std::cout.write(reinterpret_cast<const char*>(output.bytes.data()),std::streamsize(output.bytes.size()));
}

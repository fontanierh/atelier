// SPDX-License-Identifier: Apache-2.0
#include "GroundTorqueSettings.h"
#include "DataReader.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace
{
std::vector<std::uint8_t> File(const std::filesystem::path& path) {std::ifstream f(path,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
struct Input:detail::DataReader
{
    explicit Input(const std::vector<std::uint8_t>& b):DataReader{b} {at=0;}
    Vec4 Vector() {Vec4 v;for (auto& f:v) f=Float();return v;}
    Mat4 Matrix() {Mat4 m;for (auto& v:m) v=Vector();return m;}
};
struct Output
{
    std::vector<std::uint8_t> bytes;
    void Word(std::uint32_t w) {for (unsigned i=0;i<4;++i) bytes.push_back(std::uint8_t(w>>(i*8)));}
    void Float(float f) {std::uint32_t w;std::memcpy(&w,&f,4);Word(w);}
    template<std::size_t N> void Floats(const std::array<float,N>& v) {for (auto f:v) Float(f);}
    template<std::size_t N> void Curve(const PointGraph<N>& c) {Floats(c.x);Floats(c.y);}
    void Settings(const GroundTorqueSettings& s)
    {
        Word(228);Curve(s.slide.angle_response);Curve(s.slide.speed_response);Curve(s.slide.time_response);
        for (auto f:{s.slide.scalar_516,s.slide.heading_time_limit,s.slide.friction}) Float(f);
        Curve(s.straighten.time_response);for (auto f:{s.straighten.opposite_turn_limit,s.straighten.time_scalar,s.straighten.heading_time_limit,s.straighten.strength}) Float(f);
        for (auto f:{s.heading.manual_wrong_wheel_scalar,s.heading.manual_damping,s.heading.speed_max,s.heading.heading_strength,s.heading.turn_strength}) Float(f);
        Curve(s.heading.angular_response);Curve(s.heading.manual_response);Curve(s.heading.inclination_response);Curve(s.heading.speed_response);Floats(s.heading.normal_threshold);
        Curve(s.anti_flip.axis_96_response);Curve(s.anti_flip.axis_64_response);Floats(s.anti_flip.normal_threshold);
    }
};
}
int main(int argc,char** argv)
{
    if (argc!=2) return 2;SettingsDatabase data;std::string error;if (!data.Load(File(argv[1]),error)) {std::cerr<<error;return 2;}
    constexpr std::array<std::string_view,5> surfaces{"smooth","rough","slow","slippery","veryslow"};std::array<GroundTorqueSettings,5> settings;Output out;out.Word(5);
    for (std::size_t i=0;i<settings.size();++i) {if (!settings[i].Load(data,surfaces[i],error)) {std::cerr<<error;return 2;}out.Settings(settings[i]);}
    const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input in(bytes);const auto count=in.Word();out.Word(count);float previous=0;
    for (std::uint32_t index=0;index<count;++index)
    {
        const auto op=in.Word(),profile=in.Word();if (profile>=settings.size()) return 2;const auto& s=settings[profile];Output payload;
        switch (op)
        {
        case 0:{const SlideFrictionInput i{in.Float(),in.Vector(),in.Vector(),in.Vector(),in.Float(),in.Float()};payload.Floats(CalculateSlideFriction(s.slide,i));break;}
        case 1:{const StraightenInput i{in.Float(),in.Float(),in.Float(),in.Vector(),in.Vector(),in.Vector()};payload.Floats(CalculateStraighten(s.straighten,i));break;}
        case 2:{const HeadingInput i{in.Float(),in.Float(),in.Word(),in.Float(),in.Float(),in.Float(),in.Float(),in.Float(),in.Vector(),in.Vector(),in.Vector(),in.Matrix()};payload.Floats(CalculateHeading(s.heading,i,previous));payload.Float(previous);break;}
        case 3:{const AntiFlipInput i{in.Word(),in.Float(),in.Vector(),in.Vector(),in.Vector()};payload.Floats(CalculateAntiFlip(s.anti_flip,i));break;}
        case 4:previous=in.Float();payload.Float(previous);break;
        default:return 2;
        }
        out.Word(index);out.Word(op);out.Word(std::uint32_t(payload.bytes.size()/4));out.bytes.insert(out.bytes.end(),payload.bytes.begin(),payload.bytes.end());
    }
    if (!in.ok||in.at!=bytes.size()) return 2;std::cout.write(reinterpret_cast<const char*>(out.bytes.data()),std::streamsize(out.bytes.size()));return 0;
}

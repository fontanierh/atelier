#include "Pumping.h"
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
    PumpingSample Sample() {return {Vector(),Vector(),Vector(),Float(),std::uint8_t(Word())};}
    PumpingState State()
    {
        PumpingState s;s.previous_position=Vector();s.previous_normal=Vector();
        s.smoothed_height_change=Float();s.pumping_time=Float();s.previous_height=Float();s.pumping=Float();s.pump_acceleration=Float();s.angular_speed=Float();
        s.absorption=Float();s.ground_normal_absorption=Float();s.minimum_crouch=Float();s.deck_angle_absorption=Float();s.reset_only_scalar=Float();s.record_valid=Word()!=0;s.intentional_pumping=std::uint8_t(Word());return s;
    }
    GroundForceInput Ground() {return {Float(),Float(),Float(),Float(),Float(),Float(),Vector(),Vector(),Vector()};}
    GroundForceSettings GroundSettings() {return {Float(),Float(),Float(),Vector()};}
};
struct Output
{
    std::vector<std::uint8_t> bytes;
    void Word(std::uint32_t w) {for (unsigned i=0;i<4;++i) bytes.push_back(std::uint8_t(w>>(i*8)));}
    void Float(float f) {std::uint32_t w;std::memcpy(&w,&f,4);Word(w);}
    void String(std::string_view s) {Word(std::uint32_t(s.size()));bytes.insert(bytes.end(),s.begin(),s.end());}
    template<std::size_t N> void Floats(const std::array<float,N>& v) {for (const auto f:v) Float(f);}
    void State(const PumpingState& s)
    {
        Floats(s.previous_position);Floats(s.previous_normal);
        for (auto f:{s.smoothed_height_change,s.pumping_time,s.previous_height,s.pumping,s.pump_acceleration,s.angular_speed,s.absorption,s.ground_normal_absorption,s.minimum_crouch,s.deck_angle_absorption,s.reset_only_scalar}) Float(f);
        Word(s.record_valid);Word(s.intentional_pumping);const auto p=s.PhysicsOutput();
        for (auto f:{p.compression,p.absorption,p.ground_normal_absorption,p.minimum_crouch,p.deck_angle_absorption,p.pump_acceleration}) {Float(f);}Word(p.intentional_pumping);
    }
    void Settings(const PumpingConfiguration& c,const GroundForceSettings& g)
    {
        Word(118);const auto& s=c.settings;
        for (const auto* curve:{&s.pump_vs_speed,&s.pump_vs_time,&s.min_crouch_vs_ground_angle,&s.compression_vs_ground_angle,&s.compression_vs_deck_angle}) {Floats(curve->x);Floats(curve->y);}
        for (auto f:{s.height_change_damping,s.minimum_height_change,s.maximum_height_change,s.ground_compression_scale,s.deck_compression_scale,s.angular_speed_damping}) Float(f);
        for (auto m:c.modes) for (auto f:{m.controller.maximum_absorption_per_second,m.controller.maximum_acceleration_per_second,m.controller.absorption_factor,m.controller.acceleration_factor,m.unintentional_scalar}) Float(f);
        for (auto f:{g.range_1220,g.speed_scale_1224,g.scale_1228}) {Float(f);}Floats(g.normal_threshold);
    }
};
}
int main(int argc,char** argv)
{
    if (argc!=2) return 2;SettingsDatabase data;PumpingConfiguration c;GroundForceSettings g;std::string error;
    if (!data.Load(File(argv[1]),error)||!c.Load(data,error)||!LoadGroundForceSettings(data,g,error)) {std::cerr<<error;return 2;}
    const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input in(bytes);Output out;out.Settings(c,g);const auto count=in.Word();out.Word(count);PumpingState state;
    for (std::uint32_t index=0;index<count;++index)
    {
        const auto op=in.Word();Output payload;bool success=true;error.clear();
        switch (op)
        {
        case 0:state=in.State();state.Reset();payload.State(state);break;
        case 1:
        {
            const bool ground=in.Word()!=0;const auto mode=in.Word();const float dt=in.Float();const auto sample=in.Sample();GroundPumpingMode m;
            success=c.Mode(mode,m,error);if (success) {if (ground) UpdateGroundPumping(state,c.settings,m.controller,sample);else UpdatePumping(state,c.settings,m.controller,sample,dt);payload.State(state);}break;
        }
        case 2:{const float dt=in.Float();const auto sample=in.Sample();payload.Float(CalculatePumping(state,c.settings,sample,dt));payload.State(state);break;}
        case 3:{const PumpForceInput input{in.Word(),in.Float(),in.Float(),in.Float(),in.Float(),in.Vector(),in.Vector()};payload.Floats(CalculatePumpForce(input));break;}
        case 4:{const auto input=in.Ground();payload.Floats(CalculateGroundForce(g,input));break;}
        case 5:{const auto settings=in.GroundSettings();const auto input=in.Ground();payload.Floats(CalculateGroundForce(settings,input));break;}
        case 6:
        {
            const auto position=in.Vector(),normal=in.Vector();const auto sample=in.Sample();const float dt=in.Float();
            payload.Float(PumpingHeight(sample.normal,sample.com_to_deck_world));payload.Float(PumpingSpeed(position,sample.position,dt));payload.Float(PumpingAngularSpeed(position,normal,sample,dt));payload.Float(Acos(sample.normal[1]));break;
        }
        case 7:{GroundPumpingMode mode;success=c.Mode(in.Word(),mode,error);if (success) for (auto f:{mode.controller.maximum_absorption_per_second,mode.controller.maximum_acceleration_per_second,mode.controller.absorption_factor,mode.controller.acceleration_factor,mode.unintentional_scalar}) payload.Float(f);break;}
        case 8:state=in.State();payload.State(state);break;
        default:return 2;
        }
        out.Word(index);out.Word(op);out.Word(success);if (!success) out.String(error);else {out.Word(std::uint32_t(payload.bytes.size()/4));out.bytes.insert(out.bytes.end(),payload.bytes.begin(),payload.bytes.end());}
    }
    if (!in.ok||in.at!=bytes.size()) return 2;std::cout.write(reinterpret_cast<const char*>(out.bytes.data()),std::streamsize(out.bytes.size()));return 0;
}

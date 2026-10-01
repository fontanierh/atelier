// SPDX-License-Identifier: Apache-2.0
#include "OffboardSettings.h"
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
struct Input
{
    std::vector<std::uint8_t> bytes;std::size_t at=0;
    std::uint32_t Word(){if(bytes.size()-at<4)std::abort();std::uint32_t w=0;for(unsigned n=0;n<4;++n)w|=std::uint32_t(bytes[at++])<<(n*8);return w;}
    float Float(){const auto w=Word();float f;std::memcpy(&f,&w,4);return f;}
    template<class T,std::size_t N,class F>std::array<T,N> Array(F f){std::array<T,N> a;for(auto& x:a)x=f(*this);return a;}
    template<class T,class F>std::optional<T> Optional(F f){return Word()?std::optional<T>(f(*this)):std::nullopt;}
};
struct Output
{
    std::vector<std::uint32_t> words;
    void Word(std::uint32_t w){words.push_back(w);}void Float(float f){std::uint32_t w;std::memcpy(&w,&f,4);Word(w);}
    void Status(bool okay,const std::string& error){Word(okay);Word(std::uint32_t(error.size()));for(const unsigned char c:error)Word(c);}
    template<std::size_t N>void Curve(const PointGraph<N>& g){for(float f:g.x)Float(f);for(float f:g.y)Float(f);}
};
std::vector<std::uint8_t> File(const char* path){std::ifstream file(path,std::ios::binary);return {std::istreambuf_iterator<char>(file),{}};}
// GENERATED_PROTOCOL
void SettingsOut(Output& o,const OffboardSettings& s)
{
    const auto& i=s.controller.movement_intent;for(const auto& g:{i.sprint_blend,i.slide_steering})o.Curve(g);o.Curve(i.sprint_speed);o.Curve(i.normal_speed);o.Float(i.sprint_time_cap);
    const auto& v=s.controller.movement_velocity;for(const auto& g:{v.slope_speed_scalar,v.slope_mode_speed,v.turn_vs_speed,v.turn_delta_vs_speed,s.controller.slide_vs_slope,s.controller.slide_vs_speed})o.Curve(g);
    for(const auto& metric:s.metrics){o.Word(bool(metric));if(metric){o.Float(metric->translation_z);o.Float(metric->end_time);}}
    for(const auto& value:{s.board.extent_0,s.board.extent_16,s.board.offset_32})for(float f:value)o.Float(f);
    for(float f:{s.board.angle_436,s.board.angle_440,s.board.margin_444,s.board.angle_452,s.board.angle_456})o.Float(f);
    o.Curve(s.movement_vs_stick_angle);o.Curve(s.turn_vs_stick_angle);o.Float(s.air_launch.jump_speed_scalar);o.Float(s.air_launch.jump_height);
}
void Snapshot(Output& o,const OffboardController& controller)
{
    const auto prefix=o.words.size();o.Word(0);Observe(o,controller.state);Observe(o,controller.Output());o.words[prefix]=std::uint32_t(o.words.size()-prefix-1);
}
int main(int argc,char** argv)
{
    if(argc!=4&&argc!=5)return 2;SettingsDatabase database;AnimationMetadata metadata,other;std::string error;Output o;
    if(!database.Load(File(argv[1]),error)||!metadata.Load(File(argv[2]),error)||!other.Load(File(argv[3]),error)||!metadata.Merge(other,error))return 2;
    OffboardSettings settings;const auto okay=settings.Load(database,metadata,error);o.Status(okay,error);if(!okay)return 2;SettingsOut(o,settings);
    if(argc==5){SettingsDatabase invalid;if(!invalid.Load(File(argv[4]),error))return 2;const auto loaded=settings.Load(invalid,metadata,error);o.Status(loaded,error);SettingsOut(o,settings);}
    else
    {
        Input i;i.bytes={std::istreambuf_iterator<char>(std::cin),{}};const auto count=i.Word();o.Word(count);
        for(unsigned c=0;c<count;++c)
        {
            OffboardController controller(settings.controller,settings.metrics);const auto n=i.Word();o.Word(c);o.Word(n);Snapshot(o,controller);
            for(unsigned k=0;k<n;++k)
            {
                const auto op=i.Word();o.Word(op);
                switch(op)
                {
                case 0:controller.StepGround(ReadBipedGroundJob(i));break;
                case 1:controller.Place(ReadBipedPlacementInput(i));break;
                case 2:controller.Reset();break;
                case 3:controller.state.motion.correction_576=i.Array<float,4>([](Input& r){return r.Float();});controller.state.correction_target_592=i.Array<float,4>([](Input& r){return r.Float();});controller.state.motion.correction_enabled_711=i.Word()!=0;controller.state.cadence.phase=ReadBipedPhase(i);controller.state.cadence.locomotion_index=i.Word();break;
                case 4:controller.state.cadence.phase.Advance();break;
                default:return 2;
                }
                Snapshot(o,controller);
            }
        }
        if(i.at!=i.bytes.size())return 2;
    }
    for(auto w:o.words)for(unsigned n=0;n<4;++n)std::cout.put(char(w>>(n*8)));return std::cout?0:2;
}

// SPDX-License-Identifier: Apache-2.0
#include "AirStateSettings.h"
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
using namespace atelier::skate;
namespace {
std::vector<std::uint8_t> ReadFile(const char* path)
{std::ifstream in(path,std::ios::binary);return std::vector<std::uint8_t>(std::istreambuf_iterator<char>(in),std::istreambuf_iterator<char>());}
struct Output {
    std::vector<std::uint32_t> words;
    void Word(std::uint32_t w){words.push_back(w);}
    void Float(float f){std::uint32_t w;std::memcpy(&w,&f,4);Word(w);}
    void String(const std::string& s){Word(std::uint32_t(s.size()));for(std::size_t k=0;k<s.size();k+=4){std::uint32_t w=0;for(std::size_t n=0;n<4&&k+n<s.size();++n)w|=std::uint32_t(static_cast<unsigned char>(s[k+n]))<<(8*n);Word(w);}}
    void Status(bool okay,const std::string& error){Word(okay);if(!okay)String(error);}
    void Settings(const AirStateSettings& s){for(auto v:s.state.body_spin_over_time_320.x)Float(v);for(auto v:s.state.body_spin_over_time_320.y)Float(v);for(auto v:{s.state.landing_normal_blend_388,s.state.body_spin_scale_428,s.state.landing_normal_angle_limit_444,s.steering_blend})Float(v);for(auto v:s.grind_lock_distance)Float(v);}
};
}
int main(int argc,char** argv)
{
    if(argc!=3)return 2;
    SettingsDatabase stock,variant;std::string error;
    if(!stock.Load(ReadFile(argv[1]),error)||!variant.Load(ReadFile(argv[2]),error)){std::cerr<<error;return 2;}
    AirStateSettings settings;if(!settings.Load(stock,error)){std::cerr<<error;return 2;}
    Output out;out.Settings(settings);
    for(unsigned attempt=0;attempt<2;++attempt){const bool okay=settings.Load(variant,error);out.Status(okay,error);out.Settings(settings);}
    const bool recovered=settings.Load(stock,error);out.Status(recovered,error);out.Settings(settings);
    for(auto w:out.words)for(unsigned n=0;n<4;++n)std::cout.put(char(w>>(8*n)));
    return 0;
}

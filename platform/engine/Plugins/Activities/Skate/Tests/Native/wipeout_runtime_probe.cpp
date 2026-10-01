// SPDX-License-Identifier: Apache-2.0
#include "WipeoutRuntime.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace
{
struct Input:detail::DataReader
{
    explicit Input(const std::vector<std::uint8_t>& bytes):DataReader{bytes}{at=0;}
    template<std::size_t N> std::array<float,N> Floats(){std::array<float,N> v{};for(auto& x:v)x=Float();return v;}
    template<std::size_t N> std::array<std::uint32_t,N> Words(){std::array<std::uint32_t,N> v{};for(auto& x:v)x=Word();return v;}
    Mat4 Matrix(){Mat4 m{};for(auto& v:m)v=Floats<4>();return m;}
    template<std::size_t N> PointGraph<N> Curve(){return {Floats<N>(),Floats<N>()};}
};
struct Output
{
    std::vector<std::uint32_t> words;
    void Word(std::uint32_t w){words.push_back(w);}
    void Float(float v){std::uint32_t w;std::memcpy(&w,&v,4);Word(w);}
    void Value(Vec4 v){for(auto x:v)Float(x);}
    void Value(Mat4 m){for(auto v:m)Value(v);}
    template<std::size_t N> void Curve(PointGraph<N> c){for(auto v:c.x)Float(v);for(auto v:c.y)Float(v);}
    void Text(const std::string& s){Word(std::uint32_t(s.size()));for(unsigned char c:s)Word(c);}
};
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-function"
// GENERATED_PROTOCOL
#pragma clang diagnostic pop
void Requests(Output& o,const WipeoutRequests& s)
{
    for(auto v:s.reasons)o.Word(v);for(auto v:s.values)o.Float(v);
    o.Word(s.count);o.Float(s.cooldown);o.Word(std::uint32_t(s.contact_frames));o.Float(s.balance);o.Word(s.mode);
}
void Seed(Input& i,WipeoutRequests& s)
{
    for(auto& v:s.reasons)v=i.Word()!=0;for(auto& v:s.values)v=i.Float();s.count=i.Word();s.cooldown=i.Float();
    const auto w=i.Word();std::memcpy(&s.contact_frames,&w,4);s.balance=i.Float();s.mode=i.Word();
}
std::vector<std::uint8_t> File(const char* path){std::ifstream f(path,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
}
int main(int argc,char** argv)
{
    if(argc<2)return 2;SettingsDatabase data;std::string error;if(!data.Load(File(argv[1]),error))return 2;
    WipeoutRuntime r;Output out;const bool loaded=r.Load(data,error);out.Word(loaded);out.Text(error);
    if(loaded)
    {
        Observe(out,r.settings);for(const auto& m:r.modes)Observe(out,m);Requests(out,r.state);
        if(argc==2)
        {
            const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input i(bytes);const auto count=i.Word();out.Word(count);
            for(std::uint32_t n=0;n<count;++n)
            {
                WipeoutRequests state=r.state;const auto mode=i.Word();const auto commands=i.Word();out.Word(mode);out.Word(commands);
                for(std::uint32_t k=0;k<commands;++k)
                {
                    const auto op=i.Word();out.Word(op);
                    if(op<=4)
                    {
                        const auto f=ReadWipeoutFrame(i);const auto scalar=i.Float();
                        switch(op)
                        {
                        case 0:CheckWipeoutGround(state,r.settings,r.modes.at(mode),f);break;
                        case 1:CheckWipeoutAir(state,r.settings,r.modes.at(mode),f,scalar!=0);break;
                        case 2:CheckWipeoutAirCollision(state,r.settings,r.modes.at(mode),f);break;
                        case 3:CheckWipeoutPlant(state,r.settings,f);break;
                        case 4:CheckWipeoutGroundAnimation(state,r.settings,r.modes.at(mode),f,scalar);break;
                        }
                        const WipeoutRequestInput p{f.flags_2468,f.flags_2476,f.flags_2480,f.flags_2484,f.animation_up[1],f.category};
                        out.Word(state.RequestsRunout(p));out.Word(state.RequestsWipeout(p));
                    }
                    else if(op==5)Seed(i,state);
                    else if(op==6)state.ClearAfterSelection();
                    else if(op==7)state.InitializePlayer();
                    else if(op==8)state.Teleport();
                    else if(op==9)state.ResetSystems();else return 2;
                    Requests(out,state);
                }
            }
            if(!i.ok||i.Remaining())return 2;
        }
    }
    for(auto w:out.words)for(unsigned b=0;b<4;++b)std::cout.put(char(w>>(b*8)));
    return std::cout?0:2;
}

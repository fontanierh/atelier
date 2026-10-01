#include "SkeletonWobble.h"
#include <cstdio>
#include <cstring>
#include <iterator>
#include <iostream>
#include <fstream>
using namespace atelier::skate;
struct Input
{
    std::vector<std::uint32_t> words;std::size_t at=0;
    std::uint32_t Word(){if(at>=words.size())std::abort();return words[at++];}
    float Float(){const auto word=Word();float f;std::memcpy(&f,&word,4);return f;}
    Mat4 Matrix(){Mat4 m;for(auto& c:m)for(auto& x:c)x=Float();return m;}
    SkeletonWobbleSettings Settings()
    {SkeletonWobbleSettings s;for(auto* curve:{&s.takeoff_tilt,&s.landing_tilt,&s.takeoff_squish,&s.landing_squish}){for(auto& x:curve->x)x=Float();for(auto& y:curve->y)y=Float();}s.maximum_time=Float();return s;}
};
struct Output
{
    std::vector<std::uint32_t> words;
    void Word(std::uint32_t x){words.push_back(x);}
    void Float(float x){std::uint32_t w;std::memcpy(&w,&x,4);Word(w);}
    void Observe(const SkeletonWobble& s,SkeletonWobbleOutput output,const Mat4& m)
    {Word(s.active);Word(s.landing);Float(s.time);Float(s.amplitude);Float(s.direction);Word(s.SelectedLandingCurves());Word(output.sampled);Float(output.tilt);Float(output.squish);Word(output.remains_active);for(auto c:m)for(auto v:c)Float(v);}
};
int main(int argc,char** argv)
{
    if(argc!=2)return 2;std::string error;std::ifstream file(argv[1],std::ios::binary);
    const std::vector<std::uint8_t> settings_bytes((std::istreambuf_iterator<char>(file)),{});
    SettingsDatabase data;if(!data.Load(settings_bytes,error)){std::cerr<<error;return 2;}
    const auto stock=SkeletonWobbleSettings::Load(data,error);if(!stock){std::cerr<<error;return 2;}
    std::vector<char> bytes((std::istreambuf_iterator<char>(std::cin)),{});if(bytes.size()%4)return 2;
    Input i;i.words.resize(bytes.size()/4);std::memcpy(i.words.data(),bytes.data(),bytes.size());Output o;
    const auto count=i.Word();o.Word(count);
    for(std::uint32_t c=0;c<count;++c)
    {
        const auto variant=i.Word();auto settings=variant?i.Settings():*stock;SkeletonWobble state;Mat4 board=i.Matrix();
        o.Word(c);for(const auto* curve:{&settings.takeoff_tilt,&settings.landing_tilt,&settings.takeoff_squish,&settings.landing_squish}){for(auto x:curve->x)o.Float(x);for(auto y:curve->y)o.Float(y);}o.Float(settings.maximum_time);o.Observe(state,{},board);
        const auto commands=i.Word();o.Word(commands);
        for(std::uint32_t n=0;n<commands;++n)
        {
            const auto op=i.Word();SkeletonWobbleOutput result;
            switch(op)
            {
            case 0:state=SkeletonWobble{};break;
            case 1:{const bool landing=i.Word()!=0,reverse=i.Word()!=0;state.Trigger(landing,reverse);break;}
            case 2:result=state.Update(settings);ApplySkeletonWobble(result,board);break;
            case 3:state.active=i.Word()!=0;state.landing=i.Word()!=0;state.time=i.Float();state.amplitude=i.Float();state.direction=i.Float();break;
            case 4:board=i.Matrix();break;
            case 5:state.ResetForTeleport();break;
            default:std::abort();
            }
            o.Word(op);o.Observe(state,result,board);
        }
    }
    if(i.at!=i.words.size())return 3;return std::fwrite(o.words.data(),4,o.words.size(),stdout)==o.words.size()?0:4;
}

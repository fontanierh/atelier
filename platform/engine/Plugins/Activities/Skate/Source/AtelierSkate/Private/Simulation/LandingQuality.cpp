#include "LandingQuality.h"
#include "StockSettingsReader.h"
#include <cstring>
#pragma clang fp contract(off)
namespace atelier::skate
{
namespace
{
float FromBits(std::uint32_t bits){float value;std::memcpy(&value,&bits,4);return value;}
Vec4 Scaled(Vec4 a,float b){for(auto& x:a)x*=b;return a;}
Vec4 Planar(Vec4 a,Vec4 normal)
{
    const auto projected=Scaled(normal,Dot3(normal,a));
    for(unsigned i=0;i<4;++i)a[i]-=projected[i];return a;
}
Vec4 Cross(Vec4 a,Vec4 b)
{
    const auto v=Cross3(Vec3{a[0],a[1],a[2]},Vec3{b[0],b[1],b[2]});return {v.x,v.y,v.z,0.0f};
}
float UpperOne(float value){return 1.0f-value>=-0.0f?value:1.0f;}
}
bool LandingQualitySettings::Load(const SettingsDatabase& data,std::string& error)
{
    StockSettingsReader reader(data);LandingQualitySettings result;
    auto graph=[&](std::string_view name,PointGraph<4>& output)
    {
        std::vector<std::uint32_t> words;if(!reader.Words("physics_animation","default",name,8,words,error))return false;
        for(unsigned i=0;i<4;++i){output.x[i]=FromBits(words[i]);output.y[i]=FromBits(words[i+4]);}return true;
    };
    if(!graph("LandingSketchyTwistSpin",result.twist_spin)||!graph("LandingSketchySideSpeed",result.side_speed))return false;
    *this=result;return true;
}
void LandingQualityOutput::Update(LandingQualityInput input,const LandingQualitySettings& settings)
{
    if(input.previous_filtered_state==1||input.filtered_state!=1)return;
    const auto velocity=Planar(input.deck_velocity,input.ground_normal),forward=Planar(input.reckoning_forward,input.ground_normal);
    const float speed=Length3(velocity),forward_length=Length3(forward);
    float forward_speed=std::abs(Dot3(velocity,forward)),side_speed=std::abs(Dot3(Cross(forward,input.ground_normal),input.deck_velocity));
    std::uint32_t kind=0;float spin=0.0f;
    if(forward_length*speed<FromBits(0x3727c5ac)){forward_speed=0;side_speed=0;}
    else
    {
        const auto normalized_velocity=Scaled(velocity,RefinedReciprocal(speed,2)),normalized_forward=Scaled(forward,RefinedReciprocal(forward_length,2));
        float orientation=Cross(normalized_forward,normalized_velocity)[1];if(input.flipped)orientation=-orientation;
        const float angular_speed=-input.air_spin;
        const float spin_input=(std::abs(angular_speed)-0.1f)*0.14492753f;
        const float spin_curve=settings.twist_spin.Evaluate(UpperOne(spin_input));
        const float side_input=(side_speed-0.1f)*0.1010101f;
        const float side_curve=settings.side_speed.Evaluate(UpperOne(side_input));
        if(speed>=2.0f)
        {
            const auto heading=input.flipped?Scaled(normalized_forward,-1.0f):normalized_forward;
            const bool toward=Dot3(heading,normalized_velocity)>=0.0f;float magnitude;
            if(std::abs(angular_speed)<=0.1f){kind=1;magnitude=side_curve;}
            else
            {
                const float product=angular_speed*orientation;
                kind=(toward&&product<=0.0f)||(!toward&&product>0.0f)?2:1;
                magnitude=spin_curve-side_curve>=-0.0f?spin_curve:side_curve;
            }
            spin=angular_speed>=-0.0f?magnitude:-magnitude;
            if(std::abs(orientation)<0.2f&&(kind!=2||!(std::abs(spin)>0.3f))){kind=std::abs(orientation)>=0.05f?3:0;spin=0.0f;}
        }
    }
    *this={spin,side_speed,forward_speed,spin,kind,true};
}
}

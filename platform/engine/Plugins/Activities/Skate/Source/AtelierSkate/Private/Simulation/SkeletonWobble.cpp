#include "SkeletonWobble.h"
#include "StockSettingsReader.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
std::optional<SkeletonWobbleSettings> SkeletonWobbleSettings::Load(const SettingsDatabase& data,std::string& error)
{
    SkeletonWobbleSettings result;StockSettingsReader reader(data);
    if(!reader.Curve8Layout20("physics_deck_wobble","default","TiltVsTimeTakeOff",result.takeoff_tilt,error)||
       !reader.Curve8Layout20("physics_deck_wobble","default","TiltVsTimeLanding",result.landing_tilt,error)||
       !reader.Curve8Layout20("physics_deck_wobble","default","SquishVsTimeTakeOff",result.takeoff_squish,error)||
       !reader.Curve8Layout20("physics_deck_wobble","default","SquishVsTimeLanding",result.landing_squish,error)||
       !reader.Float("physics_deck_wobble","default","MaxTime",result.maximum_time,error))return std::nullopt;
    return result;
}
void SkeletonWobble::Trigger(bool is_landing,bool reverse)
{
    selected_landing_curves_=is_landing;landing=is_landing;active=true;time=0;amplitude=1;direction=reverse?-1.f:1.f;
}
SkeletonWobbleOutput SkeletonWobble::Update(const SkeletonWobbleSettings& settings)
{
    if(!active)return {};
    const auto& tilt=selected_landing_curves_?settings.landing_tilt:settings.takeoff_tilt;
    const auto& squish=selected_landing_curves_?settings.landing_squish:settings.takeoff_squish;
    const float compression=squish.Evaluate(time)*amplitude;
    const float rotation=(tilt.Evaluate(time)*direction)*amplitude;
    const std::uint32_t step_bits=0x3c888889;float step;std::memcpy(&step,&step_bits,4);time+=step;
    if(time>settings.maximum_time){active=false;time=0;}
    return {true,rotation,compression,active};
}
void SkeletonWobble::ResetForTeleport()
{
    // The original reset preserves its cached selection of curves.
    time=0;amplitude=0;direction=1;active=false;landing=false;
}
void ApplySkeletonWobble(SkeletonWobbleOutput output,Mat4& board)
{
    if(!output.sampled)return;
    const auto [sine,cosine]=SinCos(output.tilt);
    const Mat4 rotation{{{cosine,sine,0,cosine},{-sine,cosine,0,-sine},{0,0,1,0},{0,0,0,0}}};
    board=ComposeSkeletonAffine(board,rotation);
    for(unsigned lane=0;lane<4;++lane)board[3][lane]=std::fma(board[1][lane],output.squish,board[3][lane]);
}
}

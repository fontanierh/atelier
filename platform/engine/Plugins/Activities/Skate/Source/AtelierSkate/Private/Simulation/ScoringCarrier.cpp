#include "ScoringCarrier.h"
#include <cmath>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
std::uint32_t ScoringDelayTicks(float authored,float extra)
{
    const auto value=(authored+extra)*60.0f;
    // Rust's saturating f32 -> i64 cast precedes the wrapping i64 -> u32 cast.
    std::int64_t ticks;
    if(std::isnan(value))ticks=0;
    else if(value>=0x1p63f)ticks=std::numeric_limits<std::int64_t>::max();
    else if(value<=-0x1p63f)ticks=std::numeric_limits<std::int64_t>::min();
    else ticks=static_cast<std::int64_t>(value);
    return static_cast<std::uint32_t>(ticks);
}
ScoringCarrier ScoringCarrier::Create(ScoringScorable scorable,std::int32_t points,float factor,
    float threshold,std::uint32_t start,std::uint32_t delay,bool switch_stance,bool fakie)
{
    ScoringCarrier result;result.scorable=scorable;result.points=points;result.factor=factor;
    result.announcement_threshold=threshold*factor;result.start_tick=start;result.delay_ticks=delay;
    result.switch_stance=switch_stance;result.fakie=fakie;return result;
}
void ScoringCarrier::Credit(float unannounced_factor)
{auto amount=static_cast<float>(points)*factor;if(unannounced)amount*=unannounced_factor;reward+=amount;}
bool ScoringCarrier::Announce(std::uint32_t tick,float unannounced_factor)
{
    if(announced||!scorable.Valid()||tick-start_tick<delay_ticks)return false;
    announced=true;Credit(unannounced_factor);return true;
}
bool ScoringCarrier::Complete(float unannounced_factor)
{
    if(!scorable.Valid())return false;
    if(!announced){unannounced=true;Credit(unannounced_factor);}
    completed=true;return true;
}
void ScoringCarrier::ConvertTo(ScoringCarrier& replacement,float unannounced_factor)
{completed=true;replacement.announced=true;replacement.Credit(unannounced_factor);}
}

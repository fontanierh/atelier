#include "FilteredState.h"
#include <cstring>
#pragma clang fp contract(off)
namespace atelier::skate
{
FilteredGrindState ResetFilteredGrindState()
{
    return {-1,-1,EncodeAnimationName(""),EncodeAnimationName(""),false,0.0f,UINT64_MAX,UINT64_MAX};
}
namespace
{
std::int32_t Count(std::int32_t previous,bool active)
{
    if(!active)return 0;
    std::uint32_t bits;std::memcpy(&bits,&previous,4);++bits;
    std::int32_t result;std::memcpy(&result,&bits,4);return result;
}
}
void FilteredState::Reset(){*this=FilteredState{};}
FilteredStateOutput FilteredState::Update(FilteredStateInput input)
{
    using C=FilteredCategory;
    const auto old=category;previous_category=old;
    must_change=old==C::Wipeout||old==C::Invalid||(previous_physics_state==702&&input.physics_state!=702);
    air_count=Count(air_count,input.physics_category==200);
    nonspecific_count=Count(nonspecific_count,input.physics_state==701);
    nonspecific_collision_free_count=Count(nonspecific_collision_free_count,input.physics_state==701&&!input.anything_in_contact);
    nonspecific_collision_count=Count(nonspecific_collision_count,input.physics_state==701&&input.anything_in_contact);
    frames_since_ground_stairs=Count(frames_since_ground_stairs,!(input.physics_category==100&&input.physics_surface_type==8));
    switch(input.physics_state)
    {
    case 100:category=input.wall_ride_exit?C::Air:C::Ground;break;
    case 101:case 102:case 103:case 104:case 105:case 602:category=C::Ground;break;
    case 200:
    {
        const bool delay=air_count>3;
        if(old==C::Air)category=(delay&&input.anything_in_contact)||must_change?C::Ground:C::Air;
        else category=(delay&&(old!=C::Ground||frames_since_ground_stairs>9))||must_change?C::Air:old;
        break;
    }
    case 201:category=input.anything_in_contact&&!input.targeting_grind&&air_count>5?C::Ground:C::Air;break;
    case 202:case 600:case 601:category=C::Air;break;
    case 300:category=C::Wipeout;break;
    case 400:case 401:case 402:case 403:case 404:case 405:cached_grind_=input.grind;category=C::Grind;break;
    case 500:case 502:category=C::Offboard;break;
    case 501:category=input.offboard_has_landed?C::Offboard:C::OffboardAir;break;
    case 503:category=input.offboard_on_deck?C::Ground:C::Offboard;break;
    case 702:category=C::Teleport;break;
    default:category=old;break;
    }
    previous_physics_state=input.physics_state;const bool grinding=category==C::Grind;
    return {category,previous_category,grinding,grinding?cached_grind_:ResetFilteredGrindState(),input.last_grind_distance};
}
}

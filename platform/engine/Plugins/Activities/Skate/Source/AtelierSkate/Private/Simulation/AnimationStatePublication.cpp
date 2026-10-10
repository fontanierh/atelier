#include "AnimationStatePublication.h"
#include <cstring>
#pragma clang fp contract(off)
namespace atelier::skate
{
bool FilteredGrindNameText(AttributeName name,std::string& out,std::string& error)
{
    std::string text;bool ended=false;
    for(auto word:name)
    {
        for(auto weight:{79235168u,2085136u,54872u,1444u,38u,1u})
        {
            const auto digit=word/weight;word%=weight;
            if(digit==0){ended=true;continue;}
            if(ended){error="Filtered grind name contains a nonterminal NUL";return false;}
            if(digit>=1&&digit<=10)text.push_back(char('0'+digit-1));
            else if(digit>=11&&digit<=36)text.push_back(char('A'+digit-11));
            else if(digit==37)text.push_back('_');
            else{error="Filtered grind name is outside the stock alphabet";return false;}
        }
    }
    if(EncodeAnimationName(text)!=name){error="Filtered grind name did not round trip";return false;}
    out=std::move(text);return true;
}
bool PublishAnimationState(const PhysicalPlayerInput& physical,const std::optional<FilteredStateOutput>& filtered,
    float height,bool mirrored,Vec3 forward,AnimationStatePublication& out,std::string& error)
{
    bool grinding=false;auto grind=ResetFilteredGrindState();
    if(filtered)
    {
        if(std::uint32_t(filtered->category)!=physical.filtered_state_0){error="Grind graph received inconsistent completed filtered outputs";return false;}
        grinding=filtered->grinding;grind=filtered->grind;
    }
    else if(physical.filtered_state_0!=0){error="Grind graph requires the completed filtered state owner";return false;}
    std::string name;if(!FilteredGrindNameText(grind.name,name,error))return false;
    Vec3 deck_velocity;float lanes[3];for(unsigned i=0;i<3;++i)std::memcpy(&lanes[i],&physical.skateboard.vector_80[i],4);deck_velocity={lanes[0],lanes[1],lanes[2]};
    out={{physical.filtered_state_0,grinding,std::move(name)},
        {grinding,grind.name,deck_velocity,forward,physical.ground.flag_273!=0,height,grind.crouch,physical.skeleton.twist_504},
        {grinding,physical.grinds.words_136_140[0],physical.grinds.animation_chromosome_268[0],physical.grinds.trick_out_240,
            physical.air.flag_443!=0,physical.air.scalar_184,physical.grinds.dropping_in_324!=0},mirrored};
    return true;
}
}

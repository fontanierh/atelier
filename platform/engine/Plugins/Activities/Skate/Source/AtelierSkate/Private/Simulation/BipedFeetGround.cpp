#include "BipedFeet.h"
#include <cmath>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
void UpdateBipedGroundFeet(BoardPossessionManager& manager,BipedFeetInput input,foot_ik::State& ik)
{
    if(input.lines[0].valid&&input.lines[1].valid)
    {
        const std::array<float,2> delta{{input.lines[0].position[1]-input.world_foot_pairs[0][0][1],input.lines[1].position[1]-input.world_foot_pairs[1][0][1]}};
        for(std::size_t index=0;index<2;++index)if(std::abs(delta[index])>.3f&&std::abs(delta[index]-delta[1-index])>.3f)input.lines[index].valid=false;
    }
    const auto targets=UpdateBipedFeetTargets(manager,input);if((input.flags_2484&0x80000000)==0)ApplyBipedFootTargets(targets,ik);
    bool both_bad=true;
    if(manager.hands[0].flag_84||manager.hands[1].flag_84)
    {
        ++manager.words_308_to_316[2];
        for(const auto& foot:manager.hands)
        {
            const float height=foot.vectors_0_to_64[1][1]-foot.vectors_0_to_64[3][1];if(foot.flag_84&&!(height>.18f))manager.words_308_to_316[2]=0;
            const bool bad=!foot.flag_84||height>1||foot.vectors_0_to_64[4][1]<.6f;both_bad=both_bad&&bad;
        }
    }
    if(both_bad)
    {
        ++manager.words_308_to_316[1];
        if(static_cast<std::int32_t>(manager.words_308_to_316[1])>20||static_cast<std::int32_t>(manager.words_308_to_316[2])>40)manager.flags_304_to_307[1]=true;
    }
    else{manager.flags_304_to_307[1]=false;manager.words_308_to_316[1]=0;}
    manager.words_308_to_316[0]=0;manager.flags_304_to_307[2]=false;manager.vectors_224_to_272[0]={};manager.vectors_224_to_272[1]={};
}
}

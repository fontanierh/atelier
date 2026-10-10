#pragma once
#include "BoardPossession.h"
namespace atelier::skate
{
struct BoardManagerHand
{
    std::array<Vec4,5> vectors_0_to_64{{Vec4{},Vec4{},Vec4{0,1,0,0},Vec4{},Vec4{}}};
    std::uint32_t word_80=0;bool flag_84=false;
    std::array<float,2> scalars_96_100{};
    std::array<bool,4> flags_104_to_107{};
};
struct BoardManagerSkeletonReset {bool& enabled_464;std::array<float,4>& values_468;std::array<float,4>& values_484;std::array<std::uint32_t,4>& words_500;};
struct BoardPossessionManager
{
    std::array<BoardManagerHand,2> hands;
    std::array<Vec4,4> vectors_224_to_272{};
    std::array<float,3> scalars_288_to_296{};
    std::uint32_t word_300=2;
    std::array<bool,4> flags_304_to_307{};
    std::array<std::uint32_t,3> words_308_to_316{};
    void Reset();
    void Enter(std::uint32_t previous_2504,std::uint32_t current_2508,BoardManagerSkeletonReset);
};
}

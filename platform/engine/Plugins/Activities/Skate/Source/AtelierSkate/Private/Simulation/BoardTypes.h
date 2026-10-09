#pragma once
#include <cstddef>
#include <cstdint>

namespace atelier::skate
{
constexpr std::size_t BoardBodyCount=7;
enum class BoardBodyId : std::uint8_t
{
    RightFrontWheel=0,LeftFrontWheel=1,RightBackWheel=2,LeftBackWheel=3,
    FrontTruck=4,BackTruck=5,Deck=6
};
}

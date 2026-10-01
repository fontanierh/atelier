// SPDX-License-Identifier: Apache-2.0
#include "SkeletonController.h"
namespace atelier::skate
{
std::optional<std::uint32_t> SkeletonControllerState::SelectRequest(std::uint32_t value)
{
    if(has_request&&requested==value)return std::nullopt;
    std::uint32_t selected;
    if(override_enabled)
    {
        requested=value;has_request=true;
        switch(value)
        {
        case 4:selected=1;break;
        case 5:case 6:case 7:selected=2;break;
        case 8:selected=3;break;
        case 9:case 10:case 11:selected=value;break;
        default:return std::nullopt;
        }
    }
    else
    {
        if(effective>=1&&effective<=2)return std::nullopt;
        selected=value;
    }
    effective=selected;const auto mode=selected-1;
    if(mode>10)return std::nullopt;return mode;
}
bool SkeletonControllerState::Request(std::uint32_t value,SkeletonCollisionMode& collision,std::string& error)
{
    const auto mode=SelectRequest(value);if(mode)return collision.SelectDriven(*mode,error);return true;
}
bool SkeletonControllerState::UpdateAir(std::uint32_t flags,float velocity_y,SkeletonCollisionMode& collision,std::string& error)
{
    const bool ascending=(flags&0x8000)!=0||velocity_y>0;
    if(flag_18!=ascending){flag_18=ascending;return Request(ascending?7:6,collision,error);}return true;
}
}

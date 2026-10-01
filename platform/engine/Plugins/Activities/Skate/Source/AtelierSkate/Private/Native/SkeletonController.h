// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "SkeletonCollisionMode.h"
namespace atelier::skate
{
// Shared Ground/Air collision controller. Requested and effective values
// remain distinct while a physical override is enabled.
struct SkeletonControllerState
{
    std::uint32_t effective=0,requested=0;
    bool has_request=false,override_enabled=false,flag_18=false;
    std::optional<std::uint32_t> SelectRequest(std::uint32_t requested);
    bool Request(std::uint32_t requested,SkeletonCollisionMode&,std::string& error);
    bool RequestGround(SkeletonCollisionMode& collision,std::string& error)
    {return Request(6,collision,error);}
    bool UpdateAir(std::uint32_t processed_flags_2472,float velocity_y,SkeletonCollisionMode&,std::string& error);
};
}

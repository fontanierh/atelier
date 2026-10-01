// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AnimationName.h"
#include <cstdint>
namespace atelier::skate
{
struct GrindFilteredOutput
{
    std::int32_t kind,scorable_id;AttributeName name,scoring_name;bool on_front;float crouch;
    std::uint64_t pathed_guid,local_guid;
};
}

// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <array>
#include <cstdint>
#include <optional>
#include <string_view>
namespace atelier::skate
{
struct GrindName {std::int32_t skating_id;std::string_view attribute,display;std::int32_t scorable_id;};
std::optional<GrindName> LookupGrindName(std::array<std::uint32_t,6> components);
}

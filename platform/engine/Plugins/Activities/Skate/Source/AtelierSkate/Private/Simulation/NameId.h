#pragma once
#include <cstdint>
#include <string_view>

namespace atelier::skate
{
// Stable identities preserve references between converted settings and graphs.
std::uint64_t NameHash(std::string_view text);
std::uint64_t NameId(std::string_view text);
}

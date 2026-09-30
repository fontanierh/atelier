// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <array>
#include <cstdint>
#include <string_view>

namespace atelier::skate
{
using AttributeName = std::array<std::uint32_t, 5>;
using IntentKey = std::array<std::uint32_t, 6>;
// Native six-character chunks, signed bytes, wrapping u32 arithmetic and NUL
// termination. Attribute names retain 30 bytes; intent keys retain 36 bytes.
AttributeName EncodeAnimationName(std::string_view text);
IntentKey EncodeIntentKey(std::string_view text);
}

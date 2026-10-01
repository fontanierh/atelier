// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <string>
#include <string_view>

namespace atelier::skate
{
// Rust 1.97.1's format!("{text:?}") for valid UTF-8, including the quotes.
// Invalid UTF-8 has no Rust str equivalent: reject it and retain output.
bool FormatRustDebugString(std::string_view text, std::string& output,
    std::string& error);
}

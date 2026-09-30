// SPDX-License-Identifier: Apache-2.0
#include "NameId.h"
#include <array>
#include <charconv>

namespace atelier::skate
{
namespace
{
void Mix(std::uint64_t& a, std::uint64_t& b, std::uint64_t& c)
{
    constexpr std::array<std::array<int,3>,4> shifts{{{43,9,8},{38,23,5},{35,49,11},{12,18,22}}};
    for (const auto& shift : shifts)
    {
        a = (a-b-c) ^ (c>>shift[0]);
        b = (b-c-a) ^ (a<<shift[1]);
        c = (c-a-b) ^ (b>>shift[2]);
    }
}
std::uint64_t LittleWord(std::string_view text)
{
    std::uint64_t value = 0;
    for (unsigned i = 0; i < 8; ++i) value |= std::uint64_t(static_cast<unsigned char>(text[i])) << (i*8);
    return value;
}
}

std::uint64_t NameHash(std::string_view text)
{
    if (text.empty()) return 0;
    std::uint64_t a = 0xabcdef0011223344ull, b = a, c = 0x9e3779b97f4a7c13ull;
    std::size_t at = 0;
    while (text.size()-at >= 24)
    {
        a += LittleWord(text.substr(at,8));
        b += LittleWord(text.substr(at+8,8));
        c += LittleWord(text.substr(at+16,8));
        Mix(a,b,c);
        at += 24;
    }
    c += text.size();
    for (std::size_t i = 0; i < text.size()-at; ++i)
    {
        const auto byte = std::uint64_t(static_cast<unsigned char>(text[at+i]));
        if (i < 8) a += byte << (i*8);
        else if (i < 16) b += byte << ((i-8)*8);
        else c += byte << ((i-15)*8);
    }
    Mix(a,b,c);
    return c;
}

std::uint64_t NameId(std::string_view text)
{
    auto hex = text;
    bool prefixed = false;
    if (hex.substr(0,5) == "Hash_") { hex.remove_prefix(5); prefixed = true; }
    else if (hex.substr(0,2) == "0x") { hex.remove_prefix(2); prefixed = true; }
    if (prefixed)
    {
        // Rust's unsigned from_str_radix permits a leading plus sign.
        if (!hex.empty() && hex.front() == '+') hex.remove_prefix(1);
        std::uint64_t result = 0;
        const auto parsed = std::from_chars(hex.data(), hex.data()+hex.size(), result, 16);
        if (!hex.empty() && parsed.ec == std::errc{} && parsed.ptr == hex.data()+hex.size()) return result;
    }
    return NameHash(text);
}
}

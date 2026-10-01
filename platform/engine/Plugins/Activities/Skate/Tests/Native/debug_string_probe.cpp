// SPDX-License-Identifier: Apache-2.0
#include "DebugString.h"
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

namespace
{
struct Input
{
    std::vector<char> bytes;
    std::size_t at = 0;
    std::uint32_t Word()
    {
        if (bytes.size() - at < 4) std::abort();
        std::uint32_t value = 0;
        for (unsigned i = 0; i < 4; ++i) value |= std::uint32_t(std::uint8_t(bytes[at++])) << (8 * i);
        return value;
    }
    std::string Text()
    {
        const auto count = Word();
        if (bytes.size() - at < count) std::abort();
        std::string result(bytes.data() + at, count);
        at += count;
        return result;
    }
};
struct Output
{
    std::vector<char> bytes;
    void Word(std::uint32_t value)
    {
        for (unsigned i = 0; i < 4; ++i) bytes.push_back(char(std::uint8_t(value >> (8 * i))));
    }
    void Text(const std::string& text)
    {
        Word(std::uint32_t(text.size()));
        bytes.insert(bytes.end(), text.begin(), text.end());
    }
};
std::string Encode(std::uint32_t scalar)
{
    std::string result;
    if (scalar < 0x80) result += char(scalar);
    else if (scalar < 0x800)
    {
        result += char(0xc0 | (scalar >> 6));
        result += char(0x80 | (scalar & 0x3f));
    }
    else if (scalar < 0x10000)
    {
        result += char(0xe0 | (scalar >> 12));
        result += char(0x80 | ((scalar >> 6) & 0x3f));
        result += char(0x80 | (scalar & 0x3f));
    }
    else
    {
        result += char(0xf0 | (scalar >> 18));
        result += char(0x80 | ((scalar >> 12) & 0x3f));
        result += char(0x80 | ((scalar >> 6) & 0x3f));
        result += char(0x80 | (scalar & 0x3f));
    }
    return result;
}
}

int main()
{
    Input input{{std::istreambuf_iterator<char>(std::cin), std::istreambuf_iterator<char>()}};
    Output output;
    const auto commands = input.Word();
    output.Word(commands);
    std::string retained("retained\0output", 15);
    for (std::uint32_t command = 0; command < commands; ++command)
    {
        const auto op = input.Word();
        output.Word(op);
        if (op == 0)
        {
            output.Word(0x110000 - 0x800);
            for (std::uint32_t scalar = 0; scalar < 0x110000; ++scalar)
            {
                if (scalar >= 0xd800 && scalar <= 0xdfff) continue;
                std::string formatted, error;
                if (!atelier::skate::FormatRustDebugString(Encode(scalar), formatted, error)) std::abort();
                output.Word(scalar);
                output.Text(formatted);
            }
        }
        else if (op == 1 || op == 2)
        {
            const auto text = input.Text();
            std::string error;
            const bool okay = atelier::skate::FormatRustDebugString(text, retained, error);
            output.Word(okay);
            output.Text(error);
            output.Text(retained);
        }
        else std::abort();
    }
    if (input.at != input.bytes.size()) std::abort();
    std::cout.write(output.bytes.data(), std::streamsize(output.bytes.size()));
}

#include "HostScalar.h"
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace
{
struct Input
{
    std::vector<unsigned char> bytes;
    std::size_t at = 0;
    bool okay = true;
    std::uint32_t Word()
    {
        if (bytes.size() - at < 4) { okay = false; return 0; }
        std::uint32_t value = 0;
        for (unsigned i = 0; i < 4; ++i) value |= std::uint32_t(bytes[at++]) << (8 * i);
        return value;
    }
    double Double()
    {
        const std::uint64_t low = Word();
        const std::uint64_t bits = low | (std::uint64_t(Word()) << 32);
        double value; std::memcpy(&value, &bits, sizeof(value)); return value;
    }
    std::string Text()
    {
        const auto length = Word();
        if (bytes.size() - at < length) { okay = false; return {}; }
        std::string value(bytes.begin() + at, bytes.begin() + at + length);
        at += length; return value;
    }
};
void Word(std::uint32_t value)
{
    for (unsigned i = 0; i < 4; ++i) std::cout.put(char(value >> (8 * i)));
}
std::uint32_t Bits(float value)
{
    std::uint32_t bits; std::memcpy(&bits, &value, sizeof(bits)); return bits;
}
void Text(const std::string& value)
{
    Word(std::uint32_t(value.size())); std::cout.write(value.data(), std::streamsize(value.size()));
}
}

int main()
{
    Input input{{std::istreambuf_iterator<char>(std::cin), std::istreambuf_iterator<char>()}, 0, true};
    const auto count = input.Word(); Word(count);
    for (std::uint32_t index = 0; index < count; ++index)
    {
        const auto operation = input.Word();
        std::string token, error = "previous error";
        float value = -151.375f;
        bool okay = false;
        std::uint32_t direct = 0;
        if (operation == 0)
        {
            token = input.Text();
            okay = atelier::skate::ParseHostScalar(token, value, error);
        }
        else if (operation == 1 || operation == 2)
        {
            double number = input.Double();
            if (operation == 2) number *= .01; // original ToNative UE centimetres -> metres
            token = atelier::skate::FormatHostScalar(number);
            direct = std::isfinite(number) ? Bits(float(number)) : 0;
            okay = atelier::skate::ConvertHostScalar(number, value, error);
        }
        else return 2;
        if (!input.okay) return 3;
        Word(index); Word(operation); Text(token); Word(okay ? 1 : 0);
        Word(Bits(value)); Text(error); Word(direct);
    }
    return input.okay && input.at == input.bytes.size() && std::cout.good() ? 0 : 4;
}

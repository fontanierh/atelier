// Standalone test adapter; this main is not part of the Unreal module.
#include "Gestures.h"
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>

using namespace atelier::skate;
namespace
{
constexpr std::uint32_t None = 0xffffffffu;
void Word(std::uint32_t value)
{
    const char bytes[4] = {char(value), char(value>>8), char(value>>16), char(value>>24)};
    std::cout.write(bytes, 4);
}
std::uint32_t ReadWord()
{
    unsigned char b[4]{};
    std::cin.read(reinterpret_cast<char*>(b), 4);
    return std::uint32_t(b[0]) | (std::uint32_t(b[1])<<8) | (std::uint32_t(b[2])<<16) | (std::uint32_t(b[3])<<24);
}
float ReadFloat()
{
    const auto bits = ReadWord();
    float value;
    std::memcpy(&value, &bits, 4);
    return value;
}
void Float(float value)
{
    std::uint32_t bits;
    std::memcpy(&bits, &value, 4);
    Word(bits);
}
void String(const std::string& value)
{
    Word(static_cast<std::uint32_t>(value.size()));
    std::cout.write(value.data(), value.size());
}
}

int main(int argc, char** argv)
{
    if (argc != 3) { std::cerr << "usage: gesture-probe DATA dump|replay\n"; return 2; }
    std::ifstream file(argv[1], std::ios::binary);
    std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
    std::vector<GestureSet> sets;
    std::string error;
    if (!LoadGestureData(bytes, sets, error)) { std::cerr << error << '\n'; return 2; }
    if (std::string(argv[2]) == "dump")
    {
        std::cout.write("ATGEST01", 8);
        Word(static_cast<std::uint32_t>(sets.size()));
        for (const auto& set : sets)
        {
            String(set.name); Word(set.stick); Word(static_cast<std::uint32_t>(set.patterns.size()));
            for (const auto& pattern : set.patterns)
            {
                String(pattern.name); Float(pattern.tolerance_squared); Word(static_cast<std::uint32_t>(pattern.points.size()));
                for (const auto& point : pattern.points) { Float(point[0]); Float(point[1]); }
            }
        }
        return 0;
    }
    if (std::string(argv[2]) != "replay") return 2;
    std::vector<GestureRecognizer> recognizers;
    for (const auto& set : sets) recognizers.emplace_back(set.patterns);
    while (std::cin.peek() != std::char_traits<char>::eof())
    {
        const auto set = ReadWord(), operation = ReadWord(), difficulty = ReadWord(), misses = ReadWord();
        const StickPoint sample{ReadFloat(), ReadFloat()};
        if (!std::cin || set >= sets.size() || operation > 1 || misses > 255) return 2;
        auto& recognizer = recognizers[set];
        if (operation == 0)
        {
            recognizer = GestureRecognizer(sets[set].patterns);
            Word(None); Word(None); Word(0); Word(0); Word(0);
            continue;
        }
        const auto held = recognizer.Held(sample);
        const auto match = recognizer.Sample(sample, GestureSettings{static_cast<std::uint8_t>(misses), difficulty});
        Word(held ? static_cast<std::uint32_t>(*held) : None);
        Word(match ? static_cast<std::uint32_t>(match->pattern) : None);
        Float(match ? match->strength : 0.f);
        Float(match ? match->distance : 0.f);
        Float(match ? match->elapsed : 0.f);
    }
    return std::cout ? 0 : 2;
}

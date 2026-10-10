#pragma once
#include <cstdint>
#include <cstring>
#include <limits>
#include <string>
#include <vector>

namespace atelier::skate::detail
{
struct DataReader
{
    const std::vector<std::uint8_t>& bytes;
    std::size_t at = 8;
    bool ok = true;

    bool Need(std::size_t count)
    {
        if (!ok || at > bytes.size() || count > bytes.size()-at) ok = false;
        return ok;
    }
    std::size_t Remaining() const { return at <= bytes.size() ? bytes.size()-at : 0; }
    std::uint32_t Word()
    {
        if (!Need(4)) return 0;
        const std::uint32_t value = std::uint32_t(bytes[at]) | (std::uint32_t(bytes[at+1])<<8) |
            (std::uint32_t(bytes[at+2])<<16) | (std::uint32_t(bytes[at+3])<<24);
        at += 4;
        return value;
    }
    float Float()
    {
        static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559);
        const std::uint32_t bits = Word();
        float value;
        std::memcpy(&value,&bits,4);
        return value;
    }
    std::string RawString(std::size_t count)
    {
        if (!Need(count)) return {};
        std::string value(reinterpret_cast<const char*>(bytes.data()+at),count);
        at += count;
        return value;
    }
    std::string String() { const auto count = Word(); return RawString(count); }
};
}

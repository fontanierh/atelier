#include "AnimationName.h"

namespace atelier::skate
{
AttributeName EncodeAnimationName(std::string_view text)
{
    AttributeName words{};
    std::size_t position = 0;
    while (position < 30 && position < text.size() && text[position] != 0)
    {
        std::uint32_t weight = 79235168;
        const auto word = position / 6;
        std::size_t count = 0;
        while (count < 6 && position < text.size() && text[position] != 0)
        {
            const auto raw = static_cast<unsigned char>(text[position]);
            const auto byte = raw < 128 ? std::int32_t(raw) : std::int32_t(raw)-256;
            const auto digit = byte >= 97 ? byte-86 : byte > 90 ? byte-58 : byte > 57 ? byte-54 : byte-47;
            words[word] += static_cast<std::uint32_t>(digit) * weight;
            weight /= 38;
            ++count;
            ++position;
        }
    }
    return words;
}

IntentKey EncodeIntentKey(std::string_view text)
{
    const auto first = EncodeAnimationName(text);
    const auto tail = text.size() > 30 && text.substr(0,30).find('\0') == std::string_view::npos
        ? EncodeAnimationName(text.substr(30))[0] : 0;
    return {first[0],first[1],first[2],first[3],first[4],tail};
}
}

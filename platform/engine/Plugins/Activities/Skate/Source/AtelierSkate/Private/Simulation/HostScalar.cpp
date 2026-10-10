// SPDX-License-Identifier: MIT OR Apache-2.0
// Numeric parsing is a source-ordered C++ port of serde_json 1.0.151 src/de.rs
// (parse_integer/number/decimal/exponent, their overflow paths, f64_from_parts)
// and serde 1.0.228's f32 visitor. Both built with default+std only: no
// float_roundtrip or arbitrary_precision. See the focused proof's provenance.
#include "HostScalar.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <utility>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
// The original literal POW10 table is inserted below and hashed by the proof.
static const double Pow10[309] = {
    1e000, 1e001, 1e002, 1e003, 1e004, 1e005, 1e006, 1e007, 1e008, 1e009, //
    1e010, 1e011, 1e012, 1e013, 1e014, 1e015, 1e016, 1e017, 1e018, 1e019, //
    1e020, 1e021, 1e022, 1e023, 1e024, 1e025, 1e026, 1e027, 1e028, 1e029, //
    1e030, 1e031, 1e032, 1e033, 1e034, 1e035, 1e036, 1e037, 1e038, 1e039, //
    1e040, 1e041, 1e042, 1e043, 1e044, 1e045, 1e046, 1e047, 1e048, 1e049, //
    1e050, 1e051, 1e052, 1e053, 1e054, 1e055, 1e056, 1e057, 1e058, 1e059, //
    1e060, 1e061, 1e062, 1e063, 1e064, 1e065, 1e066, 1e067, 1e068, 1e069, //
    1e070, 1e071, 1e072, 1e073, 1e074, 1e075, 1e076, 1e077, 1e078, 1e079, //
    1e080, 1e081, 1e082, 1e083, 1e084, 1e085, 1e086, 1e087, 1e088, 1e089, //
    1e090, 1e091, 1e092, 1e093, 1e094, 1e095, 1e096, 1e097, 1e098, 1e099, //
    1e100, 1e101, 1e102, 1e103, 1e104, 1e105, 1e106, 1e107, 1e108, 1e109, //
    1e110, 1e111, 1e112, 1e113, 1e114, 1e115, 1e116, 1e117, 1e118, 1e119, //
    1e120, 1e121, 1e122, 1e123, 1e124, 1e125, 1e126, 1e127, 1e128, 1e129, //
    1e130, 1e131, 1e132, 1e133, 1e134, 1e135, 1e136, 1e137, 1e138, 1e139, //
    1e140, 1e141, 1e142, 1e143, 1e144, 1e145, 1e146, 1e147, 1e148, 1e149, //
    1e150, 1e151, 1e152, 1e153, 1e154, 1e155, 1e156, 1e157, 1e158, 1e159, //
    1e160, 1e161, 1e162, 1e163, 1e164, 1e165, 1e166, 1e167, 1e168, 1e169, //
    1e170, 1e171, 1e172, 1e173, 1e174, 1e175, 1e176, 1e177, 1e178, 1e179, //
    1e180, 1e181, 1e182, 1e183, 1e184, 1e185, 1e186, 1e187, 1e188, 1e189, //
    1e190, 1e191, 1e192, 1e193, 1e194, 1e195, 1e196, 1e197, 1e198, 1e199, //
    1e200, 1e201, 1e202, 1e203, 1e204, 1e205, 1e206, 1e207, 1e208, 1e209, //
    1e210, 1e211, 1e212, 1e213, 1e214, 1e215, 1e216, 1e217, 1e218, 1e219, //
    1e220, 1e221, 1e222, 1e223, 1e224, 1e225, 1e226, 1e227, 1e228, 1e229, //
    1e230, 1e231, 1e232, 1e233, 1e234, 1e235, 1e236, 1e237, 1e238, 1e239, //
    1e240, 1e241, 1e242, 1e243, 1e244, 1e245, 1e246, 1e247, 1e248, 1e249, //
    1e250, 1e251, 1e252, 1e253, 1e254, 1e255, 1e256, 1e257, 1e258, 1e259, //
    1e260, 1e261, 1e262, 1e263, 1e264, 1e265, 1e266, 1e267, 1e268, 1e269, //
    1e270, 1e271, 1e272, 1e273, 1e274, 1e275, 1e276, 1e277, 1e278, 1e279, //
    1e280, 1e281, 1e282, 1e283, 1e284, 1e285, 1e286, 1e287, 1e288, 1e289, //
    1e290, 1e291, 1e292, 1e293, 1e294, 1e295, 1e296, 1e297, 1e298, 1e299, //
    1e300, 1e301, 1e302, 1e303, 1e304, 1e305, 1e306, 1e307, 1e308,
};

class NumberReader
{
public:
    NumberReader(std::string_view input, std::string& message)
        : text(input), error(message) {}

    bool Read(float& result)
    {
        White();
        if (at == text.size()) return Fail("EOF while parsing a value", at);
        const char next = Peek();
        bool okay = false;
        if (next == '-') { ++at; okay = Integer(false, result); }
        else if (Digit(next)) okay = Integer(true, result);
        else return NonNumber();
        if (!okay) return false;
        White();
        if (at != text.size()) return PeekFail("trailing characters");
        return true;
    }

private:
    std::string_view text;
    std::string& error;
    std::size_t at = 0;

    static bool Digit(char c) { return c >= '0' && c <= '9'; }
    char Peek() const { return at < text.size() ? text[at] : '\0'; }
    void White()
    {
        while (at < text.size() && (text[at] == ' ' || text[at] == '\n'
               || text[at] == '\t' || text[at] == '\r')) ++at;
    }
    bool Fail(std::string message, std::size_t index)
    {
        std::size_t line = 1, column = 0;
        for (std::size_t i = 0; i < std::min(index, text.size()); ++i)
        {
            if (text[i] == '\n') { ++line; column = 0; }
            else ++column;
        }
        error = std::move(message) + " at line " + std::to_string(line)
              + " column " + std::to_string(column);
        return false;
    }
    bool PeekFail(std::string message)
    { return Fail(std::move(message), std::min(text.size(), at + 1)); }
    bool Ident(std::string_view suffix)
    {
        for (char expected : suffix)
        {
            if (at == text.size()) return Fail("EOF while parsing a value", at);
            if (text[at++] != expected) return Fail("expected ident", at);
        }
        return true;
    }
    bool NonNumber()
    {
        const char c = Peek();
        if (c == 'n' || c == 't' || c == 'f')
        {
            ++at;
            if (!Ident(c == 'n' ? "ull" : c == 't' ? "rue" : "alse")) return false;
            const std::string type = c == 'n' ? "null" : c == 't' ? "boolean `true`" : "boolean `false`";
            return Fail("invalid type: " + type + ", expected f32", at);
        }
        if (c == '[' || c == '{')
            return Fail(std::string("invalid type: ") + (c == '[' ? "sequence" : "map") + ", expected f32", at);
        return PeekFail("expected value");
    }
    static bool Overflow(std::uint64_t n, std::uint64_t digit)
    { return n > (std::numeric_limits<std::uint64_t>::max() - digit) / 10; }
    bool Integer(bool positive, float& result)
    {
        if (at == text.size()) return Fail("EOF while parsing a value", at);
        const char first = text[at++];
        if (first == '0')
        {
            if (Digit(Peek())) return PeekFail("invalid number");
            return Number(positive, 0, result);
        }
        if (first < '1' || first > '9') return Fail("invalid number", at);
        std::uint64_t significand = std::uint64_t(first - '0');
        while (Digit(Peek()))
        {
            const auto digit = std::uint64_t(Peek() - '0');
            if (Overflow(significand, digit)) return LongInteger(positive, significand, result);
            ++at;
            significand = significand * 10 + digit;
        }
        return Number(positive, significand, result);
    }
    bool Number(bool positive, std::uint64_t significand, float& result)
    {
        if (Peek() == '.') return Decimal(positive, significand, 0, result);
        if (Peek() == 'e' || Peek() == 'E') return Exponent(positive, significand, 0, result);
        // ParserNumber's integer variants visit f32 directly. Passing those
        // through double would introduce a second, incorrect rounding boundary.
        if (positive) result = float(significand);
        else if (significand != 0 && significand <= (std::uint64_t(1) << 63))
        {
            const auto signed_value = significand == (std::uint64_t(1) << 63)
                ? std::numeric_limits<std::int64_t>::min() : -std::int64_t(significand);
            result = float(signed_value);
        }
        else result = std::copysign(float(-double(significand)), -1.0f);
        return true;
    }
    bool Decimal(bool positive, std::uint64_t significand, std::int32_t before, float& result)
    {
        ++at; // decimal point
        std::int32_t after = 0;
        while (Digit(Peek()))
        {
            const auto digit = std::uint64_t(Peek() - '0');
            if (Overflow(significand, digit)) return DecimalOverflow(positive, significand, before + after, result);
            ++at;
            significand = significand * 10 + digit;
            --after;
        }
        if (after == 0) return at == text.size()
            ? PeekFail("EOF while parsing a value") : PeekFail("invalid number");
        const auto exponent = before + after;
        return Peek() == 'e' || Peek() == 'E'
            ? Exponent(positive, significand, exponent, result)
            : FromParts(positive, significand, exponent, result);
    }
    bool Exponent(bool positive, std::uint64_t significand, std::int32_t starting, float& result)
    {
        ++at;
        bool positive_exp = true;
        if (Peek() == '+' || Peek() == '-') positive_exp = text[at++] == '+';
        if (at == text.size()) return Fail("EOF while parsing a value", at);
        const char first = text[at++];
        if (!Digit(first)) return Fail("invalid number", at);
        std::int32_t exponent = first - '0';
        while (Digit(Peek()))
        {
            const auto digit = std::int32_t(text[at++] - '0');
            if (exponent > (std::numeric_limits<std::int32_t>::max() - digit) / 10)
                return ExponentOverflow(positive, significand == 0, positive_exp, result);
            exponent = exponent * 10 + digit;
        }
        const std::int64_t combined = std::int64_t(starting)
            + (positive_exp ? std::int64_t(exponent) : -std::int64_t(exponent));
        const auto final_exp = std::int32_t(std::clamp(combined,
            std::int64_t(std::numeric_limits<std::int32_t>::min()),
            std::int64_t(std::numeric_limits<std::int32_t>::max())));
        return FromParts(positive, significand, final_exp, result);
    }
    bool FromParts(bool positive, std::uint64_t significand, std::int32_t exponent, float& result)
    {
        double value = double(significand);
        for (;;)
        {
            // wrapping_abs(i32::MIN) converted to usize lies outside POW10.
            const std::int64_t magnitude = exponent >= 0 ? exponent : -std::int64_t(exponent);
            if (magnitude <= 308)
            {
                if (exponent >= 0)
                {
                    value *= Pow10[magnitude];
                    if (std::isinf(value)) return Fail("number out of range", at);
                }
                else value /= Pow10[magnitude];
                break;
            }
            if (value == 0.0) break;
            if (exponent >= 0) return Fail("number out of range", at);
            value /= 1e308;
            exponent += 308;
        }
        // serde std's visit_f64 copies the original sign after casting.
        const double signed_value = positive ? value : -value;
        result = std::copysign(float(signed_value), positive ? 1.0f : -1.0f);
        return true;
    }
    bool LongInteger(bool positive, std::uint64_t significand, float& result)
    {
        std::int32_t exponent = 0;
        while (Digit(Peek())) { ++at; ++exponent; }
        if (Peek() == '.') return Decimal(positive, significand, exponent, result);
        if (Peek() == 'e' || Peek() == 'E') return Exponent(positive, significand, exponent, result);
        return FromParts(positive, significand, exponent, result);
    }
    bool DecimalOverflow(bool positive, std::uint64_t significand, std::int32_t exponent, float& result)
    {
        while (Digit(Peek())) ++at;
        return Peek() == 'e' || Peek() == 'E'
            ? Exponent(positive, significand, exponent, result)
            : FromParts(positive, significand, exponent, result);
    }
    bool ExponentOverflow(bool positive, bool zero, bool positive_exp, float& result)
    {
        if (!zero && positive_exp) return Fail("number out of range", at);
        while (Digit(Peek())) ++at;
        result = positive ? 0.0f : -0.0f;
        return true;
    }
};
}

std::string FormatHostScalar(double value)
{
    // Same C printf conversion as Unreal JsonPrintPolicy::WriteDouble.
    char token[64];
    const int length = std::snprintf(token, sizeof(token), "%.17g", value);
    return length > 0 && std::size_t(length) < sizeof(token)
        ? std::string(token, std::size_t(length)) : std::string{};
}

bool ParseHostScalar(std::string_view token, float& output, std::string& error)
{
    float value = 0.0f;
    NumberReader reader(token, error);
    if (!reader.Read(value)) return false;
    output = value;
    error.clear();
    return true;
}

bool ConvertHostScalar(double value, float& output, std::string& error)
{
    return ParseHostScalar(FormatHostScalar(value), output, error);
}
}

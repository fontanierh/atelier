#pragma once
#include <string>
#include <string_view>

namespace atelier::skate
{
// Former Unreal numeric command boundary: JsonPrintPolicy formats double with
// %.17g, then default serde_json 1.0.151 deserializes the token into f32.
// This keeps its decimal rounding before the final cast. It is not a reader for
// assets or commands. Parse accepts numeric tokens/printf non-finite spellings;
// output remains unchanged on any failure, including trailing input.
std::string FormatHostScalar(double value);
bool ParseHostScalar(std::string_view token, float& output, std::string& error);
bool ConvertHostScalar(double value, float& output, std::string& error);
}

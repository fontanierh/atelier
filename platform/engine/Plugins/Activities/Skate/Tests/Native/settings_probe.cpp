#include "Settings.h"
#include "DataReader.h"
#include <algorithm>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>

using namespace atelier::skate;
namespace
{
void Word(std::uint32_t value)
{
    const char bytes[4] = {char(value),char(value>>8),char(value>>16),char(value>>24)};
    std::cout.write(bytes,4);
}
void String(const std::string& value)
{
    Word(static_cast<std::uint32_t>(value.size()));
    std::cout.write(value.data(),value.size());
}
std::string SourceValue(const SettingValue& field)
{
    if (field.is_text) return field.text;
    constexpr char digits[] = "0123456789ABCDEF";
    std::string result;
    for (std::size_t i = 0; i < field.words.size(); ++i)
    {
        const auto bytes = std::min<std::size_t>(4,field.byte_count-i*4);
        for (std::size_t b = bytes; b > 0; --b)
        {
            const auto value = (field.words[i] >> ((b-1)*8)) & 255;
            result += digits[value>>4]; result += digits[value&15];
        }
    }
    return result;
}
void Field(const SettingValue& field)
{
    String(field.name); String(field.type); String(SourceValue(field));
}
void Values(const SettingValue* field)
{
    Word(field != nullptr);
    if (!field) return;
    Field(*field);
    const auto f = field->Float();
    const auto i = field->Integer();
    const auto b = field->Boolean();
    Word((f ? 1u : 0u) | (i ? 2u : 0u) | (b ? 4u : 0u));
    std::uint32_t bits = 0;
    if (f) std::memcpy(&bits,&*f,4);
    Word(bits); Word(i.value_or(0)); Word(b.value_or(false));
}
}

int main(int argc,char** argv)
{
    if (argc != 3) return 2;
    std::ifstream file(argv[1],std::ios::binary);
    const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(file),std::istreambuf_iterator<char>()};
    SettingsDatabase database;
    std::string error;
    if (!database.Load(bytes,error)) { std::cerr << error << '\n'; return 2; }
    if (std::string(argv[2]) == "dump")
    {
        Word(static_cast<std::uint32_t>(database.Records().size()));
        for (const auto& record : database.Records())
        {
            String(record.category); String(record.key); String(record.parent);
            Word(static_cast<std::uint32_t>(record.fields.size()));
            for (const auto& field : record.fields) Field(field);
        }
    }
    else if (std::string(argv[2]) == "query")
    {
        const std::vector<std::uint8_t> input{std::istreambuf_iterator<char>(std::cin),std::istreambuf_iterator<char>()};
        detail::DataReader reader{input,0};
        const auto count = reader.Word();
        if (count > reader.Remaining()/12) return 2;
        for (std::uint32_t i = 0; i < count; ++i)
        {
            const auto category = reader.String(), key = reader.String(), name = reader.String();
            if (!reader.ok) return 2;
            Values(database.Field(category,key,name));
        }
        if (reader.Remaining() || !reader.ok) return 2;
    }
    else return 2;
    return std::cout ? 0 : 2;
}

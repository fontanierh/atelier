// SPDX-License-Identifier: Apache-2.0
#include "Settings.h"
#include "DataReader.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <utility>

namespace atelier::skate
{
std::optional<float> SettingValue::Float() const
{
    if (type != "EA::Reflection::Float" || is_text || byte_count != 4 || words.size() != 1) return std::nullopt;
    float value;
    std::memcpy(&value,words.data(),4);
    return std::isfinite(value) ? std::optional<float>(value) : std::nullopt;
}

std::optional<std::uint32_t> SettingValue::Integer() const
{
    if ((type != "EA::Reflection::Int32" && type != "EA::Reflection::UInt32") ||
        is_text || byte_count != 4 || words.size() != 1) return std::nullopt;
    return words[0];
}

std::optional<bool> SettingValue::Boolean() const
{
    if (type != "EA::Reflection::Bool" || is_text || byte_count == 0 || words.empty()) return std::nullopt;
    const auto first = words[0] >> ((std::min(byte_count,4u)-1)*8);
    if (first > 1) return std::nullopt;
    return first == 1;
}

bool SettingValue::Words(std::size_t count, const std::uint32_t*& values) const
{
    if (is_text || count != words.size() || count != byte_count/4 || byte_count%4 != 0) return false;
    values = words.data();
    return true;
}

bool SettingsDatabase::Load(const std::vector<std::uint8_t>& bytes, std::string& error)
{
    auto fail = [&]() { error = "Invalid native settings data"; return false; };
    if (bytes.size() < 16 || std::memcmp(bytes.data(),"ATATTR01",8) != 0) return fail();
    detail::DataReader input{bytes};
    const auto string_count = input.Word(), record_count = input.Word();
    if (string_count > input.Remaining()/4 || record_count > input.Remaining()/16) return fail();
    std::vector<std::string> strings;
    for (std::uint32_t i = 0; i < string_count; ++i)
    {
        strings.push_back(input.String());
        if (!input.ok) return fail();
    }
    auto string = [&]() -> std::string
    {
        const auto index = input.Word();
        if (!input.ok || index >= strings.size()) { input.ok = false; return {}; }
        return strings[index];
    };
    std::vector<SettingRecord> records;
    std::map<std::pair<std::uint64_t,std::uint64_t>,std::size_t> index;
    for (std::uint32_t r = 0; r < record_count; ++r)
    {
        SettingRecord record;
        record.category = string(); record.key = string(); record.parent = string();
        record.category_id = NameId(record.category); record.key_id = NameId(record.key); record.parent_id = NameId(record.parent);
        const auto field_count = input.Word();
        if (!input.ok || field_count > input.Remaining()/16) return fail();
        if (!index.emplace(std::make_pair(record.category_id,record.key_id),records.size()).second) return fail();
        for (std::uint32_t f = 0; f < field_count; ++f)
        {
            SettingValue field;
            field.name = string(); field.type = string(); field.id = NameId(field.name);
            const auto encoding = input.Word();
            field.byte_count = input.Word();
            if (!input.ok || encoding > 1) return fail();
            field.is_text = encoding == 1;
            if (field.is_text)
            {
                if (field.type != "EA::Reflection::Text") return fail();
                field.text = input.RawString(field.byte_count);
            }
            else
            {
                if (field.type == "EA::Reflection::Text") return fail();
                const auto count = std::size_t(field.byte_count)/4 + (field.byte_count%4 != 0);
                if (count > input.Remaining()/4) return fail();
                for (std::size_t i = 0; i < count; ++i) field.words.push_back(input.Word());
                if (field.byte_count%4 && (field.words.back() >> (8*(field.byte_count%4))) != 0) return fail();
            }
            if (!input.ok) return fail();
            if (!record.fields.empty() && record.fields.back().name >= field.name) return fail();
            record.fields.push_back(std::move(field));
        }
        records.push_back(std::move(record));
    }
    if (!input.ok || input.Remaining() != 0) return fail();
    records_ = std::move(records);
    index_ = std::move(index);
    error.clear();
    return true;
}

const SettingValue* SettingsDatabase::Field(std::string_view category, std::string_view key, std::string_view name) const
{
    const auto category_id = NameId(category), field_id = NameId(name);
    auto key_id = NameId(key);
    for (std::size_t hop = 0; hop <= records_.size(); ++hop)
    {
        const auto found = index_.find({category_id,key_id});
        if (found == index_.end()) return nullptr;
        const auto& record = records_[found->second];
        // Preserve direct-name priority before trying numeric aliases.
        const auto direct = std::lower_bound(record.fields.begin(),record.fields.end(),name,
            [](const SettingValue& field, std::string_view value) { return field.name < value; });
        if (direct != record.fields.end() && direct->name == name) return &*direct;
        for (const auto& field : record.fields) if (field.id == field_id) return &field;
        if (record.parent.empty()) return nullptr;
        key_id = record.parent_id;
    }
    return nullptr;
}
}

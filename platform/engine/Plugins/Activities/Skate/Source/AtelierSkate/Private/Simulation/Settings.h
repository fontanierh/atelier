#pragma once
#include "NameId.h"
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace atelier::skate
{
struct SettingValue
{
    std::string name;
    std::string type;
    std::uint64_t id = 0;
    bool is_text = false;
    std::uint32_t byte_count = 0;
    // Numeric fields hold exact bit words in host order, including structured
    // values such as curves. Text is stored directly as UTF-8.
    std::vector<std::uint32_t> words;
    std::string text;
    std::optional<float> Float() const;
    std::optional<std::uint32_t> Integer() const;
    std::optional<bool> Boolean() const;
    bool Words(std::size_t count, const std::uint32_t*& values) const;
};

struct SettingRecord
{
    std::string category;
    std::string key;
    std::string parent;
    std::uint64_t category_id = 0, key_id = 0, parent_id = 0;
    std::vector<SettingValue> fields;
};

class SettingsDatabase
{
public:
    bool Load(const std::vector<std::uint8_t>& bytes, std::string& error);
    const SettingValue* Field(std::string_view category, std::string_view key, std::string_view name) const;
    const std::vector<SettingRecord>& Records() const { return records_; }
private:
    std::vector<SettingRecord> records_;
    std::map<std::pair<std::uint64_t,std::uint64_t>,std::size_t> index_;
};
}

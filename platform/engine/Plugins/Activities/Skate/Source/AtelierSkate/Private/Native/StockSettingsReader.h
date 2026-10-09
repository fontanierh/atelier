#pragma once
#include "NativeMath.h"
#include "Settings.h"
namespace atelier::skate
{
// Original Collections lookup/type/decode semantics over normalized native data.
// No per-call JSON, reflection decoding, or synthetic setting defaults.
class StockSettingsReader
{
public:
    explicit StockSettingsReader(const SettingsDatabase& data):data_(data) {}
    const SettingValue* Field(std::string_view category,std::string_view key,std::string_view name,std::string& error) const;
    bool Integer(std::string_view category,std::string_view key,std::string_view name,std::uint32_t& output,std::string& error) const;
    bool Float(std::string_view category,std::string_view key,std::string_view name,float& output,std::string& error) const;
    bool Boolean(std::string_view category,std::string_view key,std::string_view name,bool& output,std::string& error) const;
    bool Curve8(std::string_view category,std::string_view key,std::string_view name,PointGraph<8>& output,std::string& error) const;
    bool Curve8Layout20(std::string_view category,std::string_view key,std::string_view name,PointGraph<8>& output,std::string& error) const;
    bool Words(std::string_view category,std::string_view key,std::string_view name,std::size_t count,std::vector<std::uint32_t>& output,std::string& error) const;
private:
    const SettingsDatabase& data_;
};
}

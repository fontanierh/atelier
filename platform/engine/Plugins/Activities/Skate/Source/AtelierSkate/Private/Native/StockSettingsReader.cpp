// SPDX-License-Identifier: Apache-2.0
#include "StockSettingsReader.h"
#include <algorithm>
#include <cmath>
#include <cstring>
namespace atelier::skate
{
namespace
{
std::string Path(std::string_view category,std::string_view key,std::string_view name)
{return std::string(category)+"/"+std::string(key)+"/"+std::string(name);}
const SettingValue* ReadField(const SettingsDatabase& data,std::string_view category,std::string_view key,std::string_view name,std::string& error)
{
    const auto category_id=NameId(category),field_id=NameId(name);auto current=key;
    for (std::size_t hop=0;hop<=data.Records().size();++hop)
    {
        const auto key_id=NameId(current);const auto found=std::find_if(data.Records().begin(),data.Records().end(),[&](const SettingRecord& record) {return record.category_id==category_id&&record.key_id==key_id;});
        if (found==data.Records().end()) {error="Missing stock collection "+std::string(category)+"/"+std::string(current);return nullptr;}
        const auto direct=std::lower_bound(found->fields.begin(),found->fields.end(),name,[](const SettingValue& field,std::string_view value) {return field.name<value;});
        if (direct!=found->fields.end()&&direct->name==name) return &*direct;
        const auto alias=std::find_if(found->fields.begin(),found->fields.end(),[&](const SettingValue& field) {return field.id==field_id;});if (alias!=found->fields.end()) return &*alias;
        if (found->parent.empty()) {error="Missing stock field "+Path(category,key,name);return nullptr;}current=found->parent;
    }
    error="Cyclic stock collection inheritance "+std::string(category)+"/"+std::string(key);return nullptr;
}
float Float(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
std::size_t Whitespace(std::string_view text,std::size_t at)
{
    const auto a=static_cast<unsigned char>(text[at]);if (a==' '||(a>=9&&a<=13)) return 1;
    if (at+1<text.size()&&a==0xc2) {const auto b=static_cast<unsigned char>(text[at+1]);if (b==0x85||b==0xa0) return 2;}
    if (at+2<text.size())
    {
        const auto b=static_cast<unsigned char>(text[at+1]),c=static_cast<unsigned char>(text[at+2]);
        if ((a==0xe1&&b==0x9a&&c==0x80)||(a==0xe2&&b==0x80&&((c>=0x80&&c<=0x8a)||c==0xa8||c==0xa9||c==0xaf))||(a==0xe2&&b==0x81&&c==0x9f)||(a==0xe3&&b==0x80&&c==0x80)) return 3;
    }
    return 0;
}
template<std::size_t N> bool Words(const SettingValue& field,std::array<std::uint32_t,N>& output,std::string& error)
{
    if (!field.is_text)
    {
        const std::uint32_t* words=nullptr;if (!field.Words(N,words)) {error="Expected "+std::to_string(N)+" big-endian words, found "+std::to_string(field.byte_count*2)+" bytes of hex";return false;}
        std::copy_n(words,N,output.begin());return true;
    }
    std::string hex;for (std::size_t at=0;at<field.text.size();) {const auto space=Whitespace(field.text,at);if (space) at+=space;else hex+=field.text[at++];}
    if (hex.size()!=N*8||std::any_of(hex.begin(),hex.end(),[](unsigned char c) {return c>=128;})) {error="Expected "+std::to_string(N)+" big-endian words, found "+std::to_string(hex.size())+" bytes of hex";return false;}
    for (std::size_t i=0;i<N;++i)
    {
        std::uint32_t word=0;for (std::size_t j=0;j<8;++j) {const auto c=hex[i*8+j];const int digit=c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;if (digit<0) {error="Invalid collection payload: invalid digit found in string";return false;}word=(word<<4)|std::uint32_t(digit);}output[i]=word;
    }
    return true;
}
bool ReadScalar(const SettingsDatabase& data,std::string_view category,std::string_view key,std::string_view name,float& output,std::string& error)
{
    const auto* field=ReadField(data,category,key,name,error);if (!field) return false;if (field->type!="EA::Reflection::Float") {error="Expected float at "+Path(category,key,name);return false;}
    std::array<std::uint32_t,1> words{};if (!Words(*field,words,error)) return false;const auto value=Float(words[0]);if (!std::isfinite(value)) {error="Non-finite stock float "+Path(category,key,name);return false;}output=value;return true;
}
bool ReadBoolean(const SettingsDatabase& data,std::string_view category,std::string_view key,std::string_view name,bool& output,std::string& error)
{
    const auto* field=ReadField(data,category,key,name,error);if (!field) return false;if (field->type!="EA::Reflection::Bool") {error="Expected boolean at "+Path(category,key,name);return false;}
    const auto value=field->Boolean();if (!value) {error="Invalid stock boolean "+Path(category,key,name);return false;}output=*value;return true;
}
bool ReadCurve(const SettingsDatabase& data,std::string_view category,std::string_view key,std::string_view name,PointGraph<8>& output,std::string& error,bool fixed_twenty=false)
{
    const auto* field=ReadField(data,category,key,name,error);if (!field) return false;std::size_t offset=0;std::array<std::uint32_t,20> values{};
    const auto size=field->is_text?field->text.size():field->byte_count*2;
    if (!fixed_twenty&&size==128) {std::array<std::uint32_t,16> words{};if (!Words(*field,words,error)) return false;std::copy(words.begin(),words.end(),values.begin());}
    else if (fixed_twenty||size==160) {if (!Words(*field,values,error)) return false;offset=4;}
    else {error="Invalid native eight-point graph "+Path(category,key,name);return false;}
    for (std::size_t i=0;i<8;++i) {output.x[i]=Float(values[offset+i]);output.y[i]=Float(values[offset+8+i]);}return true;
}
}
bool StockSettingsReader::Float(std::string_view c,std::string_view k,std::string_view n,float& output,std::string& error) const
{const auto ok=ReadScalar(data_,c,k,n,output,error);if (ok) error.clear();return ok;}
bool StockSettingsReader::Boolean(std::string_view c,std::string_view k,std::string_view n,bool& output,std::string& error) const
{const auto ok=ReadBoolean(data_,c,k,n,output,error);if (ok) error.clear();return ok;}
bool StockSettingsReader::Curve8(std::string_view c,std::string_view k,std::string_view n,PointGraph<8>& output,std::string& error) const
{const auto ok=ReadCurve(data_,c,k,n,output,error);if (ok) error.clear();return ok;}
bool StockSettingsReader::Curve8Layout20(std::string_view c,std::string_view k,std::string_view n,PointGraph<8>& output,std::string& error) const
{const auto ok=ReadCurve(data_,c,k,n,output,error,true);if (ok) error.clear();return ok;}
bool StockSettingsReader::Words(std::string_view c,std::string_view k,std::string_view n,std::size_t count,std::vector<std::uint32_t>& output,std::string& error) const
{
    const auto* field=ReadField(data_,c,k,n,error);if (!field) return false;
    std::vector<std::uint32_t> next(count);
    if (!field->is_text)
    {
        const std::uint32_t* words=nullptr;if (!field->Words(count,words)) {error="Expected "+std::to_string(count)+" big-endian words, found "+std::to_string(field->byte_count*2)+" bytes of hex";return false;}
        std::copy_n(words,count,next.begin());
    }
    else
    {
        std::string hex;for (std::size_t at=0;at<field->text.size();) {const auto space=Whitespace(field->text,at);if (space) at+=space;else hex+=field->text[at++];}
        if (hex.size()!=count*8||std::any_of(hex.begin(),hex.end(),[](unsigned char value) {return value>=128;})) {error="Expected "+std::to_string(count)+" big-endian words, found "+std::to_string(hex.size())+" bytes of hex";return false;}
        for (std::size_t i=0;i<count;++i)
        {
            std::uint32_t word=0;for (std::size_t j=0;j<8;++j) {const auto value=hex[i*8+j];const int digit=value>='0'&&value<='9'?value-'0':value>='a'&&value<='f'?value-'a'+10:value>='A'&&value<='F'?value-'A'+10:-1;if (digit<0) {error="Invalid collection payload: invalid digit found in string";return false;}word=(word<<4)|std::uint32_t(digit);}next[i]=word;
        }
    }
    output=std::move(next);error.clear();return true;
}
}

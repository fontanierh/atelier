#pragma once
#include "Settings.h"
#include "SimulationMath.h"
#include <algorithm>
#include <cstring>
namespace atelier::skate::detail
{
inline float SkeletonSettingFloat(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
// Original Collections lookup and primitive decoding used by the new skeleton
// pose/IK loaders. Structured fields deliberately retain every authored word.
class SkeletonSettingReader
{
    const SettingsDatabase& data;std::string& error;
    const SettingValue* Field(std::string_view category,std::string_view name)
    {
        if(!error.empty())return nullptr;if(const auto* value=data.Field(category,"default",name))return value;
        std::string current="default";const auto category_id=NameId(category);
        for(std::size_t hop=0;hop<=data.Records().size();++hop)
        {
            const auto id=NameId(current);const auto found=std::find_if(data.Records().begin(),data.Records().end(),[&](const SettingRecord& r){return r.category_id==category_id&&r.key_id==id;});
            if(found==data.Records().end()){error="Missing stock collection "+std::string(category)+"/"+current;return nullptr;}
            if(found->parent.empty()){error="Missing stock field "+std::string(category)+"/default/"+std::string(name);return nullptr;}current=found->parent;
        }
        error="Cyclic stock collection inheritance "+std::string(category)+"/default";return nullptr;
    }
public:
    SkeletonSettingReader(const SettingsDatabase& d,std::string& e):data(d),error(e){}
    template<std::size_t N>std::array<std::uint32_t,N> Words(std::string_view category,std::string_view name)
    {
        std::array<std::uint32_t,N> result{};const auto* value=Field(category,name);if(!value)return result;const std::uint32_t* words=nullptr;
        if(!value->Words(N,words)){error="Expected "+std::to_string(N)+" big-endian words, found "+std::to_string(value->byte_count*2)+" bytes of hex";return result;}
        std::copy_n(words,N,result.begin());return result;
    }
    float Scalar(std::string_view category,std::string_view name)
    {
        const auto* value=Field(category,name);if(!value)return 0.0f;
        if(value->type!="EA::Reflection::Float"){error="Expected float at "+std::string(category)+"/default/"+std::string(name);return 0.0f;}
        const auto word=Words<1>(category,name);if(!error.empty())return 0.0f;const float result=SkeletonSettingFloat(word[0]);
        if(!std::isfinite(result)){error="Non-finite stock float "+std::string(category)+"/default/"+std::string(name);return 0.0f;}return result;
    }
    std::uint32_t Integer(std::string_view category,std::string_view name)
    {
        const auto* value=Field(category,name);if(!value)return 0;
        if(value->type!="EA::Reflection::Int32"&&value->type!="EA::Reflection::UInt32"){error="Expected integer at "+std::string(category)+"/default/"+std::string(name);return 0;}
        return Words<1>(category,name)[0];
    }
    Vec4 Vector(std::string_view category,std::string_view name){const auto words=Words<4>(category,name);Vec4 v;for(unsigned i=0;i<4;++i)v[i]=SkeletonSettingFloat(words[i]);return v;}
    template<std::size_t N>PointGraph<N> NegativeGraph(std::string_view category,std::string_view name)
    {
        const auto words=Words<4+2*N>(category,name);PointGraph<N> g;for(unsigned i=0;i<N;++i){g.x[i]=SkeletonSettingFloat(words[4+i]);g.y[i]=SkeletonSettingFloat(words[4+N+i]);}return g;
    }
};
}

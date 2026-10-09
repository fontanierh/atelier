#include "AnimationMetadata.h"
#include "DataReader.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#include <utility>

namespace atelier::skate
{
namespace
{
std::uint64_t Wide(detail::DataReader& r) { const auto lo=r.Word(), hi=r.Word(); return lo|(std::uint64_t(hi)<<32); }
float Float(std::uint32_t bits) { float value; std::memcpy(&value,&bits,4); return value; }
bool Finite(std::uint32_t bits) { return std::isfinite(Float(bits)); }
std::string Upper(std::string_view text)
{
    std::string value(text);
    for (auto& c:value) if (c>='a' && c<='z') c=char(c-'a'+'A');
    return value;
}
bool Name(std::string_view text,std::size_t length)
{
    if (text.empty() || text.size()>length) return false;
    for (const auto c:text) if (!((c>='A'&&c<='Z') || (c>='0'&&c<='9') || c=='_')) return false;
    return true;
}
bool Count(detail::DataReader& r,std::uint32_t& count,std::size_t minimum)
{
    count=r.Word(); if (!r.ok || count>r.Remaining()/minimum) { r.ok=false; return false; } return true;
}
std::vector<std::uint32_t> Words(detail::DataReader& r)
{
    std::uint32_t count; std::vector<std::uint32_t> values;
    if (!Count(r,count,4)) return values;
    values.reserve(count); for (std::uint32_t i=0;i<count;++i) values.push_back(r.Word()); return values;
}
std::vector<std::string> Names(detail::DataReader& r)
{
    std::uint32_t count; std::vector<std::string> values;
    if (!Count(r,count,4)) return values;
    values.reserve(count); for (std::uint32_t i=0;i<count;++i) values.push_back(r.String()); return values;
}
std::vector<std::vector<std::uint32_t>> Matrix(detail::DataReader& r)
{
    std::uint32_t count; std::vector<std::vector<std::uint32_t>> values;
    if (!Count(r,count,4)) return values;
    values.reserve(count); for (std::uint32_t i=0;i<count;++i) values.push_back(Words(r)); return values;
}
bool NamesValid(const std::vector<std::string>& values,std::size_t length)
{ for (const auto& value:values) if (!Name(value,length)) return false; return true; }
template<class T> void Append(std::vector<T>& to,const std::vector<T>& from) { to.insert(to.end(),from.begin(),from.end()); }
}

bool AnimationMetadata::Load(const std::vector<std::uint8_t>& bytes,std::string& error)
{
    auto fail=[&]() { error="Invalid native animation metadata"; return false; };
    if (bytes.size()<8 || std::memcmp(bytes.data(),"ATMETA01",8)!=0) return fail();
    detail::DataReader r{bytes}; AnimationMetadata result;
    result.source_bank=r.String(); result.source_sha256=r.String(); const auto source_bytes=Wide(r);
    if (!r.ok || result.source_bank.empty() || result.source_sha256.size()!=64 || source_bytes<48) return fail();
    for (const auto c:result.source_sha256)
        if (!((c>='0'&&c<='9')||(c>='a'&&c<='f')||(c>='A'&&c<='F'))) return fail();
    result.sources_.push_back({result.source_bank,result.source_sha256,source_bytes});
    auto identity=[&](const auto& value) { return Name(value.name,36) && value.source_offset<source_bytes; };
    std::uint32_t count;
    if (!Count(r,count,32)) return fail();
    for (std::uint32_t i=0;i<count;++i)
    {
        ClipMetadata c; c.name=r.String(); c.source_offset=Wide(r); c.fps_bits=r.Word(); c.frames_bits=r.Word();
        c.base_speed_bits=r.Word(); c.flags_word=r.Word(); std::uint32_t attributes;
        if (!identity(c) || !Finite(c.fps_bits) || !(Float(c.fps_bits)>0) || !Finite(c.frames_bits) ||
            !(Float(c.frames_bits)>=1) || !Finite(c.base_speed_bits) || !(Float(c.base_speed_bits)>0) || !Count(r,attributes,28)) return fail();
        auto previous=c.source_offset;
        for (std::uint32_t a=0;a<attributes;++a)
        {
            ClipAttributeMetadata value; value.name=r.String(); const auto kind=r.Word(); value.type_id=std::uint8_t(kind);
            value.begin_bits=r.Word(); value.end_bits=r.Word(); value.source_offset=Wide(r); value.payload_words=Words(r);
            const std::size_t minimum=kind==0?1:kind==1?4:kind==3?6:0;
            if (!r.ok || kind>255 || !Name(value.name,30) || !Finite(value.begin_bits) || !Finite(value.end_bits) ||
                value.source_offset<=previous || value.source_offset>=source_bytes || value.payload_words.size()<minimum) return fail();
            previous=value.source_offset; c.attributes.push_back(std::move(value));
        }
        result.clips.push_back(std::move(c));
    }
    if (!Count(r,count,20)) return fail();
    for (std::uint32_t i=0;i<count;++i)
    {
        PhaseBlendMetadata t; t.name=r.String(); t.source_offset=Wide(r); t.parameter=r.String(); t.children=Names(r);
        if (!r.ok || !identity(t) || !Name(t.parameter,30) || t.children.size()<2 || !NamesValid(t.children,36)) return fail();
        result.phase_blends.push_back(std::move(t));
    }
    if (!Count(r,count,24)) return fail();
    for (std::uint32_t i=0;i<count;++i)
    {
        BlendSpaceMetadata t; t.name=r.String(); t.source_offset=Wide(r); t.parameters=Names(r); t.children=Names(r);
        const auto d=t.parameters.size(); std::uint32_t simplexes;
        if (!r.ok || !identity(t) || d==0 || d>4 || t.children.size()<d+1 || !NamesValid(t.parameters,30) ||
            !NamesValid(t.children,36) || !Count(r,simplexes,16) || simplexes==0) return fail();
        for (std::uint32_t j=0;j<simplexes;++j)
        {
            BlendSimplexMetadata s; s.children=Words(r); s.vertex_bits=Matrix(r); s.normal_bits=Matrix(r); s.scale_bits=Words(r);
            if (!r.ok || s.children.size()!=d+1 || s.vertex_bits.size()!=d+1 || s.normal_bits.size()!=d+1 || s.scale_bits.size()!=d+1) return fail();
            for (auto index:s.children) if (index>=t.children.size()) return fail();
            for (const auto* matrix:{&s.vertex_bits,&s.normal_bits})
                for (const auto& row:*matrix) { if (row.size()!=d) return fail(); for (auto v:row) if (!Finite(v)) return fail(); }
            for (auto v:s.scale_bits) if (!Finite(v)) return fail();
            t.simplexes.push_back(std::move(s));
        }
        result.blend_spaces.push_back(std::move(t));
    }
    if (!Count(r,count,28)) return fail();
    for (std::uint32_t i=0;i<count;++i)
    {
        SelectorMetadata t; t.name=r.String(); t.source_offset=Wide(r); t.parameter=r.String(); t.default_child=r.String();
        t.children=Names(r); t.values=Names(r);
        if (!r.ok || !identity(t) || !Name(t.parameter,30) || !Name(t.default_child,36) || t.children.size()!=t.values.size() ||
            !NamesValid(t.children,36) || !NamesValid(t.values,30)) return fail();
        result.selectors.push_back(std::move(t));
    }
    if (!Count(r,count,20)) return fail();
    for (std::uint32_t i=0;i<count;++i)
    {
        SelectionSpaceMetadata t; t.name=r.String(); t.source_offset=Wide(r); std::uint32_t parameters,candidates;
        if (!identity(t) || !Count(r,parameters,20) || parameters>10) return fail();
        for (std::uint32_t j=0;j<parameters;++j)
        {
            SelectionParameterMetadata p; p.name=r.String(); p.mode=r.Word(); p.weight_bits=r.Word(); p.minimum_bits=r.Word(); p.maximum_bits=r.Word();
            if (!r.ok || !Name(p.name,30) || !Finite(p.weight_bits) || !Finite(p.minimum_bits) || !Finite(p.maximum_bits)) return fail();
            t.parameters.push_back(std::move(p));
        }
        if (!Count(r,candidates,8) || candidates==0) return fail();
        for (std::uint32_t j=0;j<candidates;++j)
        {
            SelectionCandidateMetadata c; c.child=r.String(); c.value_bits=Words(r);
            if (!r.ok || !Name(c.child,36) || c.value_bits.size()!=parameters) return fail();
            for (auto v:c.value_bits) if (!Finite(v)) return fail();
            t.candidates.push_back(std::move(c));
        }
        result.selection_spaces.push_back(std::move(t));
    }
    if (!Count(r,count,16)) return fail();
    for (std::uint32_t i=0;i<count;++i)
    {
        UnsupportedAnimationTree t; t.name=r.String(); t.source_offset=Wide(r); t.type_id=r.Word();
        if (!r.ok || !identity(t)) return fail(); result.unsupported_trees.push_back(std::move(t));
    }
    if (!r.ok || r.Remaining()!=0) return fail();
    auto index=[&](const auto& values) { for (const auto& value:values) result.origins_[value.name]=0; };
    index(result.clips); index(result.phase_blends); index(result.blend_spaces); index(result.selectors);
    index(result.selection_spaces); index(result.unsupported_trees);
    *this=std::move(result); error.clear(); return true;
}
bool AnimationMetadata::Merge(const AnimationMetadata& other,std::string& error)
{
    for (const auto& item:other.origins_) if (origins_.count(item.first)) { error="Animation bank merge collides at "+item.first; return false; }
    const auto base=sources_.size();
    for (const auto& item:other.origins_) origins_[item.first]=base+item.second;
    Append(sources_,other.sources_); Append(clips,other.clips); Append(phase_blends,other.phase_blends); Append(blend_spaces,other.blend_spaces);
    Append(selectors,other.selectors); Append(selection_spaces,other.selection_spaces); Append(unsupported_trees,other.unsupported_trees);
    error.clear(); return true;
}
const AnimationBankSource* AnimationMetadata::SourceFor(std::string_view name) const
{ const auto found=origins_.find(Upper(name)); return found==origins_.end()?nullptr:&sources_[found->second]; }
const ClipMetadata* AnimationMetadata::Clip(std::string_view text,std::string& error) const
{
    const auto name=Upper(text); if (!Name(name,36)) { error="Invalid canonical FastString name \""+name+"\""; return nullptr; }
    const ClipMetadata* result=nullptr;
    for (const auto& c:clips) if (c.name==name && (!result || c.source_offset>=result->source_offset)) result=&c;
    if (!result) error="Missing direct clip "+name; else error.clear(); return result;
}
bool AnimationMetadata::Tree(std::string_view text,AnimationTreeMetadata& output,std::string& error) const
{
    const auto name=Upper(text); if (!Name(name,36)) { error="Invalid canonical FastString name \""+name+"\""; return false; }
    std::uint64_t last=0; bool any=false;
    auto offsets=[&](const auto& values) { for (const auto& v:values) if (v.name==name) { last=any?std::max(last,v.source_offset):v.source_offset; any=true; } };
    offsets(clips); offsets(phase_blends); offsets(blend_spaces); offsets(selectors); offsets(selection_spaces); offsets(unsupported_trees);
    if (!any) { error="Missing animation "+name+" in "+source_bank; return false; }
    output={}; error.clear();
    for (const auto& c:clips) if (c.name==name && c.source_offset==last) { output.kind=AnimationTreeKind::Clip; output.clip=&c; return true; }
    for (const auto& t:phase_blends) if (t.name==name && t.source_offset==last) { output.kind=AnimationTreeKind::PhaseBlend; output.phase_blend=&t; return true; }
    for (const auto& t:blend_spaces) if (t.name==name && t.source_offset==last) { output.kind=AnimationTreeKind::BlendSpace; output.blend_space=&t; return true; }
    for (const auto& t:selectors) if (t.name==name && t.source_offset==last) { output.kind=AnimationTreeKind::Selector; output.selector=&t; return true; }
    for (const auto& t:selection_spaces) if (t.name==name && t.source_offset==last) { output.kind=AnimationTreeKind::SelectionSpace; output.selection_space=&t; return true; }
    for (const auto& t:unsupported_trees) if (t.name==name && t.source_offset==last)
    { error="Animation "+name+" is tree type "+std::to_string(t.type_id)+"; tree evaluation is required"; return false; }
    return false;
}
bool AnimationMetadata::InitializeBank(AnimationBankSource source,std::string& error)
{
    auto fail=[&](){error="Invalid typed animation metadata";return false;};
    if(source.source_bank.empty()||source.source_sha256.size()!=64||source.source_bytes<48)return fail();
    for(char c:source.source_sha256)if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')||(c>='A'&&c<='F')))return fail();
    auto identity=[&](const auto& v){return Name(v.name,36)&&v.source_offset<source.source_bytes;};
    for(const auto& c:clips)
    {
        if(!identity(c)||!Finite(c.fps_bits)||Float(c.fps_bits)<=0||!Finite(c.frames_bits)||Float(c.frames_bits)<1
            ||!Finite(c.base_speed_bits)||Float(c.base_speed_bits)<=0)return fail();
        auto previous=c.source_offset;
        for(const auto& a:c.attributes)
        {
            const std::size_t minimum=a.type_id==0?1:a.type_id==1?4:a.type_id==3?6:0;
            if(!Name(a.name,30)||!Finite(a.begin_bits)||!Finite(a.end_bits)||a.source_offset<=previous
                ||a.source_offset>=source.source_bytes||a.payload_words.size()<minimum)return fail();
            previous=a.source_offset;
        }
    }
    for(const auto& t:phase_blends)
        if(!identity(t)||!Name(t.parameter,30)||t.children.size()<2||!NamesValid(t.children,36))return fail();
    for(const auto& t:blend_spaces)
    {
        const auto d=t.parameters.size();
        if(!identity(t)||d==0||d>4||t.children.size()<d+1||!NamesValid(t.parameters,30)
            ||!NamesValid(t.children,36)||t.simplexes.empty())return fail();
        for(const auto& s:t.simplexes)
        {
            if(s.children.size()!=d+1||s.vertex_bits.size()!=d+1||s.normal_bits.size()!=d+1||s.scale_bits.size()!=d+1)return fail();
            for(auto i:s.children)if(i>=t.children.size())return fail();
            for(const auto* m:{&s.vertex_bits,&s.normal_bits})for(const auto& row:*m)
            {if(row.size()!=d)return fail();for(auto v:row)if(!Finite(v))return fail();}
            for(auto v:s.scale_bits)if(!Finite(v))return fail();
        }
    }
    for(const auto& t:selectors)
        if(!identity(t)||!Name(t.parameter,30)||!Name(t.default_child,36)||t.children.size()!=t.values.size()
            ||!NamesValid(t.children,36)||!NamesValid(t.values,30))return fail();
    for(const auto& t:selection_spaces)
    {
        if(!identity(t)||t.parameters.size()>10||t.candidates.empty())return fail();
        for(const auto& p:t.parameters)
            if(!Name(p.name,30)||!Finite(p.weight_bits)||!Finite(p.minimum_bits)||!Finite(p.maximum_bits))return fail();
        for(const auto& c:t.candidates)
        {
            if(!Name(c.child,36)||c.value_bits.size()!=t.parameters.size())return fail();
            for(auto v:c.value_bits)if(!Finite(v))return fail();
        }
    }
    for(const auto& t:unsupported_trees)if(!identity(t))return fail();
    source_bank=source.source_bank;source_sha256=source.source_sha256;sources_={std::move(source)};origins_.clear();
    auto index=[&](const auto& values){for(const auto& v:values)origins_[v.name]=0;};
    index(clips);index(phase_blends);index(blend_spaces);index(selectors);index(selection_spaces);index(unsupported_trees);
    error.clear();return true;
}

}

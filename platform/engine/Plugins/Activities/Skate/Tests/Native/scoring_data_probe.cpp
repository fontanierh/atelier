// SPDX-License-Identifier: Apache-2.0
#include "ScoringData.h"
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace {
struct Output
{
    std::vector<std::uint32_t> words;
    void Word(std::uint32_t value){words.push_back(value);}
    void Float(float value){std::uint32_t word;std::memcpy(&word,&value,4);Word(word);}
    void String(std::string_view value){Word(std::uint32_t(value.size()));for(std::size_t i=0;i<value.size();i+=4){std::uint32_t w=0;for(std::size_t j=0;j<4&&i+j<value.size();++j)w|=std::uint32_t(static_cast<unsigned char>(value[i+j]))<<(8*j);Word(w);}}
    void Status(bool okay,const std::string& error){Word(okay);if(!okay)String(error);}
    void Graph(const PointGraph<8>& graph){for(auto v:graph.x)Float(v);for(auto v:graph.y)Float(v);}
    void Snapshot(const ScoringData& data)
    {
        const auto start=words.size();Word(0);Word(std::uint32_t(data.definitions.size()));
        for(const auto& d:data.definitions){Word(std::uint32_t(d.metadata.id));Word(d.metadata.category);Word(std::uint32_t(d.metadata.score_type));String(d.identifier);for(auto w:d.encoded_name)Word(w);Word(std::uint32_t(d.points));String(d.label);Word(d.trick_type);Float(d.completion_delay);Word(std::uint32_t(d.variant));Word(d.flags);}
        Word(std::uint32_t(data.collector.scalars.size()));for(const auto& entry:data.collector.scalars){Word(entry.first);Float(entry.second);}
        Word(std::uint32_t(data.collector.curves.size()));for(const auto& entry:data.collector.curves){Word(entry.first);Graph(entry.second);}
        Graph(data.repetition);Graph(data.announcement);
        for(auto f:{data.line_drain,data.line_capacity,data.combo_drain,data.combo_capacity})Float(f);
        for(auto pair:data.combo_levels){Float(pair.first);Float(pair.second);}
        for(auto f:{data.combo_refresh_threshold,data.unannounced_factor,data.bail_factor,data.sketchy_side_speed})Float(f);
        const auto rules=data.SessionRules();Float(rules.combo_capacity);for(auto pair:rules.combo_levels){Float(pair.first);Float(pair.second);}for(auto f:{rules.combo_refresh_threshold,rules.line_capacity,rules.bail_factor})Float(f);
        for(std::size_t id=0;id<ScoringCatalog.size();++id){const auto* a=data.ById(id);const auto* b=data.ByName(EncodeAnimationName(ScoringCatalog[id].identifier));Word(a?std::uint32_t(a->metadata.id):0xffffffff);Word(b?std::uint32_t(b->metadata.id):0xffffffff);}
        Word(data.ById(ScorableCount)?1:0);Word(data.ByName(EncodeAnimationName("missing native scorable"))?1:0);
        constexpr std::array<std::uint32_t,18> inputs={0,0x80000000,1,0x80000001,0x3f800000,0xbf800000,0x3eaaaaab,0x41200000,0x42c80000,0x447a0000,0xc47a0000,0x7f7fffff,0xff7fffff,0x7f800000,0xff800000,0x7fc12345,0xffc23456,0x7f812345};
        for(auto w:inputs){float x;std::memcpy(&x,&w,4);for(const auto& entry:data.collector.scalars)Float(data.collector.Scalar(entry.first));for(const auto& entry:data.collector.curves)Float(data.collector.Curve(entry.first,x));Float(data.repetition.Evaluate(x));Float(data.announcement.Evaluate(x));}
        words[start]=std::uint32_t(words.size()-start-1);
    }
    void Catalog(){Word(std::uint32_t(ScoringCatalog.size()));for(std::size_t i=0;i<ScoringCatalog.size();++i){const auto& d=ScoringCatalog[i];String(d.identifier);Word(d.category);Word(std::uint32_t(d.score_type));Word(std::uint32_t(ScoringConversionLinks[i].first));Word(std::uint32_t(ScoringConversionLinks[i].second));}Word(std::uint32_t(ScoringCollectorFields.size()));for(const auto& f:ScoringCollectorFields){Word(f.offset);String(f.name);Word(std::uint32_t(f.byte_count));}}
};
std::vector<std::uint8_t> Read(const char* path){std::ifstream file(path,std::ios::binary);return {std::istreambuf_iterator<char>(file),{}};}
}
int main(int argc,char** argv)
{
    if(argc!=3)return 2;SettingsDatabase stock,variant;std::string error;
    if(!stock.Load(Read(argv[1]),error)||!variant.Load(Read(argv[2]),error)){std::cerr<<error;return 2;}
    ScoringData data;if(!data.Load(stock,error)){std::cerr<<error;return 2;}
    Output out;out.Catalog();out.Snapshot(data);
    for(unsigned attempt=0;attempt<2;++attempt){const bool okay=data.Load(variant,error);out.Status(okay,error);out.Snapshot(data);}
    const bool okay=data.Load(stock,error);out.Status(okay,error);out.Snapshot(data);
    for(auto word:out.words)for(unsigned b=0;b<4;++b)std::cout.put(char(word>>(8*b)));
    return std::cout?0:2;
}

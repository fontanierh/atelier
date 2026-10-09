#include "AnimationMetadata.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
static void Word(std::ostream& out,std::uint32_t value) { for (unsigned i=0;i<4;++i) out.put(char(value>>(8*i))); }
static void Wide(std::ostream& out,std::uint64_t value) { Word(out,std::uint32_t(value));Word(out,std::uint32_t(value>>32)); }
static void String(std::ostream& out,std::string_view value) { Word(out,std::uint32_t(value.size()));out.write(value.data(),value.size()); }
template<class T> static void Words(std::ostream& out,const T& values) { Word(out,std::uint32_t(values.size()));for (auto v:values) Word(out,v); }
template<class T> static void Strings(std::ostream& out,const T& values) { Word(out,std::uint32_t(values.size()));for (const auto& v:values) String(out,v); }
template<class T> static void Matrix(std::ostream& out,const T& values) { Word(out,std::uint32_t(values.size()));for (const auto& v:values) Words(out,v); }
template<class T> static void Identity(std::ostream& out,const T& value) { String(out,value.name);Wide(out,value.source_offset); }
static std::vector<std::uint8_t> Read(const std::string& path) { std::ifstream file(path,std::ios::binary);return {std::istreambuf_iterator<char>(file),{}}; }
static void Dump(std::ostream& out,const AnimationMetadata& m)
{
    out.write("ATMETA01",8);String(out,m.source_bank);String(out,m.source_sha256);Wide(out,m.Sources()[0].source_bytes);
    Word(out,std::uint32_t(m.clips.size()));
    for (const auto& c:m.clips)
    {
        Identity(out,c);Word(out,c.fps_bits);Word(out,c.frames_bits);Word(out,c.base_speed_bits);Word(out,c.flags_word);Word(out,std::uint32_t(c.attributes.size()));
        for (const auto& a:c.attributes) { String(out,a.name);Word(out,a.type_id);Word(out,a.begin_bits);Word(out,a.end_bits);Wide(out,a.source_offset);Words(out,a.payload_words); }
    }
    Word(out,std::uint32_t(m.phase_blends.size()));for (const auto& t:m.phase_blends) {Identity(out,t);String(out,t.parameter);Strings(out,t.children);}
    Word(out,std::uint32_t(m.blend_spaces.size()));for (const auto& t:m.blend_spaces)
    {
        Identity(out,t);Strings(out,t.parameters);Strings(out,t.children);Word(out,std::uint32_t(t.simplexes.size()));
        for (const auto& s:t.simplexes) {Words(out,s.children);Matrix(out,s.vertex_bits);Matrix(out,s.normal_bits);Words(out,s.scale_bits);}
    }
    Word(out,std::uint32_t(m.selectors.size()));for (const auto& t:m.selectors) {Identity(out,t);String(out,t.parameter);String(out,t.default_child);Strings(out,t.children);Strings(out,t.values);}
    Word(out,std::uint32_t(m.selection_spaces.size()));for (const auto& t:m.selection_spaces)
    {
        Identity(out,t);Word(out,std::uint32_t(t.parameters.size()));for (const auto& p:t.parameters) {String(out,p.name);Word(out,p.mode);Word(out,p.weight_bits);Word(out,p.minimum_bits);Word(out,p.maximum_bits);}
        Word(out,std::uint32_t(t.candidates.size()));for (const auto& c:t.candidates) {String(out,c.child);Words(out,c.value_bits);}
    }
    Word(out,std::uint32_t(m.unsupported_trees.size()));for (const auto& t:m.unsupported_trees) {Identity(out,t);Word(out,t.type_id);}
}
static void Query(const AnimationMetadata& metadata,const std::string& path)
{
    std::ifstream names(path);std::string name,error;
    while (std::getline(names,name))
    {
        if (const auto c=metadata.Clip(name,error)) {Word(std::cout,1);Wide(std::cout,c->source_offset);Word(std::cout,c->flags_word);} else Word(std::cout,0);
        AnimationTreeMetadata t;
        if (metadata.Tree(name,t,error))
        {
            Word(std::cout,std::uint32_t(t.kind));std::uint64_t offset=0;
            if (t.clip) offset=t.clip->source_offset;if (t.phase_blend) offset=t.phase_blend->source_offset;
            if (t.blend_space) offset=t.blend_space->source_offset;if (t.selector) offset=t.selector->source_offset;
            if (t.selection_space) offset=t.selection_space->source_offset;Wide(std::cout,offset);
        } else {Word(std::cout,0);String(std::cout,error);}
        if (const auto source=metadata.SourceFor(name)) {Word(std::cout,1);String(std::cout,source->source_bank);String(std::cout,source->source_sha256);Wide(std::cout,source->source_bytes);} else Word(std::cout,0);
    }
}
int main(int argc,char** argv)
{
    if (argc<3) return 1;const std::string mode=argv[1];AnimationMetadata metadata;std::string error;
    if (!metadata.Load(Read(argv[2]),error)) {std::cerr<<error<<'\n';return 2;}
    if (mode=="dump") {Dump(std::cout,metadata);return 0;}
    if (mode=="query" && argc==4) {Query(metadata,argv[3]);return 0;}
    if (mode=="merge" && argc==5)
    {
        AnimationMetadata other;if (!other.Load(Read(argv[3]),error)) return 2;
        if (!metadata.Merge(other,error)) {std::cout<<error<<'\n';return 0;}Query(metadata,argv[4]);return 0;
    }
    return 1;
}

#include "ContactRetention.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <iterator>
#include <vector>
using namespace atelier::skate;
namespace
{
[[noreturn]] void Fail(const char* message) {std::cerr<<message<<'\n';std::exit(2);}
struct Reader
{
    std::vector<std::uint8_t> bytes;std::size_t at=0;
    std::uint32_t Word() {if (bytes.size()-at<4) Fail("Truncated retention input");std::uint32_t v=0;for (unsigned i=0;i<4;++i) v|=std::uint32_t(bytes[at++])<<(8*i);return v;}
    float Scalar() {const auto bits=Word();float v;std::memcpy(&v,&bits,4);return v;}
    Vec3 Vector() {return {Scalar(),Scalar(),Scalar()};}
    template<std::size_t N> std::array<std::uint32_t,N> Words() {std::array<std::uint32_t,N> v;for (auto& x:v) x=Word();return v;}
    ContactMaterial Material() {return {Scalar(),Scalar(),Scalar()};}
};
struct Writer
{
    std::vector<std::uint32_t> words;
    void Word(std::uint32_t v) {words.push_back(v);}
    void Scalar(float v) {std::uint32_t bits;std::memcpy(&bits,&v,4);Word(bits);}
    template<std::size_t N> void Words(const std::array<std::uint32_t,N>& v) {words.insert(words.end(),v.begin(),v.end());}
    void State(const ContactBuffer& b)
    {Word(b.count);Word(b.flushed);Word(b.capacity);Word(b.dropped);Scalar(b.distance_squared_threshold);Word(b.allow_flush);Word(b.deferred_reduction);Word(b.full);}
};
void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) std::cout.put(static_cast<char>(v>>(8*i)));}
}
int main()
{
    Reader reader;reader.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});const auto cases=reader.Word();
    for (std::uint32_t index=0;index<cases;++index)
    {
        const auto op=reader.Word();Writer out;
        if (op==0)
        {const auto a=reader.Words<64>(),b=reader.Words<64>();out.Word(CoplanarContacts(a,b));}
        else if (op==1)
        {
            const auto count=reader.Word();std::vector<Vec3> a,b;for (std::uint32_t i=0;i<count;++i) a.push_back(reader.Vector());for (std::uint32_t i=0;i<count;++i) b.push_back(reader.Vector());
            const auto normal=reader.Vector();auto selected=reader.Words<4>();out.Word(static_cast<std::uint32_t>(SelectContactPoints(a.data(),b.data(),a.size(),normal,selected)));out.Words(selected);
        }
        else if (op==2)
        {
            ContactBuffer buffer;buffer.count=reader.Word();buffer.flushed=reader.Word();buffer.capacity=reader.Word();buffer.dropped=reader.Word();buffer.distance_squared_threshold=reader.Scalar();
            buffer.allow_flush=static_cast<std::uint8_t>(reader.Word());buffer.deferred_reduction=static_cast<std::uint8_t>(reader.Word());buffer.full=static_cast<std::uint8_t>(reader.Word());
            for (auto& row:buffer.records) row=reader.Words<64>();std::vector<std::vector<ContactRecord>> chunks;
            ContactSink sink=[&](const ContactRecord* rows,std::size_t n){chunks.emplace_back(rows,rows+n);};
            const auto count=reader.Word();out.Word(count);
            for (std::uint32_t i=0;i<count;++i)
            {
                const auto command=reader.Word();std::optional<std::size_t> slot;bool duplicate=false;
                if (command==0)
                {
                    const auto row=reader.Words<64>();const bool test=reader.Word()!=0;slot=buffer.Allocate(sink);
                    if (slot) {buffer.records[*slot]=row;if (test && buffer.LastIsDuplicate()) {duplicate=true;--buffer.count;}}
                }
                else if (command==1) buffer.Reduce();
                else if (command==2) buffer.Flush(sink);
                else Fail("Invalid retention command");
                out.Word(command);out.Word(slot.has_value());out.Word(slot ? static_cast<std::uint32_t>(*slot):0xffffffffu);out.Word(duplicate);out.State(buffer);
            }
            out.State(buffer);for (const auto& row:buffer.records) out.Words(row);
            out.Word(static_cast<std::uint32_t>(chunks.size()));for (const auto& chunk:chunks) {out.Word(static_cast<std::uint32_t>(chunk.size()));for (const auto& row:chunk) out.Words(row);}
        }
        else if (op==3)
        {const auto a=reader.Material(),b=reader.Material();const auto material=CombineContactMaterials(a,b);out.Scalar(material.static_friction);out.Scalar(material.dynamic_friction);out.Scalar(material.restitution);}
        else Fail("Invalid retention operation");
        Word(index);Word(op);Word(static_cast<std::uint32_t>(out.words.size()));for (auto v:out.words) Word(v);
    }
    if (reader.at!=reader.bytes.size()) Fail("Trailing retention input");
}

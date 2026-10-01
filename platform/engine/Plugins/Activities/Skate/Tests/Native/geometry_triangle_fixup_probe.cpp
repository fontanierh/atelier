// SPDX-License-Identifier: Apache-2.0
#include "GeometryTriangleFixup.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <iterator>
#include <vector>
using namespace atelier::skate;
namespace
{
[[noreturn]] void Fail(const char* message) { std::cerr<<message<<'\n';std::exit(2); }
struct Reader
{
    std::vector<std::uint8_t> bytes;std::size_t at=0;
    std::uint32_t Word() {if (bytes.size()-at<4) Fail("Truncated fixup input");std::uint32_t word=0;for (unsigned i=0;i<4;++i) word|=std::uint32_t(bytes[at++])<<(8*i);return word;}
    float Scalar() {const auto word=Word();float v;std::memcpy(&v,&word,4);return v;}
    Vec3 Vector() {const float x=Scalar(),y=Scalar(),z=Scalar();return {x,y,z};}
    TriangleFeature Feature()
    {
        TriangleFeature t;t.normal=Vector();for (auto& e:t.edges) e=Vector();t.flags=Word();for (auto& c:t.edge_cosines) c=Scalar();return t;
    }
};
void Word(std::uint32_t word) {for (unsigned i=0;i<4;++i) std::cout.put(static_cast<char>(word>>(8*i)));}
void Scalar(float v) {std::uint32_t word;std::memcpy(&word,&v,4);Word(word);}
void Vector(Vec3 v) {Scalar(v.x);Scalar(v.y);Scalar(v.z);}
}
int main()
{
    Reader reader;reader.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});const auto count=reader.Word();
    for (std::uint32_t index=0;index<count;++index)
    {
        const auto op=reader.Word();const auto feature=reader.Feature();auto normal=reader.Vector();Word(index);Word(op);
        if (op==0) Word(static_cast<std::uint32_t>(ClassifyTriangleFeature(feature,normal)));
        else if (op==1)
        {
            TriangleFixup settings;settings.reverse=reader.Word()!=0;settings.edge_cos_bend_normal_threshold=reader.Scalar();settings.convexity_epsilon=reader.Scalar();settings.is_object=reader.Word()!=0;
            const auto n=reader.Word();if (n>16) Fail("Invalid contact count");std::array<ContactPair,16> contacts;
            for (auto& pair:contacts) {pair.a=reader.Vector();pair.b=reader.Vector();}
            Word(FixUpTriangle(feature,normal,contacts.data(),n,settings));Vector(normal);
            for (auto pair:contacts) {Vector(pair.a);Vector(pair.b);}
        }
        else Fail("Invalid fixup operation");
    }
    if (reader.at!=reader.bytes.size()) Fail("Trailing fixup input");
}

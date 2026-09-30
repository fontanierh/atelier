// SPDX-License-Identifier: Apache-2.0
#include "WorldPrimitiveContact.h"
#include "WorldGeometry.h"
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
    std::uint32_t Word() {if (bytes.size()-at<4) Fail("Truncated primitive contact input");std::uint32_t v=0;for (unsigned i=0;i<4;++i) v|=std::uint32_t(bytes[at++])<<(8*i);return v;}
    float Scalar() {const auto bits=Word();float v;std::memcpy(&v,&bits,4);return v;}
    Vec3 Vector() {return {Scalar(),Scalar(),Scalar()};}
    Basis3 Basis() {Basis3 basis;for (auto& column:basis.columns) for (float& v:column) v=Scalar();return basis;}
    AffineTransform Transform() {return {Basis(),Vector()};}
    Triangle ReadTriangle(bool transformed)
    {
        const std::array<Vec3,3> v={Vector(),Vector(),Vector()};const float fat=Scalar();const std::array<float,3> cos={Scalar(),Scalar(),Scalar()};const auto flags=Word();
        if (transformed) return TransformTriangleVolume(v,fat,cos,flags,Transform());
        return TriangleFromVolume(v,fat,cos,flags);
    }
    ContactPrimitive Primitive()
    {
        switch (Word())
        {
        case 0:return Sphere{Vector(),Scalar()};
        case 1:return Capsule{Vector(),Vector(),Scalar(),Scalar()};
        case 2:return ReadTriangle(true);
        case 3:return RoundedBox{Vector(),Basis(),Vector(),Scalar()};
        default:Fail("Invalid contact primitive");
        }
    }
    WorldContactSettings Settings() {return {Scalar(),Scalar(),Scalar(),Scalar(),Word()!=0};}
};
void Word(std::uint32_t word) {for (unsigned i=0;i<4;++i) std::cout.put(static_cast<char>(word>>(8*i)));}
void Scalar(float value) {std::uint32_t word;std::memcpy(&word,&value,4);Word(word);}
void Vector(Vec3 value) {Scalar(value.x);Scalar(value.y);Scalar(value.z);}
void WriteTriangle(const Triangle& t)
{
    for (auto v:t.vertices) Vector(v);Vector(t.feature.normal);for (auto e:t.feature.edges) Vector(e);Word(t.feature.flags);
    for (float c:t.feature.edge_cosines) Scalar(c);for (float length:t.edge_lengths) Scalar(length);Scalar(t.fatness);
}
}
int main()
{
    Reader reader;reader.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});const auto count=reader.Word();
    for (std::uint32_t index=0;index<count;++index)
    {
        const auto op=reader.Word();Word(index);Word(op);
        if (op==0)
        {
            const auto velocity=reader.Vector(),normal=reader.Vector();const float padding=reader.Scalar(),maximum=reader.Scalar();Scalar(WorldSeparationLimit(velocity,normal,padding,maximum));
        }
        else if (op==1) WriteTriangle(reader.ReadTriangle(true));
        else if (op==2)
        {
            const auto primitive=reader.Primitive();const auto triangle=reader.ReadTriangle(false);const auto velocity=reader.Vector();const auto settings=reader.Settings();
            const auto contact=PrimitiveTriangleWorldContacts(primitive,triangle,velocity,settings);Word(contact.has_value());
            const auto result=contact.value_or(PrimitiveContactManifold{});Vector(result.normal);Word(static_cast<std::uint32_t>(result.count));
            for (const auto& pair:result.points) {Vector(pair.a);Vector(pair.b);}
        }
        else Fail("Invalid primitive contact operation");
    }
    if (reader.at!=reader.bytes.size()) Fail("Trailing primitive contact input");
}

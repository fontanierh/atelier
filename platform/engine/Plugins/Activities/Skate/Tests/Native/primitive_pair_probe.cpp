// SPDX-License-Identifier: Apache-2.0
#include "GeometryPrimitivePair.h"
#include "WorldGeometry.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <iterator>
#include <vector>
using namespace atelier::skate;
namespace
{
[[noreturn]] void Fail(const char* message){std::cerr<<message<<'\n';std::exit(2);}
struct Reader
{
    std::vector<std::uint8_t> bytes;std::size_t at=0;
    std::uint32_t Word(){if(bytes.size()-at<4)Fail("Truncated primitive pair input");std::uint32_t v=0;for(unsigned i=0;i<4;++i)v|=std::uint32_t(bytes[at++])<<(8*i);return v;}
    float Scalar(){const auto word=Word();float v;std::memcpy(&v,&word,4);return v;}
    Vec3 Vector(){return {Scalar(),Scalar(),Scalar()};}
    Basis3 Basis(){Basis3 b;for(auto& c:b.columns)for(auto& v:c)v=Scalar();return b;}
    ContactPrimitive Primitive()
    {
        switch(Word())
        {
        case 0:return Sphere{Vector(),Scalar()};
        case 1:return Capsule{Vector(),Vector(),Scalar(),Scalar()};
        case 2:{const std::array<Vec3,3> vertices{{Vector(),Vector(),Vector()}};const float fat=Scalar();const std::array<float,3> cosines{{Scalar(),Scalar(),Scalar()}};const auto flags=Word();const AffineTransform frame{Basis(),Vector()};return TransformTriangleVolume(vertices,fat,cosines,flags,frame);}
        case 3:return RoundedBox{Vector(),Basis(),Vector(),Scalar()};
        default:Fail("Invalid primitive pair kind");
        }
    }
    PrimitivePairSettings Settings(){return {Scalar(),Scalar(),Scalar(),Scalar(),Scalar()};}
};
void Word(std::uint32_t word){for(unsigned i=0;i<4;++i)std::cout.put(static_cast<char>(word>>(8*i)));}
void Scalar(float v){std::uint32_t w;std::memcpy(&w,&v,4);Word(w);}
void Vector(Vec3 v){Scalar(v.x);Scalar(v.y);Scalar(v.z);}
}
int main()
{
    Reader i;i.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});const auto n=i.Word();
    for(std::uint32_t index=0;index<n;++index)
    {
        const auto op=i.Word();Word(index);Word(op);
        if(op==0){const auto s=PrimitivePairSettings::SkaterSelfCollision();for(float v:{s.padding_a,s.padding_b,s.additional_padding,s.edge_cos_bend_normal_threshold,s.convexity_epsilon})Scalar(v);}
        else if(op==1)
        {
            const auto a=i.Primitive(),b=i.Primitive();const auto s=i.Settings();const auto hit=PrimitivePairContacts(a,b,s);Word(hit.has_value());const auto result=hit.value_or(PrimitiveContactManifold{});Vector(result.normal);Word(static_cast<std::uint32_t>(result.count));for(const auto& p:result.points){Vector(p.a);Vector(p.b);}
        }
        else Fail("Invalid primitive pair operation");
    }
    if(i.at!=i.bytes.size())Fail("Trailing primitive pair input");
}

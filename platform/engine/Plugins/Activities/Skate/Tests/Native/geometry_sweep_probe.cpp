// SPDX-License-Identifier: Apache-2.0
#include "GeometrySweep.h"
#include <cstring>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>
using namespace atelier::skate;
namespace
{
struct Reader
{
    std::vector<std::uint8_t> bytes;
    std::size_t at=0;
    std::uint32_t Word()
    {
        if (bytes.size()-at<4) throw std::runtime_error("Truncated sweep input");
        std::uint32_t value=0;
        for (unsigned i=0;i<4;++i) value|=std::uint32_t(bytes[at++])<<(i*8);
        return value;
    }
    float Scalar() { const auto word=Word(); float value;std::memcpy(&value,&word,4);return value; }
    Vec3 Vector() { return {Scalar(),Scalar(),Scalar()}; }
};
void Word(std::uint32_t value) { for (unsigned i=0;i<4;++i) std::cout.put(static_cast<char>(value>>(i*8))); }
void Scalar(float value) { std::uint32_t word;std::memcpy(&word,&value,4);Word(word); }
void Vector(Vec3 value) { Scalar(value.x);Scalar(value.y);Scalar(value.z); }
}
int main()
{
    try
    {
        Reader reader;reader.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});
        const auto count=reader.Word();
        for (std::uint32_t index=0;index<count;++index)
        {
            TriangleLineHit result{reader.Vector(),reader.Vector(),reader.Scalar(),
                {reader.Scalar(),reader.Scalar(),reader.Scalar()}};
            const Vec3 start=reader.Vector(),direction=reader.Vector();
            const std::array<Vec3,3> vertices={reader.Vector(),reader.Vector(),reader.Vector()};
            const float line_radius=reader.Scalar(),triangle_fatness=reader.Scalar();
            const bool found=TriangleSegment(result,start,direction,vertices,line_radius,triangle_fatness);
            Word(index);Word(found);Vector(result.position);Vector(result.normal);Scalar(result.fraction);
            for (float lane:result.volume_parameter) Scalar(lane);
        }
        if (reader.at!=reader.bytes.size()) throw std::runtime_error("Trailing sweep input");
    }
    catch (const std::exception& error) { std::cerr<<error.what()<<'\n';return 2; }
}

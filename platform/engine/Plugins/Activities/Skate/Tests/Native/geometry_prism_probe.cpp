#include "GeometryPrism.h"
#include <cstdlib>
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
    std::uint32_t Word()
    {
        if (bytes.size()-at<4) Fail("Truncated prism input");
        std::uint32_t word=0;for (unsigned i=0;i<4;++i) word|=std::uint32_t(bytes[at++])<<(8*i);return word;
    }
    template<std::size_t N> std::array<std::uint32_t,N> Words()
    { std::array<std::uint32_t,N> words;for (auto& word:words) word=Word();return words; }
};
void Word(std::uint32_t word) { for (unsigned i=0;i<4;++i) std::cout.put(static_cast<char>(word>>(8*i))); }
template<std::size_t N> void Words(const std::array<std::uint32_t,N>& words) { for (auto word:words) Word(word); }
}
int main()
{
    Reader reader;reader.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});const auto count=reader.Word();
    for (std::uint32_t index=0;index<count;++index)
    {
        const auto op=reader.Word();Word(index);Word(op);
        if (op==0)
        {
            const auto segment=reader.Words<16>();auto point=reader.Words<4>();Word(ClosestFeatureSegment(segment,point));Words(point);
        }
        else if (op==2)
        {
            const auto face=reader.Words<144>();const auto normal=reader.Words<4>();auto point=reader.Words<4>();
            Word(ClampPointToFeature(face,normal,point));Words(point);
        }
        else if (op==3)
        {
            const auto face=reader.Words<144>(),segment=reader.Words<144>();const auto normal=reader.Words<4>();
            auto interval=reader.Words<2>();auto outside=reader.Words<8>();
            Word(ClipSegmentToFeature(face,segment,normal,interval,outside));Words(interval);Words(outside);
        }
        else
        {
            auto output=reader.Words<136>();auto a=reader.Words<144>(),b=reader.Words<144>();const auto normal=reader.Words<4>();
            std::uint32_t result=0;
            switch (op)
            {
            case 1:result=IntersectPointFace(output,a,b,normal,reader.Word()!=0);break;
            case 4:result=IntersectFeatureSegments(output,a,b,normal,reader.Word()!=0);break;
            case 5:result=IntersectSegmentFace(output,a,b,normal,reader.Word()!=0);break;
            case 6:
            {
                const auto corner=reader.Word(),edge=reader.Word();result=IntersectFeatureCornerEdge(output,a,b,corner,edge,reader.Word()!=0);break;
            }
            case 7:result=FindFeatureIntersectionPrism(output,a,b,normal);break;
            default:Fail("Invalid prism operation");
            }
            Word(result);Words(output);Words(a);Words(b);
        }
    }
    if (reader.at!=reader.bytes.size()) Fail("Trailing prism input");
}

// SPDX-License-Identifier: Apache-2.0
#include "GeometryFeatures.h"
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
    std::vector<std::uint8_t> bytes;
    std::size_t at=0;
    std::uint32_t Word()
    {
        if (bytes.size()-at<4) Fail("Truncated geometry feature input");
        std::uint32_t word=0;
        for (unsigned i=0;i<4;++i) word|=std::uint32_t(bytes[at++])<<(i*8);
        return word;
    }
    template<std::size_t N> std::array<std::uint32_t,N> Words()
    { std::array<std::uint32_t,N> words;for (auto& word:words) word=Word();return words; }
    PrimitiveKind Kind()
    {
        const auto kind=Word();if (kind>3) Fail("Invalid primitive kind");return static_cast<PrimitiveKind>(kind);
    }
};
void Word(std::uint32_t value) { for (unsigned i=0;i<4;++i) std::cout.put(static_cast<char>(value>>(i*8))); }
template<std::size_t N> void Words(const std::array<std::uint32_t,N>& value) { for (auto word:value) Word(word); }
}
int main()
{
    {
        Reader reader;reader.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});const auto count=reader.Word();
        for (std::uint32_t index=0;index<count;++index)
        {
            const auto operation=reader.Word();Word(index);Word(operation);
            switch (operation)
            {
            case 0:
            {
                const auto kind=reader.Kind();const auto gp=reader.Words<48>();
                const auto direction_count=reader.Word(),output_count=reader.Word();
                if (output_count<direction_count) Fail("Insufficient projection outputs");
                std::vector<DirectionWords> directions;
                for (std::uint32_t i=0;i<direction_count;++i) directions.push_back(reader.Words<4>());
                std::vector<ProjectionInterval> output;
                for (std::uint32_t i=0;i<output_count;++i) output.push_back(reader.Words<12>());
                auto single=output;
                for (std::size_t i=0;i<directions.size();++i) ProjectDirection(gp,kind,directions[i],single[i]);
                ProjectDirections(gp,kind,directions,output);
                for (const auto& interval:single) Words(interval);
                for (const auto& interval:output) Words(interval);
                break;
            }
            case 1:
            {
                const auto a=reader.Words<48>(),b=reader.Words<48>();SeparatingAxes output;
                for (auto& axis:output) axis=reader.Words<4>();
                const auto a_kind=reader.Kind(),b_kind=reader.Kind();
                Word(static_cast<std::uint32_t>(SeparatingAxisCandidates(a,b,output)));
                for (const auto& axis:output) Words(axis);
                const auto best=BestSeparatingDirection(a,a_kind,b,b_kind);Words(best.first);Words(best.second);break;
            }
            case 2:
            {
                auto output=reader.Words<16>();const auto origin=reader.Words<4>(),end=reader.Words<4>();
                InitializeFeatureSegment(output,origin,end);Words(output);break;
            }
            case 3:
            {
                const auto gp=reader.Words<48>();const auto direction=reader.Words<4>();auto output=reader.Words<144>();auto scratch=reader.Words<16>();
                CapsuleMaximumFeature(gp,direction,output,scratch);Words(output);Words(scratch);break;
            }
            case 4:
            {
                const auto gp=reader.Words<48>();const auto mode=reader.Word();const auto direction=reader.Words<4>();auto output=reader.Words<144>();
                TriangleMaximumFeature(gp,mode,direction,output);Words(output);break;
            }
            case 5:
            {
                const auto gp=reader.Words<48>();const auto mode=reader.Word();const auto direction=reader.Words<4>();auto output=reader.Words<144>();
                const auto incoming=reader.Words<4>();BoxMaximumFeature(gp,mode,direction,output,incoming);Words(output);break;
            }
            case 6:
            {
                auto output=reader.Words<144>();const auto mode=reader.Word();const auto direction=reader.Words<4>();
                BuildFeatureEdgePlanes(output,mode,direction);Words(output);break;
            }
            default:Fail("Invalid geometry feature operation");
            }
        }
        if (reader.at!=reader.bytes.size()) Fail("Trailing geometry feature input");
    }
}

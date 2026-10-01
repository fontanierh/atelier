// SPDX-License-Identifier: Apache-2.0
#include "BoardPose.h"
#include <cstdlib>
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
    std::uint32_t Word() {if (bytes.size()-at<4) Fail("Truncated board pose input");std::uint32_t v=0;for (unsigned i=0;i<4;++i) v|=std::uint32_t(bytes[at++])<<(8*i);return v;}
    template<std::size_t N> std::array<std::uint32_t,N> Words() {std::array<std::uint32_t,N> v;for (auto& x:v) x=Word();return v;}
    PartPose Part()
    {
        const auto mask=Word();PartPose p;p.transform=Words<16>();const auto local=Words<16>();const auto body=Words<44>();const auto inertia=Words<10>();
        if (mask&1) p.local_mass_frame=local;if (mask&2) p.body=body;if (mask&4) p.inertia=inertia;return p;
    }
};
struct Writer
{
    std::vector<std::uint32_t> words;
    void Word(std::uint32_t v) {words.push_back(v);}
    template<std::size_t N> void Words(const std::array<std::uint32_t,N>& v) {words.insert(words.end(),v.begin(),v.end());}
    void Part(const PartPose& p)
    {
        Word((p.local_mass_frame ? 1:0)|(p.body ? 2:0)|(p.inertia ? 4:0));Words(p.transform);Words(p.local_mass_frame.value_or(PoseMatrix{}));Words(p.body.value_or(std::array<std::uint32_t,44>{}));Words(p.inertia.value_or(std::array<std::uint32_t,10>{}));
    }
};
void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) std::cout.put(static_cast<char>(v>>(8*i)));}
}
int main()
{
    Reader reader;reader.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});const auto count=reader.Word();
    for (std::uint32_t index=0;index<count;++index)
    {
        const auto op=reader.Word();Writer out;
        if (op==0) out.Words(OrthonormalizeRotation(reader.Words<16>()));
        else if (op==1) out.Words(OrthonormalizePartBasis(reader.Words<16>()));
        else if (op==2)
        {
            auto part=reader.Part();out.Words(PartTransform(part));const auto n=reader.Word();out.Word(n);
            for (std::uint32_t i=0;i<n;++i) {SetPartTransform(part,reader.Words<16>());out.Part(part);out.Words(PartTransform(part));}
        }
        else if (op==3)
        {
            std::array<PartPose,7> parts;for (auto& p:parts) p=reader.Part();auto hook=reader.Part();const auto n=reader.Word();out.Word(n);
            for (std::uint32_t i=0;i<n;++i)
            {
                SetBoardTransform(parts,hook,reader.Words<16>());for (const auto& p:parts) {out.Part(p);out.Words(PartTransform(p));}out.Part(hook);out.Words(PartTransform(hook));
            }
        }
        else Fail("Invalid board pose operation");
        Word(index);Word(op);Word(static_cast<std::uint32_t>(out.words.size()));for (auto w:out.words) Word(w);
    }
    if (reader.at!=reader.bytes.size()) Fail("Trailing board pose input");
}

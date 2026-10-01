// SPDX-License-Identifier: Apache-2.0
#include "PlayerPostInput.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <iterator>
#include <optional>
#include <vector>
using namespace atelier::skate;
struct Input
{
    std::vector<std::uint8_t> bytes;std::size_t at=0;
    std::uint32_t Word(){if(at>bytes.size()||bytes.size()-at<4)std::abort();std::uint32_t w=0;for(unsigned n=0;n<4;++n)w|=std::uint32_t(bytes[at++])<<(8*n);return w;}
    float Float(){const auto w=Word();float f;std::memcpy(&f,&w,4);return f;}
    template<class T,std::size_t N,class F>std::array<T,N> Array(F f){std::array<T,N> a;for(auto& v:a)v=f(*this);return a;}
};
struct Output
{
    std::vector<std::uint32_t> words;
    void Word(std::uint32_t w){words.push_back(w);}
    void Float(float f){std::uint32_t w;std::memcpy(&w,&f,4);Word(w);}
};
// GENERATED_PROTOCOL
struct Services final:PostInputServices
{
    std::uint8_t valid=0;float heading=0;std::vector<std::uint32_t> calls;
    void UpdateGrindManager() override{calls.push_back(1);}
    std::uint8_t UpdateTrajectorySelector() override{calls.push_back(2);return valid;}
    float CalculateHeading() override{calls.push_back(3);return heading;}
    void RegisterCandidate(CandidateRegistration r) override{calls.push_back(r==CandidateRegistration::First1888?4:5);}
};
int main()
{
    Input i;i.bytes={std::istreambuf_iterator<char>(std::cin),{}};Output o;
    const auto cases=i.Word();o.Word(cases);
    for(std::uint32_t c=0;c<cases;++c)
    {
        auto player=ReadPostInputPlayerFields(i);auto processed=ReadPostInputProcessedFields(i);
        auto output=ReadPostInputPhysOutFields(i);auto candidates=ReadCandidatePublicationFields(i);
        const auto count=i.Word();o.Word(c);o.Word(count);
        for(std::uint32_t n=0;n<count;++n)
        {
            const auto op=i.Word();o.Word(op);
            if(op==0)
            {
                processed.flags_2468=i.Word();processed.flags_2472=i.Word();processed.flags_2480=i.Word();processed.flags_2484=i.Word();processed.current_state_2508=i.Word();
                output=ReadPostInputPhysOutFields(i);candidates=ReadCandidatePublicationFields(i);
                Services services;services.valid=std::uint8_t(i.Word());services.heading=i.Float();
                RunPostInput({player,processed,output,candidates},services);
                o.Word(std::uint32_t(services.calls.size()));for(auto call:services.calls)o.Word(call);
                Observe(o,player);Observe(o,processed);Observe(o,output);Observe(o,candidates);
            }
            else if(op==1)
            {
                auto destination=i.Array<std::uint32_t,72>([](Input& r){return r.Word();});
                const auto source=i.Array<std::uint32_t,72>([](Input& r){return r.Word();});
                CopyGrabRecord(destination,source);for(auto word:destination)o.Word(word);
            }
            else return 2;
        }
    }
    if(i.at!=i.bytes.size())return 2;
    for(auto word:o.words)for(unsigned n=0;n<4;++n)std::cout.put(char(word>>(8*n)));
    return std::cout?0:2;
}

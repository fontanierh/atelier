#include "ConstraintSolver.h"
#include <iostream>
#include <stdexcept>
using namespace atelier::skate;
namespace
{
std::uint32_t Word(){char b[4];if(!std::cin.read(b,4))throw std::runtime_error("truncated input");return std::uint32_t(static_cast<unsigned char>(b[0]))|(std::uint32_t(static_cast<unsigned char>(b[1]))<<8)|(std::uint32_t(static_cast<unsigned char>(b[2]))<<16)|(std::uint32_t(static_cast<unsigned char>(b[3]))<<24);}
void Out(std::uint32_t w){const char b[4]={char(w),char(w>>8),char(w>>16),char(w>>24)};std::cout.write(b,4);}
template<std::size_t N> std::array<std::uint32_t,N> Words(){std::array<std::uint32_t,N> a;for(auto& w:a)w=Word();return a;}
template<std::size_t N> void Out(const std::array<std::uint32_t,N>& words){for(auto w:words)Out(w);}
template<std::size_t N> std::vector<Constraint<N>> Constraints(std::size_t n)
{
    std::vector<Constraint<N>> output(n);for(auto& c:output){c.reaction_a=Word();c.reaction_b=Word();c.words=Words<N>();}return output;
}
}
int main()
{
    try
    {
        const auto count=Word();
        for(std::uint32_t record=0;record<count;++record)
        {
            const auto nr=Word(),nc=Word(),nj=Word(),nd=Word(),iterations=Word(),repeat=Word();
            std::vector<PackedReaction> reactions(nr);for(auto& r:reactions)r=Words<16>();
            auto contacts=Constraints<64>(nc);auto joints=Constraints<96>(nj);auto drives=Constraints<96>(nd);
            for(std::uint32_t i=0;i<repeat;++i)
            {
                Out(std::uint32_t(SolveConstraints(contacts,joints,drives,reactions,iterations)));
                for(const auto& c:contacts)Out(c.words);
                for(const auto& c:joints)Out(c.words);
                for(const auto& c:drives)Out(c.words);
                for(const auto& r:reactions)Out(r);
            }
        }
        if(std::cin.peek()!=std::char_traits<char>::eof())throw std::runtime_error("trailing input");
    }
    catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}
}

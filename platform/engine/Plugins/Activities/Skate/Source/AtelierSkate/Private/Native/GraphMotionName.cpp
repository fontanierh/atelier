// SPDX-License-Identifier: Apache-2.0
#include "GraphMotionName.h"
#include <cstdint>
namespace atelier::skate
{
namespace
{
bool White(std::uint32_t c)
{
    return c==0 || (c>=9 && c<=13) || c==0x20 || c==0x85 || c==0xa0 || c==0x1680 ||
        (c>=0x2000 && c<=0x200a) || c==0x2028 || c==0x2029 || c==0x202f || c==0x205f || c==0x3000;
}
}
std::string_view TrimMotionGraphName(std::string_view text)
{
    std::size_t first=text.size(),last=0,at=0;
    while (at<text.size())
    {
        const auto begin=at;const auto byte=static_cast<unsigned char>(text[at++]);
        std::uint32_t c=byte;unsigned remaining=0;
        if ((byte&0xe0)==0xc0) {c=byte&31;remaining=1;}
        else if ((byte&0xf0)==0xe0) {c=byte&15;remaining=2;}
        else if ((byte&0xf8)==0xf0) {c=byte&7;remaining=3;}
        while (remaining--!=0 && at<text.size()) c=(c<<6)|(static_cast<unsigned char>(text[at++])&63);
        if (!White(c)) {if (first==text.size()) first=begin;last=at;}
    }
    return first==text.size()?std::string_view{}:text.substr(first,last-first);
}
}

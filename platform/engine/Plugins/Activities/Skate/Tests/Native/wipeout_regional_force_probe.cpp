// SPDX-License-Identifier: Apache-2.0
#include "WipeoutRuntime.h"
#include "DataReader.h"
#include <iostream>
#include <iterator>
using namespace atelier::skate;
int main()
{
    const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};
    detail::DataReader input{bytes};input.at=0;const auto count=input.Word();
    for(std::uint32_t i=0;i<count;++i)
    {
        WipeoutFrame frame{};for(auto& v:frame.regions_force)v=input.Float();
        const auto body=input.Float(),arms=input.Float();const std::uint32_t result=CheckWipeoutRegionalForce(frame,body,arms);
        for(unsigned b=0;b<4;++b)std::cout.put(char(result>>(b*8)));
    }
    return input.ok&&input.Remaining()==0&&std::cout?0:2;
}

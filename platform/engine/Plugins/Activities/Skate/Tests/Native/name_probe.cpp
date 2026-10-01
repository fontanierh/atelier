// SPDX-License-Identifier: Apache-2.0
#include "NameId.h"
#include <iomanip>
#include <iostream>
#include <string>

int main()
{
    std::string line;
    while (std::getline(std::cin,line))
        std::cout << std::hex << std::setfill('0') << std::setw(16) << atelier::skate::NameHash(line)
                  << ' ' << std::setw(16) << atelier::skate::NameId(line) << '\n';
    return std::cout ? 0 : 2;
}

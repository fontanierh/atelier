// SPDX-License-Identifier: Apache-2.0
#include "PhysicsSkeleton.h"
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
void Word(std::uint32_t w){const char b[4]={char(w),char(w>>8),char(w>>16),char(w>>24)};std::cout.write(b,4);}
void Wide(std::uint64_t w){Word(std::uint32_t(w));Word(std::uint32_t(w>>32));}
void String(const std::string& v){Word(std::uint32_t(v.size()));std::cout.write(v.data(),v.size());}
void Float(float v){std::uint32_t w;std::memcpy(&w,&v,4);Word(w);}
int main(int argc,char** argv)
{
    if(argc!=4)return 2;
    std::ifstream file(argv[1],std::ios::binary);std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(file),std::istreambuf_iterator<char>()};
    PhysicsSkeletons data;std::string error;if(!data.Load(bytes,argv[2],error)){std::cerr<<error<<'\n';return 2;}
    const auto* skeleton=data.Find(argv[3]);if(!skeleton)return 2;
    // A failed reload must not invalidate the live package or returned records.
    if(data.Load({},argv[2],error)||data.Find(argv[3])!=skeleton)return 3;
    String(skeleton->name);Wide(skeleton->record);Word(std::uint32_t(skeleton->bones.size()));
    for(const auto& bone:skeleton->bones)
    {
        String(bone.name);Wide(bone.record);for(auto w:bone.words)Word(w);
        for(auto v:bone.Size())Float(v);for(auto v:bone.Rotation())Float(v);for(auto v:bone.Translation())Float(v);
    }
}

// SPDX-License-Identifier: Apache-2.0
#include "PhysicsSkeleton.h"
#include "DataReader.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <set>
namespace atelier::skate
{
namespace
{
float FromBits(std::uint32_t bits){float value;std::memcpy(&value,&bits,4);return value;}
unsigned char Lower(unsigned char c){return c>='A'&&c<='Z'?c+('a'-'A'):c;}
bool EqualName(std::string_view a,std::string_view b)
{
    if(a.size()!=b.size())return false;
    for(std::size_t i=0;i<a.size();++i)if(Lower(a[i])!=Lower(b[i]))return false;
    return true;
}
}
std::array<float,3> PhysicsBone::Size() const{return {FromBits(words[8]),FromBits(words[9]),FromBits(words[10])};}
std::array<float,4> PhysicsBone::Rotation() const{return {FromBits(words[12]),FromBits(words[13]),FromBits(words[14]),FromBits(words[15])};}
std::array<float,3> PhysicsBone::Translation() const{return {FromBits(words[16]),FromBits(words[17]),FromBits(words[18])};}
bool PhysicsSkeletons::Load(const std::vector<std::uint8_t>& bytes,std::string_view expected_bank,std::string& error)
{
    const auto fail=[&](const char* message){error=message;return false;};
    if(bytes.size()<8||std::memcmp(bytes.data(),"ATPHYS01",8)!=0)return fail("Invalid native physics skeleton signature");
    detail::DataReader reader{bytes};PhysicsSkeletons value;
    value.bank_=reader.String();
    if(!reader.ok||value.bank_!=expected_bank)return fail("Physics skeleton bank identity differs from animation data");
    const auto count=reader.Word();
    if(count>reader.Remaining()/16)return fail("Truncated native physics skeleton records");
    std::set<std::string> names;
    for(std::uint32_t i=0;i<count;++i)
    {
        PhysicsSkeleton skeleton;skeleton.name=reader.String();
        const auto low=reader.Word(),high=reader.Word();skeleton.record=std::uint64_t(low)|(std::uint64_t(high)<<32);
        const auto bones=reader.Word();
        if(!reader.ok||!names.insert(skeleton.name).second||bones==0||bones>255||bones>reader.Remaining()/124)
            return fail("Invalid native physical bone count or repeated skeleton name");
        std::set<std::string> bone_names;
        for(std::uint32_t j=0;j<bones;++j)
        {
            PhysicsBone bone;bone.name=reader.String();
            const auto lo=reader.Word(),hi=reader.Word();bone.record=std::uint64_t(lo)|(std::uint64_t(hi)<<32);
            for(auto& word:bone.words)word=reader.Word();
            if(!reader.ok||!bone_names.insert(bone.name).second)return fail("Truncated or repeated native physical bone");
            for(auto lane:{8,9,10,12,13,14,15,16,17,18})
                if(!std::isfinite(FromBits(bone.words[lane])))return fail("Nonfinite native physical bone transform");
            skeleton.bones.push_back(std::move(bone));
        }
        value.records_.push_back(std::move(skeleton));
    }
    if(!reader.ok||reader.Remaining()!=0)return fail("Truncated or trailing native physics skeleton bytes");
    *this=std::move(value);error.clear();return true;
}
const PhysicsSkeleton* PhysicsSkeletons::Find(std::string_view name) const
{
    for(const auto& skeleton:records_)if(EqualName(skeleton.name,name))return &skeleton;
    return nullptr;
}
}

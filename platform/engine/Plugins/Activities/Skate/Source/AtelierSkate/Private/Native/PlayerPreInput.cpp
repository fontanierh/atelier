// SPDX-License-Identifier: Apache-2.0
#include "PlayerPreInput.h"
#include <cstring>
namespace atelier::skate
{
PlayerPreInputResult PlayerPreInputResult::Reset()
{
    Mat4 frame=SkeletonIdentity;frame[3]={};
    const std::uint32_t bits=0x501502f9;float limit;std::memcpy(&limit,&bits,4);
    return {{},{0,1,0,0},frame,{},{0,1,0,0},{},{},0,0,limit,limit,0,0};
}
bool PlayerPreInputManager::Prepare(std::uint32_t& counter,std::string& error)
{
    result=PlayerPreInputResult::Reset();result_counts={};counter=30;
    if(pending_geometry){error="Pending82D811C8 trajectory batch requires its complete82D81610 geometry consumer";return false;}
    error.clear();return true;
}
}

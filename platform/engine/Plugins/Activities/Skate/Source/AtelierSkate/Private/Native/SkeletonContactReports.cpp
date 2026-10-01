// SPDX-License-Identifier: Apache-2.0
#include "SkeletonContactReports.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word){float v;std::memcpy(&v,&word,4);return v;}
std::uint32_t Word(float v){std::uint32_t w;std::memcpy(&w,&v,4);return w;}
Vec4 Load(const std::vector<std::uint32_t>& words,std::size_t at)
{return {Float(words[at]),Float(words[at+1]),Float(words[at+2]),Float(words[at+3])};}
const BodySnapshot* Resolve(std::uint32_t id,const SkeletonReportOwners& owners)
{
    const auto body=CollisionBody::FromContactId(id);
    if(body.kind==CollisionBody::Kind::StaticWorld)return nullptr;
    if(body.kind==CollisionBody::Kind::Board)return &owners.board[body.index];
    return body.index<owners.attached.size() ? owners.attached[body.index]:nullptr;
}
Vec4 Center(std::uint32_t id,const SkeletonReportOwners& owners)
{const auto* body=Resolve(id,owners);if(!body)return {};const auto p=body->rates.position;return {p.x,p.y,p.z,0};}
SkeletonContactBody ContactBody(const BodySnapshot* body)
{if(!body)return {1,0,{}};const auto v=body->rates.linear_velocity;return {body->state_flags,body->inertia.inverse_mass,{v.x,v.y,v.z,0}};}
std::size_t Spy(std::vector<std::uint32_t>& storage,std::size_t count,float frequency,const SkeletonReportOwners& owners)
{
    const float squared_frequency=frequency*frequency;std::size_t write=0,spies=0;
    for(std::size_t index=0;index<count;++index)
    {
        const auto start=index*64;if((storage[start+11]&8u)==0)continue;
        const auto impulse=Load(storage,start+20);if(!(impulse[0]>0.0f))continue;
        const auto a=storage[start+31],b=storage[start+43];const auto bc=Center(b,owners),ac=Center(a,owners);
        const auto ap=Load(storage,start),bp=Load(storage,start+4);
        const float aw=Float(storage[start+35]),bw=Float(storage[start+39]);
        const auto normal=Load(storage,start+28),t0=Load(storage,start+40),t1=Load(storage,start+52);
        Vec4 tangent,position;const float inverse=1.0f/(bw+aw);
        for(unsigned i=0;i<4;++i)
        {
            tangent[i]=std::fma(t0[i],impulse[1],t1[i]*impulse[2]);
            position[i]=std::fma(ac[i]+ap[i],aw,(bc[i]+bp[i])*bw)*inverse;
        }
        const auto tag=storage[start+55];storage[write+24]=a;storage[write+25]=b;storage[write+26]=tag;
        for(unsigned i=0;i<4;++i)
        {
            storage[write+16+i]=Word((normal[i]*impulse[0])*squared_frequency);
            storage[write+20+i]=Word(tangent[i]*squared_frequency);
            storage[write+i]=Word(normal[i]);storage[write+4+i]=Word(t0[i]);storage[write+8+i]=Word(t1[i]);storage[write+12+i]=Word(position[i]);
        }
        ++spies;write+=28;
    }
    return spies;
}
}
void CollectSkeletonContactReports(std::vector<SkeletonContactReport>& output,const std::vector<ContactConstraint>& contacts,
    const SkeletonReportOwners& owners,float frequency)
{
    std::vector<std::uint32_t> storage;storage.reserve(contacts.size()*64);
    for(const auto& row:contacts)storage.insert(storage.end(),row.words.begin(),row.words.end());
    const auto count=Spy(storage,contacts.size(),frequency,owners);output.clear();output.reserve(16);
    const auto external=[&](CollisionBody body){return body.kind==CollisionBody::Kind::StaticWorld || (body.kind==CollisionBody::Kind::Attached && body.index>=owners.local_attached_count);};
    for(std::size_t index=0;index<count;++index)
    {
        const auto at=index*28;const auto a=CollisionBody::FromContactId(storage[at+24]),b=CollisionBody::FromContactId(storage[at+25]);
        if(!external(a) && !external(b))continue;
        const std::array<CollisionBody,2> sides{{a,b}},others{{b,a}};
        for(unsigned side=0;side<2;++side)
        {
            const auto own=sides[side],other=others[side];if(own.kind!=CollisionBody::Kind::Attached || own.index>=24 || output.size()==16)continue;
            const bool side_a=side==0;auto normal=Load(storage,at);for(auto& v:normal)v*=side_a ? 1.0f:-1.0f;
            const std::uint32_t group=other.kind==CollisionBody::Kind::StaticWorld ? 0:other.kind==CollisionBody::Kind::Board ? owners.board_group:owners.skeleton_group;
            output.push_back({own.index,normal,Load(storage,at+12),side_a ? storage[at+26]&0xffffu:storage[at+26]>>16,group,std::nullopt,
                ContactBody(Resolve(storage[at+24],owners)),ContactBody(Resolve(storage[at+25],owners)),side_a,Load(storage,at+20)});
        }
    }
}
}

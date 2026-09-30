// SPDX-License-Identifier: Apache-2.0
#include "ContactRetention.h"
#include <algorithm>
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <vector>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
float Scalar(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
double Scalar64(std::uint64_t word) {double value;std::memcpy(&value,&word,8);return value;}
std::uint32_t Word(float value) {std::uint32_t word;std::memcpy(&word,&value,4);return word;}
Vec3 Vector(const ContactRecord& row,std::size_t offset) {return {Scalar(row[offset]),Scalar(row[offset+1]),Scalar(row[offset+2])};}
void Require(bool valid) {if (!valid) {assert(false && "Contact retention storage contract exceeded");std::abort();}}
std::uint32_t Quiet(std::uint32_t bits)
{return (bits&0x7f800000u)==0x7f800000u && (bits&0x007fffffu) ? bits|0x00400000u:bits;}
float MaterialStore(float value) {return Scalar(Quiet(Word(value)));}
}
ContactMaterial CombineContactMaterials(ContactMaterial a,ContactMaterial b)
{
    return {MaterialStore(a.static_friction>b.static_friction ? a.static_friction:b.static_friction),
            MaterialStore(a.dynamic_friction>b.dynamic_friction ? a.dynamic_friction:b.dynamic_friction),
            MaterialStore(a.restitution<b.restitution ? a.restitution:b.restitution)};
}
bool CoplanarContacts(const ContactRecord& a,const ContactRecord& b)
{
    const Vec3 normal=Vector(a,8);
    if (Scalar(0x3f7fbe77)>Dot3(normal,Vector(b,8))) return false;
    const float da=std::fabs(Dot3(normal,Subtract(Vector(a,0),Vector(b,0)))),db=std::fabs(Dot3(normal,Subtract(Vector(a,4),Vector(b,4))));
    return (da-db>=0.0f ? db:da)<Scalar(0x3c23d70a);
}
std::size_t SelectContactPoints(const Vec3* a,const Vec3* b,std::size_t count,Vec3 normal,std::array<std::uint32_t,4>& output)
{
    Require(count>0);std::size_t first=0;Vec3 origin=a[0];float depth=Dot3(normal,Subtract(a[0],b[0]));
    for (std::size_t i=1;i<count;++i)
    {
        const float candidate=Dot3(normal,Subtract(a[i],b[i]));
        if (depth>candidate) {depth=candidate;first=i;origin=a[i];}
    }
    Vec3 third_delta=Subtract(a[0],origin),far_delta=third_delta;std::size_t far=0;float distance=Dot3(far_delta,far_delta);
    for (std::size_t i=1;i<count;++i)
    {
        const Vec3 delta=Subtract(a[i],origin);const float candidate=Dot3(delta,delta);
        if (candidate>distance) {distance=candidate;far=i;far_delta=delta;}
    }
    if (first==far) {output[0]=static_cast<std::uint32_t>(first);return 1;}
    std::size_t third=0;const auto initial_area=Cross3(third_delta,far_delta);float area=Dot3(initial_area,initial_area);
    for (std::size_t i=1;i<count;++i)
    {
        const auto delta=Subtract(a[i],origin),area_vector=Cross3(delta,far_delta);const float candidate=Dot3(area_vector,area_vector);
        if (candidate>area) {area=candidate;third=i;third_delta=delta;}
    }
    output[0]=static_cast<std::uint32_t>(first);output[1]=static_cast<std::uint32_t>(far);output[2]=static_cast<std::uint32_t>(third);
    if (third==first || third==far) return 2;
    const Vec3 side=Cross3(normal,far_delta);const float sign=Dot3(side,third_delta)>=0.0f ? 1.0f:-1.0f;
    const Vec3 far_side=Scale(side,sign),third_side=Scale(Cross3(normal,third_delta),sign),edge=Subtract(third_delta,far_delta);
    std::size_t fourth=9999;float best=-1.0f;
    for (std::size_t i=0;i<count;++i)
    {
        const Vec3 delta=Subtract(a[i],origin);Vec3 selected;
        if (Dot3(delta,far_side)>0.0f)
            selected=Dot3(delta,third_side)>0.0f ? Cross3(delta,third_delta):Cross3(Subtract(delta,far_delta),edge);
        else selected=Cross3(delta,far_delta);
        const float candidate=Dot3(selected,selected);
        if (candidate>best) {best=candidate;fourth=i;}
    }
    output[3]=static_cast<std::uint32_t>(fourth);return 3+(fourth!=first && fourth!=far && fourth!=third && fourth!=9999);
}
std::optional<std::size_t> ContactBuffer::Allocate(const ContactSink& sink)
{
    Require(count<=50);
    if (count+flushed>=capacity)
    {
        if (!full) {if (deferred_reduction) Reduce();if (count+flushed>=capacity) full=1;}
        if (full) {++dropped;return std::nullopt;}
    }
    if (count>=50)
    {
        if (!allow_flush) {full=1;return std::nullopt;}
        Flush(sink);
    }
    const std::size_t index=count;++count;return index;
}
bool ContactBuffer::LastIsDuplicate()
{
    if (distance_squared_threshold<0.0f || deferred_reduction) return false;
    Require(count>0 && count<=50);const auto& current=records[count-1];
    for (std::size_t i=0;i+1<count;++i)
    {
        const auto& previous=records[i];if (previous[3]!=current[3] || previous[7]!=current[7]) continue;
        const auto a=Subtract(Vector(previous,0),Vector(current,0)),b=Subtract(Vector(previous,4),Vector(current,4));
        if (distance_squared_threshold>Dot3(a,a) && Dot3(b,b)<distance_squared_threshold
            && static_cast<double>(Dot3(Vector(previous,8),Vector(current,8)))>Scalar64(0x3fee147ae147ae14)) {++dropped;return true;}
    }
    return false;
}
void ContactBuffer::Reduce()
{
    const std::size_t original=count;Require(original<=50);std::array<bool,50> assigned{};std::vector<std::size_t> retained;retained.reserve(original);
    for (std::size_t first=0;first<original;++first)
    {
        if (assigned[first]) continue;assigned[first]=true;std::vector<std::size_t> group{first};
        for (std::size_t next=first+1;next<original;++next)
            if (!assigned[next] && records[first][3]==records[next][3] && records[first][7]==records[next][7] && CoplanarContacts(records[first],records[next]))
            {assigned[next]=true;group.push_back(next);}
        if (group.size()<=4) retained.insert(retained.end(),group.begin(),group.end());
        else
        {
            std::vector<Vec3> a,b;for (auto i:group) {a.push_back(Vector(records[i],0));b.push_back(Vector(records[i],4));}
            std::array<std::uint32_t,4> selected={0,1,2,3};const auto n=SelectContactPoints(a.data(),b.data(),a.size(),Vector(records[first],8),selected);
            for (std::size_t i=0;i<n;++i) retained.push_back(group[selected[i]]);
        }
    }
    if (retained.size()<original)
    {
        std::sort(retained.begin(),retained.end());count=static_cast<std::uint32_t>(retained.size());
        for (std::size_t destination=0;destination<retained.size();++destination)
        {
            const auto source=retained[destination];if (destination==source) continue;
            // Original scalar float copies quiet sNaNs; body IDs and tag are integer stores.
            const auto original_row=records[source];for (unsigned i=0;i<64;++i) records[destination][i]=Quiet(original_row[i]);
            for (auto i:{3,7,23}) records[destination][i]=original_row[i];
        }
    }
}
void ContactBuffer::Flush(const ContactSink& sink)
{
    if (!count) return;
    if (deferred_reduction) Reduce();sink(records.data(),count);flushed+=count;count=0;
}
}

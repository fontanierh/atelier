// SPDX-License-Identifier: Apache-2.0
#include "OffboardContactPrivate.h"
#include <cstdlib>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::offboard_contact
{
namespace
{
float Slope(OffboardToolkitInput input,float low,float high)
{const auto speed=VectorMin(VectorMax(Length(input.velocity),2),6);return Tangent((((speed-2.0f)*(low-high))*.25f+high)*.017453292f);}
float UpSlope(OffboardToolkitInput input,float height){return height>.4f?Slope(input,35,50):Slope(input,15,30);}
float DownSlope(OffboardToolkitInput input,float height){return height>.4f?Slope(input,30,50):Slope(input,15,30);}
float BetweenSlope(OffboardToolkitInput input,Vec4 a,Vec4 b)
{const auto d=Sub(b,a);const auto x=Dot(input.forward,d);return x<.001f?1000:Reciprocal(x)*Dot(input.up,d);}
struct Builder
{
    OffboardToolkitInput input;const Profile& profile;float obstruction;std::vector<OffboardContactCandidate> candidates;
    void Add(Vec4 position,Vec4 normal,Vec4 direction,std::int32_t segment,std::uint32_t flags,std::uint32_t kind)
    {
        const auto order=Dot(input.forward,Sub(position,input.position));OffboardContactCandidate c;c.position=position;c.normal=normal;c.direction=direction;c.segment=segment;c.flags=flags;c.kind=kind;c.order=order;c.low=order;c.high=order;
        if(segment<0)c.low=0;
        else
        {
            if(std::size_t(segment)>=profile.segments.size())std::abort();const auto s=profile.segments[std::size_t(segment)];
            if(s.kind!=0){const auto point=s.kind==2?s.start:s.end;const auto distance=Dot(input.forward,Sub(point,input.position));if(distance>=order)c.high=distance;else c.low=distance;}
        }
        candidates.push_back(c);
    }
    void Point(Vec4 position,Vec4 normal,std::int32_t segment,std::uint32_t flags,std::uint32_t kind)
    {const auto delta=Sub(position,input.position);Add(position,normal,Length(delta)>=.02f?delta:input.forward,segment,flags,kind);}
    std::array<float,2> Local(Vec4 p) const {const auto d=Sub(p,input.position);return {Dot(input.forward,d),Dot(input.up,d)};}
    Vec4 NextNormal(std::size_t i) const
    {if(profile.last_ground==0||i>=profile.last_ground)std::abort();return i==profile.last_ground-1?input.up:profile.segments[i+1].normal;}
    void ApproachUp(std::size_t index,std::uint32_t flags,float slope)
    {
        if(index>=profile.segments.size())std::abort();const auto p=Local(profile.segments[index].end);const std::array<float,2> goal{-1,std::fma(-1.0f-p[0],slope,p[1])};
        for(std::size_t prior=index;prior>0;)
        {
            const auto i=--prior;const auto s=profile.segments[i];const auto t=Intersection(Local(s.start),Local(s.end),p,goal);
            if(t<0){if(i==0){Point(input.position,input.up,std::int32_t(index),flags,1);return;}}
            else if(t<=1)
            {const auto position=s.kind==0?Madd(s.direction,s.length*t,s.start):s.start,normal=s.kind==0?s.normal:NextNormal(i);if(Local(position)[0]<=.75f)Point(position,normal,std::int32_t(index),flags,1);return;}
        }
    }
    void ApproachDown(std::int32_t index,std::uint32_t flags,float slope,std::uint32_t kind)
    {
        if(index>=0&&std::size_t(index)>=profile.segments.size())std::abort();const auto point=index>=0?profile.segments[std::size_t(index)].start:input.position;
        const auto p=Local(point);const std::array<float,2> goal{2.8f,std::fma(2.8f-p[0],slope,p[1])};
        for(auto i=std::size_t(index+1);i<profile.last_ground;++i)
        {const auto s=profile.segments[i];const auto t=Intersection(Local(s.start),Local(s.end),p,goal);if(t>=0&&t<=1){if(s.kind==0)Point(Madd(s.direction,s.length*t,s.start),s.normal,index,flags,kind);else if(Local(s.end)[0]<=obstruction-.35f)Point(s.end,NextNormal(i),index,flags,kind);return;}}
    }
    void Advance(float distance)
    {
        for(std::size_t i=0;i<profile.last_ground;++i)
        {const auto s=profile.segments[i];if(s.kind==2){distance+=s.length/DownSlope(input,s.length);continue;}distance-=s.length;if(distance>0)continue;if(s.kind==1)Point(s.end,NextNormal(i),std::int32_t(i),0,9);else Point(Madd(s.direction,distance,s.end),s.normal,std::int32_t(i),0,9);return;}
    }
};
}
std::vector<OffboardContactCandidate> Generate(OffboardToolkitInput input,const Profile& profile,const OffboardContactPrefix& prefix,float obstruction,std::uint32_t retained_flags)
{
    Builder builder{input,profile,obstruction,{}};const auto supported=(prefix.flags_176&1)!=0;
    if(supported)
    {const auto planar=Sub(input.velocity,Scale(input.up,Dot(input.up,input.velocity)));if(Length(planar)<.01f){builder.Add(prefix.position,prefix.normal,Cross(input.right,prefix.normal),-1,0,0);return builder.candidates;}}
    if(profile.last_ground==0)return builder.candidates;
    std::optional<std::size_t> highest;bool have_rise=false,saw_drop=false;const auto forward=[&](Vec4 p){return Dot(Sub(p,input.position),input.forward);};
    for(std::size_t i=0;i<profile.last_ground;++i)
    {
        const auto segment=profile.segments[i];auto normal=segment.normal;
        if(i+1<profile.last_ground){const auto next=profile.segments[i+1];normal=segment.kind!=0&&next.kind!=0?input.up:next.normal;}
        if(!saw_drop){const auto prior=highest?profile.segments[*highest].end:input.position;if(Dot(Sub(segment.end,prior),input.up)>0)highest=i;}
        if(segment.kind==1&&segment.length>.05f)
        {
            const auto tall=segment.length>.4f;bool combined=false,eligible=false;auto slope=UpSlope(input,segment.length);auto j=i+1;
            while(j<profile.last_ground)
            {const auto next=profile.segments[j];if(!eligible&&next.kind==2)eligible=forward(next.start)<obstruction-.35f;if(next.kind!=0&&(next.kind!=1||next.length>=.05f))break;if(!eligible)eligible=Dot(next.direction,input.forward)>.70700002f&&forward(next.start)<obstruction-.35f;++j;}
            if(j<profile.last_ground&&profile.segments[j].kind==1)
            {const auto next_end=profile.segments[j].end;const auto joined=BetweenSlope(input,segment.end,next_end);if(joined>UpSlope(input,segment.length)*.5f){slope=joined;combined=true;if(!have_rise)combined=BetweenSlope(input,input.position,next_end)>=UpSlope(input,segment.length)*.5f;}}
            if(!have_rise)have_rise=eligible;
            if(eligible){builder.ApproachUp(i,tall?0x80:0,slope);const auto flags=std::uint32_t{0x40}|(combined||!tall?std::uint32_t{0}:std::uint32_t{0x100});builder.Point(segment.end,normal,std::int32_t(i),flags,combined?2:3);}
        }
        else if(segment.kind==2&&segment.length>.05f)
        {
            const auto tall=segment.length>.4f;bool combined=false;auto slope=-DownSlope(input,segment.length);auto j=i+1;
            while(j<profile.last_ground){const auto next=profile.segments[j];if(next.kind!=0&&!(next.kind==2&&next.length<.05f))break;++j;}
            if(j<profile.last_ground&&profile.segments[j].kind==2){const auto joined=BetweenSlope(input,segment.start,profile.segments[j].start);if(joined<DownSlope(input,segment.length)*-.5f){combined=true;slope=joined;}}
            bool suppress=false;if(!saw_drop&&!have_rise&&highest){suppress=Dot(Sub(profile.segments[*highest].end,input.position),input.up)>.02f;if(i==1&&profile.segments[0].kind==0)suppress=false;}saw_drop=true;
            if(!suppress)
            {if(combined)builder.Point(segment.start,normal,std::int32_t(i),0x40,5);else if(forward(segment.start)<=.75f){builder.ApproachDown(std::int32_t(i),tall?0x100:0,slope,4);builder.Point(segment.start,normal,std::int32_t(i),std::uint32_t{0x40}|(tall?std::uint32_t{0x80}:std::uint32_t{0}),6);}}
        }
    }
    const auto gap=input.position[1]-prefix.position[1];
    if(supported&&gap>.01f)
    {const auto flags=gap>=.4f?(retained_flags&0x100)|0x40:retained_flags&0x140;if(builder.candidates.empty()||!saw_drop)builder.ApproachDown(-1,flags,-DownSlope(input,.8f),builder.candidates.empty()?7:8);}
    else if(builder.candidates.empty())builder.Advance(Length(input.velocity)*.016666668f);
    return builder.candidates;
}
}
namespace atelier::skate
{
void OffboardContactHistory::Classify(OffboardContactPrefix& prefix,Vec4 direction)
{
    using namespace offboard_contact;const auto horizontal=Length({direction[0],0,direction[2],0}),inverse=1.0f/(.001f-horizontal>=0?.001f:horizontal),slope=inverse*direction[1];prefix.scalar_160=slope;
    const auto low=Tangent(Bits(0x3dd67750)),high=Tangent(Bits(0x3f0efa35)),magnitude=std::abs(slope);
    auto proposed=magnitude<=high?(magnitude<=low?std::uint32_t{0}:slope>0?std::uint32_t{1}:std::uint32_t{3}):slope>0?std::uint32_t{2}:std::uint32_t{4};
    if(proposed!=0&&(prefix.flags_176&0x40)==0)proposed+=4;prefix.kind_164=proposed;
    if(proposed==0)*this={};else if(std::all_of(samples.begin(),samples.end(),[&](auto sample){return sample==proposed;}))accepted=proposed;
    else {cursor=(cursor+1)%3;samples[cursor]=proposed;prefix.kind_164=accepted;}
}
}
namespace atelier::skate::offboard_contact
{
void Publish(OffboardToolkitInput input,const Profile& profile,const OffboardContactSamples& samples,std::vector<OffboardContactCandidate>& candidates,float obstruction,OffboardContactCandidate& retained,OffboardContactHistory& history,OffboardContactPrefix& prefix)
{
    prefix.edge_position=input.position;prefix.edge_normal=input.up;prefix.distance_168=0;
    if(profile.last_ground!=0)
    {
        const auto end=profile.segments[profile.last_ground-1].end;const auto reach=Dot(Sub(end,input.position),input.forward);prefix.distance_168=reach>=1.65f?1.0e10f:reach;
        const auto segment=std::find_if(profile.segments.begin(),profile.segments.end(),[](const auto& s){return (s.kind==1||s.kind==2)&&s.length>.05f;});if(segment!=profile.segments.end())prefix.distance_168=Dot(Sub(segment->start,input.position),input.forward);
        if((prefix.flags_176&1)!=0&&input.forward[1]>.2f&&prefix.normal[1]<.7f)
        {
            const std::array<std::pair<const std::vector<OffboardContactSample>*,std::size_t>,2> sets{{{&samples.ground,std::min(samples.original_ground_count,samples.ground.size())},{&samples.other,samples.other.size()}}};
            for(const auto& set:sets)
            {const auto& points=*set.first;for(std::size_t i=0;i<set.second;++i)if(points[i].normal[1]>.95f||(points[i].flags&0x10)!=0){if(Dot(Sub(points[i].position,input.position),input.up)>0)prefix.flags_176|=0x200;break;}}
        }
        auto distance=Length(input.velocity)*.25f;
        for(const auto& s:profile.segments)
        {if(s.kind!=0&&s.normal[1]<=.9f)continue;prefix.edge_normal=s.normal;distance-=s.length;if(distance<=0){prefix.edge_position=Madd(s.direction,distance,s.end);break;}prefix.edge_position=s.end;prefix.flags_176|=4;}
    }
    std::stable_sort(candidates.begin(),candidates.end(),[](const auto& a,const auto& b){return a.order<b.order;});
    if(candidates.empty()){if(obstruction>=.3f)prefix.flags_176&=~std::uint32_t{1};else prefix.flags_176|=0x400;return;}
    const auto step=Length(input.velocity)*.016666668f;auto selected=candidates.size()-1;
    for(std::size_t i=0;i<candidates.size();++i)
    {
        const auto& candidate=candidates[i];const auto behind=i+1<candidates.size()&&Dot(input.forward,Sub(candidate.position,input.position))<step;
        if(candidate.kind==1)
        {
            auto overridden=behind;
            if(!overridden)for(std::size_t n=i+1;n<candidates.size()&&candidates[n].low<=candidate.high;++n)if(candidates[n].kind==4||candidates[n].kind==7||candidates[n].kind==8){overridden=true;break;}
            if(overridden){selected=i;for(std::size_t n=i+1;n<candidates.size();++n)if(candidates[n].segment==candidate.segment){selected=n;break;}break;}
        }
        if(!behind){selected=i;break;}
    }
    retained=candidates[selected];prefix.target_position=retained.position;prefix.target_normal=retained.normal;prefix.flags_176|=retained.flags|2;
    if((prefix.flags_176&1)==0){prefix.flags_176|=0x3b;prefix.position=input.position;prefix.normal=input.up;}history.Classify(prefix,retained.direction);
}
}

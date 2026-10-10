#include "GeometryPrism.h"
#include <algorithm>
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
float Scalar(std::uint32_t word) { float value;std::memcpy(&value,&word,4);return value; }
std::uint32_t Word(float value) { std::uint32_t word;std::memcpy(&word,&value,4);return word; }
Vec4 Load(const std::uint32_t* words) { return {Scalar(words[0]),Scalar(words[1]),Scalar(words[2]),Scalar(words[3])}; }
Vec4 Load(DirectionWords words) { return Load(words.data()); }
DirectionWords Words(const Vec4& value) { return {Word(value[0]),Word(value[1]),Word(value[2]),Word(value[3])}; }
void Store(std::uint32_t* output,const Vec4& value) { const auto words=Words(value);std::copy(words.begin(),words.end(),output); }
Vec4 Sub(const Vec4& a,const Vec4& b) { return {a[0]-b[0],a[1]-b[1],a[2]-b[2],a[3]-b[3]}; }
Vec4 Scale(const Vec4& a,float b) { return {a[0]*b,a[1]*b,a[2]*b,a[3]*b}; }
Vec4 Madd(const Vec4& a,float b,const Vec4& c)
{ return {std::fma(a[0],b,c[0]),std::fma(a[1],b,c[1]),std::fma(a[2],b,c[2]),std::fma(a[3],b,c[3])}; }
Vec4 Normalized(const Vec4& value) { return Scale(value,InverseLengthSquared(Dot3(value,value),2)); }
float Length(const Vec4& value)
{
    const float squared=Dot3(value,value);return squared==0.0f ? 0.0f:squared*InverseLengthSquared(squared,2);
}
void Require(bool condition)
{
    if (!condition) { assert(false && "Native feature storage contract exceeded");std::abort(); }
}
FeatureSegment Segment(const MaximumFeature& feature,std::size_t edge=0)
{
    FeatureSegment segment;std::copy_n(feature.begin()+4+edge*16,16,segment.begin());return segment;
}
Vec4 Vertex(const MaximumFeature& feature,std::size_t edge) { return Load(feature.data()+4+edge*16); }
Vec4 End(const MaximumFeature& feature,std::size_t edge)
{
    const Vec4 origin=Vertex(feature,edge),direction=Load(feature.data()+8+edge*16),length=Load(feature.data()+16+edge*16);
    return {std::fma(direction[0],length[0],origin[0]),std::fma(direction[1],length[1],origin[1]),
            std::fma(direction[2],length[2],origin[2]),std::fma(direction[3],length[3],origin[3])};
}
Vec4 Endpoint(MaximumFeature& feature,bool start)
{
    feature[0]=start ? feature[0]-1u:feature[0]+1u;return start ? Vertex(feature,0):End(feature,0);
}
Vec4 ProjectToFace(const MaximumFeature& face,const Vec4& point)
{
    const Vec4 normal=Load(face.data()+132);return Madd(normal,Dot3(normal,Sub(Vertex(face,0),point)),point);
}
float PlaneDistance(const MaximumFeature& feature,std::size_t edge,const Vec4& point)
{ return Dot3(Load(feature.data()+12+edge*16),Sub(point,Vertex(feature,edge))); }
void Append(FeaturePrism& output,const Vec4& a,const Vec4& b)
{
    const std::size_t offset=output[132]*4u;Require(offset<64);
    Store(output.data()+offset,a);Store(output.data()+64+offset,b);++output[132];
}
void AppendSpecialized(FeaturePrism& output,std::size_t& count,const MaximumFeature& a,const MaximumFeature& b,
                       const Vec4& point,bool a_is_first)
{
    Require(count<16);const std::size_t ao=a_is_first ? 0:64,bo=a_is_first ? 64:0;
    Store(output.data()+ao+count*4,ProjectToFace(a,point));Store(output.data()+bo+count*4,ProjectToFace(b,point));++count;
}
float ContainmentDot(const Vec4& delta,const Vec4& normal)
{ return std::fma(delta[2],normal[2],std::fma(delta[0],normal[0],delta[1]*normal[1])); }
std::uint32_t SpecializedFaces(FeaturePrism& output,const MaximumFeature& a,const MaximumFeature& b,
                               DirectionWords normal_words,bool a_is_first)
{
    std::size_t count=0;const std::size_t b_count=b[140];
    for (std::size_t edge_a=0;edge_a<4;++edge_a)
    {
        const Vec4 a_origin=Vertex(a,edge_a),a_direction=Load(a.data()+8+edge_a*16),a_plane=Load(a.data()+12+edge_a*16);
        const float a_length=Scalar(a[16+edge_a*16]);
        for (std::size_t edge_b=0;edge_b<b_count;++edge_b)
        {
            const Vec4 b_origin=Vertex(b,edge_b),b_direction=Load(b.data()+8+edge_b*16);
            const float b_length=Scalar(b[16+edge_b*16]),denominator=Dot3(b_direction,a_plane),offset=Dot3(Sub(a_origin,b_origin),a_plane);
            const Vec4 point=Madd(b_direction,RefinedReciprocal(denominator,2)*offset,b_origin);
            const float along=Dot3(Sub(point,a_origin),a_direction);
            const bool valid=std::fabs(denominator)>Scalar(0x34000000)
                && !(std::fabs(offset)>std::fabs(b_length*denominator)) && !(0.0f>offset*denominator)
                && !(along>a_length) && !(0.0f>along);
            if (valid) AppendSpecialized(output,count,a,b,point,a_is_first);
        }
    }
    const Vec4 normal=Load(normal_words);
    for (unsigned pass=0;pass<2;++pass)
    {
        const MaximumFeature& source=pass==0 ? a:b;
        const MaximumFeature& target=pass==0 ? b:a;
        const std::size_t source_count=pass==0 ? 4:b_count,target_count=pass==0 ? b_count:4;
        for (std::size_t corner=0;corner<source_count;++corner)
        {
            const Vec4 origin=Vertex(source,corner);
            const float distance=ContainmentDot(Sub(Vertex(target,0),origin),normal);
            Vec4 point=Madd(normal,distance,origin);point[3]=1.0f;
            bool inside=true;
            for (std::size_t edge=0;edge<target_count;++edge)
                if (!(0.0f>ContainmentDot(Sub(point,Vertex(target,edge)),Load(target.data()+12+edge*16)))) {inside=false;break;}
            if (inside) AppendSpecialized(output,count,a,b,point,a_is_first);
        }
    }
    output[132]=static_cast<std::uint32_t>(count);return count!=0;
}
std::uint32_t GeneralFaces(FeaturePrism& output,MaximumFeature& a,MaximumFeature& b)
{
    constexpr std::uint32_t outside_a=0x40000000u,outside_b=0x20000000u;
    const std::size_t a_count=a[140],b_count=b[140];std::array<std::uint32_t,8> masks{};
    std::size_t nearest_corner=0,nearest_edge=0;bool edge_is_a=false;
    float largest_minimum=-std::numeric_limits<float>::max();output[132]=0;
    for (std::size_t edge=0;edge<a_count;++edge)
    {
        std::size_t previous=b_count-1,minimum_corner=previous;
        float previous_distance=PlaneDistance(a,edge,Vertex(b,previous)),minimum=previous_distance;
        for (std::size_t corner=0;corner<b_count;++corner)
        {
            const float distance=PlaneDistance(a,edge,Vertex(b,corner));
            if (distance<minimum) {minimum=distance;minimum_corner=corner;}
            if (distance>0.0f) masks[corner]|=outside_b;
            if (!(distance*previous_distance>0.0f)) masks[previous]|=1u<<edge;
            previous=corner;previous_distance=distance;
        }
        if (minimum>largest_minimum) {largest_minimum=minimum;nearest_corner=minimum_corner;nearest_edge=edge;edge_is_a=true;}
    }
    for (std::size_t corner=0;corner<b_count;++corner)
        if (!(masks[corner]&outside_b)) {const Vec4 point=Vertex(b,corner);Append(output,ProjectToFace(a,point),point);}
    if (output[132]==b_count) return 1;
    for (std::size_t edge=0;edge<b_count;++edge)
    {
        std::size_t previous=a_count-1,minimum_corner=previous;
        float previous_distance=PlaneDistance(b,edge,Vertex(a,previous)),minimum=previous_distance;
        for (std::size_t corner=0;corner<a_count;++corner)
        {
            const float distance=PlaneDistance(b,edge,Vertex(a,corner));
            if (distance<minimum) {minimum=distance;minimum_corner=corner;}
            if (distance>0.0f) masks[corner]|=outside_a;
            const float difference=previous_distance-distance;
            if (!(distance*previous_distance>0.0f) && (masks[edge]&(1u<<previous)) && std::fabs(difference)>std::numeric_limits<float>::min())
            {
                const float inverse=1.0f/difference;
                const Vec4 origin=Vertex(a,previous),direction=Load(a.data()+8+previous*16),length=Load(a.data()+16+previous*16);
                Vec4 point;
                for (unsigned lane=0;lane<4;++lane)
                {
                    const float numerator=length[lane]*previous_distance,along=inverse*numerator;
                    point[lane]=std::fma(direction[lane],along,origin[lane]);
                }
                Append(output,point,ProjectToFace(b,point));
            }
            previous=corner;previous_distance=distance;
        }
        if (minimum>largest_minimum) {largest_minimum=minimum;nearest_corner=minimum_corner;nearest_edge=edge;edge_is_a=false;}
    }
    for (std::size_t corner=0;corner<a_count;++corner)
        if (!(masks[corner]&outside_a)) {const Vec4 point=Vertex(a,corner);Append(output,point,ProjectToFace(b,point));}
    if (!output[132])
    {
        output[132]=edge_is_a ? IntersectFeatureCornerEdge(output,b,a,nearest_corner,nearest_edge,false)
                             : IntersectFeatureCornerEdge(output,a,b,nearest_corner,nearest_edge,true);
        const Vec4 delta=Sub(Load(output.data()+64),Load(output.data()));const float length=Length(delta);
        if (length>std::numeric_limits<float>::min()) {Store(output.data()+128,Scale(delta,1.0f/length));output[133]=1;}
    }
    return 1;
}
std::uint32_t SegmentPoint(FeaturePrism& output,MaximumFeature& segment,const MaximumFeature& point,bool segment_is_a)
{
    output[132]=1;std::copy_n(point.begin()+136,4,output.begin());std::copy_n(point.begin()+136,4,output.begin()+64);
    const std::size_t offset=segment_is_a ? 0:64;DirectionWords position;
    std::copy_n(output.begin()+offset,4,position.begin());
    const auto region=ClosestFeatureSegment(Segment(segment),position);segment[0]=(segment[0]-region)+2u;
    std::copy(position.begin(),position.end(),output.begin()+offset);return 1;
}
}

std::uint32_t ClosestFeatureSegment(const FeatureSegment& segment,DirectionWords& point)
{
    const Vec4 origin=Load(segment.data()),direction=Load(segment.data()+4),p=Load(point);
    const float along=Dot3(Sub(p,origin),direction);
    if (0.0f>along) {std::copy_n(segment.begin(),4,point.begin());return 1;}
    const Vec4 length=Load(segment.data()+12);
    const bool after=std::all_of(length.begin(),length.end(),[&](float v){return along>v;});
    for (unsigned i=0;i<4;++i) point[i]=Word(std::fma(direction[i],after ? length[i]:along,origin[i]));
    return after ? 3:2;
}
std::uint32_t IntersectPointFace(FeaturePrism& output,MaximumFeature& face,const MaximumFeature& point,
                               DirectionWords normal_words,bool face_is_a)
{
    output[132]=1;const Vec4 p=Load(point.data()+136),normal=Load(normal_words),origin=Vertex(face,0);
    const float distance=Dot3(normal,Sub(origin,p));Vec4 projected=Madd(normal,distance,p);
    if (static_cast<std::int32_t>(face[140])>0)
    {
        const std::size_t count=face[140];Require(count<=8);std::size_t selected=0;float worst=0.0f;
        for (std::size_t edge=0;edge<count;++edge)
        {
            const float distance=PlaneDistance(face,edge,projected);
            if (!edge || distance>worst) {worst=distance;selected=edge;}
        }
        if (worst>0.0f)
        {
            DirectionWords projected_words=Words(Sub(projected,Scale(Load(face.data()+12+selected*16),worst)));
            const auto region=ClosestFeatureSegment(Segment(face,selected),projected_words);
            face[0]+=static_cast<std::uint32_t>(selected)*2u+region;projected=Load(projected_words);
        }
    }
    const std::size_t face_offset=face_is_a ? 0:64,point_offset=face_is_a ? 64:0;
    Store(output.data()+face_offset,projected);std::copy_n(point.begin()+136,4,output.begin()+point_offset);return 1;
}
std::uint32_t ClampPointToFeature(const MaximumFeature& face,DirectionWords normal_words,DirectionWords& point)
{
    const Vec4 normal=Load(normal_words),p=Load(point);const auto signed_count=static_cast<std::int32_t>(face[140]);
    const std::size_t count=signed_count>0 ? signed_count:0;Require(count<=8);
    std::size_t selected=0;float minimum=0.0f;Vec4 selected_plane{};
    for (std::size_t edge=0;edge<count;++edge)
    {
        Vec4 plane=Cross3(normal,Load(face.data()+8+edge*16));
        if (Dot3(plane,plane)>Scalar(0x34000000)) plane=Normalized(plane);
        const float distance=Dot3(plane,Sub(p,Vertex(face,edge)));
        if (!edge || minimum>distance) {minimum=distance;selected=edge;selected_plane=plane;}
    }
    if (0.0f>minimum)
    {
        point=Words(Sub(p,Scale(selected_plane,minimum)));
        return ClosestFeatureSegment(Segment(face,selected),point)+static_cast<std::uint32_t>(selected)*2u;
    }
    return 0;
}
std::uint32_t ClipSegmentToFeature(const MaximumFeature& face,const MaximumFeature& segment,DirectionWords normal_words,
                                  std::array<std::uint32_t,2>& interval,std::array<std::uint32_t,8>& outside)
{
    interval[0]=0;interval[1]=std::isnan(Scalar(segment[16])) ? segment[16]|0x00400000u:segment[16];
    const Vec4 normal=Load(normal_words);const auto signed_count=static_cast<std::int32_t>(face[140]);
    const std::size_t count=signed_count>0 ? signed_count:0;Require(count<=8);bool rejected=false;
    for (std::size_t edge=0;edge<count;++edge)
    {
        Vec4 plane=Cross3(normal,Load(face.data()+8+edge*16));
        if (Length(plane)<Scalar(0x3a83126f)) continue;
        plane=Normalized(plane);const Vec4 origin=Vertex(face,edge);
        const float denominator=Dot3(Load(segment.data()+8),plane),numerator=Dot3(Sub(origin,Vertex(segment,0)),plane);
        if (std::fabs(denominator)<Scalar(0x3d4ccccd))
        {
            if (numerator>0.0f) {rejected=true;std::copy_n(face.begin()+4+edge*16,4,outside.begin());Store(outside.data()+4,plane);}
        }
        else
        {
            const float position=numerator/denominator;
            if (denominator>0.0f)
            {
                if (position>Scalar(interval[0])) interval[0]=Word(position);
                if (Scalar(interval[0])>Scalar(interval[1])) {interval[0]=interval[1];return 0;}
            }
            else
            {
                if (position<Scalar(interval[1])) interval[1]=Word(position);
                if (Scalar(interval[1])<Scalar(interval[0])) {interval[1]=interval[0];return 0;}
            }
        }
    }
    return !rejected;
}
std::uint32_t IntersectFeatureSegments(FeaturePrism& output,MaximumFeature& a,MaximumFeature& b,
                                     DirectionWords normal_words,bool a_is_first)
{
    const std::size_t ao=a_is_first ? 0:64,bo=a_is_first ? 64:0;
    const Vec4 ad=Load(a.data()+8),bd=Load(b.data()+8),start_a=Vertex(a,0),start_b=Vertex(b,0);
    const Vec4 perpendicular=Cross3(ad,bd);
    if (Dot3(perpendicular,perpendicular)>Scalar(0x34000000))
    {
        const Vec4 plane=Cross3(Normalized(perpendicular),bd);
        float along=Dot3(Sub(start_b,start_a),plane)/Dot3(ad,plane);
        if (along<0.0f) along=0.0f;
        const Vec4 length=Load(a.data()+16);
        if (std::all_of(length.begin(),length.end(),[&](float v){return along>v;})) along=length[0];
        output[132]=1;DirectionWords point=Words(Madd(ad,along,start_a));
        const auto b_region=ClosestFeatureSegment(Segment(b),point);b[0]=(b[0]-b_region)+2u;
        std::copy(point.begin(),point.end(),output.begin()+bo);
        const auto a_region=ClosestFeatureSegment(Segment(a),point);a[0]=(a[0]-a_region)+2u;
        std::copy(point.begin(),point.end(),output.begin()+ao);return 1;
    }
    const Vec4 normal=Load(normal_words);
    const Vec4 axis=std::fabs(Dot3(normal,ad))<std::fabs(Dot3(normal,bd)) ? ad:bd;
    const Vec4 end_a=End(a,0),end_b=End(b,0);
    const float a0=Dot3(axis,start_a),b0=Dot3(axis,start_b),a1=Dot3(axis,end_a),b1=Dot3(axis,end_b);
    const float amin=a1>a0 ? a0:a1,amax=a1>a0 ? a1:a0,bmin=b1>b0 ? b0:b1,bmax=b1>b0 ? b1:b0;
    const float low=amin>bmin ? amin:bmin,high=bmax>amax ? amax:bmax;
    if (high>low)
    {
        const Vec4 ap=Normalized(Cross3(Cross3(normal,ad),ad)),bp=Normalized(Cross3(Cross3(normal,bd),bd));
        const std::array<float,2> positions={low,high};
        for (std::size_t i=0;i<2;++i)
        {
            const Vec4 anchor=Scale(axis,positions[i]);
            for (unsigned pass=0;pass<2;++pass)
            {
                const auto offset=pass==0 ? ao:bo;const Vec4 origin=pass==0 ? start_a:start_b,direction=pass==0 ? ad:bd,plane=pass==0 ? ap:bp;
                const float inverse=RefinedReciprocal(Dot3(normal,plane),2),distance=inverse*Dot3(Sub(origin,anchor),plane);
                const Vec4 projected=Madd(normal,distance,anchor);
                Store(output.data()+offset+i*4,Madd(direction,Dot3(Sub(projected,origin),direction),origin));
            }
        }
        output[132]=2;
    }
    else
    {
        output[132]=1;const bool a_start=bmin>amin ? a0>a1:a0<a1,b_start=bmin>amin ? b0<b1:b0>b1;
        Store(output.data()+ao,Endpoint(a,a_start));Store(output.data()+bo,Endpoint(b,b_start));
    }
    return 1;
}
std::uint32_t IntersectSegmentFace(FeaturePrism& output,MaximumFeature& face,MaximumFeature& segment,
                                 DirectionWords normal_words,bool face_is_a)
{
    const std::size_t fo=face_is_a ? 0:64,so=face_is_a ? 64:0;
    std::array<std::uint32_t,2> interval{};std::array<std::uint32_t,8> outside{};
    const auto inside=ClipSegmentToFeature(face,segment,normal_words,interval,outside);
    const Vec4 normal=Load(normal_words),origin=Vertex(segment,0),direction=Load(segment.data()+8),face_origin=Vertex(face,0);
    const float low=Scalar(interval[0]),high=Scalar(interval[1]);
    if (inside)
    {
        output[132]=2;const Vec4 face_normal=Load(face.data()+132);const std::array<float,2> distances={low,high};
        for (std::size_t i=0;i<2;++i)
        {
            const Vec4 p=Madd(direction,distances[i],origin);Store(output.data()+so+i*4,p);
            const float t=Dot3(Sub(face_origin,p),face_normal)/Dot3(normal,face_normal);
            Store(output.data()+fo+i*4,Madd(normal,t,p));
        }
        return 1;
    }
    const float span=high-low;
    if (span>Scalar(0x3a83126f))
    {
        output[132]=2;const Vec4 outside_origin=Load(outside.data()),outside_plane=Load(outside.data()+4);
        Vec4 projected=Madd(normal,Dot3(normal,Sub(face_origin,origin)),origin);
        projected=Madd(outside_plane,Dot3(outside_plane,Sub(outside_origin,projected)),projected);
        DirectionWords first=Words(Madd(direction,low,projected)),second=Words(Madd(direction,span,Load(first)));
        const auto first_code=ClampPointToFeature(face,normal_words,first),second_code=ClampPointToFeature(face,normal_words,second);
        face[0]+=std::max(first_code,second_code)&~1u;
        std::copy(first.begin(),first.end(),output.begin()+fo);std::copy(second.begin(),second.end(),output.begin()+fo+4);
        ClosestFeatureSegment(Segment(segment),first);ClosestFeatureSegment(Segment(segment),second);
        std::copy(first.begin(),first.end(),output.begin()+so);std::copy(second.begin(),second.end(),output.begin()+so+4);
        const Vec4 delta=Sub(Load(output.data()+fo),Load(first));
        if (Length(delta)>std::numeric_limits<float>::min())
        {
            output[133]=1;Store(output.data()+128,Normalized(Cross3(direction,Cross3(delta,direction))));
        }
    }
    else
    {
        output[132]=1;const Vec4 p=Madd(direction,low,origin);
        DirectionWords point=Words(Madd(normal,Dot3(normal,Sub(face_origin,p)),p));
        const auto code=ClampPointToFeature(face,normal_words,point);face[0]+=code;
        std::copy(point.begin(),point.end(),output.begin()+fo);
        const auto region=ClosestFeatureSegment(Segment(segment),point);segment[0]=(segment[0]-region)+2u;
        std::copy(point.begin(),point.end(),output.begin()+so);
    }
    return 1;
}
std::uint32_t IntersectFeatureCornerEdge(FeaturePrism& output,MaximumFeature& a,MaximumFeature& b,
                                       std::size_t corner,std::size_t edge,bool a_is_first)
{
    const std::size_t ao=a_is_first ? 0:64,bo=a_is_first ? 64:0,previous=corner ? corner-1:a[140]-1u;
    Require(corner<8 && edge<8 && previous<8);
    const Vec4 bd=Load(b.data()+8+edge*16);std::size_t selected=previous;
    auto nearly_parallel=[&](std::size_t index){return Scalar(0x3d4ccccd)>std::fabs(Dot3(Load(a.data()+12+index*16),bd));};
    bool parallel=nearly_parallel(previous);
    if (!parallel) {selected=corner;parallel=nearly_parallel(corner);}
    const Vec4 b_origin=Vertex(b,edge);
    if (!parallel)
    {
        a[0]=static_cast<std::uint32_t>(corner)*2u+1u;b[0]=(static_cast<std::uint32_t>(edge)+1u)*2u;
        const Vec4 origin=Vertex(a,corner);float position=Dot3(bd,Sub(origin,b_origin));
        if (position<std::numeric_limits<float>::min()) {--b[0];position=0.0f;}
        else
        {
            const Vec4 length=Load(b.data()+16+edge*16);
            if (std::all_of(length.begin(),length.end(),[&](float v){return position>v;})) {++b[0];position=length[0];}
        }
        Store(output.data()+ao,origin);Store(output.data()+bo,Madd(bd,position,b_origin));return 1;
    }
    a[0]=(static_cast<std::uint32_t>(selected)+1u)*2u;b[0]=(static_cast<std::uint32_t>(edge)+1u)*2u;
    const Vec4 a_origin=Vertex(a,selected),ad=Load(a.data()+8+selected*16);
    const float distance=Dot3(ad,Sub(b_origin,a_origin));
    if (distance<std::numeric_limits<float>::min())
    {
        Store(output.data()+ao,a_origin);Store(output.data()+bo,b_origin);--a[0];--b[0];return 1;
    }
    const Vec4 al=Load(a.data()+16+selected*16),bl=Load(b.data()+16+edge*16);bool beyond=true;
    for (unsigned i=0;i<4;++i) if (!(std::numeric_limits<float>::min()>(al[i]+bl[i])-distance)) {beyond=false;break;}
    if (beyond) {Store(output.data()+ao,End(a,selected));Store(output.data()+bo,End(b,edge));++a[0];++b[0];return 1;}
    if (std::all_of(al.begin(),al.end(),[&](float v){return std::numeric_limits<float>::min()>v-distance;}))
    {
        Store(output.data()+ao,End(a,selected));Vec4 offset;
        for (unsigned i=0;i<4;++i) offset[i]=bd[i]*(al[i]-distance);
        Store(output.data()+bo,Sub(b_origin,offset));
    }
    else {Store(output.data()+ao,Madd(ad,distance,a_origin));Store(output.data()+bo,b_origin);}
    if (std::all_of(bl.begin(),bl.end(),[&](float v){return std::numeric_limits<float>::min()>v-distance;}))
    {
        Vec4 offset;for (unsigned i=0;i<4;++i) offset[i]=ad[i]*(bl[i]-distance);
        Store(output.data()+ao+4,Sub(a_origin,offset));Store(output.data()+bo+4,End(b,edge));
    }
    else {Store(output.data()+ao+4,a_origin);Store(output.data()+bo+4,Madd(bd,distance,b_origin));}
    return 2;
}
std::uint32_t FindFeatureIntersectionPrism(FeaturePrism& output,MaximumFeature& a,MaximumFeature& b,DirectionWords normal)
{
    const auto ae=a[140],be=b[140];Require(ae<=8 && be<=8);
    if (!ae && !be)
    {
        output[132]=1;std::copy_n(a.begin()+136,4,output.begin());std::copy_n(b.begin()+136,4,output.begin()+64);return 1;
    }
    if (ae==1 && !be) return SegmentPoint(output,a,b,true);
    if (!ae && be==1) return SegmentPoint(output,b,a,false);
    if (!ae) return IntersectPointFace(output,b,a,normal,false);
    if (!be) return IntersectPointFace(output,a,b,normal,true);
    if (ae==1 && be==1) return IntersectFeatureSegments(output,a,b,normal,true);
    if (ae==1) return IntersectSegmentFace(output,b,a,normal,false);
    if (be==1) return IntersectSegmentFace(output,a,b,normal,true);
    if (ae==4 && be==3) {if (SpecializedFaces(output,a,b,normal,true)) return 1;}
    else if (ae==3 && be==4) {if (SpecializedFaces(output,b,a,normal,false)) return 1;}
    else if (ae==4 && be==4) {if (SpecializedFaces(output,a,b,normal,true)) return 1;}
    return GeneralFaces(output,a,b);
}
}

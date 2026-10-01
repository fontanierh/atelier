// SPDX-License-Identifier: Apache-2.0
#include "OffboardGrabMath.h"
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
OffboardGrabDescriptor GrabRecordDescriptor(const OffboardGrabRecord& r){return {r.words[47],r.words[48]};}
std::array<Vec4,2> GrabRecordEndpoints(const OffboardGrabRecord& r){return {GrabRecordVector(r,64),GrabRecordVector(r,80)};}
std::optional<std::uint32_t> GrabRecordAssembly(const OffboardGrabRecord& r){return r.words[52]?std::optional<std::uint32_t>{r.words[52]}:std::nullopt;}
bool GrabRecordValid(const OffboardGrabRecord& r){return r.words[49]!=0;}
Vec4 GrabRecordVector(const OffboardGrabRecord& r,std::size_t offset){if(offset/4+4>r.words.size())std::abort();Vec4 v{};for(unsigned n=0;n<4;++n)v[n]=offboard_grab_math::Bits(r.words[offset/4+n]);return v;}
float GrabRecordScalar(const OffboardGrabRecord& r,std::size_t offset){if(offset/4>=r.words.size())std::abort();return offboard_grab_math::Bits(r.words[offset/4]);}
void SetGrabRecordVector(OffboardGrabRecord& r,std::size_t offset,Vec4 v){if(offset/4+4>r.words.size())std::abort();for(unsigned n=0;n<4;++n)r.words[offset/4+n]=offboard_grab_math::Word(v[n]);}
bool BuildGrabRecord(GrabRecordInput input,OffboardGrabRecord& output,std::string& error)
{
    using namespace offboard_grab_math;if(!input.geometry){error="Grab geometry needs a real identity and native byte-sized point counts";return false;}const auto& g=*input.geometry;
    if(g.id==0||g.points.empty()||g.points.size()>255||g.approach_vectors.size()>255){error="Grab geometry needs a real identity and native byte-sized point counts";return false;}
    const auto finite=[](Vec4 v){for(const auto lane:v)if(!std::isfinite(lane))return false;return true;};for(const auto& v:g.points)if(!finite(v)){error="Nonfinite authored grab geometry/frame";return false;}for(const auto& v:g.approach_vectors)if(!finite(v)){error="Nonfinite authored grab geometry/frame";return false;}for(const auto& v:input.frame)if(!finite(v)){error="Nonfinite authored grab geometry/frame";return false;}if(!finite(input.object_vector_128)){error="Nonfinite authored grab geometry/frame";return false;}
    OffboardGrabRecord r{{},input.geometry};for(unsigned n=0;n<4;++n)SetGrabRecordVector(r,n*16,input.frame[n]);r.words[47]=input.descriptor.kind;r.words[48]=input.descriptor.id;r.words[49]=g.id;r.words[50]=0x80000000;r.words[51]=g.word_60;r.words[68]=input.word_272;
    const auto start=Point(input.frame,g.points.front()),end=Point(input.frame,g.points.back());const auto approach=g.approach_vectors.empty()?Vec4{0,1,0,0}:g.approach_vectors.front();
    SetGrabRecordVector(r,64,start);SetGrabRecordVector(r,80,end);SetGrabRecordVector(r,96,Direction(input.frame,approach));SetGrabRecordVector(r,128,input.object_vector_128);SetGrabRecordVector(r,224,{1,1,1,1});r.words[60]=Word(1);r.words[61]=Word(1);r.words[62]=Word(std::numeric_limits<float>::max());r.words[63]=Word(std::numeric_limits<float>::max());
    if(input.assembly)
    {
        const auto& a=*input.assembly;if(a.identity==0){error="Zero assembly identity is reserved for native null";return false;}r.words[52]=a.identity;
        if(a.first_part){const auto& p=*a.first_part;if(p.identity==0){error="Zero part identity is reserved for native null";return false;}r.words[53]=p.identity;for(unsigned n=0;n<10;++n)r.words[56+n]=Word(p.coefficients_0_to_36[n]);if(p.rates){const auto& rates=*p.rates;if(rates.identity==0){error="Zero rates identity is reserved for native null";return false;}r.words[54]=rates.identity;r.words[50]|=0x40000000;SetGrabRecordVector(r,144,rates.vector_48);SetGrabRecordVector(r,160,rates.transform_position_48);}}
    }
    const auto delta=Sub(end,start);const auto straight=Length(delta),inverse=RecordReciprocal(straight);SetGrabRecordVector(r,112,Mul(delta,inverse));r.words[45]=Word(straight*.5f);float total=0;for(std::size_t n=1;n<g.points.size();++n)total+=Length(Sub(g.points[n],g.points[n-1]));r.words[44]=Word(total);output=std::move(r);error.clear();return true;
}
bool GrabObject::Record(const GrabSpline& spline,OffboardGrabRecord& output,std::string& error) const
{return BuildGrabRecord({spline.descriptor,spline.geometry,frame,object_vector_128,assembly?&*assembly:nullptr,spline.word_272},output,error);}
}

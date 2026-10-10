#include "GrindCamera.h"
#include <cstring>
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace {Vec4 FloatVector(RawVector a){Vec4 v;std::memcpy(v.data(),a.data(),16);return v;}RawVector Raw(Vec4 v){RawVector a;std::memcpy(a.data(),v.data(),16);return a;}}
void GrindCamera::ConditionFields(GrindOutputFields& out)
{
    if(out.grinding_316==0){active=false;return;}
    const auto point=FloatVector(out.point_16),direction=FloatVector(out.direction_0);
    const auto start=FloatVector(out.primitive_start_64),end=FloatVector(out.primitive_end_80);
    Vec4 next_midpoint;for(std::size_t i=0;i<4;++i)next_midpoint[i]=(start[i]+end[i])*0.5f;
    if(!active){error={};current=point;previous=point;}
    else if(out.words_136_140[0]!=family || next_midpoint[0]!=midpoint[0] || next_midpoint[1]!=midpoint[1] || next_midpoint[2]!=midpoint[2])
        for(std::size_t i=0;i<4;++i)error[i]=current[i]+(current[i]-previous[i])-point[i];
    for(float& v:error)v*=0.95f;
    previous=current;for(std::size_t i=0;i<4;++i)current[i]=point[i]+error[i];
    family=out.words_136_140[0];midpoint=next_midpoint;active=true;
    out.direction_0=Raw(direction);out.camera_target_96=Raw(current);
}
}

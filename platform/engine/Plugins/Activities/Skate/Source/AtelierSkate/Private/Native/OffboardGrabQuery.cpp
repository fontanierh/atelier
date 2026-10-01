// SPDX-License-Identifier: Apache-2.0
#include "OffboardGrabMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
bool OffboardGrabScene::Query(const OffboardGrabQuery& q,std::vector<OffboardGrabRecord>& output,std::string& error) const
{
    using namespace offboard_grab_math;if(q.mode!=4){error="This offboard provider implements native bounded mode4 only";return false;}if(q.capacity>32){error="Native grab query buffer capacity is32";return false;}
    const auto finite=[](Vec4 v){for(const auto x:v)if(!std::isfinite(x))return false;return true;};if(!finite(q.position)||!finite(q.sort_position)||!finite(q.bounds_extents)){error="Nonfinite grab query";return false;}for(const auto& v:q.bounds_frame)if(!finite(v)){error="Nonfinite grab query";return false;}
    const auto radius=Length(q.bounds_extents);const auto center=q.bounds_frame[3];std::vector<OffboardGrabRecord> records;records.reserve(32);
    for(const auto& object:registry_->objects)
    {
        if(object.disabled||!object.assembly_ready||!object.assembly)continue;
        if(object.provider==GrabProvider::Dmo){if(!object.record_enabled||std::uint32_t(object.selection_variant)!=((q.selection_flags_2948>>1)&1)||!(q.matching_id_2952==-1||object.matching_group==-1||object.matching_group==q.matching_id_2952))continue;}
        else{const auto d=Sub(object.frame[3],center);const auto limit=radius+15;if(Dot(d,d)>=limit*limit)continue;}
        for(const auto& spline:object.splines)
        {
            const auto& g=*spline.geometry;if(spline.descriptor.kind!=2||g.points.size()<2||g.approach_vectors.empty())continue;bool intersects=false;
            for(std::size_t n=1;n<g.points.size();++n){const auto delta=Sub(g.points[n],g.points[n-1]);if(Dot(delta,delta)>Bits(0x3727c5ac)&&SphereSegment(center,radius,Point(object.frame,g.points[n-1]),Point(object.frame,g.points[n]))){intersects=true;break;}}
            if(!intersects||records.size()==32)continue;OffboardGrabRecord r;if(!object.Record(spline,r,error))return false;if(QualifyGrabRecord(r,q.position,q.bounds_frame,q.bounds_extents,q.margin,q.angle_a,q.angle_b))records.push_back(std::move(r));
        }
    }
    for(auto& r:records){const auto delta=Sub(q.sort_position,ClosestGrabPoint(q.sort_position,GrabRecordEndpoints(r)));r.words[46]=Word(Dot(delta,delta));}
    for(std::size_t n=1;n<records.size();++n){auto j=n;while(j>0&&GrabRecordScalar(records[j],184)<GrabRecordScalar(records[j-1],184)){std::swap(records[j],records[j-1]);--j;}}
    if(records.size()>q.capacity)records.resize(q.capacity);output=std::move(records);error.clear();return true;
}
}

// SPDX-License-Identifier: Apache-2.0
#include "OffboardGrabRuntime.h"
#include "OffboardGrabMath.h"
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
void ValidateGrabRecords(std::vector<OffboardGrabRecord>& records,const std::vector<std::optional<OffboardGrabHit>>& hits)
{
    std::size_t record=0,hit=0;while(record<records.size())
    {
        const auto assembly=GrabRecordAssembly(records[record]);bool obstructed=false;
        for(unsigned n=0;n<3;++n){if(hit>=hits.size())std::abort();const auto& value=hits[hit];if(value)obstructed=!value->assembly||(assembly&&value->assembly!=assembly);++hit;if(obstructed)break;}
        // The original does not restart/round hit_index after swap_remove.
        if(obstructed){if(record+1<records.size())records[record]=std::move(records.back());records.pop_back();}else ++record;
    }
}
}
void OffboardGrabRuntime::Query(OffboardGrabQuery query)
{cache_.query_position=query.position;cache_.query_result.reset();cache_.queries.push_back(std::move(query));}
void OffboardGrabRuntime::RequestPrimary(OffboardGrabDescriptor descriptor)
{cache_.requests[0]=descriptor;cache_.data[0].reset();cache_.data_ready[0]=false;}
void OffboardGrabRuntime::RequestInteractable(Mat4 frame,OffboardGroundContext context)
{
    using namespace offboard_grab_math;std::array<OffboardGrabLine,5> lines;for(unsigned n=0;n<5;++n){auto start=frame[3];start[1]+=float(n)*Bits(0x3eb851eb);lines[n]={start,Madd(frame[2],2,start),.2f,context.matching_id_2952,0,2,context.selection_flags_2948};}
    if(!cache_.interactable_request)cache_.interactable_request=lines;cache_.interactable_result.reset();
}
bool OffboardGrabRuntime::ExecuteQueries(const OffboardGrabScene& scene,std::string& error)
{
    for(const auto& q:cache_.queries){std::vector<OffboardGrabRecord> result;if(!scene.Query(q,result,error))return false;cache_.query_result=std::move(result);}cache_.queries.clear();
    for(unsigned n=0;n<2;++n)if(cache_.requests[n]){const auto descriptor=*cache_.requests[n];cache_.requests[n].reset();std::optional<OffboardGrabRecord> record;if(!scene.Resolve(descriptor,record,error))return false;cache_.data[n]=std::move(record);cache_.data_ready[n]=true;}
    if(cache_.interactable_request)
    {
        const auto lines=*cache_.interactable_request;cache_.interactable_request.reset();auto nearest=std::numeric_limits<float>::max();std::optional<std::uint32_t> object;
        for(const auto& line:lines){std::optional<OffboardGrabHit> hit;if(!scene.Line(line,hit,error))return false;if(hit&&hit->fraction!=0&&hit->fraction<nearest&&hit->assembly){const auto id=scene.EligibleObject(*hit);if(id){nearest=hit->fraction;object=id;}}}
        cache_.interactable_result.emplace(object);
    }
    error.clear();return true;
}
bool OffboardGrabRuntime::Sync(const OffboardGrabScene& scene,OffboardGroundContext context,std::string& error)
{
    using namespace offboard_grab_math;cache_.flags_12836&=std::uint8_t(~0x40);
    if(cache_.validation)
    {
        auto hits=std::move(*cache_.validation);cache_.validation.reset();if((cache_.flags_12836&0x80)!=0)
        {
            ValidateGrabRecords(cache_.pending,hits);if(cache_.query_result)for(auto& old:cache_.pending)for(const auto& record:*cache_.query_result)if(Same(GrabRecordDescriptor(old),GrabRecordDescriptor(record))){old=record;break;}
        }
        cache_.validated=cache_.pending;cache_.flags_12836=((cache_.flags_12836>>1)&0x40)|(cache_.flags_12836&0x3f);cache_.validation_position={};
    }
    if(cache_.query_result)
    {
        auto results=std::move(*cache_.query_result);cache_.query_result.reset();if(results.size()>5)results.resize(5);cache_.pending=std::move(results);cache_.validation_position=cache_.query_position;cache_.query_position={};cache_.flags_12836|=0x80;
        std::vector<std::optional<OffboardGrabHit>> hits;hits.reserve(cache_.pending.size()*3);
        for(const auto& record:cache_.pending)
        {
            auto end=ClosestGrabPoint(cache_.validation_position,GrabRecordEndpoints(record)),start=cache_.validation_position;auto height=start[1]-Bits(0x3ecccccd);
            for(unsigned n=0;n<3;++n){start[1]=height;end[1]=height;std::optional<OffboardGrabHit> hit;if(!scene.Line({start,end,.2f,context.matching_id_2952,0,7,context.selection_flags_2948},hit,error))return false;hits.push_back(hit);height+=Bits(0x3ecccccd);}
        }
        cache_.validation=std::move(hits);
    }
    error.clear();return true;
}
OffboardGrabPublication OffboardGrabRuntime::Publish()
{
    OffboardGrabPublication output;for(unsigned n=0;n<2;++n){if(cache_.data_ready[n]&&cache_.data[n]&&GrabRecordValid(*cache_.data[n]))output.records[n]=cache_.data[n];cache_.data_ready[n]=false;}output.object=cache_.interactable_result;cache_.interactable_result.reset();if(output.object)cache_.interactable_latched=output.object->has_value();return output;
}
}

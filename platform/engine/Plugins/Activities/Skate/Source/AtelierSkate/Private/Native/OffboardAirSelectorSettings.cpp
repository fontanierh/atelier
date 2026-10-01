// SPDX-License-Identifier: Apache-2.0
#include "OffboardAirSelector.h"
#include "OffboardAirMath.h"
#include "StockSettingsReader.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
bool SelectorBlend(const StockSettingsReader& reader,PointGraph<8>& output,std::string& error)
{
    constexpr auto category="physics_state_offboard_air",name="TrajBlendAmountVsTime";const std::string path=std::string(category)+"/default/"+name;
    const auto* field=reader.Field(category,"default",name,error);if(!field)return false;
    if(field->type!="Sk8::PointNegGraphData8"){error="Expected PointNegGraphData8 at "+path;return false;}
    std::vector<std::uint32_t> words;
    if(!reader.Words(category,"default",name,20,words,error))
    {
        error=path+": "+(error=="Invalid collection payload: invalid digit found in string"?"invalid digit found in string":"Invalid native graph payload length");return false;
    }
    std::array<float,20> values{};for(std::size_t n=0;n<values.size();++n)values[n]=offboard_air_math::Bits(words[n]);
    for(const auto value:values)if(!std::isfinite(value)){error=path+": Non-finite native graph value";return false;}
    PointGraph<8> graph;for(std::size_t n=0;n<8;++n){graph.x[n]=values[4+n];graph.y[n]=values[12+n];}
    for(std::size_t n=1;n<8;++n)if(graph.x[n-1]>graph.x[n]){error=path+": Native graph X values are not ordered";return false;}
    output=graph;return true;
}
}
bool OffboardAirSelectorSettings::Load(const SettingsDatabase& data,std::string& error)
{
    OffboardAirSelectorSettings next;const StockSettingsReader reader(data);std::uint32_t start=0;
    if(!reader.Float("physics_state_offboard_air","default","Hash_AB0D9EAEBFC584E9",next.query.height,error)||
       !reader.Float("physics_state_offboard_air","default","TrajectorySphereRadius",next.query.sphere_radius,error)||
       !reader.Integer("physics_state_offboard_air","default","TrajectoryStartIndex",start,error))return false;
    next.query.start_index=static_cast<std::int32_t>(start);
    if(!std::isfinite(next.query.height)||!std::isfinite(next.query.sphere_radius)||next.query.sphere_radius<=0){error="Invalid stock BipedAir height/radius";return false;}
    if(!SelectorBlend(reader,next.blend,error)||!reader.Float("physics_grinds","default","DeckCenterToTruck",next.deck_center_to_truck,error))return false;
    if(!std::isfinite(next.deck_center_to_truck)||next.deck_center_to_truck<=0){error="Invalid stock DeckCenterToTruck";return false;}
    *this=std::move(next);error.clear();return true;
}
}

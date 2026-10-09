#include "ScoringData.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <set>
namespace atelier::skate
{
namespace
{
constexpr std::string_view ScorableClass="Hash_6918469984A8C596";
constexpr std::string_view ScoringTuningClass="Hash_349215E2E817703C";
float ScoringFloat(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
std::int32_t ScoringSigned(std::uint32_t word){std::int32_t value;std::memcpy(&value,&word,4);return value;}
bool ScoringCurve(const StockSettingsReader& reader,std::string_view category,std::string_view name,
    PointGraph<8>& output,std::string& error,bool validate)
{
    std::vector<std::uint32_t> words;if(!reader.Words(category,"default",name,20,words,error))return false;
    PointGraph<8> curve{};for(std::size_t i=0;i<8;++i){curve.x[i]=ScoringFloat(words[4+i]);curve.y[i]=ScoringFloat(words[12+i]);}
    if(validate)
    {
        bool invalid=false;
        for(std::size_t i=0;i<8;++i)invalid|=!std::isfinite(curve.x[i])||!std::isfinite(curve.y[i])||(i>0&&curve.x[i-1]>curve.x[i]);
        if(invalid){error="Invalid native scoring curve "+std::string(name);return false;}
    }
    output=curve;return true;
}
bool LoadCollector(const StockSettingsReader& reader,ScoringCollectorTuning& output,std::string& error)
{
    constexpr std::string_view category="Hash_546C36B656038E04";
    for(const auto& field:ScoringCollectorFields)
    {
        if(field.byte_count==4)
        {float value;if(!reader.Float(category,"default",field.name,value,error))return false;output.scalars.emplace(field.offset,value);}
        else
        {PointGraph<8> value;if(!ScoringCurve(reader,category,field.name,value,error,false))return false;output.curves.emplace(field.offset,value);}
    }
    return true;
}
}
bool ScoringData::Load(const SettingsDatabase& database,std::string& error)
{
    const StockSettingsReader reader(database);ScoringData next;std::set<std::uint64_t> available;
    const auto category=NameId(ScorableClass);
    for(const auto& row:database.Records())if(row.category_id==category)available.insert(row.key_id);
    for(std::size_t id=0;id<ScoringCatalog.size();++id)
    {
        const auto& entry=ScoringCatalog[id];if(!available.count(NameId(entry.identifier)))continue;
        const auto word=[&](std::string_view name,std::uint32_t& value){std::vector<std::uint32_t> words;if(!reader.Words(ScorableClass,entry.identifier,name,1,words,error))return false;value=words[0];return true;};
        std::uint32_t actual_id;if(!word("Hash_B2383F16252DFE8E",actual_id))return false;
        if(actual_id!=id){error="Scorable "+std::string(entry.identifier)+": enum "+std::to_string(id)+" disagrees with VLT "+std::to_string(actual_id);return false;}
        const auto* label=reader.Field(ScorableClass,entry.identifier,"Hash_843613E915014627",error);if(!label)return false;
        if(label->type!="EA::Reflection::Text"){error="Invalid scorable label "+std::string(entry.identifier);return false;}
        ScoringDefinition definition{};definition.metadata={id,entry.category,entry.score_type};definition.identifier=entry.identifier;
        definition.encoded_name=EncodeAnimationName(entry.identifier);std::uint32_t points,variant;
        if(!reader.Integer(ScorableClass,entry.identifier,"Hash_937F62AE5C1ED284",points,error))return false;
        definition.points=ScoringSigned(points);definition.label=label->text;
        if(!word("TrickType",definition.trick_type)
            ||!reader.Float(ScorableClass,entry.identifier,"Hash_DC7F402E5680BA02",definition.completion_delay,error)
            ||!word("Hash_2E90BC04042A0B5A",variant)||!word("Hash_D34A84B044B60CE3",definition.flags))return false;
        definition.variant=ScoringSigned(variant);next.definitions.push_back(std::move(definition));
    }
    if(next.definitions.empty()){error="No native scorable definitions in owned VLT data";return false;}
    if(!LoadCollector(reader,next.collector,error)
        ||!ScoringCurve(reader,ScoringTuningClass,"Hash_59D91EAABF033A24",next.repetition,error,true)
        ||!ScoringCurve(reader,ScoringTuningClass,"Hash_263B277F8CA17126",next.announcement,error,true))return false;
    const auto field=[&](std::string_view name,float& value){return reader.Float(ScoringTuningClass,"default",name,value,error);};
    if(!field("Hash_FE02A45231F7B06A",next.line_drain)||!field("Hash_57478337ACCFFF18",next.line_capacity)
        ||!field("Hash_88407506DC9780ED",next.combo_drain)||!field("Hash_28767A5F961C7129",next.combo_capacity)
        ||!field("Hash_829887D8C24A5B8A",next.combo_levels[0].first)||!field("Hash_4752056364FF91FE",next.combo_levels[0].second)
        ||!field("Hash_FB8408A15C17A9D4",next.combo_levels[1].first)||!field("Hash_F4993A13ED7B44C1",next.combo_levels[1].second)
        ||!field("Hash_30AAE071A7868771",next.combo_levels[2].first)||!field("Hash_DC0C3853F6C5FC2E",next.combo_levels[2].second)
        ||!field("Hash_E36197BFC8EA1CAD",next.combo_refresh_threshold)||!field("Hash_2577DF0FCE5251E4",next.unannounced_factor)
        ||!field("Hash_B0B56FF046508506",next.bail_factor)||!field("Hash_6DC5982591F80A4C",next.sketchy_side_speed))return false;
    *this=std::move(next);error.clear();return true;
}
ScoringSessionRules ScoringData::SessionRules() const
{return {combo_capacity,combo_levels,combo_refresh_threshold,line_capacity,bail_factor};}
const ScoringDefinition* ScoringData::ByName(const AttributeName& name) const
{const auto found=std::find_if(definitions.begin(),definitions.end(),[&](const ScoringDefinition& d){return d.encoded_name==name;});return found==definitions.end()?nullptr:&*found;}
const ScoringDefinition* ScoringData::ById(std::size_t id) const
{const auto found=std::find_if(definitions.begin(),definitions.end(),[&](const ScoringDefinition& d){return d.metadata.id==id;});return found==definitions.end()?nullptr:&*found;}
}

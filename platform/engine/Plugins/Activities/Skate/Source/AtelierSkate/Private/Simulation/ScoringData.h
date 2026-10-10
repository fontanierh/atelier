#pragma once
#include "ScoringCatalog.h"
#include "ScoringSession.h"
#include "AnimationName.h"
#include "StockSettingsReader.h"
#include <map>
namespace atelier::skate
{
struct ScoringDefinition
{
    ScoringScorable metadata;
    std::string_view identifier;
    AttributeName encoded_name;
    std::int32_t points;
    std::string label;
    std::uint32_t trick_type;
    float completion_delay;
    std::int32_t variant;
    std::uint32_t flags;
};
struct ScoringCollectorTuning
{
    std::map<std::uint16_t,float> scalars;
    std::map<std::uint16_t,PointGraph<8>> curves;
    float Scalar(std::uint16_t offset) const {return scalars.at(offset);}
    float Curve(std::uint16_t offset,float input) const {return curves.at(offset).Evaluate(input);}
};
class ScoringData
{
public:
    ScoringCollectorTuning collector;
    std::vector<ScoringDefinition> definitions;
    PointGraph<8> repetition,announcement;
    float line_drain{},line_capacity{},combo_drain{},combo_capacity{};
    std::array<std::pair<float,float>,3> combo_levels{};
    float combo_refresh_threshold{},unannounced_factor{},bail_factor{},sketchy_side_speed{};
    bool Load(const SettingsDatabase&,std::string& error);
    ScoringSessionRules SessionRules() const;
    const ScoringDefinition* ByName(const AttributeName&) const;
    const ScoringDefinition* ById(std::size_t id) const;
};
}

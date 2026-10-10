#include "GraphMotionSpecialConditions.h"
#include "Graph.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace
{
std::vector<std::uint8_t> File(const char* path) {std::ifstream f(path,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
struct Input:detail::DataReader
{
    explicit Input(const std::vector<std::uint8_t>& bytes):DataReader{bytes} {at=0;}
    bool Bool() {return Word()!=0;}
};
struct Output
{
    std::vector<std::uint8_t> bytes;
    void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) bytes.push_back(std::uint8_t(v>>(8*i)));}
    void String(std::string_view s) {Word(std::uint32_t(s.size()));bytes.insert(bytes.end(),s.begin(),s.end());}
};
}
int main(int argc,char** argv)
{
    if (argc!=3) return 2;std::string error;Graph graph;SettingsDatabase settings;GraphBinding binding;
    MotionGraphPrelandingConditionSettings preland_settings;
    if (!graph.Load(File(argv[1]),error) || !binding.Bind(graph,error) || !settings.Load(File(argv[2]),error) || !preland_settings.Load(settings,error)) {std::cerr<<error;return 2;}
    std::vector<GraphMotionSpecialCondition> conditions;
    for (const auto& op:binding.operations)
    {
        if (op.kind!=GraphOperationKind::Condition) return 2;GraphMotionSpecialCondition condition;bool recognized;
        if (!ParseGraphMotionSpecialCondition(GraphAttributes(graph.elements[op.element].attributes),condition,recognized,error) || !recognized) {std::cerr<<error;return 2;}
        conditions.push_back(std::move(condition));
    }
    std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input r(bytes);Output out;
    const auto frames=r.Word();out.Word(frames);out.Word(std::uint32_t(conditions.size()));
    for (std::uint32_t tick=0;tick<frames;++tick)
    {
        const auto mask=r.Word();
        const MotionGraphGrindConditionInputs g{r.Bool(),r.Word(),r.Word(),r.Word(),r.Bool(),r.Float(),r.Bool()};
        const MotionGraphLandingInputs l{r.Float(),r.Float(),r.Word(),r.Float()};
        const bool over=r.Bool();const auto collision=r.Float(),no_support=r.Float();const auto profile=r.Word();const bool below=r.Bool(),orientation=r.Bool();const auto y=r.Float(),right=r.Float(),up=r.Float();
        const MotionGraphWipeoutConditionInputs w{over,collision,no_support,profile,below,orientation?std::optional<float>(y):std::nullopt,right,up};
        const MotionGraphPrelandingInputs p{r.Bool(),r.Float(),r.Float(),r.Float(),r.Bool(),r.Bool(),r.Float(),r.Bool(),r.Float(),r.Float(),r.Float()};
        const auto grind=(mask&1)?std::optional<MotionGraphGrindConditionInputs>(g):std::nullopt;
        const auto landing=(mask&2)?std::optional<MotionGraphLandingInputs>(l):std::nullopt;
        const auto wipeout=(mask&4)?std::optional<MotionGraphWipeoutConditionInputs>(w):std::nullopt;
        const auto prelanding=(mask&8)?std::optional<MotionGraphPrelandingInputs>(p):std::nullopt;
        for (const auto& condition:conditions)
        {bool result;const bool success=condition.Evaluate({grind,landing,wipeout,prelanding,preland_settings},result,error);out.Word(result);out.String(success?"":error);}
    }
    if (!r.ok || r.at!=bytes.size()) return 2;std::cout.write(reinterpret_cast<const char*>(out.bytes.data()),std::streamsize(out.bytes.size()));return 0;
}

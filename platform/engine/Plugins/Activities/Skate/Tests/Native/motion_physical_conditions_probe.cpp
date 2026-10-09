#include "GraphMotionPhysicalConditions.h"
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
    Vec4 Vector() {Vec4 v;for (auto& x:v) x=Float();return v;}
    MotionGraphGameplayInputs Gameplay()
    {
        MotionGraphGameplayInputs p;
        p.state=Word();p.wants_runout=Bool();p.physics_wiping=Bool();p.body_flipping=Bool();p.wants_wipeout=Bool();p.bumped=Bool();
        p.grabbing_object=Bool();p.retrieving_board=Bool();p.dropping_board=Bool();p.in_biped_air=Bool();p.hippy_hurdling=Bool();
        p.handplant_flags=Word();p.handplant_time=Float();for (auto& x:p.handplant_thresholds) x=Float();
        p.footplant_active=Bool();p.footplant_duration=Float();p.footplant_contact_time=Float();p.time_to_skitch=Float();p.skitch_transition_time=Float();
        p.time_to_land=Float();p.time_to_land_valid=Bool();p.offboard_time_to_land=Float();p.offboard_air_scalar_92=Float();
        p.offboard_air_translation=Vector();p.offboard_landing_normal=Vector();p.offboard_committed_to_motion=Bool();
        p.offboard_obstacle_distance=Float();p.offboard_edge_distance=Float();p.offboard_trajectory_time=Float();p.offboard_trajectory_valid=Bool();
        p.reached_apex=Bool();p.can_land_on_board=Bool();p.landing_turning=Bool();p.grind_contact=Bool();p.wheel_contact=Bool();
        p.trucks_or_deck_contact=Bool();p.moving_object=Bool();p.tricks_blocked_on_stairs=Bool();return p;
    }
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
    if (argc!=4) return 2;std::string error;AnimationMetadata metadata,other;Graph graph;
    if (!metadata.Load(File(argv[1]),error) || !other.Load(File(argv[2]),error) || !metadata.Merge(other,error) || !graph.Load(File(argv[3]),error)) {std::cerr<<error;return 2;}
    GraphBinding binding;if (!binding.Bind(graph,error)) {std::cerr<<error;return 2;}
    std::vector<GraphMotionPhysicalCondition> conditions;
    for (const auto& op:binding.operations)
    {
        if (op.kind!=GraphOperationKind::Condition) return 2;
        GraphMotionPhysicalCondition condition;bool recognized;
        if (!ParseGraphMotionPhysicalCondition(GraphAttributes(graph.elements[op.element].attributes),condition,recognized,error) || !recognized) {std::cerr<<error;return 2;}
        conditions.push_back(std::move(condition));
    }
    MotionAnimation animation(std::move(metadata));std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input r(bytes);Output out;
    const auto frames=r.Word();out.Word(frames);out.Word(std::uint32_t(conditions.size()));
    for (std::uint32_t tick=0;tick<frames;++tick)
    {
        const auto mask=r.Word();MotionGraphPhysicalPublication p;const auto game=r.Gameplay();if (mask&1) p.gameplay=game;
        const auto stance=std::pair<bool,bool>{r.Bool(),r.Bool()};const auto loco=r.Word(),slope=r.Word();const bool thin=r.Bool(),held=r.Bool(),free=r.Bool(),manual=r.Bool();const auto height=r.Float();
        const MotionGraphRidingConditionInputs riding{r.Vector(),r.Vector(),r.Vector(),r.Float(),r.Float()};
        const GraphPushBrakeInputs push{r.Float(),r.Bool(),r.Float()};
        if (mask&2) p.physical_stance=stance;if (mask&4) p.offboard_locomotion_state=loco;if (mask&8) p.ground_slope_type=slope;
        if (mask&16) p.biped_ground_thin=thin;if (mask&32) {p.holding_board=held;p.free_board=free;}
        if (mask&64) p.manual_exit=manual;if (mask&128) p.animation_height_72=height;if (mask&512) p.conditions.push_brake=push;
        const auto completed_riding=(mask&256)?std::optional<MotionGraphRidingConditionInputs>(riding):std::nullopt;
        for (const auto& condition:conditions)
        {bool result;const bool success=condition.Evaluate({animation,p,completed_riding},result,error);out.Word(result);out.String(success?"":error);}
    }
    if (!r.ok || r.at!=bytes.size()) return 2;std::cout.write(reinterpret_cast<const char*>(out.bytes.data()),std::streamsize(out.bytes.size()));return 0;
}

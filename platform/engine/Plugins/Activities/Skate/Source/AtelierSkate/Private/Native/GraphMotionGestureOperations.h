#pragma once
#include "GraphMotionName.h"
#include "Graph.h"
#include "MotionAnimation.h"
namespace atelier::skate
{
struct MotionGraphGesturePublication {std::uint32_t gesture;bool down;};
struct MotionGraphCharacterGesturePhysical
{
    bool ground321,state_offboard75;
    std::optional<std::array<std::uint32_t,4>> selections;
    bool suppress_up,force_brake_bypass;
};
struct MotionGraphCharacterGestureInputs
{
    const IntentMap& motion_intents;
    std::array<std::uint32_t,2> busy_hands;
    std::uint32_t filtered_state;
    bool ground321,board_held311,state_offboard75;
    float distance_to_cog;
    std::optional<std::array<std::uint32_t,4>> selections;
    bool suppress_up,force_brake_bypass;
};
class MotionGraphCharacterGestureState
{
public:
    void End(MotionAnimation&);
    bool Update(MotionAnimation&,const MotionGraphCharacterGestureInputs&,std::optional<MotionGraphGesturePublication>& output,std::string& error);
private:
    bool active_=false;
    std::int32_t stage_=-1,direction_=-1,hands_=-1;
    void ClearActive() {active_=false;direction_=-1;hands_=-1;}
    bool NextStage(MotionAnimation&,const MotionGraphCharacterGestureInputs&,std::int32_t,std::string& error);
};
struct MotionCharacterGestureContext
{
    MotionAnimation& animation;
    std::array<std::uint32_t,2> busy_hands;
    const std::optional<MotionGraphCharacterGesturePhysical>& physical;
    std::optional<std::uint32_t> filtered_category;
    const PlaybackContext& playback;
    std::optional<float> animation_height;
    std::optional<MotionGraphGesturePublication>& publication;
};
// CharacterGesture has no Begin/End action. EndGesture's Begin loops every
// allocated CharacterGesture instance (including inactive owners), calls End
// in host instance order, then clears the one graph-wide publication.
bool ExecuteMotionGraphCharacterGesture(MotionGraphCharacterGestureState&,MotionCharacterGestureContext,std::uint8_t phase,std::string& error);
enum class MotionGraphGestureOperation {Character,End};
bool ParseMotionGraphGestureOperation(const GraphAttributes&,MotionGraphGestureOperation&,bool& recognized,std::string& error);
std::string_view MotionGraphGestureCatalogName(std::uint32_t);

struct GraphMotionShoveOperation
{
    std::string selection,selection_board,anticipation,anticipation_board;
};
struct MotionGraphShovePhysical
{
    bool interaction_trigger;
    Vec4 direction;
    bool in_biped_category,board_on_ground;
    float animation_height;
};
struct MotionGraphShoveState
{
    float angle=0;
    bool board_anticipation=false;
    void Begin() {angle=0;board_anticipation=false;}
    bool Update(const GraphMotionShoveOperation&,MotionAnimation&,MotionGraphShovePhysical,std::array<std::uint32_t,2> busy_hands,bool mirrored,std::string& error);
    void End(MotionAnimation&,bool keep_channels);
};
struct MotionShoveOperationContext
{
    MotionAnimation& animation;
    const std::optional<MotionGraphShovePhysical>& physical;
    std::array<std::uint32_t,2> busy_hands;
    const PlaybackContext& playback;
    bool keep_channels;
};
bool ParseGraphMotionShoveOperation(const GraphAttributes&,GraphMotionShoveOperation&,bool& recognized,std::string& error);
bool ExecuteGraphMotionShoveOperation(const GraphMotionShoveOperation&,MotionGraphShoveState&,MotionShoveOperationContext,std::uint8_t phase,std::string& error);
float MotionGraphShoveDirectionAngle(Vec4 direction,bool mirrored);
}

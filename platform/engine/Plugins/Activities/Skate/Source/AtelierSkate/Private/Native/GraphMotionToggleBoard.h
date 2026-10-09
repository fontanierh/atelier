#pragma once
#include "Graph.h"
#include "GraphMotionName.h"
#include "MotionAnimation.h"
#include <optional>
namespace atelier::skate
{
enum class MotionGraphToggleBoardPhase {Idle,RetrieveStart,RetrieveInto,RetrieveCycle,RetrieveOut,DropStart,DropPlaying};
enum class MotionGraphToggleBoardClip {Throw,Drop,FrontInto,FrontCycle,FrontOut,BackInto,BackCycle,BackOut};
struct MotionGraphToggleBoardInput
{
    bool grabbing_object,holding_board,retrieval_blocked,retrieval_active;
    bool drop_requested,throw_requested,retrieve_requested;
    float yaw_radians,pitch_radians;
    bool mirrored;
};
struct MotionGraphToggleBoardPhysical
{
    bool grabbing_object,holding_board,free_board,retrieval_blocked,retrieval_active;
    float yaw_radians,pitch_radians;
};
struct MotionGraphToggleBoardChannel {bool exists;float remaining,elapsed;};
struct MotionGraphToggleBoardCommand
{
    enum class Kind {Blend,Sequence,Stop};
    Kind kind;
    MotionGraphToggleBoardClip clip;
    float blend_seconds;
};
struct MotionGraphToggleBoardOutput
{
    bool retrieving=false,dropping=false,retrieve=false;
    std::optional<std::array<float,2>> yaw_pitch;
    std::optional<MotionGraphToggleBoardCommand> channel;
};
class MotionGraphToggleBoardState
{
public:
    MotionGraphToggleBoardPhase phase=MotionGraphToggleBoardPhase::Idle;
    void Begin();
    MotionGraphToggleBoardOutput Update(MotionGraphToggleBoardInput,MotionGraphToggleBoardChannel);
private:
    float previous_yaw_=0,yaw_=0,pitch_=0;
    bool initialized_yaw_=false,back_=false,throwing_=false;
    void ResetOrientation();
    void Orientation(MotionGraphToggleBoardInput);
    void Cycle(MotionGraphToggleBoardOutput&);
    void Stop(MotionGraphToggleBoardOutput&);
};
std::string_view MotionGraphToggleBoardClipName(MotionGraphToggleBoardClip);
bool ParseGraphMotionToggleBoard(const GraphAttributes&,bool& recognized,std::string& error);
bool ExecuteGraphMotionToggleBoard(MotionGraphToggleBoardState&,MotionAnimation&,
    const std::optional<MotionGraphToggleBoardPhysical>&,std::uint8_t phase,std::string& error);
}

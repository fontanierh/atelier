// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GraphMotionConditions.h"
#include <map>
namespace atelier::skate
{
struct MotionGraphScorePacket
{
    using NamedVector=std::pair<AttributeName,std::array<float,2>>;
    std::optional<NamedVector> handplant,grab;
    std::array<std::optional<AttributeName>,2> trick_names;
    std::optional<std::uint32_t> name;
    std::uint32_t flags=0;
    void Set(std::uint32_t value);
};
class MotionGraphMovingObjectRegistry
{
public:
    std::map<std::uint32_t,std::string> objects;
    std::optional<std::uint32_t> active;
    std::uint32_t Register(std::string_view path);
    bool Begin(std::string_view path,std::string& error);
    bool Update(std::string_view path,bool& enabled,std::string& error) const;
    void End() {active.reset();}
    bool Active() const {return bool(active);}
};
struct MotionScoreOperationContext
{
    MotionAnimation& animation;
    MotionConditionRandom& random;
    MotionGraphScorePacket& score;
    MotionGraphMovingObjectRegistry& moving_objects;
    const PlaybackContext& playback;
    const std::pair<bool,bool>& trick_height_settings;
};
struct GraphMotionScoreOperation
{
    enum class Kind {Unsupported,ScoringTrick,ScoringGrabs,ScoringHandPlants,ScoreAugmentation,TrickHeight,TrickAttribute,
        TweakProject,RandomLanding,EndShimmy,InitMovingObjects,MovingObject};
    Kind kind=Kind::Unsupported;
    AttributeName name{},rename{};
    std::string base,path;
    std::array<std::optional<std::string>,4> directions;
    std::array<std::string,2> intents;
    std::optional<float> value;
    std::array<std::uint32_t,2> augmentation{};
    std::int32_t count=1;
    bool manual=false,grind=false,invert_y=false,polar=false;
    bool Execute(MotionScoreOperationContext,std::uint8_t phase,std::string& error) const;
};
bool ParseGraphMotionScoreOperation(const GraphAttributes&,GraphMotionScoreOperation&,bool& recognized,std::string& error);
std::string_view SelectGraphMotionGrabScore(std::string_view base,const std::array<std::optional<std::string>,4>& directions,float x,float y);
}

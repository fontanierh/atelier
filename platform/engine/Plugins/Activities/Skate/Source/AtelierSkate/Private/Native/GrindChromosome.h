// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "PlayerGrindInput.h"
#include <deque>
namespace atelier::skate
{
struct GrindApproachPose {Vec4 right,position;std::array<Vec4,2> feet;bool fakie;};
struct GrindChromosomeInput
{
    std::uint32_t category;bool grinding_316,air_event_439;std::optional<PlayerGrindFamily> family;
    Vec4 basic_right_0,basic_forward_32,basic_position_48,basic_location_axis_96,basic_twist_axis_128,basic_location_position_144;
    std::array<Vec4,2> feet_256_272;bool fakie_155;Vec4 point,direction,normal,across;
};
using GrindComponents=std::array<std::uint32_t,6>;
struct GrindChromosomePublication {GrindComponents volatile_components;std::optional<GrindComponents> animation,scoring;};
class GrindChromosome
{
public:
    std::deque<GrindApproachPose> history;
    GrindApproachPose saved{{1,0,0,0},{},{{Vec4{{1,0,0,0}},Vec4{{1,0,0,0}}}},false};
    bool saved_fakie_initialized=false;
    std::uint32_t approach=0,previous_category=0;
    std::optional<PlayerGrindFamily> previous_kind;
    std::int32_t away_frames=31;bool reversed=false;
    std::optional<std::uint32_t> orientation;
    std::optional<GrindComponents> pending,animation,scoring;std::int32_t pending_frames=0;
    void InitializeHostFakie(bool);
    bool Update(GrindChromosomeInput,std::optional<GrindChromosomePublication>& output,std::string& error);
    bool Publish(const GrindChromosomePublication&,GrindOutputFields&,std::string& error) const;
private:
    GrindApproachPose Reference() const;
    bool Travel(GrindChromosomeInput,PlayerGrindFamily,std::uint32_t&,std::string& error);
};
}

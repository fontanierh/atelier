// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "PlayerSceneProbe.h"
#include "TeleportStateRuntime.h"
#include "Settings.h"
namespace atelier::skate
{
struct RespawnCandidate {Mat4 transform;std::uint32_t stance;bool offboard;float score;};
struct RespawnGround {Vec4 position;bool offboard;};
struct RespawnObservation
{
    std::int32_t measurements;
    Vec4 root_position,com_position;
    bool teleport_requested;
    std::uint32_t physical_state,state_frames;
    bool ground_suppressed,offboard_correction;
    std::uint32_t ground_category;
    std::array<std::uint32_t,2> foot_categories;
    Mat4 riding_transform,offboard_transform;
    std::uint32_t stance;
    bool alternate_world;
};
class RespawnValidation
{
public:
    virtual ~RespawnValidation()=default;
    virtual bool Ground(const Mat4&,std::optional<RespawnGround>&,std::string&)=0;
    virtual bool Location(const Mat4&,bool&,std::string&)=0;
    virtual bool Occupants(const Mat4&,bool&,std::string&)=0;
    virtual bool Edges(const Mat4&,bool&,std::string&)=0;
};
bool RespawnSurfaceAllowed(std::uint32_t);
float RespawnSurfaceScore(std::uint32_t);
class RespawnHistory
{
public:
    explicit RespawnHistory(RespawnCandidate);
    Mat4 current_orientation;
    Vec4 current_position;
    bool Observe(const RespawnObservation&,std::uint32_t minimum_state_frames,RespawnValidation&,std::string&);
    bool RecordingDue(std::int32_t measurements,Vec4 root_position);
    void Insert(RespawnCandidate);
    bool Automatic(std::uint32_t stance,RespawnValidation&,std::optional<RespawnCandidate>& output,std::string&);
    const RespawnCandidate& Initial() const {return initial_;}
    const std::vector<RespawnCandidate>& Entries() const {return entries_;}
    std::int32_t Cooldown() const {return cooldown_;}
private:
    RespawnCandidate initial_;
    std::vector<RespawnCandidate> entries_;
    std::int32_t cooldown_=20;
    std::optional<RespawnCandidate> PopBest();
};
struct RespawnSettings
{
    float height,radius,drop,normal_y;
    std::uint32_t minimum_frames;
    bool Load(const SettingsDatabase&,std::string&);
};
// Full concrete current static-scene predicates. Normal-world Location=true
// and absent living actors are original host constants; metadata is required.
class RespawnScene final:public RespawnValidation
{
public:
    RespawnScene(const WorldGeometry& world,const RespawnSettings& settings):world_(world),settings_(settings){}
    bool Ground(const Mat4&,std::optional<RespawnGround>&,std::string&) override;
    bool Location(const Mat4&,bool&,std::string&) override;
    bool Occupants(const Mat4&,bool&,std::string&) override;
    bool Edges(const Mat4&,bool&,std::string&) override;
private:
    const WorldGeometry& world_;
    const RespawnSettings& settings_;
};
Mat4 RespawnHeading(Mat4,Vec4 velocity);
void RespawnFlip(Mat4&);
class PhysicalSimulationRuntime;
class PlayerInputRuntime;
class SkaterAnimation;
// Required source producers: the current selector's actual state_count and
// Biped contact.active. Neither is inferred from a physical state or terrain.
struct RespawnCompletedState {std::uint32_t state_frames;bool offboard_contact_active;};
class RespawnRuntime
{
public:
    static std::optional<RespawnRuntime> Load(const SettingsDatabase&,Mat4 initial,std::uint32_t stance,std::string&);
    void ResetMeasurements(){measurements_=0;}
    bool Observe(const PhysicalSimulationRuntime&,const PlayerInputRuntime&,const SkaterAnimation&,RespawnCompletedState,std::string&);
    bool Request(const WorldGeometry&,SkaterAnimation&,TeleportStateRuntime&,std::string&);
    const RespawnHistory& History() const {return history_;}
    RespawnHistory& History(){return history_;}
    const RespawnSettings& Settings() const {return settings_;}
    std::int32_t Measurements() const {return measurements_;}
private:
    explicit RespawnRuntime(RespawnCandidate c,RespawnSettings s):history_(c),settings_(s){}
    RespawnHistory history_;
    RespawnSettings settings_;
    std::int32_t measurements_=0;
};
}

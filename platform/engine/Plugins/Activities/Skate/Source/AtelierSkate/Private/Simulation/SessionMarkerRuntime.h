#pragma once
#include "ControllerInputRuntime.h"
#include "GameplayRuntime.h"
namespace atelier::skate
{
struct SessionMarkerHoldStep {float progress=0;bool relocate=false;};
struct SessionMarkerHold
{
    float elapsed=0;
    bool fired=false;
    std::uint8_t tail=0;
    void Cancel(){*this={};}
    SessionMarkerHoldStep Update(bool held,bool usable,float distance,bool ready);
};
struct SessionMarkerValidation
{
    float slope=0,max_drop=0,clearance_length=0,clearance_radius=0;
    bool Load(const SettingsDatabase&,std::string& error);
    bool Check(const WorldGeometry&,Vec4 position) const;
};
class SessionMarkerRuntime
{
public:
    struct Marker {Mat4 transform;bool on_board,foot_forward;std::uint64_t generation;};
    SessionMarkerValidation validation;
    std::optional<Marker> marker;
    SessionMarkerHold hold;
    std::uint64_t generation=0,last_batch=0;
    bool visible=false,can_place=false,can_return=false,blocked_until_release=false;
    float progress=0;
    double ui_time=0;
    bool Load(const SettingsDatabase&,std::string& error);
    void Suspend();
    void CollectTime(double dt){ui_time+=dt;}
    void Advance(const ControllerInputRuntime&,GameplayRuntime&);
};
}

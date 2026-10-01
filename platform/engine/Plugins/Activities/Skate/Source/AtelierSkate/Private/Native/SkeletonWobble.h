// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "SkeletonPoseFrames.h"
#include "Settings.h"
#include <optional>
#include <string>
namespace atelier::skate
{
struct SkeletonWobbleSettings
{
    PointGraph<8> takeoff_tilt,landing_tilt,takeoff_squish,landing_squish;
    float maximum_time;
    static std::optional<SkeletonWobbleSettings> Load(const SettingsDatabase&,std::string& error);
};
struct SkeletonWobbleOutput
{
    bool sampled=false;
    float tilt=0,squish=0;
    bool remains_active=false;
};
class SkeletonWobble
{
public:
    bool active=false,landing=false;
    float time=0,amplitude=0,direction=1;
    void Trigger(bool landing,bool reverse);
    SkeletonWobbleOutput Update(const SkeletonWobbleSettings&);
    void ResetForTeleport();
    bool SelectedLandingCurves() const {return selected_landing_curves_;}
private:
    bool selected_landing_curves_=true;
};
// This alters the observed board record, never the physical deck body.
void ApplySkeletonWobble(SkeletonWobbleOutput,Mat4& observed_board);
}

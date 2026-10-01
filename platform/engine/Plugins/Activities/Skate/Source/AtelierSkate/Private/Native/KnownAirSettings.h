// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "KnownAirTypes.h"
#include "Settings.h"
namespace atelier::skate
{
struct KnownAirConfiguration
{
    KnownAirSettings settings;
    std::array<KnownAirModeSettings,5> modes;
    KnownAirWipeoutSettings wipeout;
    Vec4 flip_axis_adjustment;
};
bool LoadKnownAirConfiguration(const SettingsDatabase&,KnownAirConfiguration&,std::string& error);
}

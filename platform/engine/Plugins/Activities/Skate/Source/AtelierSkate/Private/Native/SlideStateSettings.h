// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "SlideState.h"
#include "GeometryTypes.h"
#include "Settings.h"
namespace atelier::skate
{
struct SlideSurfaceProfile {SlideSurface surface;ContactMaterial material;};
struct SlideStateSettings
{
    SlideSettings settings;
    std::array<SlideSurfaceProfile,5> surfaces;
    float manual_scalar;
    bool Load(const SettingsDatabase&,std::string& error);
    bool Surface(std::uint32_t mode,const SlideSurfaceProfile*& output,std::string& error) const;
};
}

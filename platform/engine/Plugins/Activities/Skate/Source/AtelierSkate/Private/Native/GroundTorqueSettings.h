// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "SlideFriction.h"
#include "Straighten.h"
#include "Heading.h"
#include "AntiFlip.h"
#include "Settings.h"
namespace atelier::skate
{
struct GroundTorqueSettings
{
    SlideFrictionSettings slide;
    StraightenSettings straighten;
    HeadingSettings heading;
    AntiFlipSettings anti_flip;
    // SurfacePhysics owns normalization/selection; this loads its actual key.
    bool Load(const SettingsDatabase&,std::string_view surface_key,std::string& error);
};
}

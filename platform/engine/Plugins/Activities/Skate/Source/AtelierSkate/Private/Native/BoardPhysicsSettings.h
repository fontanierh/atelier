// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "BoardRuntime.h"
#include "DeckGeometry.h"
#include "Settings.h"

namespace atelier::skate
{
struct BoardCollisionSettings
{
    DeckGeometry deck_geometry{DeckGeometrySettings::Stock()};
    MassShape truck_shape{};
    bool truck_collisions=false;
    ContactMaterial truck_material{},deck_material{},wheel_material{};
    float wheel_radius=0;
};
struct BoardPhysicsSettings
{
    BoardStepSettings step{};
    std::array<BodyMassProperties,BoardBodyCount> masses{};
    std::array<AffineTransform,BoardBodyCount> authored{};
    BoardCollisionSettings collision;
    ContactMaterial standard_wheel_material{},floor_material{};
    float input_magnitude_threshold=0;
    static std::optional<BoardPhysicsSettings> Load(const SettingsDatabase&,std::string& error);
};
}

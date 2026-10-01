// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "LandingOnDeckState.h"
#include "SkeletonLanding.h"
namespace atelier::skate
{
struct LandingOnDeckConfiguration
{
    LandingOnDeckSettings state;LandingOnBoardSettings root;
    bool Load(const SettingsDatabase&,std::string& error);
};
}

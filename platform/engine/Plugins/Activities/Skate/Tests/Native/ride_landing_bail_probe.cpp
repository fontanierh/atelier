// SPDX-License-Identifier: Apache-2.0
// Native's bad-landing and DangerZone limits (WipeoutBadLanding's and CheckWipeoutAir's settings), as
// WipeoutSettings.cpp's loader reads them from a stock settings.skate, for the check of Ride's landing bail
// (Private/Ride/RideSession.cpp's LandingAngleCurve and the Bail* fields of RideTuning.h) against them.
//
// usage: ride_landing_bail_probe settings.skate [speed ...]
//
// Floats are printed as their binary32 bits in hex. Output, one record per line:
//   curve x y                                       (max_landing_angle's points: m/s, radians)
//   mode index check_bad_landing bad_landing_scale  (easy, normal, hardcore, motorized, test)
//   limits max_landing_speed max_stairs_speed max_grind_speed
//   danger xz_trick y_trick ignore_danger_frames      (the last in decimal)
//   eval speed angle                                (max_landing_angle.Evaluate at each speed given)
#include "WipeoutSettings.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
using namespace atelier::skate;

namespace
{
unsigned Bits(float value)
{
    unsigned out;
    std::memcpy(&out, &value, 4);
    return out;
}
}

int main(int argc, char** argv)
{
    if (argc < 2) { std::fprintf(stderr, "usage: ride_landing_bail_probe settings.skate [speed ...]\n"); return 2; }
    std::ifstream in(argv[1], std::ios::binary);
    const std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    SettingsDatabase data;
    std::string error;
    if (!data.Load(bytes, error)) { std::fprintf(stderr, "settings: %s\n", error.c_str()); return 1; }
    WipeoutSettings settings;
    std::array<WipeoutMode, 5> modes;
    if (!LoadWipeoutSettings(data, settings, modes, error)) { std::fprintf(stderr, "wipeout: %s\n", error.c_str()); return 1; }
    const auto& air = settings.air;
    for (std::size_t i = 0; i < air.max_landing_angle.x.size(); ++i)
        std::printf("curve %08x %08x\n", Bits(air.max_landing_angle.x[i]), Bits(air.max_landing_angle.y[i]));
    for (std::size_t i = 0; i < modes.size(); ++i)
        std::printf("mode %zu %d %08x\n", i, modes[i].check_bad_landing ? 1 : 0, Bits(modes[i].bad_landing_scale));
    std::printf("limits %08x %08x %08x\n", Bits(air.max_landing_speed), Bits(air.max_stairs_speed), Bits(air.max_grind_speed));
    std::printf("danger %08x %08x %d\n", Bits(air.xz_trick), Bits(air.y_trick), int(air.ignore_danger_frames));
    for (int i = 2; i < argc; ++i)
    {
        const float speed = std::strtof(argv[i], nullptr);
        std::printf("eval %08x %08x\n", Bits(speed), Bits(air.max_landing_angle.Evaluate(speed)));
    }
    return 0;
}

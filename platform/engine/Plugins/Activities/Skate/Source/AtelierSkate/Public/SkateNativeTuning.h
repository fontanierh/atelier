#pragma once
#include "SkateNative.h"

// Selected retail controller constants and all 78 authored skater.pat variants.
// The variants intentionally repeat names; the recognizer chooses the best fitting path.
// Provenance, source revision and adapter limitations: NATIVE_PORT.md.
namespace SkateNative
{
enum class Difficulty { Easy, Normal, Hardcore };
inline Settings RetailSettings(Difficulty Mode = Difficulty::Normal)
{
    Settings S;
    // physics_steering
    S.HardTurnIncrease=1.f;
    S.Damping=0.699999988f;
    S.SpeedGraphMax=50.f;
    S.PushIncrement=0.0500000007f;
    S.PushDecrement=0.0149999997f;
    S.PushSteerMin=0.5f;
    S.GeneralSteer=0.600000024f;
    S.TightTrucks=0.699999988f;
    S.TiltBlend=0.200000003f;
    S.SteerSpeed.Count=8;
    S.SteerSpeed.X={0.0569550917f, 0.123767801f, 0.173055902f, 0.219058096f, 0.297918886f, 0.400000006f, 0.5f, 1.f};
    S.SteerSpeed.Y={1.f, 0.969594598f, 0.847972989f, 0.608108103f, 0.395270288f, 0.300000012f, 0.280000001f, 0.270000011f};
    S.SteerInput.Count=8;
    S.SteerInput.X={0.f, 0.05859375f, 0.25f, 0.375f, 0.508789122f, 0.690429688f, 0.857715428f, 1.f};
    S.SteerInput.Y={0.f, 0.f, 0.0337837897f, 0.0777027011f, 0.172297299f, 0.334459513f, 0.564189196f, 0.834459424f};
    // physics_manual
    S.ManualSteer=0.600000024f;
    S.ManualP=0.0500000007f;
    S.ManualI=0.0299999993f;
    S.ManualD=-0.800000012f;
    S.ManualMaxAngle=24.f;
    S.ManualMaxError=0.100000001f;
    S.ManualDerivativeLimit=0.0399999991f;
    S.ManualStartTorque=0.f;
    S.ManualNoise=0.0500000007f;
    S.ManualFrequency=1.5f;
    S.ManualBleed=0.959999979f;
    S.ManualNoContact=0.f;
    S.ManualNoiseSpeed.Count=8;
    S.ManualNoiseSpeed.X={0.f, 1.31921804f, 2.52443004f, 3.90879512f, 5.35830498f, 6.82410479f, 7.85016298f, 10.f};
    S.ManualNoiseSpeed.Y={0.292857111f, 0.378571391f, 0.485714287f, 0.617857218f, 0.821428597f, 0.949999988f, 1.f, 1.f};
    // physics_push
    S.MaxPushSpeed=8.5f;
    // physics_pumping
    S.PumpSpeed.Count=8;
    S.PumpSpeed.X={0.f, 2.44951105f, 4.56026077f, 7.00977182f, 8.80781746f, 10.6840401f, 12.1954403f, 14.2019501f};
    S.PumpSpeed.Y={4.f, 2.44285703f, 1.10000002f, 1.f, 0.964285672f, 0.571428597f, 0.157142907f, 0.00714285718f};
    S.PumpTime.Count=8;
    S.PumpTime.X={0.f, 0.402280092f, 0.506514728f, 0.571661174f, 0.653094471f, 0.741042316f, 0.861563504f, 0.995114028f};
    S.PumpTime.Y={1.f, 1.f, 0.896428585f, 0.732142925f, 0.432142913f, 0.246428594f, 0.1142857f, 0.0964285731f};
    S.MinCrouch.Count=8;
    S.MinCrouch.X={0.f, 0.0895765498f, 0.161237806f, 0.340390891f, 0.460911989f, 0.60749191f, 0.791531026f, 1.f};
    S.MinCrouch.Y={0.f, 0.f, 0.0304054003f, 0.364864886f, 0.537162185f, 0.665540576f, 0.75f, 0.793918908f};
    S.Compression.Count=8;
    S.Compression.X={0.f, 0.0716612414f, 0.146579802f, 0.237784997f, 0.381107509f, 0.793159604f, 0.938110828f, 1.f};
    S.Compression.Y={0.f, 0.0439189114f, 0.195945904f, 0.320945889f, 0.371621609f, 0.479729712f, 0.756756783f, 1.f};
    S.DeckCompression.Count=8;
    S.DeckCompression.X={0.f, 0.0608695596f, 0.1119565f, 0.163043499f, 0.239130393f, 0.312703609f, 0.370652199f, 0.528260887f};
    S.DeckCompression.Y={0.f, 0.253378391f, 0.418918908f, 0.60135138f, 0.766891897f, 0.878378391f, 0.929054022f, 1.f};
    S.PumpDamping=0.100000001f;
    S.PumpMinChange=0.00400000019f;
    S.PumpMaxChange=0.00600000005f;
    S.AngularDamping=0.200000003f;
    S.CompressionGround=-8.f;
    S.CompressionDeck=-8.f;
    // physics_animation
    S.LandingSpin.Count=4;
    S.LandingSpin.X={0.f, 0.260586292f, 0.561889172f, 1.f};
    S.LandingSpin.Y={0.f, 0.506944418f, 0.8125f, 1.f};
    S.LandingSide.Count=4;
    S.LandingSide.X={0.f, 0.228658497f, 0.551829278f, 0.833841383f};
    S.LandingSide.Y={0.f, 0.215277806f, 0.819444418f, 1.f};
    // physics_friction
    S.CoastDrag.Count=8;
    S.CoastDrag.X={0.f, 1.14514506f, 2.28228211f, 3.33133101f, 4.19619608f, 5.15715694f, 6.52652597f, 8.f};
    S.CoastDrag.Y={0.128571406f, 0.151785702f, 0.207142904f, 0.292857111f, 0.385714293f, 0.441071391f, 0.480357111f, 0.5f};
    S.ManualDrag.Count=8;
    S.ManualDrag.X={0.f, 1.15372396f, 2.30744791f, 3.34706807f, 4.19651413f, 5.16006279f, 6.54199696f, 7.97464323f};
    S.ManualDrag.Y={0.132142901f, 0.151785702f, 0.2071428f, 0.292857111f, 0.382142901f, 0.442857087f, 0.485714287f, 0.5f};
    S.NoInputTime=3.f;
    // physics_speed_conservation
    S.Gravity=9.80000019f;
    // physics_jump
    S.JumpLowSpeed.Count=8;
    S.JumpLowSpeed.X={0.f, 0.400000006f, 0.54560262f, 0.640065074f, 0.719869673f, 0.798045576f, 0.907166123f, 1.f};
    S.JumpLowSpeed.Y={1.f, 1.f, 1.f, 1.f, 1.f, 1.f, 1.f, 1.f};
    S.JumpHighSpeed.Count=8;
    S.JumpHighSpeed.X={0.f, 0.400000006f, 0.496742696f, 0.552117288f, 0.587947905f, 0.64820838f, 0.750814319f, 1.f};
    S.JumpHighSpeed.Y={1.f, 1.f, 0.945945919f, 0.80067569f, 0.64864862f, 0.520270228f, 0.466216207f, 0.460000008f};
    S.JumpVertical.Count=16;
    S.JumpVertical.X={0.00223214296f, 0.0736607164f, 0.145089298f, 0.214285702f, 0.294642895f, 0.439739406f, 0.519543886f, 0.578175902f, 0.713355124f, 0.773615718f, 0.827361584f, 0.872964084f, 0.910423517f, 0.944625378f, 0.970684111f, 1.f};
    S.JumpVertical.Y={1.f, 1.f, 1.f, 1.f, 1.f, 1.f, 0.945736408f, 0.833333313f, 0.441860408f, 0.282945812f, 0.147286803f, 0.108527102f, 0.069767423f, 0.0620155297f, 0.0503876209f, 0.0620155297f};
    S.JumpYScalar.Count=8;
    S.JumpYScalar.X={0.f, 0.0439739414f, 0.0684039071f, 0.102605902f, 0.159609094f, 0.188925102f, 0.242670998f, 1.f};
    S.JumpYScalar.Y={1.5f, 1.5f, 1.47321403f, 1.30892897f, 1.08571398f, 1.04107106f, 1.f, 1.f};
    S.JumpResponseSpeed=27.7999992f;
    S.JumpAbsoluteMin=0.949999988f;
    S.JumpMinimumScalar=0.100000001f;
    S.JumpYBonus=1.5f;
    // physics_trajectory
    S.GrindMaxDown=7.f;
    S.GrindMaxRail=64.f;
    S.GrindMaxLedge=36.f;
    S.GrindAdjustAngle=11.f;
    // physics_grinds_air
    S.GrindMaxOffset=0.200000003f;
    S.GrindMaxDelta=0.0299999993f;
    S.PushTimeMax.Count=8;
    S.PushTimeMax.X={0.f, 0.323932886f, 1.03827405f, 2.87848592f, 4.61686611f, 5.55378485f, 6.67131519f, 8.47742367f};
    S.PushTimeMax.Y={0.226785704f, 0.25f, 0.25f, 0.25f, 0.25f, 0.25f, 0.25f, 0.25f};
    S.PushStrengthCurve.Count=8;
    S.PushStrengthCurve.X={0.f, 0.241699904f, 0.342629492f, 0.419654697f, 0.515272319f, 0.767596304f, 0.884462178f, 1.f};
    S.PushStrengthCurve.Y={0.75f, 1.04464304f, 1.43035698f, 2.04107094f, 2.5232141f, 2.97321391f, 3.50357103f, 4.5f};
    S.PushHoldingMax=4.f;
    S.SurfaceDrag.Count=8;
    S.SurfaceDrag.X={0.f, 8.12052155f, 10.42134f, 12.0454397f, 12.8574896f, 14.3322496f, 18.4039097f, 26.9781799f};
    S.SurfaceDrag.Y={0.f, 0.f, 0.0299999993f, 0.162857205f, 0.600000024f, 0.904053986f, 1.04999995f, 1.20000005f};
    if (Mode==Difficulty::Easy)
    {
        S.JumpMin=1.71000004f;
        S.JumpMax=1.71000004f;
        S.PushDVStart=1.5f;
        S.PushDVEnd=1.5f;
        S.PumpAcceleration=18.f;
        S.PumpAbsorption=1.f;
        S.PumpMaxAcceleration=10.f;
        S.PumpMaxAbsorption=0.f;
        S.UnintentionalPump=1.f;
        S.GrindLockDistance=1.35000002f;
    }
    else if (Mode==Difficulty::Normal)
    {
        S.JumpMin=1.33000004f;
        S.JumpMax=1.71000004f;
        S.PushDVStart=0.600000024f;
        S.PushDVEnd=0.5f;
        S.PumpAcceleration=18.f;
        S.PumpAbsorption=1.f;
        S.PumpMaxAcceleration=10.f;
        S.PumpMaxAbsorption=0.f;
        S.UnintentionalPump=0.699999988f;
        S.GrindLockDistance=0.899999976f;
    }
    else if (Mode==Difficulty::Hardcore)
    {
        S.JumpMin=1.21000004f;
        S.JumpMax=1.71000004f;
        S.PushDVStart=0.5f;
        S.PushDVEnd=0.25f;
        S.PumpAcceleration=18.f;
        S.PumpAbsorption=9.f;
        S.PumpMaxAcceleration=8.f;
        S.PumpMaxAbsorption=8.f;
        S.UnintentionalPump=0.f;
        S.GrindLockDistance=0.150000006f;
    }
    return S;
}
inline std::vector<Pattern> RetailPatterns()
{
    return {
        {"Ollie", {{-0.245714f, 0.942857f}, {0.371429f, -0.908571f}}, 0.55f * 0.55f},
        {"Kickflip", {{-0.028571f, 0.691429f}, {0.908571f, -0.417143f}}, 0.4f * 0.4f},
        {"Heelflip", {{-0.291429f, 0.622857f}, {-0.68f, -0.714286f}}, 0.4f * 0.4f},
        {"PopShuvit", {{0.257143f, 0.942857f}, {0.862857f, 0.451429f}, {0.908571f, -0.36f}}, 0.35f * 0.35f},
        {"VarialKickflip", {{-0.702857f, 0.702857f}, {0.234286f, 0.954286f}, {0.851429f, -0.508571f}}, 0.4f * 0.4f},
        {"InwardHeelflip", {{-0.714286f, 0.714286f}, {0.211429f, 0.977143f}, {-0.737143f, -0.645714f}}, 0.4f * 0.4f},
        {"FSPopShuvit", {{-0.2f, 0.965714f}, {-0.851429f, 0.52f}, {-0.942857f, -0.28f}}, 0.35f * 0.35f},
        {"VarialHeelflip", {{0.725714f, 0.702857f}, {-0.131429f, 0.977143f}, {-0.497143f, -0.84f}}, 0.4f * 0.4f},
        {"Hardflip", {{0.737143f, 0.668571f}, {-0.142857f, 0.988571f}, {0.6f, -0.771429f}}, 0.4f * 0.4f},
        {"360PopShuvit", {{-0.874286f, 0.485714f}, {0.165714f, 0.988571f}, {0.954286f, 0.245714f}}, 0.35f * 0.35f},
        {"360Flip", {{-0.965714f, 0.268571f}, {-0.497143f, 0.84f}, {0.211429f, 0.988571f}, {0.908571f, -0.405714f}}, 0.4f * 0.4f},
        {"360InwardHeelflip", {{-0.977143f, 0.177143f}, {-0.634286f, 0.76f}, {0.051429f, 0.977143f}, {-0.497143f, -0.828571f}}, 0.4f * 0.4f},
        {"FS360PopShuvit", {{0.862857f, 0.485714f}, {-0.165714f, 0.988571f}, {-0.965714f, 0.257143f}}, 0.35f * 0.35f},
        {"Laserflip", {{1.f, 0.177143f}, {0.657143f, 0.76f}, {0.04f, 0.988571f}, {-0.84f, -0.485714f}}, 0.4f * 0.4f},
        {"360Hardflip", {{0.977143f, 0.177143f}, {0.577143f, 0.817143f}, {-0.12f, 0.988571f}, {0.702857f, -0.691429f}}, 0.4f * 0.4f},
        {"Nollie", {{-0.005714f, -0.988571f}, {-0.005714f, 1.f}}, 0.55f * 0.55f},
        {"N_Kickflip", {{-0.017143f, -0.691429f}, {0.714286f, 0.668571f}}, 0.4f * 0.4f},
        {"N_Heelflip", {{0.005714f, -0.691429f}, {-0.737143f, 0.645714f}}, 0.4f * 0.4f},
        {"N_PopShuvit", {{0.268571f, -0.965714f}, {0.931429f, -0.371429f}, {0.84f, 0.508571f}}, 0.35f * 0.35f},
        {"N_Hardflip", {{0.68f, -0.725714f}, {-0.222857f, -0.965714f}, {0.748571f, 0.577143f}}, 0.4f * 0.4f},
        {"N_VarialHeelflip", {{0.691429f, -0.714286f}, {-0.2f, -0.965714f}, {-0.44f, 0.725714f}}, 0.4f * 0.4f},
        {"N_FSPopShuvit", {{-0.222857f, -1.f}, {-0.92f, -0.508571f}, {-0.92f, 0.44f}}, 0.35f * 0.35f},
        {"N_VarialKickflip", {{-0.611429f, -0.794286f}, {0.291429f, -0.942857f}, {0.245714f, 0.817143f}}, 0.4f * 0.4f},
        {"N_InwardHeelflip", {{-0.622857f, -0.794286f}, {0.314286f, -0.931429f}, {-0.76f, 0.645714f}}, 0.4f * 0.4f},
        {"N_FS360PopShuvit", {{0.954286f, -0.588571f}, {-0.2f, -0.885714f}, {-1.f, -0.28f}}, 0.35f * 0.35f},
        {"N_360Hardflip", {{0.988571f, -0.142857f}, {0.634286f, -0.782857f}, {-0.2f, -0.977143f}, {0.748571f, 0.565714f}}, 0.4f * 0.4f},
        {"N_Laserflip", {{0.954286f, -0.268571f}, {0.508571f, -0.862857f}, {-0.188571f, -0.725714f}, {-0.737143f, 0.645714f}}, 0.4f * 0.4f},
        {"N_360PopShuvit", {{-0.862857f, -0.497143f}, {0.177143f, -0.988571f}, {0.942857f, -0.291429f}}, 0.35f * 0.35f},
        {"N_360Flip", {{-0.965714f, -0.2f}, {-0.554286f, -0.84f}, {0.097143f, -0.977143f}, {0.851429f, 0.531429f}}, 0.4f * 0.4f},
        {"N_360InwardHeelflip", {{-0.954286f, -0.257143f}, {-0.485714f, -0.862857f}, {0.234286f, -0.965714f}, {-0.84f, 0.52f}}, 0.4f * 0.4f},
        {"Ollie", {{-0.005714f, 0.474286f}, {0.005714f, -0.851429f}}, 0.4f * 0.4f},
        {"Nollie", {{0.005714f, -0.531429f}, {-0.005714f, 0.942857f}}, 0.4f * 0.4f},
        {"Kickflip", {{-0.005714f, 0.977143f}, {0.885714f, -0.462857f}}, 0.4f * 0.4f},
        {"Heelflip", {{0.005714f, 0.988571f}, {-0.714286f, -0.725714f}}, 0.4f * 0.4f},
        {"N_Hardflip", {{0.691429f, -0.725714f}, {-0.28f, -0.954286f}, {0.394286f, 0.782857f}}, 0.45f * 0.45f},
        {"N_InwardHeelflip", {{-0.588571f, -0.794286f}, {0.337143f, -0.931429f}, {-0.36f, 0.76f}}, 0.4f * 0.4f},
        {"N_VarialKickflip", {{-0.611429f, -0.794286f}, {0.314286f, -0.942857f}, {0.771429f, 0.577143f}}, 0.4f * 0.4f},
        {"N_VarialHeelflip", {{0.68f, -0.725714f}, {-0.234286f, -0.965714f}, {-0.885714f, 0.417143f}}, 0.4f * 0.4f},
        {"N_360Hardflip", {{0.988571f, -0.142857f}, {0.462857f, -0.874286f}, {-0.257143f, -0.965714f}, {0.371429f, 0.76f}}, 0.4f * 0.4f},
        {"N_360InwardHeelflip", {{-0.942857f, -0.28f}, {-0.474286f, -0.874286f}, {0.302857f, -0.954286f}, {-0.451429f, 0.748571f}}, 0.4f * 0.4f},
        {"N_VarialKickflip", {{-0.325714f, -0.931429f}, {0.611429f, -0.782857f}, {0.165714f, 0.794286f}}, 0.4f * 0.4f},
        {"VarialKickflip", {{-0.691429f, 0.725714f}, {0.222857f, 0.977143f}, {0.508571f, -0.714286f}}, 0.4f * 0.4f},
        {"360Flip", {{-1.f, 0.051429f}, {-0.771429f, 0.645714f}, {-0.291429f, 0.954286f}, {0.885714f, -0.417143f}}, 0.45f * 0.45f},
        {"VarialHeelflip", {{0.691429f, 0.702857f}, {-0.188571f, 0.977143f}, {-0.954286f, -0.314286f}}, 0.4f * 0.4f},
        {"Hardflip", {{0.714286f, 0.702857f}, {-0.2f, 0.977143f}, {0.874286f, -0.474286f}}, 0.4f * 0.4f},
        {"InwardHeelflip", {{-0.668571f, 0.714286f}, {0.257143f, 0.954286f}, {-0.348571f, -0.908571f}}, 0.4f * 0.4f},
        {"360Hardflip", {{0.988571f, 0.188571f}, {0.577143f, 0.771429f}, {-0.062857f, 0.988571f}, {0.302857f, -0.771429f}}, 0.4f * 0.4f},
        {"360InwardHeelflip", {{-1.f, 0.177143f}, {-0.417143f, 0.908571f}, {0.508571f, 0.862857f}, {-0.142857f, -0.965714f}}, 0.4f * 0.4f},
        {"Ollie", {{0.691429f, 0.714286f}, {0.268571f, -0.942857f}}, 0.4f * 0.4f},
        {"Ollie", {{-0.714286f, 0.702857f}, {-0.302857f, -0.954286f}}, 0.4f * 0.4f},
        {"Nollie", {{-0.691429f, -0.725714f}, {-0.268571f, 0.942857f}}, 0.4f * 0.4f},
        {"Nollie", {{0.668571f, -0.725714f}, {0.222857f, 0.942857f}}, 0.4f * 0.4f},
        {"Kickflip", {{-0.737143f, 0.68f}, {0.702857f, -0.725714f}}, 0.4f * 0.4f},
        {"Heelflip", {{0.68f, 0.714286f}, {-0.702857f, -0.702857f}}, 0.4f * 0.4f},
        {"N_Heelflip", {{0.645714f, -0.771429f}, {-0.737143f, 0.645714f}}, 0.4f * 0.4f},
        {"N_Kickflip", {{-0.691429f, -0.737143f}, {0.702857f, 0.702857f}}, 0.4f * 0.4f},
        {"Kickflip", {{-0.131429f, 0.68f}, {0.908571f, -0.382857f}}, 0.35f * 0.35f},
        {"Heelflip", {{-0.188571f, 0.657143f}, {-0.485714f, -0.862857f}}, 0.4f * 0.4f},
        {"Laserflip", {{1.f, 0.12f}, {0.68f, 0.702857f}, {0.097143f, 0.977143f}, {-0.337143f, -0.725714f}}, 0.4f * 0.4f},
        {"N_Laserflip", {{0.977143f, -0.234286f}, {0.451429f, -0.885714f}, {-0.28f, -0.988571f}, {-0.325714f, 0.748571f}}, 0.4f * 0.4f},
        {"N_360Flip", {{-0.954286f, -0.314286f}, {-0.542857f, -0.84f}, {0.154286f, -1.f}, {0.142857f, 0.817143f}}, 0.4f * 0.4f},
        {"Ollie", {{-0.234286f, 0.977143f}, {-0.28f, -0.965714f}}, 0.4f * 0.4f},
        {"360Flip", {{-0.988571f, 0.188571f}, {-0.634286f, 0.76f}, {0.062857f, 0.988571f}, {0.474286f, -0.874286f}}, 0.4f * 0.4f},
        {"VarialKickflip", {{-0.702857f, 0.702857f}, {0.257143f, 0.977143f}, {0.188571f, -0.771429f}}, 0.4f * 0.4f},
        {"VarialHeelflip", {{0.691429f, 0.714286f}, {-0.177143f, 0.965714f}, {0.097143f, -0.988571f}}, 0.4f * 0.4f},
        {"N_VarialHeelflip", {{0.68f, -0.725714f}, {-0.211429f, -0.965714f}, {-0.005714f, 0.851429f}}, 0.4f * 0.4f},
        {"N_360Flip", {{-0.965714f, -0.291429f}, {-0.554286f, -0.817143f}, {0.085714f, -1.f}, {0.44f, 0.725714f}}, 0.4f * 0.4f},
        {"N_Laserflip", {{0.931429f, -0.337143f}, {0.485714f, -0.862857f}, {-0.2f, -1.f}, {-0.04f, 0.851429f}}, 0.4f * 0.4f},
        {"Hardflip", {{0.291429f, 0.942857f}, {-0.668571f, 0.714286f}, {0.36f, -0.634286f}}, 0.4f * 0.4f},
        {"VarialHeelflip", {{0.245714f, 0.965714f}, {-0.68f, 0.748571f}, {-0.017143f, -0.817143f}}, 0.4f * 0.4f},
        {"VarialKickflip", {{-0.302857f, 0.931429f}, {0.622857f, 0.782857f}, {0.222857f, -0.76f}}, 0.4f * 0.4f},
        {"InwardHeelflip", {{-0.28f, 0.942857f}, {0.622857f, 0.771429f}, {-0.428571f, -0.782857f}}, 0.4f * 0.4f},
        {"N_Hardflip", {{0.302857f, -0.942857f}, {-0.6f, -0.794286f}, {0.337143f, 0.657143f}}, 0.4f * 0.4f},
        {"N_VarialHeelflip", {{0.291429f, -0.942857f}, {-0.6f, -0.794286f}, {-0.245714f, 0.817143f}}, 0.4f * 0.4f},
        {"N_InwardHeelflip", {{-0.325714f, -0.931429f}, {0.588571f, -0.782857f}, {-0.325714f, 0.737143f}}, 0.4f * 0.4f},
        {"VarialHeelflip", {{1.f, 0.062857f}, {0.508571f, 0.862857f}, {-0.657143f, -0.702857f}}, 0.4f * 0.4f},
        {"VarialKickflip", {{-0.988571f, 0.131429f}, {-0.462857f, 0.874286f}, {0.897143f, -0.417143f}}, 0.4f * 0.4f},
        {"N_VarialHeelflip", {{0.977143f, -0.154286f}, {0.382857f, -0.908571f}, {-0.714286f, 0.702857f}}, 0.4f * 0.4f},
    };
}
}

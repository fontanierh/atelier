#include "JapanPreferences.h"
#include "BotwRider.h"
#include "BotwMoveSet.h"
#include "CairoCharacter.h"
#include "SkateComponent.h"
#include "WandererCharacter.h"
#include "WandererDefinition.h"
#include "JapanWorld.h"
#include "Engine/Engine.h"
#include "AudioDevice.h"
#include "Engine/GameViewportClient.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/DirectionalLight.h"
#include "Components/DirectionalLightComponent.h"
#include "Engine/SkyLight.h"
#include "Components/SkyLightComponent.h"
#include "Engine/ExponentialHeightFog.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "EngineUtils.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/Paths.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "HAL/IConsoleManager.h"
#include "Framework/Application/SlateApplication.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SWrapBox.h"
#include "TimerManager.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Input/SSlider.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Text/STextBlock.h"

// The menu's Light section, in its order. Raising LightVersion gives every saved file the defaults of these keys once.
static const TCHAR* const LightKeys[] = {TEXT("exposure"),TEXT("saturation"),TEXT("sun_height"),TEXT("sun_yaw"),
    TEXT("sun_warmth"),TEXT("sun_strength"),TEXT("sky_fill"),TEXT("bounce")};
static constexpr int32 LightVersion = 3;

namespace
{
// The Skate feel page (docs/SKATE.md, "Skate feel menu"): every value that changes how the board rides, saved as
// skate_<name>. The mode picks Easy, Normal or Hardcore as made, or Custom, where every value below is tuned on a base
// difficulty; the stick, mouse and camera (bAlways) apply in every mode. A knob without a field is a choice: the mode
// (0 easy, 1 normal, 2 hardcore, 3 custom), the base difficulty (0 easy, 1 normal, 2 hardcore) or a switch (0 the
// difficulty's own, 1 off, 2 on).
struct FSkateKnob { const TCHAR* Key; const TCHAR* Label; const TCHAR* Hint; float Minimum, Maximum, Step; float FSkateFeel::* Field; bool bAlways = false; };
struct FSkateGroup { const TCHAR* Name; TArray<FSkateKnob> Knobs; };
const TArray<FSkateGroup>& SkateGroups()
{
    static const TArray<FSkateGroup> Groups = {
        {TEXT("Mode"), {
            {TEXT("skate_mode"), TEXT("Skating mode"), TEXT("Easy, Normal or Hardcore as made, or Custom to tune every value."), 0, 3, 1, nullptr, true}}},
        {TEXT("Custom base"), {
            {TEXT("skate_difficulty"), TEXT("Base difficulty"), TEXT("The difficulty every custom multiplier scales: easy is forgiving, hardcore strict."), 0, 2, 1, nullptr},
            {TEXT("skate_trucks"), TEXT("Truck tightness"), TEXT("0 loose, quick to turn; 1 tight and stable."), 0, 1, .05f, &FSkateFeel::TruckTightness}}},
        {TEXT("Flick-It"), {
            {TEXT("skate_flick_radius"), TEXT("Flick tolerance"), TEXT("How far a flick may stray from a trick's shape. Higher reads sloppy flicks as tricks."), .5f, 2, .05f, &FSkateFeel::FlickRadius},
            {TEXT("skate_flick_window"), TEXT("Flick time window"), TEXT("How long a flick may take from start to finish. Higher accepts slower flicks."), .5f, 3, .05f, &FSkateFeel::FlickWindow},
            {TEXT("skate_flick_pace"), TEXT("Flick speed for full pop"), TEXT("How fast a flick must be to pop at full height. Lower pops high with gentler flicks."), .5f, 2, .05f, &FSkateFeel::FlickPace}}},
        {TEXT("Air"), {
            {TEXT("skate_pop"), TEXT("Ollie pop"), TEXT("Ollie and nollie height."), .5f, 2, .05f, &FSkateFeel::Pop},
            {TEXT("skate_boneless"), TEXT("Boneless height"), TEXT("Height of a boneless."), .5f, 3, .05f, &FSkateFeel::Boneless},
            {TEXT("skate_hippy"), TEXT("Hippy jump height"), TEXT("Height of a hippy jump."), .5f, 3, .05f, &FSkateFeel::Hippy},
            {TEXT("skate_gravity"), TEXT("Gravity"), TEXT("Lower floats, higher drops. Jumps keep their height; the time in the air changes."), .5f, 1.5f, .05f, &FSkateFeel::Gravity},
            {TEXT("skate_spin"), TEXT("Spin speed"), TEXT("How fast the body spins in the air."), .5f, 3, .05f, &FSkateFeel::Spin},
            {TEXT("skate_assisted_air"), TEXT("Assisted spins and flips"), TEXT("Body spins and flips completed for you."), 0, 2, 1, nullptr},
            {TEXT("skate_vert_assist"), TEXT("Vert assist"), TEXT("Sends straight airs back into quarter pipes that are short of vertical."), 0, 1, .05f, &FSkateFeel::VertAssist}}},
        {TEXT("Rails"), {
            {TEXT("skate_rail_magnetism"), TEXT("Rail magnetism"), TEXT("How far, how sharply and how fast a jump is pulled onto a rail or ledge."), .25f, 3, .05f, &FSkateFeel::RailMagnetism},
            {TEXT("skate_grind_pop"), TEXT("Grind pop"), TEXT("Height of an ollie out of a grind."), .5f, 2, .05f, &FSkateFeel::GrindPop},
            {TEXT("skate_grind_friction"), TEXT("Grind friction"), TEXT("How fast grinds and slides slow down. 0 never slows."), 0, 3, .05f, &FSkateFeel::GrindFriction}}},
        {TEXT("Pushing and rolling"), {
            {TEXT("skate_push_speed"), TEXT("Top push speed"), TEXT("The speed pushing reaches."), .5f, 2, .05f, &FSkateFeel::PushSpeed},
            {TEXT("skate_push_power"), TEXT("Push strength"), TEXT("Speed gained with each push."), .5f, 3, .05f, &FSkateFeel::PushPower},
            {TEXT("skate_auto_push"), TEXT("Auto push"), TEXT("Keeps you rolling without pushing."), 0, 2, 1, nullptr},
            {TEXT("skate_pump"), TEXT("Pumping"), TEXT("Speed gained by pumping through transitions."), 0, 3, .05f, &FSkateFeel::Pump},
            {TEXT("skate_rolling_friction"), TEXT("Rolling resistance"), TEXT("How fast speed above cruising bleeds off on the flat. 0 keeps every bit of speed."), 0, 3, .05f, &FSkateFeel::RollingFriction},
            {TEXT("skate_hill_speed"), TEXT("Hill speed"), TEXT("How hard slopes pull the board down."), 0, 2, .05f, &FSkateFeel::HillSpeed},
            {TEXT("skate_braking"), TEXT("Braking"), TEXT("How hard the foot brake stops."), .25f, 3, .05f, &FSkateFeel::Braking}}},
        {TEXT("Turning"), {
            {TEXT("skate_steering"), TEXT("Steering"), TEXT("How much the stick turns the board."), .5f, 2, .05f, &FSkateFeel::Steering},
            {TEXT("skate_carve"), TEXT("Carve"), TEXT("How hard a leaning board turns."), .5f, 2, .05f, &FSkateFeel::Carve},
            {TEXT("skate_grip"), TEXT("Wheel grip"), TEXT("How well the wheels hold a turn before sliding out."), .5f, 2, .05f, &FSkateFeel::Grip},
            {TEXT("skate_powerslide"), TEXT("Powerslide bite"), TEXT("How hard a powerslide slows the board."), .25f, 3, .05f, &FSkateFeel::Powerslide}}},
        {TEXT("Balance"), {
            {TEXT("skate_wobble"), TEXT("Speed wobble"), TEXT("How much the board shakes at speed. 0 never wobbles."), 0, 3, .05f, &FSkateFeel::Wobble},
            {TEXT("skate_wobble_onset"), TEXT("Wobble starts at"), TEXT("The speed the wobble starts at, as a multiple of the difficulty's."), .5f, 3, .05f, &FSkateFeel::WobbleOnset},
            {TEXT("skate_manual_drift"), TEXT("Manual drift"), TEXT("How much a manual tips off balance by itself. 0 holds still."), 0, 3, .05f, &FSkateFeel::ManualDrift}}},
        {TEXT("Bails"), {
            {TEXT("skate_landing"), TEXT("Landing forgiveness"), TEXT("How crooked and how hard a landing may be before you bail."), .5f, 3, .05f, &FSkateFeel::Landing},
            {TEXT("skate_impact"), TEXT("Impact toughness"), TEXT("How hard a knock you ride through."), .5f, 3, .05f, &FSkateFeel::Impact},
            {TEXT("skate_get_up"), TEXT("Time down after a bail"), TEXT("How long the body lies before getting up."), .25f, 2, .05f, &FSkateFeel::GetUpDelay}}},
        {TEXT("Controls and camera · every mode"), {
            {TEXT("skate_dead_zone"), TEXT("Stick dead zone"), TEXT("Stick travel ignored around the centre. Raise it for a worn stick."), .25f, .6f, .01f, &FSkateFeel::StickDeadZone, true},
            {TEXT("skate_stick_reach"), TEXT("Stick full tilt at"), TEXT("Stick travel that counts as fully pushed. Lower reaches the edge sooner."), .6f, 1, .01f, &FSkateFeel::StickReach, true},
            {TEXT("skate_mouse_flick"), TEXT("Mouse flick strength"), TEXT("How far a mouse movement moves the trick stick, beside look sensitivity."), .25f, 4, .05f, &FSkateFeel::MouseFlick, true},
            {TEXT("skate_cam_dist"), TEXT("Skate camera distance"), TEXT("Nearer or farther than the skate camera's own."), .6f, 1.6f, .05f, &FSkateFeel::CameraDistance, true},
            {TEXT("skate_cam_fov"), TEXT("Skate camera field of view"), TEXT("Degrees added to the skate camera's view."), -20, 20, 1, &FSkateFeel::CameraFOV, true}}}};
    return Groups;
}
const TCHAR* const SkateDifficulties[] = {TEXT("easy"), TEXT("normal"), TEXT("hardcore")};
const TCHAR* const SkateModes[] = {TEXT("Easy"), TEXT("Normal"), TEXT("Hardcore"), TEXT("Custom")};
constexpr int32 SkateCustom = 3;
FString SkateChoice(const FString& Key, int32 Choice)
{
    if (Key == TEXT("skate_mode")) return SkateModes[FMath::Clamp(Choice, 0, SkateCustom)];
    if (Key == TEXT("skate_difficulty"))
        return Choice == 0 ? TEXT("Easy · forgiving") : Choice == 2 ? TEXT("Hardcore · strict") : TEXT("Normal");
    return Choice == 1 ? TEXT("Off") : Choice == 2 ? TEXT("On") : TEXT("As the difficulty has it");
}
// The value a knob starts at: the game's DefaultGame.ini for the settings it had, the stock feel for the rest.
float SkateDefault(const FSkateKnob& Knob, const FSkateFeel& Defaults)
{
    if (Knob.Field) return Defaults.*Knob.Field;
    if (FCString::Strcmp(Knob.Key, TEXT("skate_difficulty")) == 0 || FCString::Strcmp(Knob.Key, TEXT("skate_mode")) == 0)
    {
        for (int32 I = 0; I < 3; ++I) if (Defaults.Difficulty.Equals(SkateDifficulties[I], ESearchCase::IgnoreCase)) return float(I);
        return 1.f;
    }
    return float((FCString::Strcmp(Knob.Key, TEXT("skate_auto_push")) == 0 ? Defaults.AutoPush : Defaults.AssistedAir) + 1);
}
}

void UJapanPreferences::Initialize(AWandererCharacter* Pawn)
{
    Owner = Pawn;
    Values = {
        {TEXT("performance"),TEXT("Graphics"),1.f,0.f,1.f},
        // Session-only desktop tuning; both profiles share instance occlusion culling.
        {TEXT("desktop"),TEXT("Desktop profile"),0.f,0.f,1.f},
        {TEXT("show_fps"),TEXT("Frame rate"),1.f,0.f,1.f},
        {TEXT("fog"),TEXT("Volumetric fog"),1.f,0.f,1.f},
        // The fog's look (AJapanWorld::ApplyVolumetricFog, docs/VOLUMETRIC_FOG.md); the defaults are FVolumetricFogLook's.
        {TEXT("fog_density"),TEXT("Fog density"),.07f,0.f,.2f,.005f},
        {TEXT("fog_reach"),TEXT("Fog reach (m)"),30.f,10.f,120.f,5.f},
        {TEXT("fog_falloff"),TEXT("Fog height falloff"),.12f,.02f,.5f,.01f},
        {TEXT("fog_glow"),TEXT("Fog glow toward the sun"),.5f,0.f,.9f,.05f},
        {TEXT("fog_shafts"),TEXT("Light shafts"),1.f,0.f,4.f,.1f},
        {TEXT("fog_town"),TEXT("Fog in Hidamari"),0.f,0.f,1.f,.05f},
        {TEXT("volume"),TEXT("Volume"),1.f,0.f,1.f},
        {TEXT("goofy"),TEXT("Skate stance"),0.f,0.f,1.f},
        {TEXT("stamina_rings"),TEXT("Stamina rings"),2.f,1.f,5.f},
        {TEXT("mouse"),TEXT("Look sensitivity"),.4f,.04f,.8f},
        {TEXT("cam_dist"),TEXT("Camera distance"),420.f,200.f,800.f},
        {TEXT("fov"),TEXT("Field of view"),70.f,50.f,100.f},
        {TEXT("render_scale"),TEXT("Resolution limit (%)"),100.f,50.f,100.f},
        {TEXT("painterly"),TEXT("Paint strength"),.35f,0.f,1.f},
        {TEXT("paint_radius"),TEXT("Brush radius"),2.f,1.f,8.f},
        {TEXT("toon"),TEXT("Toon strength"),0.f,0.f,1.f},
        {TEXT("toon_bands"),TEXT("Toon bands"),7.f,2.f,10.f},
        {TEXT("toon_soft"),TEXT("Toon softness"),.45f,0.f,1.f},
        {TEXT("outline"),TEXT("Outlines"),0.f,0.f,1.f},
        {TEXT("wind"),TEXT("Wind (m/s)"),3.5f,0.f,12.f},
        // The light (the menu's Light section, LightKeys): the map's sun, sky light and unbound volume
        // (setup_project.py build_level) as the player tunes them. The defaults are a low, warm afternoon sun
        // with long shadows, chosen in a live trial of five looks (build/yorimichi/scout/hidamari-light1). Its
        // direction (yaw -30: from the west-south-west, so the south-facing fronts and the city seen from the sea are
        // in sun and the east-west streets get diagonal shadows) won a trial of five (build/yorimichi/scout/hidamari-v14).
        {TEXT("exposure"),TEXT("Exposure"),.95f,.4f,2.2f},
        {TEXT("saturation"),TEXT("Saturation"),1.f,.6f,1.6f},
        {TEXT("sun_height"),TEXT("Sun elevation"),26.f,5.f,80.f},
        {TEXT("sun_yaw"),TEXT("Sun direction"),-30.f,-180.f,180.f},
        {TEXT("sun_warmth"),TEXT("Sun warmth"),.9f,0.f,1.f},
        {TEXT("sun_strength"),TEXT("Sun strength (lux)"),11.f,2.f,16.f},
        {TEXT("sky_fill"),TEXT("Sky fill"),2.3f,0.f,6.f},
        {TEXT("bounce"),TEXT("Bounce light"),1.9f,0.f,4.f}};
    {
        const FSkateFeel Defaults = FSkateFeel::Defaults();
        for (const FSkateGroup& Group : SkateGroups())
            for (const FSkateKnob& Knob : Group.Knobs)
                Values.Add({Knob.Key, Knob.Label, SkateDefault(Knob, Defaults), Knob.Minimum, Knob.Maximum, Knob.Step});
    }
    // The move set (UBotwMoveSet::Chosen: merged by default, Cairo's legacy moves or the legacy BOTW set) and its shield
    // (UBotwMoveSet::SetShield: off by default, the sword guards and parries).
    if (ACairoCharacter::HasBotw() || ABotwRider::Available().Num())
    {
        const int32 After = Values.IndexOfByPredicate([](const FJapanPreference& V) { return V.Key == TEXT("goofy"); })+1;
        Values.Insert({TEXT("shield"),TEXT("Shield"),0.f,0.f,1.f},After);
        Values.Insert({TEXT("moveset"),TEXT("Move set"),0.f,0.f,2.f},After);
    }
    Defaults.Reset();
    for (const FJapanPreference& V : Values) Defaults.Add(V.Key,V.Value);
    SettingsFile=FilePath();
    UE_LOG(LogTemp,Display,TEXT("PREFERENCES file=%s"),*SettingsFile);
    SavedValues=ReadSaved();
    for (FJapanPreference& V : Values)
        if (const FString* Text = SavedValues.Find(V.Key))
        {
            float Number = 0;
            if (LexTryParseString(Number,**Text) && FMath::IsFinite(Number)) V.Value = FMath::Clamp(Number,V.Minimum,V.Maximum);
        }
    // The skating engine is the game's config (Ride); Native is a console-only reference (skate.Backend), so an engine
    // saved by an older menu no longer applies.
    SavedValues.Remove(TEXT("skate_engine"));
    for (TActorIterator<APostProcessVolume> It(Owner->GetWorld()); It; ++It)
        for (FWeightedBlendable& Blend : It->Settings.WeightedBlendables.Array)
            if (UMaterialInterface* Source = Cast<UMaterialInterface>(Blend.Object))
            {
                // After a character switch the volume holds the previous character's instances: start from their source.
                if (const auto* Previous = Cast<UMaterialInstanceDynamic>(Source); Previous && Previous->GetOuter()->IsA<UJapanPreferences>()) Source = Previous->Parent;
                auto* Material = UMaterialInstanceDynamic::Create(Source,this);
                Blend.Object = Material; Materials.Add(Material);
            }
    Apply();
}
FString UJapanPreferences::FilePath()
{
    // Desktop previews keep menu edits in their own file; ordinary play/stream
    // keeps the existing shared path. The launcher seeds a separate copy.
    FString PreviewFile;
    if (FParse::Value(FCommandLine::Get(),TEXT("preferencesfile="),PreviewFile) && !PreviewFile.IsEmpty())
        return FPaths::ConvertRelativePathToFull(PreviewFile);
    return FPaths::ProjectSavedDir()/TEXT("settings.txt");
}
TMap<FString,FString> UJapanPreferences::ReadSaved()
{
    TMap<FString,FString> Result;
    TArray<FString> Lines;
    FFileHelper::LoadFileToStringArray(Lines,*FilePath());
    for (const FString& Line : Lines)
    {
        FString K,V;
        // A stale desktop key in the shared file must not switch a phone session into the profile.
        if (Line.Split(TEXT("="),&K,&V) && !IsSessionOnly(K.TrimStartAndEnd()))
            Result.Add(K.TrimStartAndEnd(),V.TrimStartAndEnd());
    }
    // A file saved before the current default light keeps every light value it wrote, the old defaults
    // among them: let it take the new light once. Command-line overrides below still apply.
    if (float Version = 0; !Result.Contains(TEXT("light_version")) || !LexTryParseString(Version,*Result[TEXT("light_version")]) || Version < LightVersion)
    {
        for (const TCHAR* Key : LightKeys) Result.Remove(Key);
        Result.Add(TEXT("light_version"),FString::FromInt(LightVersion));
    }
    FString Overrides;
    if (FParse::Value(FCommandLine::Get(),TEXT("set="),Overrides))
    {
        TArray<FString> Pairs; Overrides.ParseIntoArray(Pairs,TEXT(";"));
        for (const auto& Pair : Pairs) { FString K,V; if (Pair.Split(TEXT("="),&K,&V)) Result.Add(K,V); }
    }
    return Result;
}
float UJapanPreferences::Saved(const FString& Key, float Default)
{
    const TMap<FString,FString> Read = ReadSaved();
    float Number = Default;
    if (const FString* Text = Read.Find(Key); Text && LexTryParseString(Number,**Text) && FMath::IsFinite(Number)) return Number;
    return Default;
}
bool UJapanPreferences::IsToggle(const FString& Key)
{
    return Key == TEXT("performance") || Key == TEXT("show_fps") || Key == TEXT("fog") || Key == TEXT("goofy") || Key == TEXT("shield");
}
float UJapanPreferences::Get(const TCHAR* Key) const
{
    for (const auto& V : Values) if (V.Key == Key) return V.Value;
    return 0;
}
bool UJapanPreferences::SetValue(const FString& Key, float Number)
{
    if (!FMath::IsFinite(Number)) return false;
    // Custom from a preset, with nothing tuned yet, starts on that preset's difficulty (the menu and the phone alike).
    if (Key == TEXT("skate_mode") && FMath::RoundToInt(Number) == SkateCustom && IsSkateCustomStock())
    {
        const int32 Was = FMath::RoundToInt(Get(TEXT("skate_mode")));
        if (Was != SkateCustom) for (FJapanPreference& V : Values) if (V.Key == TEXT("skate_difficulty")) V.Value = float(FMath::Clamp(Was, 0, 2));
    }
    for (auto& V : Values) if (V.Key == Key)
    {
        V.Value = FMath::Clamp(Number,V.Minimum,V.Maximum);
        if (V.Step > 0.f) V.Value = FMath::Clamp(V.Minimum+FMath::RoundToFloat((V.Value-V.Minimum)/V.Step)*V.Step,V.Minimum,V.Maximum);
        if (IsToggle(Key)) V.Value = V.Value > .5f ? 1.f : 0.f;
        if (Key == TEXT("stamina_rings") || Key == TEXT("moveset")) V.Value=FMath::RoundToFloat(V.Value);
        Apply(); Save(); return true;
    }
    return false;
}
void UJapanPreferences::Apply()
{
    if (!Owner) return;
    Owner->SetStaminaRings(FMath::RoundToInt(Get(TEXT("stamina_rings"))));
    if (USkateComponent* Skate = Owner->GetSkate())
    {
        Skate->SetGoofy(Get(TEXT("goofy")) > .5f);
        // At once, mid-ride too; an unchanged feel leaves the session alone.
        FString Error;
        if (!Skate->SetFeel(GetSkateFeel(), Error)) UE_LOG(LogTemp, Warning, TEXT("PREFERENCES skate feel refused: %s"), *Error);
    }
    // The move set takes the shield and the merged or legacy BOTW rules at once; Cairo's legacy moves need the
    // character switch (ToggleMenu).
    if (UBotwMoveSet* Moves = Owner->GetMoves(); Moves && Values.ContainsByPredicate([](const FJapanPreference& V) { return V.Key == TEXT("moveset"); }))
    {
        Moves->SetLegacy(FMath::RoundToInt(Get(TEXT("moveset"))) == UBotwMoveSet::LegacyBotw);
        Moves->SetShield(Get(TEXT("shield")) > .5f);
    }
    const int32 PerformanceMode = Get(TEXT("performance")) > .5f ? 1 : 0;
    const bool Desktop = Get(TEXT("desktop")) > .5f;
    const auto Set = [](const TCHAR* Name, float Value)
    {
        if (auto* CVar = IConsoleManager::Get().FindConsoleVariable(Name))
            CVar->Set(Value,ECVF_SetByCode);
    };
    // Saved Unreal GameUserSettings can override the ini cap with zero.
    // Explicit console overrides still allow the benchmark to run uncapped.
    Set(TEXT("t.MaxFPS"),60.f);
    // Cull instances the depth buffer already hides. In addition to the desktop
    // checks, paired phone-profile captures at native 720p save 6.5-7.3 ms in
    // settled spawn pairs. Keep this visibility optimization on for both profiles.
    Set(TEXT("r.InstanceCulling.OcclusionCull"),1.f);
    // The harbor's second directional light needs no CSMs when every receiver
    // is beyond cascade range. Desktop experiments retain the phone baseline.
    Set(TEXT("japan.HarborFillAuto"),Desktop ? 1.f : 0.f);
    // R11G11B10 retains HDR at half the scene-color bandwidth. Paired native
    // 1440p tests save ~1 ms in forest/harbor, with original resolution and TAA.
    // Keep FloatRGBA for the phone and full-quality mode; no saved setting changes.
    Set(TEXT("r.SceneColorFormat"),Desktop && PerformanceMode ? 2.f : 4.f);
    // UE 5.8's lighter input filter retains anti-ghosting. Native 1440p paired
    // captures save ~0.3 ms; sprint/double-jump frames retain character edges.
    Set(TEXT("r.TemporalAA.Quality"),Desktop && PerformanceMode ? 3.f : 2.f);
    if (AppliedPerformanceMode != PerformanceMode)
    {
        // Use the engine's original medium irradiance-volume lighting in the
        // performance profile. The user reverted the screen-probe lighting change.
        Set(TEXT("sg.GlobalIlluminationQuality"),PerformanceMode ? 1.f : 3.f);
        Set(TEXT("r.Shadow.CSM.MaxCascades"),PerformanceMode ? 2.f : 10.f);
        Set(TEXT("r.Shadow.MaxCSMResolution"),PerformanceMode ? 1024.f : 2048.f);
        Set(TEXT("r.Shadow.DistanceScale"),PerformanceMode ? .5f : 1.5f);
        Set(TEXT("r.DistanceFieldShadowing"),PerformanceMode ? 0.f : 1.f);
        Set(TEXT("foliage.LODDistanceScale"),PerformanceMode ? .75f : 1.f);
        AppliedPerformanceMode = PerformanceMode;
    }
    // Keep character edges near native resolution. The cheaper grass LODs leave
    // room for a higher floor; still respect a manually chosen lower ceiling.
    Set(TEXT("r.DynamicRes.MinScreenPercentage"),FMath::Min(85.f,Get(TEXT("render_scale"))));
    Set(TEXT("r.DynamicRes.MaxScreenPercentage"),Get(TEXT("render_scale")));
    Set(TEXT("r.DynamicRes.FrameTimeBudget"),1000.f/60.f);
    Set(TEXT("r.DynamicRes.TargetedGPUHeadRoomPercentage"),10.f);
    Set(TEXT("r.DynamicRes.OperationMode"),PerformanceMode ? 2.f : 0.f);
    Owner->ApplyCameraPreferences(Get(TEXT("mouse")),Get(TEXT("cam_dist")),Get(TEXT("fov")));
    // Every sound in the game (the audio device's primary volume).
    if (FAudioDeviceHandle Audio = Owner->GetWorld()->GetAudioDevice(); Audio.IsValid()) Audio->SetTransientPrimaryVolume(Get(TEXT("volume")));
    for (const auto& Material : Materials)
        for (const auto& Pair : TArray<TPair<FName,const TCHAR*>>{
            {TEXT("Strength"),TEXT("painterly")},{TEXT("Radius"),TEXT("paint_radius")},{TEXT("Toon"),TEXT("toon")},
            {TEXT("Bands"),TEXT("toon_bands")},{TEXT("Soft"),TEXT("toon_soft")},{TEXT("Outline"),TEXT("outline")}})
            Material->SetScalarParameterValue(Pair.Key,Get(Pair.Value));
    for (TActorIterator<APostProcessVolume> It(Owner->GetWorld()); It; ++It)
    {
        It->Settings.bOverride_AutoExposureBias = true;
        It->Settings.AutoExposureBias = Get(TEXT("exposure"));
        It->Settings.bOverride_ColorSaturation = true;
        It->Settings.ColorSaturation = FVector4(Get(TEXT("saturation")),Get(TEXT("saturation")),Get(TEXT("saturation")),1.f);
        for (auto& Blend : It->Settings.WeightedBlendables.Array)
            if (Materials.Contains(Cast<UMaterialInstanceDynamic>(Blend.Object)))
                Blend.Weight = Get(TEXT("painterly"))+Get(TEXT("toon"))+Get(TEXT("outline"))>.001f ? 1.f : 0.f;
    }
    // Volumetric fog (docs/VOLUMETRIC_FOG.md): the froxel grid at the engine's Epic scalability in Quality (8 px, 128
    // slices) and its High one in Performance (16 px, 64 slices); off skips the passes entirely.
    const bool Fog = Get(TEXT("fog")) > .5f;
    Set(TEXT("r.VolumetricFog"),Fog ? 1.f : 0.f);
    Set(TEXT("r.VolumetricFog.GridPixelSize"),PerformanceMode ? 16.f : 8.f);
    Set(TEXT("r.VolumetricFog.GridSizeZ"),PerformanceMode ? 64.f : 128.f);
    FVolumetricFogLook FogLook;
    FogLook.Density = Get(TEXT("fog_density")); FogLook.Reach = Get(TEXT("fog_reach"))*100.f;
    FogLook.Falloff = Get(TEXT("fog_falloff")); FogLook.Scattering = Get(TEXT("fog_glow"));
    FogLook.Shafts = Get(TEXT("fog_shafts")); FogLook.Town = Get(TEXT("fog_town"));
    FogLook.bPerformance = PerformanceMode != 0;
    for (TActorIterator<AJapanWorld> It(Owner->GetWorld()); It; ++It)
    {
        It->WindSpeed = Get(TEXT("wind"))*100.f;
        It->ApplyPerformanceSettings(PerformanceMode != 0);
        It->ApplyVolumetricFog(Fog,FogLook);
    }
    // The sun: warmth 0 is a white noon sun, .5 the map's own (1, .90, .76), 1 a golden afternoon.
    const float Warmth = Get(TEXT("sun_warmth"));
    const FLinearColor SunColour = Warmth < .5f
        ? FMath::Lerp(FLinearColor(1.f,.97f,.92f),FLinearColor(1.f,.90f,.76f),Warmth*2.f)
        : FMath::Lerp(FLinearColor(1.f,.90f,.76f),FLinearColor(1.f,.72f,.48f),Warmth*2.f-1.f);
    for (TActorIterator<ADirectionalLight> It(Owner->GetWorld()); It; ++It)
    {
        It->SetActorRotation(FRotator(-Get(TEXT("sun_height")),Get(TEXT("sun_yaw")),0));
        if (auto* Light = Cast<UDirectionalLightComponent>(It->GetLightComponent()))
        {
            Light->SetIntensity(Get(TEXT("sun_strength")));
            Light->SetLightColor(SunColour);
        }
    }
    // The shadows' fill: the sky light, bluer as the sun warms (the map's (.95, .96, 1) at warmth .5 and below),
    // and Lumen's bounce on the unbound volume; bounded looks (the harbor's) keep their own.
    const FLinearColor SkyColour = FMath::Lerp(FLinearColor(.95f,.96f,1.f),FLinearColor(.84f,.89f,1.f),FMath::Max(0.f,Warmth*2.f-1.f));
    for (TActorIterator<ASkyLight> It(Owner->GetWorld()); It; ++It)
        if (USkyLightComponent* Sky = It->GetLightComponent())
        {
            Sky->SetIntensity(Get(TEXT("sky_fill")));
            Sky->SetLightColor(SkyColour);
        }
    for (TActorIterator<APostProcessVolume> It(Owner->GetWorld()); It; ++It)
        if (It->bUnbound)
        {
            It->Settings.bOverride_IndirectLightingIntensity = true;
            It->Settings.IndirectLightingIntensity = Get(TEXT("bounce"));
        }
    if (auto* Scale = IConsoleManager::Get().FindConsoleVariable(TEXT("r.ScreenPercentage"))) Scale->Set(Get(TEXT("render_scale")),ECVF_SetByCode);
    ReportProfile();
}

FSkateFeel UJapanPreferences::GetSkateFeel() const
{
    // Easy, Normal and Hardcore are the difficulty as made; Custom tunes every value on its base difficulty. The stick,
    // mouse and camera apply in every mode. Custom values stay saved while a preset is played.
    FSkateFeel Feel = FSkateFeel::Defaults();
    const int32 Mode = FMath::Clamp(FMath::RoundToInt(Get(TEXT("skate_mode"))), 0, SkateCustom);
    for (const FSkateGroup& Group : SkateGroups())
        for (const FSkateKnob& Knob : Group.Knobs)
            if (Knob.Field && (Knob.bAlways || Mode == SkateCustom)) Feel.*Knob.Field = Get(Knob.Key);
    if (Mode != SkateCustom) Feel.Difficulty = SkateDifficulties[Mode];
    else
    {
        Feel.Difficulty = SkateDifficulties[FMath::Clamp(FMath::RoundToInt(Get(TEXT("skate_difficulty"))), 0, 2)];
        Feel.AutoPush = int8(FMath::Clamp(FMath::RoundToInt(Get(TEXT("skate_auto_push"))), 0, 2) - 1);
        Feel.AssistedAir = int8(FMath::Clamp(FMath::RoundToInt(Get(TEXT("skate_assisted_air"))), 0, 2) - 1);
    }
    // Full tilt stays clear of the dead zone (FSkateFeel::Validate).
    Feel.StickReach = FMath::Min(1.f, FMath::Max(Feel.StickReach, Feel.StickDeadZone + .2f));
    return Feel;
}
void UJapanPreferences::ResetSkate(bool bCustom)
{
    const FSkateFeel Defaults = FSkateFeel::Defaults();
    for (const FSkateGroup& Group : SkateGroups())
        for (const FSkateKnob& Knob : Group.Knobs)
            if (Knob.bAlways != bCustom && FCString::Strcmp(Knob.Key, TEXT("skate_mode")) != 0)
                for (FJapanPreference& V : Values) if (V.Key == Knob.Key) V.Value = SkateDefault(Knob, Defaults);
    Apply(); Save();
}
bool UJapanPreferences::IsSkateCustomStock() const
{
    const FSkateFeel Defaults = FSkateFeel::Defaults();
    for (const FSkateGroup& Group : SkateGroups())
        for (const FSkateKnob& Knob : Group.Knobs)
            if (!Knob.bAlways && FCString::Strcmp(Knob.Key, TEXT("skate_difficulty")) != 0 && !FMath::IsNearlyEqual(Get(Knob.Key), SkateDefault(Knob, Defaults), 1e-4f))
                return false;
    return true;
}

void UJapanPreferences::ReportProfile() const
{
    // Read the values back rather than logging what we intended to set: a saved GameUserSettings, a
    // command line -ExecCmds or a later scalability change can win, and a ledger row that records an
    // intention instead of the effective value is worthless. Harnesses parse this line as JSON.
    const auto Number = [](const TCHAR* Name) -> FString
    {
        if (const auto* CVar = IConsoleManager::Get().FindConsoleVariable(Name))
            return FString::SanitizeFloat(CVar->GetFloat());
        return TEXT("null");
    };
    FString Fog = TEXT("null"), FogFalloff = TEXT("null"), FogVolumetric = TEXT("null"), Contact = TEXT("null");
    if (Owner && Owner->GetWorld())
    {
        for (TActorIterator<AExponentialHeightFog> It(Owner->GetWorld()); It; ++It)
            if (const auto* Component = It->GetComponent())
            {
                Fog = FString::SanitizeFloat(Component->FogDensity);
                FogFalloff = FString::SanitizeFloat(Component->FogHeightFalloff);
                FogVolumetric = Component->bEnableVolumetricFog ? TEXT("1") : TEXT("0");
                break;
            }
        for (TActorIterator<ADirectionalLight> It(Owner->GetWorld()); It; ++It)
            if (const auto* Light = Cast<UDirectionalLightComponent>(It->GetLightComponent()))
            {
                Contact = FString::SanitizeFloat(Light->ContactShadowLength);
                break;
            }
    }
    UE_LOG(LogTemp,Display,TEXT("PROFILE {\"desktop\": %.0f, \"haze\": %.3f, \"supersample\": %.3f, ")
        TEXT("\"performance\": %.0f, \"render_scale\": %.1f, \"painterly\": %.3f, ")
        TEXT("\"gi_quality\": %s, \"gi_gather\": %s, \"gi_probe_resolution\": %s, \"gi_probe_budget\": %s, ")
        TEXT("\"gi_irradiance_format\": %s, \"gi_stochastic\": %s, ")
        TEXT("\"occlusion_cull\": %s, \"contact_shadows\": %s, \"contact_length\": %s, ")
        TEXT("\"short_range_ao\": %s, \"fog_density\": %s, \"fog_falloff\": %s, ")
        TEXT("\"volumetric_fog\": %s, \"volumetric_fog_cvar\": %s, \"volumetric_fog_grid\": %s, ")
        TEXT("\"dynres_mode\": %s, \"dynres_min\": %s, \"dynres_max\": %s, \"dynres_headroom\": %s, ")
        TEXT("\"dynres_budget\": %s, \"screen_percentage\": %s, \"aa_method\": %s, \"max_fps\": %s}"),
        Get(TEXT("desktop")),0.f,1.f,
        Get(TEXT("performance")),Get(TEXT("render_scale")),Get(TEXT("painterly")),
        *Number(TEXT("sg.GlobalIlluminationQuality")),*Number(TEXT("r.Lumen.FinalGatherMethod")),
        *Number(TEXT("r.Lumen.ScreenProbeGather.RadianceCache.ProbeResolution")),
        *Number(TEXT("r.Lumen.ScreenProbeGather.RadianceCache.NumProbesToTraceBudget")),
        *Number(TEXT("r.Lumen.ScreenProbeGather.IrradianceFormat")),
        *Number(TEXT("r.Lumen.ScreenProbeGather.StochasticInterpolation")),
        *Number(TEXT("r.InstanceCulling.OcclusionCull")),*Number(TEXT("r.ContactShadows")),*Contact,
        *Number(TEXT("r.Lumen.ScreenProbeGather.ShortRangeAO")),*Fog,*FogFalloff,
        *FogVolumetric,*Number(TEXT("r.VolumetricFog")),*Number(TEXT("r.VolumetricFog.GridPixelSize")),
        *Number(TEXT("r.DynamicRes.OperationMode")),*Number(TEXT("r.DynamicRes.MinScreenPercentage")),
        *Number(TEXT("r.DynamicRes.MaxScreenPercentage")),*Number(TEXT("r.DynamicRes.TargetedGPUHeadRoomPercentage")),
        *Number(TEXT("r.DynamicRes.FrameTimeBudget")),*Number(TEXT("r.ScreenPercentage")),
        *Number(TEXT("r.AntiAliasingMethod")),*Number(TEXT("t.MaxFPS")));
}
bool UJapanPreferences::IsSessionOnly(const FString& Key)
{
    // Desktop-specific tuning is chosen per launch (japan/run.sh desktop), never saved.
    // Retired haze/supersample keys stay excluded so old experiment files cannot leak into saves.
    // One shared settings.txt serves the phone stream from this same project, and a saved desktop=1
    // would silently switch the phone into the desktop profile the next time the stream started.
    return Key == TEXT("desktop") || Key == TEXT("haze") || Key == TEXT("supersample");
}

void UJapanPreferences::Save()
{
    for (const auto& V : Values)
    {
        if (IsSessionOnly(V.Key)) { SavedValues.Remove(V.Key); continue; }
        SavedValues.Add(V.Key,FString::SanitizeFloat(V.Value));
    }
    TArray<FString> Keys; SavedValues.GetKeys(Keys); Keys.Sort();
    FString Content;
    for (const auto& K : Keys) Content += K+TEXT("=")+SavedValues[K]+TEXT("\n");
    FFileHelper::SaveStringToFile(Content,*SettingsFile);
}
void UJapanPreferences::ResetLight()
{
    for (auto& V : Values)
        for (const TCHAR* Key : LightKeys)
            if (V.Key == Key) V.Value = Defaults.FindRef(V.Key);
    Apply(); Save();
}
void UJapanPreferences::ToggleMenu()
{
    if (Menu) { CloseMenu(); return; }
    OpenMenu(false);
}
void UJapanPreferences::OpenMenu(bool bSkate)
{
    if (!GEngine || !GEngine->GameViewport) return;
    if (Menu) { GEngine->GameViewport->RemoveViewportWidgetContent(Menu.ToSharedRef()); Menu.Reset(); }
    TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
    TSharedPtr<SButton> FirstControl;
    // A value's slider row: its label, the slider and the value with as many decimals as its step shows.
    const auto AddSlider = [this,&Rows](int32 I, TFunction<bool()> Enabled, const FString& Hint)
    {
        TSharedRef<SSlider> Slider = SNew(SSlider)
            .StepSize(Values[I].Step > 0.f ? Values[I].Step/(Values[I].Maximum-Values[I].Minimum) : .01f)
            .IsEnabled_Lambda([Enabled] { return !Enabled || Enabled(); })
            .Value_Lambda([this,I] { const auto& V = Values[I]; return (V.Value-V.Minimum)/(V.Maximum-V.Minimum); })
            .OnValueChanged_Lambda([this,I](float N) { const auto& V = Values[I]; SetValue(V.Key,FMath::Lerp(V.Minimum,V.Maximum,N)); });
        Rows->AddSlot().AutoHeight().Padding(0,6)[SNew(SHorizontalBox).ToolTipText(FText::FromString(Hint))
            + SHorizontalBox::Slot().FillWidth(.48f)[SNew(STextBlock).Text(FText::FromString(Values[I].Label)).Font(FCoreStyle::GetDefaultFontStyle("Regular",14)).ColorAndOpacity(FLinearColor::White)]
            + SHorizontalBox::Slot().FillWidth(.38f)[Slider]
            + SHorizontalBox::Slot().FillWidth(.14f).Padding(12,0)[SNew(STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Regular",14)).ColorAndOpacity(FLinearColor::White).Text_Lambda([this,I]
            {
                // As many decimals as the slider's step shows (fog density moves by 0.005).
                const float Step = Values[I].Step;
                const int32 Digits = Step <= 0.f ? 2 : Step >= 1.f ? 0 : FMath::Clamp(FMath::CeilToInt(-FMath::LogX(10.f,Step)-1e-3f),1,3);
                FNumberFormattingOptions Format; Format.SetUseGrouping(false).SetMinimumFractionalDigits(Digits).SetMaximumFractionalDigits(Digits);
                return FText::AsNumber(Values[I].Value,&Format);
            })]];
    };
    // Another page, out of the click that asked for it.
    const auto ShowPage = [this](bool bToSkate)
    {
        if (AWandererCharacter* Pawn = Owner)
            Pawn->GetWorldTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(this,[this,bToSkate] { if (Menu) OpenMenu(bToSkate); }));
    };
    const auto Finish = [this,&Rows,&FirstControl]
    {
        Menu = SNew(SBorder).HAlign(HAlign_Center).VAlign(VAlign_Center).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0,0,0,.55f))
            [SNew(SBox).WidthOverride(620).MaxDesiredHeight(760)
                [SNew(SBorder).Padding(28).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(.025f,.032f,.028f,1))
                    [SNew(SScrollBox)+SScrollBox::Slot()[Rows]]]];
        GEngine->GameViewport->AddViewportWidgetContent(Menu.ToSharedRef(),20);
        Owner->SetMenuOpen(true);
        GEngine->GameViewport->SetMouseCaptureMode(EMouseCaptureMode::NoCapture);
        FSlateApplication::Get().SetKeyboardFocus(FirstControl, EFocusCause::SetDirectly);
    };
    if (bSkate)
    {
        // The Skate feel page: the mode (a preset difficulty or Custom), then every custom value by what it changes,
        // greyed out unless Custom is picked, then the stick, mouse and camera for every mode. Changes apply at once,
        // mid-ride too, and are saved like the rest.
        const auto IsCustom = [this] { return FMath::RoundToInt(Get(TEXT("skate_mode"))) == SkateCustom; };
        Rows->AddSlot().AutoHeight().Padding(0,0,0,12)[SNew(STextBlock).Text(FText::FromString(TEXT("Skate feel"))).Font(FCoreStyle::GetDefaultFontStyle("Bold",24)).ColorAndOpacity(FLinearColor::White)];
        // The mode: four buttons, the current one lit.
        TSharedRef<SHorizontalBox> Modes = SNew(SHorizontalBox);
        for (int32 M = 0; M <= SkateCustom; ++M)
        {
            TSharedRef<SButton> Button = SNew(SButton).HAlign(HAlign_Center).Text(FText::FromString(SkateModes[M]))
                .ToolTipText(FText::FromString(M == SkateCustom ? TEXT("Tune every value below on a base difficulty.") : TEXT("This difficulty as made.")))
                .ButtonColorAndOpacity_Lambda([this,M] { return FSlateColor(FMath::RoundToInt(Get(TEXT("skate_mode"))) == M ? FLinearColor(.35f,.75f,.55f) : FLinearColor(.45f,.45f,.45f)); })
                .OnClicked_Lambda([this,M] { SetValue(TEXT("skate_mode"), float(M)); return FReply::Handled(); });
            if (!FirstControl) FirstControl = Button;
            Modes->AddSlot().FillWidth(1.f).Padding(M ? 6 : 0,0,0,0)[Button];
        }
        Rows->AddSlot().AutoHeight().Padding(0,0,0,10)[Modes];
        Rows->AddSlot().AutoHeight().Padding(0,0,0,6)[SNew(STextBlock).AutoWrapText(true).ColorAndOpacity(FLinearColor(.8f,.84f,.82f))
            .Text_Lambda([this,IsCustom] { return FText::FromString(IsCustom()
                ? TEXT("Custom: multipliers on the base difficulty's own values. Changes take effect at once, even mid-ride; Reset custom values puts each back to the game's own. Hover a row for what it does.")
                : FString::Printf(TEXT("%s, as made. Pick Custom to tune the values below; your custom values are kept while you play a preset."), SkateModes[FMath::Clamp(FMath::RoundToInt(Get(TEXT("skate_mode"))),0,2)])); })];
        for (const FSkateGroup& Group : SkateGroups())
        {
            if (FCString::Strcmp(Group.Name, TEXT("Mode")) == 0) continue;
            const bool bAlways = Group.Knobs.Num() && Group.Knobs[0].bAlways;
            if (bAlways)
                Rows->AddSlot().AutoHeight().Padding(0,18,0,0)[SNew(SButton).Text(FText::FromString(TEXT("Reset custom values to stock")))
                    .IsEnabled_Lambda(IsCustom).OnClicked_Lambda([this] { ResetSkate(true); return FReply::Handled(); })];
            Rows->AddSlot().AutoHeight().Padding(0,14,0,4)[SNew(STextBlock).Text(FText::FromString(Group.Name)).Font(FCoreStyle::GetDefaultFontStyle("Bold",16))
                .ColorAndOpacity_Lambda([IsCustom,bAlways] { return FSlateColor(bAlways || IsCustom() ? FLinearColor::White : FLinearColor(.5f,.52f,.5f)); })];
            for (const FSkateKnob& Knob : Group.Knobs)
            {
                const int32 I = Values.IndexOfByPredicate([&Knob](const FJapanPreference& V) { return V.Key == Knob.Key; });
                if (I == INDEX_NONE) continue;
                const TFunction<bool()> Enabled = Knob.bAlways ? TFunction<bool()>() : TFunction<bool()>(IsCustom);
                if (Knob.Field) { AddSlider(I, Enabled, Knob.Hint); continue; }
                const FString Key = Knob.Key, Label = Knob.Label;
                const int32 Choices = FMath::RoundToInt(Knob.Maximum) + 1;
                Rows->AddSlot().AutoHeight().Padding(0,4)[SNew(SButton).ToolTipText(FText::FromString(Knob.Hint)).IsEnabled_Lambda([Enabled] { return !Enabled || Enabled(); })
                    .Text_Lambda([this,Key,Label] { return FText::FromString(Label+TEXT(": ")+SkateChoice(Key,FMath::RoundToInt(Get(*Key)))); })
                    .OnClicked_Lambda([this,Key,Choices] { SetValue(Key,float((FMath::RoundToInt(Get(*Key))+1)%Choices)); return FReply::Handled(); })];
            }
        }
        Rows->AddSlot().AutoHeight().Padding(0,18,0,0)[SNew(SButton).Text(FText::FromString(TEXT("Reset controls and camera")))
            .OnClicked_Lambda([this] { ResetSkate(false); return FReply::Handled(); })];
        Rows->AddSlot().AutoHeight().Padding(0,10,0,0)[SNew(SButton).Text(FText::FromString(TEXT("Back")))
            .OnClicked_Lambda([ShowPage] { ShowPage(false); return FReply::Handled(); })];
        Finish();
        return;
    }
    Rows->AddSlot().AutoHeight().Padding(0,0,0,18)[SNew(STextBlock).Text(FText::FromString(TEXT("Yorimichi — settings"))).Font(FCoreStyle::GetDefaultFontStyle("Bold",24)).ColorAndOpacity(FLinearColor::White)];
    Rows->AddSlot().AutoHeight().Padding(0,0,0,12)[SNew(STextBlock).AutoWrapText(true)
        .Text_Lambda([this] { return FText::FromString(Get(TEXT("performance")) > .5f
            ? TEXT("Performance uses lighter shadows and distant detail to keep movement smooth.")
            : TEXT("Quality increases shadow detail at the selected resolution.")); })];
    // The character switch (ABotwRider::SwitchPlayer): Cairo, with the merged move set when it is built, and every BOTW
    // character with a rider definition. The switch waits for the next tick, out of the menu's click.
    const auto Switch = [this](const FString& Name)
    {
        CloseMenu();
        if (AWandererCharacter* Pawn = Owner)
            Pawn->GetWorldTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(Pawn,[Pawn,Name] { ABotwRider::SwitchPlayer(Pawn,Name); }));
    };
    const FString Playing = ABotwRider::NameOf(Owner);
    const bool bPlayingCairo = Playing == TEXT("Cairo") || Playing == ACairoCharacter::BotwName();
    const auto CairoName = [this] { return ACairoCharacter::HasBotw() && FMath::RoundToInt(Get(TEXT("moveset"))) != UBotwMoveSet::LegacyCairo
        ? ACairoCharacter::BotwName() : FString(TEXT("Cairo")); };
    if (const TArray<FString> Riders = ABotwRider::Available(); Riders.Num())
    {
        TSharedRef<SWrapBox> Characters = SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(8,8));
        TArray<FString> Names = {TEXT("Cairo")}; Names.Append(Riders);
        for (const FString& Name : Names)
        {
            const bool bCairo = Name == TEXT("Cairo");
            Characters->AddSlot()[SNew(SButton).IsEnabled(bCairo ? !bPlayingCairo : Name != Playing)
                .Text(FText::FromString(ABotwRider::Label(Name)))
                .OnClicked_Lambda([Switch,CairoName,Name,bCairo] { Switch(bCairo ? CairoName() : Name); return FReply::Handled(); })];
        }
        Rows->AddSlot().AutoHeight().Padding(0,0,0,6)[SNew(STextBlock).Text(FText::FromString(TEXT("Character"))).Font(FCoreStyle::GetDefaultFontStyle("Bold",16)).ColorAndOpacity(FLinearColor::White)];
        Rows->AddSlot().AutoHeight().Padding(0,0,0,18)[Characters];
    }
    TArray<FString> Toggles = {TEXT("performance"),TEXT("fog"),TEXT("show_fps"),TEXT("goofy")};
    if (Values.ContainsByPredicate([](const FJapanPreference& V) { return V.Key == TEXT("moveset"); })) Toggles.Append({TEXT("moveset"),TEXT("shield")});
    for (const FString& Key : Toggles)
    {
        TSharedRef<SButton> Button = SNew(SButton)
            .Text_Lambda([this,Key]
            {
                const bool Enabled = Get(*Key) > .5f;
                if (Key == TEXT("goofy")) return FText::FromString(Enabled
                    ? TEXT("Skate stance: Goofy · right foot forward")
                    : TEXT("Skate stance: Regular · left foot forward"));
                if (Key == TEXT("moveset"))
                {
                    const int32 Choice = FMath::RoundToInt(Get(*Key));
                    return FText::FromString(Choice == UBotwMoveSet::LegacyCairo ? TEXT("Move set: Cairo (legacy) · roll and dashes")
                        : Choice == UBotwMoveSet::LegacyBotw ? TEXT("Move set: Breath of the Wild (legacy) · no double jump")
                        : TEXT("Move set: merged · double jump, glider, dodges"));
                }
                if (Key == TEXT("fog")) return FText::FromString(Enabled
                    ? TEXT("Volumetric fog: on · valley mist and light shafts")
                    : TEXT("Volumetric fog: off"));
                if (Key == TEXT("shield")) return FText::FromString(Enabled
                    ? TEXT("Shield: carried · it guards and parries")
                    : TEXT("Shield: off · the sword guards and parries"));
                return FText::FromString(Key == TEXT("performance")
                    ? (Enabled ? TEXT("Graphics: Performance · 60 fps target") : TEXT("Graphics: Quality"))
                    : (Enabled ? TEXT("Frame rate: shown") : TEXT("Frame rate: hidden")));
            })
            .OnClicked_Lambda([this,Key,Switch,CairoName,bPlayingCairo]
            {
                if (Key == TEXT("moveset"))
                {
                    // Merged, Cairo (legacy), BOTW (legacy), round again. Cairo between his legacy moves and a move set
                    // needs the character switch; anything else takes it at once (Apply).
                    const FString Before = CairoName();
                    SetValue(Key,float((FMath::RoundToInt(Get(*Key))+1)%3));
                    if (bPlayingCairo && CairoName() != Before) Switch(CairoName());
                    return FReply::Handled();
                }
                SetValue(Key,Get(*Key) > .5f ? 0.f : 1.f);   // Apply hands the shield to the move set at once
                return FReply::Handled();
            });
        if (!FirstControl) FirstControl = Button;
        Rows->AddSlot().AutoHeight().Padding(0,0,0,10)[Button];
    }
    // Every way the board rides, on a page of its own.
    Rows->AddSlot().AutoHeight().Padding(0,0,0,10)[SNew(SButton).Text(FText::FromString(TEXT("Skate feel · pop, flicks, rails, speed, bails...")))
        .OnClicked_Lambda([ShowPage] { ShowPage(true); return FReply::Handled(); })];
    for (int32 I = 0; I < Values.Num(); ++I)
    {
        // Session-only keys are launch flags (japan/run.sh desktop), not player settings, so they
        // stay out of a menu that the phone shows too.
        if (IsSessionOnly(Values[I].Key)) continue;
        if (IsToggle(Values[I].Key) || Values[I].Key == TEXT("moveset")) continue;   // a button above
        if (Values[I].Key.StartsWith(TEXT("skate_"))) continue;                       // the Skate feel page
        if (Values[I].Key == LightKeys[0])
            Rows->AddSlot().AutoHeight().Padding(0,16,0,4)[SNew(STextBlock).Text(FText::FromString(TEXT("Light"))).Font(FCoreStyle::GetDefaultFontStyle("Bold",16)).ColorAndOpacity(FLinearColor::White)];
        const bool bFogDetail = Values[I].Key.StartsWith(TEXT("fog_"));
        AddSlider(I, bFogDetail ? TFunction<bool()>([this] { return Get(TEXT("fog")) > .5f; }) : TFunction<bool()>(), FString());
    }
    Rows->AddSlot().AutoHeight().Padding(0,8,0,0)[SNew(SButton).Text(FText::FromString(TEXT("Reset the light")))
        .OnClicked_Lambda([this] { ResetLight(); return FReply::Handled(); })];
    Rows->AddSlot().AutoHeight().Padding(0,18,0,0)[SNew(SButton).Text(FText::FromString(TEXT("Resume"))).OnClicked_Lambda([this] { CloseMenu(); return FReply::Handled(); })];
    Finish();
}
void UJapanPreferences::CloseMenu()
{
    if (Menu && GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(Menu.ToSharedRef());
    Menu.Reset();
    if (Owner) Owner->SetMenuOpen(false);
}

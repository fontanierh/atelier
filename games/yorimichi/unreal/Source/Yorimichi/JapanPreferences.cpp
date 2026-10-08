#include "JapanPreferences.h"
#include "AtelierSettings.h"
#include "JapanNetwork.h"
#include "JapanSession.h"
#include "PlayableCharacter.h"
#include "AdventureMoveSet.h"
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
#include "HAL/PlatformMisc.h"
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
FString RendererRestartRequest()
{
    FString Request;
    if (FParse::Param(FCommandLine::Get(),TEXT("renderrestart")))
        FParse::Value(FCommandLine::Get(),TEXT("renderrestartrequest="),Request);
    return Request;
}
const TCHAR* RendererName(int32 Renderer) { return Renderer ? TEXT("Lumen") : TEXT("Forward"); }
// A packaged game is cooked for forward shading only (the shader compiler fixes FORWARD_SHADING for the target), so it
// has no Lumen shaders to switch to. The editor keeps both.
constexpr bool bLumenAvailable = WITH_EDITOR != 0;
const TCHAR* const LumenUnavailable = TEXT("Lumen is not available in this build: it is packaged for forward lighting only.");
// The Skate feel page (docs/SKATE.md, "Skate feel menu"): every value that changes how the board rides, saved as
// skate_<name>. The mode picks Easy, Normal or Hardcore as made, or Custom, where every value below is tuned on a base
// difficulty; the stick, mouse, tight flicks and camera (bAlways) apply in every mode. A knob without a field is a choice:
// the mode (0 easy, 1 normal, 2 hardcore, 3 custom), the base difficulty (0 easy, 1 normal, 2 hardcore), tight flicks
// (0 off, 1 on) or a switch (0 the difficulty's own, 1 off, 2 on).
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
            {TEXT("skate_tight_flicks"), TEXT("Tight hardflips and inwards"), TEXT("Also reads a hardflip or inward heelflip flicked close to straight down then up, as newer skate games do, beside the wide arc."), 0, 1, 1, nullptr, true},
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
    if (Key == TEXT("skate_tight_flicks")) return Choice == 1 ? TEXT("On") : TEXT("Off");
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
    if (FCString::Strcmp(Knob.Key, TEXT("skate_tight_flicks")) == 0) return float(Defaults.TightFlicks);
    return float((FCString::Strcmp(Knob.Key, TEXT("skate_auto_push")) == 0 ? Defaults.AutoPush : Defaults.AssistedAir) + 1);
}
}

void UJapanPreferences::Initialize(AWandererCharacter* Pawn)
{
    Owner = Pawn;
    Values = {
        {TEXT("performance"),TEXT("Graphics"),1.f,0.f,1.f},
        {TEXT("renderer"),TEXT("Lighting"),0.f,0.f,1.f},
        {TEXT("tree_optimization"),TEXT("Tree optimization"),1.f,0.f,1.f},
        {TEXT("tree_lod_mode"),TEXT("Tree detail comparison"),0.f,0.f,3.f,1.f},
        {TEXT("tree_lod_distance"),TEXT("Keep tree detail farther (x)"),1.5f,.5f,3.f,.1f},
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
    // The merged move set is the default; Cairo's original moves remain available.
    const FPlayableCharacter* MergedDefault = FPlayableCharacter::Find(FPlayableCharacter::Default().MoveSet);
    if ((MergedDefault && MergedDefault->Built()) || FPlayableCharacter::Available().Num())
    {
        const int32 After = Values.IndexOfByPredicate([](const FJapanPreference& V) { return V.Key == TEXT("goofy"); })+1;
        Values.Insert({TEXT("moveset"),TEXT("Move set"),0.f,0.f,1.f},After);
    }
    DefaultValues.Reset();
    for (const FJapanPreference& V : Values) DefaultValues.Add(V.Key,V.Value);
    SettingsFile=FilePath();
    UE_LOG(LogTemp,Display,TEXT("PREFERENCES file=%s"),*SettingsFile);
    SavedValues=ReadSaved();
    for (FJapanPreference& V : Values)
        if (const FString* Text = SavedValues.Find(V.Key))
        {
            float Number = 0;
            if (LexTryParseString(Number,**Text) && FMath::IsFinite(Number)) V.Value = FMath::Clamp(Number,V.Minimum,V.Maximum);
        }
    for (FJapanPreference& V : Values)
        if (V.Key==TEXT("tree_lod_mode") || V.Key==TEXT("tree_lod_distance"))
            V.Value=FMath::Clamp(V.Minimum+FMath::RoundToFloat((V.Value-V.Minimum)/V.Step)*V.Step,V.Minimum,V.Maximum);
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
    // Desktop previews keep menu edits in their own file (-preferencesfile=); ordinary play/stream
    // keeps the existing shared path. The launcher seeds a separate copy.
    return AtelierSettings::FilePath();
}
TMap<FString,FString> UJapanPreferences::ReadSaved()
{
    TMap<FString,FString> Result = AtelierSettings::ReadFile(FilePath());
    // A stale desktop key in the shared file must not switch a phone session into the profile.
    for (auto It = Result.CreateIterator(); It; ++It) if (IsSessionOnly(It.Key())) It.RemoveCurrent();
    // A file saved before the current default light keeps every light value it wrote, the old defaults
    // among them: let it take the new light once. Command-line overrides below still apply.
    if (float Version = 0; !Result.Contains(TEXT("light_version")) || !LexTryParseString(Version,*Result[TEXT("light_version")]) || Version < LightVersion)
    {
        for (const TCHAR* Key : LightKeys) Result.Remove(Key);
        Result.Add(TEXT("light_version"),FString::FromInt(LightVersion));
    }
    Result.Append(AtelierSettings::Overrides());
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
    return Key == TEXT("performance") || Key == TEXT("renderer") || Key == TEXT("tree_optimization") ||
        Key == TEXT("show_fps") || Key == TEXT("fog") || Key == TEXT("goofy") || Key == TEXT("shield");
}
float UJapanPreferences::Get(const TCHAR* Key) const
{
    for (const auto& V : Values) if (V.Key == Key) return V.Value;
    return 0;
}
bool UJapanPreferences::SetValue(const FString& Key, float Number)
{
    GraphicsError.Reset();
    if (!FMath::IsFinite(Number)) return false;
    if (Key == TEXT("renderer") && Number > .5f && !bLumenAvailable)
    {
        GraphicsError = LumenUnavailable;   // refused before anything is changed or saved
        return false;
    }
    if (Key == TEXT("renderer") || Key == TEXT("tree_optimization") ||
        Key == TEXT("tree_lod_mode") || Key == TEXT("tree_lod_distance")) return SetGraphicsChoice(Key,Number);
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
bool UJapanPreferences::CanRestartRenderer() { return !RendererRestartRequest().IsEmpty(); }
int32 UJapanPreferences::CurrentRenderer()
{
    const auto* Forward = IConsoleManager::Get().FindConsoleVariable(TEXT("r.ForwardShading"));
    return Forward && Forward->GetInt() == 0 ? 1 : 0;
}
bool UJapanPreferences::SetGraphicsChoice(const FString& Key, float Number)
{
    for (FJapanPreference& Value : Values) if (Value.Key == Key)
    {
        const float Before = Value.Value;
        Number=FMath::Clamp(Number,Value.Minimum,Value.Maximum);
        if (Value.Step>0.f) Number=FMath::Clamp(Value.Minimum+FMath::RoundToFloat((Number-Value.Minimum)/Value.Step)*Value.Step,Value.Minimum,Value.Maximum);
        if (IsToggle(Key)) Number=Number>.5f?1.f:0.f;
        const bool bTree=Key==TEXT("tree_optimization") || Key==TEXT("tree_lod_mode") || Key==TEXT("tree_lod_distance");
        const bool BeforeEnabled=Get(TEXT("tree_optimization"))>.5f;
        const int32 BeforeMode=FMath::RoundToInt(Get(TEXT("tree_lod_mode")));
        const float BeforeDistance=Get(TEXT("tree_lod_distance"));
        const bool NextEnabled=Key==TEXT("tree_optimization")?Number>.5f:BeforeEnabled;
        const int32 NextMode=Key==TEXT("tree_lod_mode")?FMath::RoundToInt(Number):BeforeMode;
        const float NextDistance=Key==TEXT("tree_lod_distance")?Number:BeforeDistance;
        TArray<AJapanWorld*> ChangedWorlds;
        const auto RestoreTrees = [&]()
        {
            bool bRestored = true;
            for (AJapanWorld* World : ChangedWorlds)
                if (!World->ApplyTreeOptimization(BeforeEnabled,BeforeMode,BeforeDistance)) bRestored = false;
            return bRestored;
        };
        if (bTree && Owner && Owner->GetWorld())
            for (TActorIterator<AJapanWorld> It(Owner->GetWorld());It;++It) if (It->bLoaded)
            {
                ChangedWorlds.Add(*It);
                if (!It->ApplyTreeOptimization(NextEnabled,NextMode,NextDistance))
                {
                    GraphicsError = RestoreTrees()
                        ? TEXT("Tree detail could not be changed. Your previous setting is kept. Check that the game's tree assets are built.")
                        : TEXT("Tree detail could not be changed or restored. Restart the game before changing tree detail again.");
                    return false;
                }
            }
        Value.Value = Number;
        if (!Save())
        {
            Value.Value = Before;
            GraphicsError = RestoreTrees()
                ? TEXT("Settings could not be saved. The game has not restarted. Try again after checking storage access.")
                : TEXT("Settings could not be saved and the previous tree detail could not be restored. Restart the game before changing tree detail again.");
            return false;
        }
        const FString Request = RendererRestartRequest();
        if (Key == TEXT("renderer") && CurrentRenderer() != int32(Value.Value) && !Request.IsEmpty())
        {
            // macOS's generic RequestExitWithStatus ignores a requested return code.
            // The launcher consumes this attempt-specific request after a clean exit.
            if (!FFileHelper::SaveStringToFile(FString::Printf(TEXT("renderer=%d\n"),int32(Value.Value)),*Request,
                FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))
            {
                GraphicsError = TEXT("Your setting is saved, but the restart could not be requested. The game is still running; try again or relaunch later.");
                return false;
            }
            UE_LOG(LogTemp,Display,TEXT("GRAPHICS RESTART renderer=%s request=%s"),RendererName(int32(Value.Value)),*Request);
            FPlatformMisc::RequestExit(false);
        }
        else Apply();
        return true;
    }
    return false;
}
void UJapanPreferences::Apply()
{
    if (!Owner || !Owner->IsLocallyControlled()) return;
    if (!JapanNetwork::IsOnline(Owner->GetWorld())) Owner->SetStaminaRings(FMath::RoundToInt(Get(TEXT("stamina_rings"))));
    if (USkateComponent* Skate = Owner->GetSkate())
    {
        Skate->SetGoofy(Get(TEXT("goofy")) > .5f);
        // At once, mid-ride too; an unchanged feel leaves the session alone.
        FString Error;
        if (!Skate->SetFeel(JapanNetwork::IsOnline(Owner->GetWorld()) ? FSkateFeel::Defaults() : GetSkateFeel(), Error)) UE_LOG(LogTemp, Warning, TEXT("PREFERENCES skate feel refused: %s"), *Error);
    }
    // Cairo changes between his original moves and the merged set through the character switch.
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
        if (!It->ApplyTreeOptimization(Get(TEXT("tree_optimization")) > .5f,
            FMath::RoundToInt(Get(TEXT("tree_lod_mode"))),Get(TEXT("tree_lod_distance"))) && It->bLoaded)
            GraphicsError = TEXT("Tree optimization could not be applied. Check that the game's tree assets are built.");
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
    // mouse, tight flicks and camera apply in every mode. Custom values stay saved while a preset is played.
    FSkateFeel Feel = FSkateFeel::Defaults();
    const int32 Mode = FMath::Clamp(FMath::RoundToInt(Get(TEXT("skate_mode"))), 0, SkateCustom);
    for (const FSkateGroup& Group : SkateGroups())
        for (const FSkateKnob& Knob : Group.Knobs)
            if (Knob.Field && (Knob.bAlways || Mode == SkateCustom)) Feel.*Knob.Field = Get(Knob.Key);
    Feel.TightFlicks = int8(FMath::Clamp(FMath::RoundToInt(Get(TEXT("skate_tight_flicks"))), 0, 1));
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
        TEXT("\"forward_shading\": %s, \"renderer_requested\": %.0f, \"tree_optimization_requested\": %.0f, ")
        TEXT("\"performance\": %.0f, \"render_scale\": %.1f, \"painterly\": %.3f, ")
        TEXT("\"gi_quality\": %s, \"gi_gather\": %s, \"gi_probe_resolution\": %s, \"gi_probe_budget\": %s, ")
        TEXT("\"gi_irradiance_format\": %s, \"gi_stochastic\": %s, ")
        TEXT("\"occlusion_cull\": %s, \"contact_shadows\": %s, \"contact_length\": %s, ")
        TEXT("\"short_range_ao\": %s, \"fog_density\": %s, \"fog_falloff\": %s, ")
        TEXT("\"volumetric_fog\": %s, \"volumetric_fog_cvar\": %s, \"volumetric_fog_grid\": %s, ")
        TEXT("\"dynres_mode\": %s, \"dynres_min\": %s, \"dynres_max\": %s, \"dynres_headroom\": %s, ")
        TEXT("\"dynres_budget\": %s, \"screen_percentage\": %s, \"aa_method\": %s, \"max_fps\": %s}"),
        Get(TEXT("desktop")),0.f,1.f,
        *Number(TEXT("r.ForwardShading")),Get(TEXT("renderer")),Get(TEXT("tree_optimization")),
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
    // Desktop-specific tuning is chosen per launch (the desktop play profile in game.toml), never saved.
    // Retired haze/supersample keys stay excluded so old experiment files cannot leak into saves.
    // One shared settings.txt serves the phone stream from this same project, and a saved desktop=1
    // would silently switch the phone into the desktop profile the next time the stream started.
    return Key == TEXT("desktop") || Key == TEXT("haze") || Key == TEXT("supersample");
}

bool UJapanPreferences::Save()
{
    TMap<FString,FString> NextValues = SavedValues;
    for (const auto& V : Values)
    {
        if (IsSessionOnly(V.Key)) { NextValues.Remove(V.Key); continue; }
        NextValues.Add(V.Key,FString::SanitizeFloat(V.Value));
    }
    const bool Saved = AtelierSettings::WriteFile(SettingsFile,NextValues);
    if (Saved) SavedValues = MoveTemp(NextValues);
    else
    {
        UE_LOG(LogTemp,Error,TEXT("PREFERENCES could not save %s; previous file preserved"),*SettingsFile);
    }
    return Saved;
}
void UJapanPreferences::ResetLight()
{
    for (auto& V : Values)
        for (const TCHAR* Key : LightKeys)
            if (V.Key == Key) V.Value = DefaultValues.FindRef(V.Key);
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
    Rows->AddSlot().AutoHeight().Padding(0,0,0,12)[SNew(STextBlock).Text_Lambda([this] { return FText::FromString(GraphicsError); })
        .AutoWrapText(true).ColorAndOpacity(FLinearColor(1.f,.5f,.4f))];
    // Renderer selection is persisted, but forward/deferred shaders are chosen before the process starts.
    // Never try to turn r.ForwardShading into a runtime console toggle.
    // It stays focusable (it is the menu's first control); in a packaged build it explains instead of switching.
    FirstControl = SNew(SButton).Text_Lambda([this]
        {
            if (!bLumenAvailable) return FText::FromString(TEXT("Lighting: Forward · Lumen is not in this build"));
            const int32 Choice = Get(TEXT("renderer")) > .5f ? 1 : 0;
            return FText::FromString(FString::Printf(TEXT("Lighting: %s%s"),RendererName(Choice),
                Choice == CurrentRenderer() ? TEXT("") : TEXT(" · saved, restart pending")));
        })
        .OnClicked_Lambda([this]
        {
            GraphicsError.Reset();
            if (!bLumenAvailable)
            {
                GraphicsError = LumenUnavailable;
                return FReply::Handled();
            }
            Owner->GetWorldTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(this,
                [this] { if (Menu) OpenGraphicsWarning(TEXT("renderer")); }));
            return FReply::Handled();
        });
    Rows->AddSlot().AutoHeight().Padding(0,0,0,10)[FirstControl.ToSharedRef()];
    Rows->AddSlot().AutoHeight().Padding(0,0,0,10)[SNew(SButton).Text_Lambda([this]
        { return FText::FromString(Get(TEXT("tree_optimization")) > .5f
            ? TEXT("Tree optimization: on · lighter distant leaves") : TEXT("Tree optimization: off · full detail at every distance")); })
        .OnClicked_Lambda([this]
        {
            if (Get(TEXT("tree_optimization")) < .5f) SetValue(TEXT("tree_optimization"),1.f);
            else
            {
                GraphicsError.Reset();
                Owner->GetWorldTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(this,
                    [this] { if (Menu) OpenGraphicsWarning(TEXT("tree_optimization")); }));
            }
            return FReply::Handled();
        })];
    Rows->AddSlot().AutoHeight().Padding(0,0,0,10)[SNew(SButton)
        .IsEnabled_Lambda([this] { return Get(TEXT("tree_optimization"))>.5f; })
        .Text_Lambda([this]
        {
            const TCHAR* Names[]={TEXT("Automatic · nearby trees retain full detail"),TEXT("Full detail · higher GPU cost"),
                TEXT("Intermediate detail · comparison at every distance"),TEXT("Distant detail · comparison at every distance")};
            return FText::FromString(FString(TEXT("Tree detail: "))+Names[FMath::Clamp(FMath::RoundToInt(Get(TEXT("tree_lod_mode"))),0,3)]);
        })
        .OnClicked_Lambda([this]
        {
            const int32 Next=(FMath::RoundToInt(Get(TEXT("tree_lod_mode")))+1)%4;
            if (Next==1) Owner->GetWorldTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(this,
                [this] { if (Menu) OpenGraphicsWarning(TEXT("tree_lod_mode")); }));
            else SetValue(TEXT("tree_lod_mode"),float(Next));
            return FReply::Handled();
        })];
    Rows->AddSlot().AutoHeight().Padding(0,0,0,10)[SNew(STextBlock).AutoWrapText(true)
        .Text(FText::FromString(TEXT("Automatic changes distant leaf outlines only. Higher distance values keep detailed trees farther away and cost more GPU time. Forced intermediate/distant modes are comparisons, not the default. Turning optimization off restores original full-detail trees immediately.")))];
    Rows->AddSlot().AutoHeight().Padding(0,0,0,18)[SNew(SButton).Text(FText::FromString(TEXT("Play with friends")))
        .OnClicked_Lambda([this] { CloseMenu(); if (Owner) if (auto* Session=Owner->GetGameInstance<UJapanGameInstance>()) Session->Friends(); return FReply::Handled(); })];
    // The character switch (FPlayableCharacter::SwitchPlayer): the default character (Cairo), with the merged move set when it is
    // built, and every other playable character. The switch waits for the next tick, out of the menu's click.
    const auto Switch = [this](const FString& Name)
    {
        CloseMenu();
        if (AWandererCharacter* Pawn = Owner)
            Pawn->GetWorldTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(Pawn,[Pawn,Name] { FPlayableCharacter::SwitchPlayer(Pawn,Name); }));
    };
    const FString Playing = FPlayableCharacter::NameOf(Owner);
    const FPlayableCharacter& Default = FPlayableCharacter::Default();
    const bool bPlayingDefault = Playing == Default.Name || Playing == Default.MoveSet;
    const auto DefaultName = [this]
    {
        const FPlayableCharacter& Default = FPlayableCharacter::Default();
        const FPlayableCharacter* Merged = FPlayableCharacter::Find(Default.MoveSet);
        return Merged && Merged->Built() && FMath::RoundToInt(Get(TEXT("moveset"))) != UAdventureMoveSet::LegacyCairo ? Merged->Name : Default.Name;
    };
    if (const TArray<FString> Riders = FPlayableCharacter::Available(); Riders.Num())
    {
        TSharedRef<SWrapBox> Characters = SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(8,8));
        TArray<FString> Names = {Default.Name}; Names.Append(Riders);
        for (const FString& Name : Names)
        {
            const bool bDefault = Name == Default.Name;
            Characters->AddSlot()[SNew(SButton).IsEnabled(!JapanNetwork::IsOnline(Owner->GetWorld()) && (bDefault ? !bPlayingDefault : Name != Playing))
                .Text(FText::FromString(FPlayableCharacter::Label(Name)))
                .OnClicked_Lambda([Switch,DefaultName,Name,bDefault] { Switch(bDefault ? DefaultName() : Name); return FReply::Handled(); })];
        }
        Rows->AddSlot().AutoHeight().Padding(0,0,0,6)[SNew(STextBlock).Text(FText::FromString(TEXT("Character"))).Font(FCoreStyle::GetDefaultFontStyle("Bold",16)).ColorAndOpacity(FLinearColor::White)];
        Rows->AddSlot().AutoHeight().Padding(0,0,0,18)[Characters];
    }
    if (JapanNetwork::IsOnline(Owner->GetWorld()))
        Rows->AddSlot().AutoHeight().Padding(0,0,0,12)[SNew(STextBlock).AutoWrapText(true).ColorAndOpacity(FLinearColor::White)
            .Text(FText::FromString(TEXT("Choose your character before joining. Shared games use the merged move set, two stamina rings and default skate physics.")))];
    TArray<FString> Toggles = {TEXT("performance"),TEXT("fog"),TEXT("show_fps"),TEXT("goofy")};
    if (Values.ContainsByPredicate([](const FJapanPreference& V) { return V.Key == TEXT("moveset"); })) Toggles.Add(TEXT("moveset"));
    for (const FString& Key : Toggles)
    {
        TSharedRef<SButton> Button = SNew(SButton)
            .IsEnabled(!JapanNetwork::IsOnline(Owner->GetWorld()) || (Key != TEXT("moveset") && Key != TEXT("shield")))
            .Text_Lambda([this,Key]
            {
                const bool Enabled = Get(*Key) > .5f;
                if (Key == TEXT("goofy")) return FText::FromString(Enabled
                    ? TEXT("Skate stance: Goofy · right foot forward")
                    : TEXT("Skate stance: Regular · left foot forward"));
                if (Key == TEXT("moveset"))
                {
                    const int32 Choice = FMath::RoundToInt(Get(*Key));
                    return FText::FromString(Choice == UAdventureMoveSet::LegacyCairo ? TEXT("Move set: Cairo (legacy) · roll and dashes")
                        : TEXT("Move set: merged · double jump, glider, dodges"));
                }
                if (Key == TEXT("fog")) return FText::FromString(Enabled
                    ? TEXT("Volumetric fog: on · valley mist and light shafts")
                    : TEXT("Volumetric fog: off"));
                return FText::FromString(Key == TEXT("performance")
                    ? (Enabled ? TEXT("Graphics: Performance · 60 fps target") : TEXT("Graphics: Quality"))
                    : (Enabled ? TEXT("Frame rate: shown") : TEXT("Frame rate: hidden")));
            })
            .OnClicked_Lambda([this,Key,Switch,DefaultName,bPlayingDefault]
            {
                if (Key == TEXT("moveset"))
                {
                    // Merged and Cairo (legacy), round again. Cairo between his legacy moves and a move set
                    // needs the character switch; anything else takes it at once (Apply).
                    const FString Before = DefaultName();
                    SetValue(Key,float((FMath::RoundToInt(Get(*Key))+1)%2));
                    if (bPlayingDefault && DefaultName() != Before) Switch(DefaultName());
                    return FReply::Handled();
                }
                SetValue(Key,Get(*Key) > .5f ? 0.f : 1.f);
                return FReply::Handled();
            });
        if (!FirstControl) FirstControl = Button;
        Rows->AddSlot().AutoHeight().Padding(0,0,0,10)[Button];
    }
    // Every way the board rides, on a page of its own.
    Rows->AddSlot().AutoHeight().Padding(0,0,0,10)[SNew(SButton).IsEnabled(!JapanNetwork::IsOnline(Owner->GetWorld())).Text(FText::FromString(TEXT("Skate feel · pop, flicks, rails, speed, bails...")))
        .OnClicked_Lambda([ShowPage] { ShowPage(true); return FReply::Handled(); })];
    for (int32 I = 0; I < Values.Num(); ++I)
    {
        // Session-only keys are launch flags (the desktop play profile), not player settings, so they
        // stay out of a menu that the phone shows too.
        if (IsSessionOnly(Values[I].Key)) continue;
        if (IsToggle(Values[I].Key) || Values[I].Key == TEXT("moveset") || Values[I].Key == TEXT("tree_lod_mode")) continue;   // a button above
        if (Values[I].Key.StartsWith(TEXT("skate_"))) continue;                       // the Skate feel page
        if (Values[I].Key == LightKeys[0])
            Rows->AddSlot().AutoHeight().Padding(0,16,0,4)[SNew(STextBlock).Text(FText::FromString(TEXT("Light"))).Font(FCoreStyle::GetDefaultFontStyle("Bold",16)).ColorAndOpacity(FLinearColor::White)];
        if (Values[I].Key == TEXT("stamina_rings") && JapanNetwork::IsOnline(Owner->GetWorld())) continue;
        const bool bFogDetail = Values[I].Key.StartsWith(TEXT("fog_"));
        if (Values[I].Key==TEXT("tree_lod_distance"))
        { AddSlider(I,[this] { return Get(TEXT("tree_optimization"))>.5f && Get(TEXT("tree_lod_mode"))<.5f; },FString());continue; }
        AddSlider(I, bFogDetail ? TFunction<bool()>([this] { return Get(TEXT("fog")) > .5f; }) : TFunction<bool()>(), FString());
    }
    Rows->AddSlot().AutoHeight().Padding(0,8,0,0)[SNew(SButton).Text(FText::FromString(TEXT("Reset the light")))
        .OnClicked_Lambda([this] { ResetLight(); return FReply::Handled(); })];
    Rows->AddSlot().AutoHeight().Padding(0,18,0,0)[SNew(SButton).Text(FText::FromString(TEXT("Resume"))).OnClicked_Lambda([this] { CloseMenu(); return FReply::Handled(); })];
    Finish();
}
void UJapanPreferences::OpenGraphicsWarning(const FString& Key)
{
    if (!Owner || !GEngine || !GEngine->GameViewport) return;
    const bool bRenderer = Key == TEXT("renderer");
    const bool bFullComparison=Key==TEXT("tree_lod_mode");
    const float Choice = Get(*Key) > .5f ? 0.f : 1.f;
    const bool bRestart = bRenderer && CurrentRenderer() != int32(Choice);
    const bool bLauncherRestart = CanRestartRenderer();
    const FString Title = bRenderer ? FString::Printf(TEXT("Switch to %s?"),RendererName(int32(Choice)))
        : bFullComparison ? TEXT("Compare full-detail trees?") : TEXT("Turn off tree optimization?");
    FString Warning = bRenderer
        ? (Choice > .5f ? TEXT("Lumen is a resource hog: it uses substantially more GPU time and memory, and can lower the frame rate. Forward is the recommended default for smooth play.")
            : TEXT("Forward uses lighter lighting and is the recommended default for smooth play."))
        : TEXT("Full-detail trees at every distance use more GPU time and can lower the frame rate. Optimization preserves close trees, materials and collision, while simplifying distant leaf outlines. This change applies immediately.");
    if (bRestart) Warning += bLauncherRestart
        ? TEXT("\n\nThe game must restart to change lighting. Your settings will be saved; your position in the current session will be lost.")
        : TEXT("\n\nLighting changes take effect on the next launch through the game launcher. Your current lighting stays active until then.");
    if (Menu) GEngine->GameViewport->RemoveViewportWidgetContent(Menu.ToSharedRef());
    TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
    Rows->AddSlot().AutoHeight().Padding(0,0,0,16)[SNew(STextBlock).Text(FText::FromString(Title))
        .Font(FCoreStyle::GetDefaultFontStyle("Bold",24)).ColorAndOpacity(FLinearColor::White)];
    Rows->AddSlot().AutoHeight().Padding(0,0,0,18)[SNew(STextBlock).Text(FText::FromString(Warning)).AutoWrapText(true)
        .ColorAndOpacity(FLinearColor(.9f,.85f,.7f))];
    Rows->AddSlot().AutoHeight().Padding(0,0,0,12)[SNew(STextBlock).Text_Lambda([this] { return FText::FromString(GraphicsError); })
        .AutoWrapText(true).ColorAndOpacity(FLinearColor(1.f,.5f,.4f))];
    TSharedRef<SButton> Cancel = SNew(SButton).Text(FText::FromString(TEXT("Cancel")))
        .OnClicked_Lambda([this]
        {
            Owner->GetWorldTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(this,[this] { if (Menu) OpenMenu(false); }));
            return FReply::Handled();
        });
    Rows->AddSlot().AutoHeight().Padding(0,0,0,10)[Cancel];
    Rows->AddSlot().AutoHeight()[SNew(SButton).Text(FText::FromString(bRestart && bLauncherRestart ? TEXT("Save and restart")
        : bRestart ? TEXT("Save for next launch") : TEXT("Confirm")))
        .OnClicked_Lambda([this,Key,Choice,bRestart,bLauncherRestart]
        {
            if (!SetValue(Key,Choice)) return FReply::Handled();
            if (!bRestart || !bLauncherRestart)
                Owner->GetWorldTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(this,[this] { if (Menu) OpenMenu(false); }));
            return FReply::Handled();
        })];
    Menu = SNew(SBorder).HAlign(HAlign_Center).VAlign(VAlign_Center).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush"))
        .BorderBackgroundColor(FLinearColor(0,0,0,.55f))
        [SNew(SBox).WidthOverride(620)[SNew(SBorder).Padding(28).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush"))
            .BorderBackgroundColor(FLinearColor(.025f,.032f,.028f,1))[Rows]]];
    GEngine->GameViewport->AddViewportWidgetContent(Menu.ToSharedRef(),20);
    Owner->SetMenuOpen(true);
    GEngine->GameViewport->SetMouseCaptureMode(EMouseCaptureMode::NoCapture);
    FSlateApplication::Get().SetKeyboardFocus(Cancel,EFocusCause::SetDirectly);
}
void UJapanPreferences::CloseMenu()
{
    if (Menu && GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(Menu.ToSharedRef());
    Menu.Reset();
    if (Owner) Owner->SetMenuOpen(false);
}

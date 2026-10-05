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

void UJapanPreferences::Initialize(AWandererCharacter* Pawn)
{
    Owner = Pawn;
    Values = {
        {TEXT("performance"),TEXT("Graphics"),1.f,0.f,1.f},
        // Session-only desktop tuning; both profiles share instance occlusion culling.
        {TEXT("desktop"),TEXT("Desktop profile"),0.f,0.f,1.f},
        {TEXT("show_fps"),TEXT("Frame rate"),1.f,0.f,1.f},
        {TEXT("fog"),TEXT("Volumetric fog"),1.f,0.f,1.f},
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
        {TEXT("exposure"),TEXT("Exposure"),.95f,.4f,2.2f},
        {TEXT("saturation"),TEXT("Saturation"),1.f,.6f,1.6f},
        {TEXT("wind"),TEXT("Wind (m/s)"),3.5f,0.f,12.f},
        {TEXT("sun_height"),TEXT("Sun elevation"),48.f,5.f,80.f},
        {TEXT("sun_yaw"),TEXT("Sun direction"),15.f,-180.f,180.f}};
    // The move set (UBotwMoveSet::Chosen: merged by default, Cairo's legacy moves or the legacy BOTW set) and its shield
    // (UBotwMoveSet::SetShield: off by default, the sword guards and parries).
    if (ACairoCharacter::HasBotw() || ABotwRider::Available().Num())
    {
        const int32 After = Values.IndexOfByPredicate([](const FJapanPreference& V) { return V.Key == TEXT("goofy"); })+1;
        Values.Insert({TEXT("shield"),TEXT("Shield"),0.f,0.f,1.f},After);
        Values.Insert({TEXT("moveset"),TEXT("Move set"),0.f,0.f,2.f},After);
    }
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
    for (auto& V : Values) if (V.Key == Key)
    {
        V.Value = FMath::Clamp(Number,V.Minimum,V.Maximum);
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
    if (Owner->GetSkate()) Owner->GetSkate()->SetGoofy(Get(TEXT("goofy")) > .5f);
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
    for (TActorIterator<AJapanWorld> It(Owner->GetWorld()); It; ++It)
    {
        It->WindSpeed = Get(TEXT("wind"))*100.f;
        It->ApplyPerformanceSettings(PerformanceMode != 0);
        It->ApplyVolumetricFog(Fog,PerformanceMode != 0);
    }
    for (TActorIterator<ADirectionalLight> It(Owner->GetWorld()); It; ++It) It->SetActorRotation(FRotator(-Get(TEXT("sun_height")),Get(TEXT("sun_yaw")),0));
    if (auto* Scale = IConsoleManager::Get().FindConsoleVariable(TEXT("r.ScreenPercentage"))) Scale->Set(Get(TEXT("render_scale")),ECVF_SetByCode);
    ReportProfile();
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
void UJapanPreferences::ToggleMenu()
{
    if (Menu) { CloseMenu(); return; }
    if (!GEngine || !GEngine->GameViewport) return;
    TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
    TSharedPtr<SButton> FirstControl;
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
    for (int32 I = 0; I < Values.Num(); ++I)
    {
        // Session-only keys are launch flags (japan/run.sh desktop), not player settings, so they
        // stay out of a menu that the phone shows too.
        if (IsSessionOnly(Values[I].Key)) continue;
        if (IsToggle(Values[I].Key) || Values[I].Key == TEXT("moveset")) continue;   // a button above
        TSharedRef<SSlider> Slider = SNew(SSlider)
            .Value_Lambda([this,I] { const auto& V = Values[I]; return (V.Value-V.Minimum)/(V.Maximum-V.Minimum); })
            .OnValueChanged_Lambda([this,I](float N) { const auto& V = Values[I]; SetValue(V.Key,FMath::Lerp(V.Minimum,V.Maximum,N)); });
        Rows->AddSlot().AutoHeight().Padding(0,6)[SNew(SHorizontalBox)
            + SHorizontalBox::Slot().FillWidth(.48f)[SNew(STextBlock).Text(FText::FromString(Values[I].Label)).Font(FCoreStyle::GetDefaultFontStyle("Regular",14)).ColorAndOpacity(FLinearColor::White)]
            + SHorizontalBox::Slot().FillWidth(.38f)[Slider]
            + SHorizontalBox::Slot().FillWidth(.14f).Padding(12,0)[SNew(STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Regular",14)).ColorAndOpacity(FLinearColor::White).Text_Lambda([this,I] { return FText::FromString(FString::Printf(TEXT("%.2f"),Values[I].Value)); })]];
    }
    Rows->AddSlot().AutoHeight().Padding(0,18,0,0)[SNew(SButton).Text(FText::FromString(TEXT("Resume"))).OnClicked_Lambda([this] { CloseMenu(); return FReply::Handled(); })];
    Menu = SNew(SBorder).HAlign(HAlign_Center).VAlign(VAlign_Center).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(0,0,0,.55f))
        [SNew(SBox).WidthOverride(620).MaxDesiredHeight(760)
            [SNew(SBorder).Padding(28).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(.025f,.032f,.028f,1))
                [SNew(SScrollBox)+SScrollBox::Slot()[Rows]]]];
    GEngine->GameViewport->AddViewportWidgetContent(Menu.ToSharedRef(),20);
    Owner->SetMenuOpen(true);
    GEngine->GameViewport->SetMouseCaptureMode(EMouseCaptureMode::NoCapture);
    FSlateApplication::Get().SetKeyboardFocus(FirstControl, EFocusCause::SetDirectly);
}
void UJapanPreferences::CloseMenu()
{
    if (Menu && GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(Menu.ToSharedRef());
    Menu.Reset();
    if (Owner) Owner->SetMenuOpen(false);
}

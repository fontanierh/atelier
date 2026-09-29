#include "JapanWorld.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "EngineUtils.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialInstanceDynamic.h"
#if WITH_EDITOR
#include "AssetCompilingManager.h"
#endif

// Runtime art comparison only. Retain the same unlit dome, tint, geometry and
// already captured ambient lighting so the first test isolates the painted sky.
static FAutoConsoleCommandWithWorldAndArgs SkyStudyCommand(TEXT("japan.SkyStudy"),
    TEXT("0 original sky, 1 Sunburst sky. Optional brightness multiplier, default 1. Requires build_sky_study.py."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* Game)
    {
        if (!Game || Args.Num()<1 || Args.Num()>2) return;
        const bool Enabled=FCString::Atoi(*Args[0])!=0;
        auto* Material=Enabled?LoadObject<UMaterialInterface>(nullptr,
            TEXT("/Game/Experiments/Sky/V3/MI_SkySunburst.MI_SkySunburst")):nullptr;
        if (Enabled && !Material)
        { UE_LOG(LogTemp,Error,TEXT("SKY STUDY material is missing")); return; }
        auto* T=LoadObject<UTexture2D>(nullptr,Enabled?
            TEXT("/Game/Experiments/Sky/V3/T_SkySunburst.T_SkySunburst"):
            TEXT("/Game/Japan/Textures/T_sky.T_sky"));
#if WITH_EDITOR
        // An imported editor texture can initially expose a 32px placeholder
        // while its derived data compiles. Complete this before binding the
        // material and starting the benchmark's settling interval.
        FAssetCompilingManager::Get().FinishAllCompilation();
#endif
        if (!T || T->GetSizeX()<1024 || T->GetSizeY()<512)
        { UE_LOG(LogTemp,Error,TEXT("SKY STUDY texture is not ready at its expected resolution")); return; }
        if (Enabled && (!T->SRGB || T->CompressionSettings!=TC_Default))
        { UE_LOG(LogTemp,Error,TEXT("SKY STUDY requires an sRGB colour texture, not normal-map compression")); return; }
        // Finish residency before binding or collecting evidence. A loaded editor
        // texture can still have only its small mip tail on the GPU.
        T->SetForceMipLevelsToBeResident(120.f);
        T->WaitForStreaming();
        if (!T->IsFullyStreamedIn())
        { UE_LOG(LogTemp,Error,TEXT("SKY STUDY texture is not fully resident")); return; }
        for (TActorIterator<AJapanWorld> It(Game); It; ++It)
        {
            auto* Sky=It->SkyDome;
            if (!Sky || !Sky->GetStaticMesh()) continue;
            auto* Selected=Enabled?Material:Sky->GetStaticMesh()->GetMaterial(0);
            if (Enabled && Args.Num()==2)
            {
                auto* Variant=UMaterialInstanceDynamic::Create(Selected,Sky);
                FLinearColor Tint(1.35,1.35,1.35,1);
                Selected->GetVectorParameterValue(FMaterialParameterInfo(TEXT("Tint")),Tint);
                Variant->SetVectorParameterValue(TEXT("Tint"),Tint*FMath::Clamp(FCString::Atof(*Args[1]),.1f,2.f));
                Selected=Variant;
            }
            Sky->SetMaterial(0,Selected);
            if (T)
            {
                UE_LOG(LogTemp,Display,TEXT("SKY texture=%s size=%dx%d residentMips=%d totalMips=%d neverStream=%d"),
                    *T->GetName(),T->GetSizeX(),T->GetSizeY(),T->GetNumResidentMips(),T->GetNumMips(),T->NeverStream);
            }
            UE_LOG(LogTemp,Display,TEXT("SKY STUDY enabled=%d"),Enabled);
        }
    }));

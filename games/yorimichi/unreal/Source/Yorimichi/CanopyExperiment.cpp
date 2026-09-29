#include "JapanWorld.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "HAL/IConsoleManager.h"
#include "Materials/Material.h"
#include "Materials/MaterialInstanceDynamic.h"

// Explicit runtime experiment only. Never changes a mesh asset or saved preferences.
static FAutoConsoleCommandWithWorldAndArgs CanopyNormalsCommand(TEXT("japan.CanopyNormals"),
    TEXT("Canopy study: 0 original, 1 coherent normals, 2 calm palette. Optional second argument: palette blend 0..1. Requires experiment assets."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* World)
    {
        if (!World || Args.Num()<1 || Args.Num()>2) return;
        const int32 Mode=FCString::Atoi(*Args[0]);
        if (Mode<0 || Mode>2) return;
        UMaterialInterface* Parent=Mode==1?LoadObject<UMaterialInterface>(nullptr,
            TEXT("/Game/Experiments/Canopy/M_FoliageCanopy.M_FoliageCanopy")):nullptr;
        if (Mode==1 && !Parent)
        {
            UE_LOG(LogTemp,Error,TEXT("CANOPY experiment material is missing"));
            return;
        }
        int32 Sections=0;
        for (TActorIterator<AJapanWorld> It(World); It; ++It)
            for (auto* Group:It->Groups)
            {
                if (!Group || !Group->GetStaticMesh()) continue;
                const UStaticMesh* Mesh=Group->GetStaticMesh();
                for (int32 Index=0;Index<Mesh->GetStaticMaterials().Num();++Index)
                {
                    auto* Source=Mesh->GetMaterial(Index);
                    if (!Source || Source->GetMaterial()->GetFName()!=TEXT("M_Foliage")) continue;
                    auto* Selected=Parent;
                    if (Mode==2 && Source->GetName().StartsWith(TEXT("MI_Leaf")))
                    {
                        const FString Path=TEXT("/Game/Experiments/Canopy/CalmV1/")+Source->GetName();
                        Selected=LoadObject<UMaterialInterface>(nullptr,*Path);
                        if (!Selected)
                            UE_LOG(LogTemp,Error,TEXT("CANOPY palette material missing: %s"),*Path);
                    }
                    if (!Selected) Group->SetMaterial(Index,Source);
                    else
                    {
                        auto* Variant=UMaterialInstanceDynamic::Create(Selected,Group);
                        UTexture* Texture=nullptr;
                        FLinearColor Tint;
                        if (Source->GetTextureParameterValue(FMaterialParameterInfo(TEXT("Tex")),Texture))
                            Variant->SetTextureParameterValue(TEXT("Tex"),Texture);
                        if (Source->GetVectorParameterValue(FMaterialParameterInfo(TEXT("Tint")),Tint))
                            Variant->SetVectorParameterValue(TEXT("Tint"),Tint);
                        if (Mode==2 && Args.Num()==2)
                            Variant->SetScalarParameterValue(TEXT("CalmBlend"),FMath::Clamp(FCString::Atof(*Args[1]),0.f,1.f));
                        Group->SetMaterial(Index,Variant);
                    }
                    ++Sections;
                }
            }
        UE_LOG(LogTemp,Display,TEXT("CANOPY mode=%d sections=%d"),Mode,Sections);
    }));

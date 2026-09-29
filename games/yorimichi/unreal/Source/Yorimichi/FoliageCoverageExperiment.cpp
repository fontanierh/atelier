#include "JapanWorld.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "HAL/IConsoleManager.h"

// Benchmark-only mesh swap. Never writes production packages or player settings.
static FAutoConsoleCommandWithWorldAndArgs FoliageCoverageCommand(TEXT("japan.FoliageCoverage"),
    TEXT("0 original, 1 all k8 variants, 2 detailed maple only, 3 reduced backdrop species only. Import variants first."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* World)
    {
        if (!World || Args.Num()!=1) return;
        const int32 Mode=FCString::Atoi(*Args[0]);
        if (Mode<0 || Mode>3) return;
        int32 Groups=0, Instances=0;
        for (const FString Name:{TEXT("Tree_Maple_lo"),TEXT("Tree_Broad_lo"),TEXT("Tree_Maple_A")})
        {
            const bool Reduced=Name.EndsWith(TEXT("_lo"));
            const bool Enabled=Mode==1 || (Mode==2 && !Reduced) || (Mode==3 && Reduced);
            const FString Variant=Name+TEXT("_k8");
            const FString Path=Enabled?FString::Printf(TEXT("/Game/Japan/FoliageCoverage/k8/%s.%s"),*Variant,*Variant):
                FString::Printf(TEXT("/Game/Japan/Assets/%s.%s"),*Name,*Name);
            auto* Mesh=LoadObject<UStaticMesh>(nullptr,*Path);
            if (!Mesh)
            { UE_LOG(LogTemp,Error,TEXT("COVERAGE missing %s"),*Path); return; }
            for (TActorIterator<AJapanWorld> It(World); It; ++It)
                for (auto* Group:It->Groups)
                    if (Group && Group->GetStaticMesh() &&
                        (Group->GetStaticMesh()->GetName()==Name || Group->GetStaticMesh()->GetName()==Variant))
                    {
                        Group->SetStaticMesh(Mesh);
                        Group->EmptyOverrideMaterials();
                        ++Groups; Instances+=Group->GetInstanceCount();
                    }
        }
        UE_LOG(LogTemp,Display,TEXT("COVERAGE mode=%d groups=%d instances=%d"),Mode,Groups,Instances);
    }));

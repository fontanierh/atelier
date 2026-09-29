#include "HarborLook.h"
#include "JapanWorld.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"

static const FName TileTag(TEXT("HarborVisibilityTile"));

// The original sea is one 1.5 x 2.2 km quad, including the land under the city.
// Split its identical surface into independently occluded pieces, with the same
// shared mesh/material. This is an opt-in runtime test; no asset is rewritten.
static FAutoConsoleCommandWithWorldAndArgs HarborSeaTilesCommand(TEXT("japan.HarborSeaTiles"),
    TEXT("0 original sea, 1 identical sea surface split into visibility tiles."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* Game)
    {
        if (!Game || Args.Num()!=1) return;
        const bool Enabled=FCString::Atoi(*Args[0])!=0;
        for (TActorIterator<AJapanWorld> It(Game); It; ++It)
        {
            auto* World=*It;
            UHierarchicalInstancedStaticMeshComponent* Source=nullptr;
            TArray<UHierarchicalInstancedStaticMeshComponent*> Tiles;
            for (auto* Group:World->Groups)
            {
                if (!Group) continue;
                if (Group->ComponentHasTag(TileTag)) Tiles.Add(Group);
                else if (Group->GetStaticMesh() && Group->GetStaticMesh()->GetName()==TEXT("HD_Sea")) Source=Group;
            }
            if (!Source || Source->GetInstanceCount()!=1)
            { UE_LOG(LogTemp,Error,TEXT("HARBOR TILES expected one original sea instance")); continue; }
            if (Enabled && Tiles.IsEmpty())
            {
                const FBox Box=Source->GetStaticMesh()->GetBounds().GetBox();
                FTransform Original; Source->GetInstanceTransform(0,Original,true);
                constexpr int32 NX=8, NY=11;
                const FVector Scale(1.f/NX,1.f/NY,1.f);
                for (int32 X=0;X<NX;++X) for (int32 Y=0;Y<NY;++Y)
                {
                    auto* Tile=NewObject<UHierarchicalInstancedStaticMeshComponent>(World);
                    Tile->SetupAttachment(World->GetRootComponent());
                    Tile->SetMobility(EComponentMobility::Static);
                    Tile->SetStaticMesh(Source->GetStaticMesh());
                    for (int32 Index=0;Index<Source->GetNumMaterials();++Index) Tile->SetMaterial(Index,Source->GetMaterial(Index));
                    Tile->ComponentTags.Add(TileTag);
                    Tile->SetLightingChannels(true,true,false);
                    Tile->SetCastShadow(false);
                    Tile->SetCollisionEnabled(ECollisionEnabled::NoCollision);
                    Tile->SetCanEverAffectNavigation(false);
                    Tile->RegisterComponent();
                    // Translate the scaled source minimum onto this tile's minimum.
                    const FVector Corner(Box.Min.X+Box.GetSize().X*X/NX,Box.Min.Y+Box.GetSize().Y*Y/NY,Box.Min.Z);
                    const FTransform Local(FQuat::Identity,Corner-Box.Min*Scale,Scale);
                    Tile->AddInstance(Local*Original,true);
                    Tiles.Add(Tile); World->Groups.Add(Tile);
                }
            }
            Source->SetVisibility(!Enabled);
            for (auto* Tile:Tiles) Tile->SetVisibility(Enabled);
            UE_LOG(LogTemp,Display,TEXT("HARBOR TILES enabled=%d tiles=%d"),Enabled,Tiles.Num());
        }
    }));

bool ExperimentalHarborFillVisible(AJapanWorld* World)
{
    auto* Camera=UGameplayStatics::GetPlayerCameraManager(World,0);
    if (!Camera) return true;
    const FVector P=Camera->GetCameraLocation();
    // Preserve water-level sailing and aerial views, including abrupt teleports.
    if (P.Z<1000.f || P.Z>8000.f) return true;
    bool Tiled=false;
    for (auto* Group:World->Groups)
    {
        if (!Group || !Group->IsVisible() || !Group->LightingChannels.bChannel1) continue;
        const bool Tile=Group->ComponentHasTag(TileTag);
        Tiled|=Tile;
        // Keep the fill ready before approaching any solid waterfront receiver.
        if (!Tile && Group->Bounds.GetBox().ComputeSquaredDistanceToPoint(P)<FMath::Square(10000.f)) return true;
        if (World->GetWorld()->TimeSince(Group->GetLastRenderTimeOnScreen())<1.f) return true;
    }
    // Without tiles the huge original sea gives unreliable visibility, so fail on.
    return !Tiled;
}

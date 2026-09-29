#include "JapanWorld.h"
#include "YoriData.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/SkyLight.h"
#include "Components/SkyLightComponent.h"
#include "TimerManager.h"
#include "EngineUtils.h"
#include "HAL/IConsoleManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#if WITH_EDITOR
#include "AssetCompilingManager.h"
#endif

// Keep original collision and all original geometry/attributes. Only visibility
// bounds change. Assets are deliberately isolated and never loaded in normal play.
static FAutoConsoleCommandWithWorldAndArgs CitySurfaceTilesCommand(TEXT("japan.CitySurfaceTiles"),
    TEXT("TAG 0|1: original city surfaces or full-detail visibility tiles (diagnostic only)."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* Game)
    {
        if (!Game || Args.Num()!=2 || (Args[1]!=TEXT("0") && Args[1]!=TEXT("1"))) return;
        const FString Tag=Args[0];
        for (TCHAR C:Tag) if (!FChar::IsAlnum(C) && C!=TEXT('_')) return;
        const bool Enabled=Args[1]==TEXT("1");
        const FName TileTag(*FString::Printf(TEXT("CitySurfaceTiles_%s"),*Tag));
        FString Text;
        const FString Filename=YoriDataPath(TEXT("city_surface_tiles")/Tag/TEXT("manifest.json"));
        TSharedPtr<FJsonObject> Manifest;
        if (!FFileHelper::LoadFileToString(Text,*Filename) ||
            !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Manifest) || !Manifest.IsValid() ||
            !Manifest->GetBoolField(TEXT("complete")))
        { UE_LOG(LogTemp,Error,TEXT("CITY TILES missing completed manifest %s"),*Filename); return; }
        for (TActorIterator<AJapanWorld> It(Game);It;++It)
        {
            auto* World=*It;
            TArray<UHierarchicalInstancedStaticMeshComponent*> Originals,Tiles;
            TArray<TPair<UHierarchicalInstancedStaticMeshComponent*,UStaticMesh*>> Pending;
            for (auto* Group:World->Groups)
                if (Group)
                {
                    for (const FName& ExistingTag:Group->ComponentTags)
                        if (ExistingTag.ToString().StartsWith(TEXT("CitySurfaceTiles_")) && ExistingTag!=TileTag)
                        { UE_LOG(LogTemp,Error,TEXT("CITY TILES use one variant per process")); return; }
                    if (Group->ComponentHasTag(TileTag)) Tiles.Add(Group);
                }
            bool Valid=true;
            for (const auto& Pair:Manifest->GetObjectField(TEXT("sources"))->Values)
            {
                const FString SourceName(Pair.Key);
                UHierarchicalInstancedStaticMeshComponent* Source=nullptr;
                for (auto* Group:World->Groups)
                    if (Group && Group->GetStaticMesh() && Group->GetStaticMesh()->GetName()==SourceName) Source=Group;
                if (!Source || Source->GetInstanceCount()!=1) { Valid=false; break; }
                Originals.Add(Source);
                if (Enabled && Tiles.IsEmpty())
                    for (const auto& Tile:Pair.Value->AsObject()->GetArrayField(TEXT("tiles")))
                    {
                        const FString Name=Tile->AsObject()->GetStringField(TEXT("name"));
                        const FString Path=FString::Printf(TEXT("/Game/Experiments/CitySurfaces/%s/%s.%s"),*Tag,*Name,*Name);
                        UStaticMesh* Mesh=LoadObject<UStaticMesh>(nullptr,*Path);
                        if (!Mesh) { Valid=false; break; }
                        Pending.Emplace(Source,Mesh);
                    }
            }
            // A failed or partial import must leave the original scenery visible.
            if (!Valid) { UE_LOG(LogTemp,Error,TEXT("CITY TILES invalid sources or incomplete import")); return; }
#if WITH_EDITOR
            // Freshly imported meshes can still be building distance fields/cards
            // in the background. Finish those before registering tiles and before
            // the benchmark's settling interval; otherwise timings are polluted.
            if (!Pending.IsEmpty()) FAssetCompilingManager::Get().FinishAllCompilation();
#endif
            for (const auto& Pair:Pending)
            {
                auto* Source=Pair.Key;
                auto* Tile=NewObject<UHierarchicalInstancedStaticMeshComponent>(World);
                Tile->SetupAttachment(World->GetRootComponent());
                Tile->SetMobility(EComponentMobility::Static);
                Tile->SetStaticMesh(Pair.Value);
                for (int32 M=0;M<Source->GetNumMaterials();++M) Tile->SetMaterial(M,Source->GetMaterial(M));
                Tile->ComponentTags.Add(TileTag);
                Tile->SetLightingChannels(Source->LightingChannels.bChannel0,Source->LightingChannels.bChannel1,Source->LightingChannels.bChannel2);
                Tile->SetCastShadow(Source->CastShadow);
                Tile->bAffectDistanceFieldLighting=Source->bAffectDistanceFieldLighting;
                Tile->SetCanEverAffectNavigation(false);
                Tile->SetCollisionEnabled(ECollisionEnabled::NoCollision);
                Tile->RegisterComponent();
                FTransform Transform; Source->GetInstanceTransform(0,Transform,true);
                Tile->AddInstance(Transform,true);
                World->Groups.Add(Tile); Tiles.Add(Tile);
            }
            for (auto* Original:Originals) Original->SetVisibility(!Enabled);
            for (auto* Tile:Tiles) Tile->SetVisibility(Enabled);
            if (!Pending.IsEmpty())
            {
                // Synchronous first-load compilation can let the non-realtime
                // sky capture run before the painted dome is ready. Refresh once
                // after normal world ticks resume, never on each A/B toggle/frame.
                FTimerHandle Refresh;
                Game->GetTimerManager().SetTimer(Refresh,FTimerDelegate::CreateWeakLambda(World,[World]()
                {
                    int32 Count=0;
                    for (TActorIterator<ASkyLight> It(World->GetWorld());It;++It)
                        if (auto* Sky=It->GetLightComponent(); Sky && !Sky->IsRealTimeCaptureEnabled())
                        { Sky->RecaptureSky(); ++Count; }
                    USkyLightComponent::UpdateSkyCaptureContents(World->GetWorld());
                    UE_LOG(LogTemp,Display,TEXT("CITY TILES refreshed startup sky captures=%d"),Count);
                }),2.f,false);
            }
            UE_LOG(LogTemp,Display,TEXT("CITY TILES tag=%s enabled=%d originals=%d tiles=%d"),*Tag,Enabled,Originals.Num(),Tiles.Num());
        }
    }));

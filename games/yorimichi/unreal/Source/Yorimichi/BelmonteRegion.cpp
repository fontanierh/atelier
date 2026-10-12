#include "BelmonteRegion.h"
#include "AtelierData.h"
#include "JapanWorld.h"
#include "JapanSeeThrough.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Dom/JsonObject.h"
#include "Materials/MaterialInterface.h"

namespace
{
FVector Vector(const TArray<TSharedPtr<FJsonValue>>& Values)
{
    return FVector(Values[0]->AsNumber(), Values[1]->AsNumber(), Values[2]->AsNumber());
}

FTransform Transform(const TSharedPtr<FJsonObject>& Value)
{
    const auto& Q = Value->GetArrayField(TEXT("rotation_xyzw"));
    return FTransform(FQuat(Q[0]->AsNumber(), Q[1]->AsNumber(), Q[2]->AsNumber(), Q[3]->AsNumber()),
                      Vector(Value->GetArrayField(TEXT("translation_cm"))), Vector(Value->GetArrayField(TEXT("scale"))));
}
}

ABelmonteRegion::ABelmonteRegion()
{
    PrimaryActorTick.bCanEverTick = false;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

void ABelmonteRegion::Clear(const TSharedPtr<FJsonObject>& WorldData, const FString& Path)
{
    const auto Data = AtelierReadJson(Path);
    if (!WorldData || !Data) return;
    const auto& B = Data->GetArrayField(TEXT("clearance_m"));
    const auto Instances = WorldData->GetObjectField(TEXT("instances"));
    for (auto& Pair : Instances->Values)
    {
        if (!Pair.Key.StartsWith(TEXT("Tree")) && !Pair.Key.StartsWith(TEXT("HD_NorthTree"))
            && !Pair.Key.StartsWith(TEXT("Bush")) && !Pair.Key.StartsWith(TEXT("Grass"))) continue;
        TArray<TSharedPtr<FJsonValue>> Kept;
        for (const auto& Item : Pair.Value->AsArray())
        {
            const auto& P = Item->AsArray();
            const double X = P[0]->AsNumber(), Y = P[1]->AsNumber();
            if (X < B[0]->AsNumber() || X > B[2]->AsNumber() || Y <= B[1]->AsNumber() || Y > B[3]->AsNumber()) Kept.Add(Item);
        }
        Pair.Value = MakeShared<FJsonValueArray>(Kept);
    }
}

ABelmonteRegion* ABelmonteRegion::Spawn(AJapanWorld* Landscape, const FString& Path)
{
    const auto Data = AtelierReadJson(Path);
    if (!Landscape || !Data) return nullptr;
    auto* Region = Landscape->GetWorld()->SpawnActor<ABelmonteRegion>();
    if (!Region) return nullptr;
    Region->SetActorLocation(Vector(Data->GetArrayField(TEXT("origin_cm"))));
    Region->GetRootComponent()->SetMobility(EComponentMobility::Static);
    Region->Tags.Add(TEXT("belmonte"));
    int32 Missing = 0;
    for (const auto& Value : Data->GetArrayField(TEXT("groups")))
    {
        const auto Entry = Value->AsObject();
        const FString Asset = Entry->GetStringField(TEXT("asset"));
        auto* Mesh = LoadObject<UStaticMesh>(nullptr, *Asset);
        if (!Mesh)
        {
            ++Missing;
            UE_LOG(LogTemp, Error, TEXT("BELMONTE missing mesh %s"), *Asset);
            continue;
        }
        const bool Plant = Entry->GetBoolField(TEXT("plant"));
        auto* Group = NewObject<UHierarchicalInstancedStaticMeshComponent>(Plant ? static_cast<UObject*>(Landscape) : Region);
        Group->SetStaticMesh(Mesh);
        Group->SetMobility(EComponentMobility::Static);
        Group->SetupAttachment(Plant ? Landscape->GetRootComponent() : Region->GetRootComponent());
        Group->SetCanEverAffectNavigation(false);
        Group->SetGenerateOverlapEvents(false);
        Group->SetCollisionEnabled(Entry->GetBoolField(TEXT("collision")) ? ECollisionEnabled::QueryOnly : ECollisionEnabled::NoCollision);
        Group->SetCastShadow(Entry->GetBoolField(TEXT("shadow")));
        const int32 Cull = Entry->GetIntegerField(TEXT("cull_cm"));
        Group->SetCullDistances(FMath::RoundToInt(Cull * .8f), Cull);
        if (Plant && Mesh->GetName().StartsWith(TEXT("Grass_"))) Group->bAffectDistanceFieldLighting = false;
        for (int32 Index = 0; Index < Entry->GetArrayField(TEXT("materials")).Num(); ++Index)
        {
            const FString MaterialPath = Entry->GetArrayField(TEXT("materials"))[Index]->AsString();
            auto* Material = LoadObject<UMaterialInterface>(nullptr, *MaterialPath);
            if (Material) Group->SetMaterial(Index, Material);
            else { ++Missing; UE_LOG(LogTemp, Error, TEXT("BELMONTE missing material %s"), *MaterialPath); }
        }
        if (Plant)
        {
            const int32 Fade = JapanSeeThrough::FadeMode(Mesh->GetName(), Mesh);
            if (Fade != JapanSeeThrough::FadeSolid)
            {
                Group->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
                Group->SetCustomPrimitiveDataFloat(0, float(Fade));
            }
            Group->SetWorldPositionOffsetDisableDistance(18000);
        }
        Group->bAutoRebuildTreeOnInstanceChanges = false;
        Group->RegisterComponent();
        TArray<FTransform> Instances;
        for (const auto& Item : Entry->GetArrayField(TEXT("transforms")))
        {
            FTransform Placement = Transform(Item->AsObject());
            // Plant components belong to JapanWorld, so the normal tree settings
            // and LOD swaps apply to this district too.
            if (Plant) Placement.AddToTranslation(Region->GetActorLocation());
            Instances.Add(Placement);
        }
        Group->AddInstances(Instances, false, false, false);
        Group->BuildTreeIfOutdated(true, true);
        Group->bAutoRebuildTreeOnInstanceChanges = true;
        if (Plant) { Landscape->Groups.Add(Group); Region->PlantInstances += Instances.Num(); }
        else Region->SceneryInstances += Instances.Num();
    }
    for (const auto& Value : Data->GetArrayField(TEXT("signs")))
    {
        const auto Entry = Value->AsObject();
        const FString Text = Entry->GetStringField(TEXT("text"));
        if (Text.IsEmpty()) continue;
        auto* Sign = NewObject<UTextRenderComponent>(Region);
        Sign->SetupAttachment(Region->GetRootComponent());
        Sign->SetRelativeTransform(Transform(Entry->GetObjectField(TEXT("transform"))));
        Sign->SetText(FText::FromString(Text));
        Sign->SetWorldSize(Entry->GetNumberField(TEXT("size_cm")));
        Sign->SetHorizontalAlignment(EHTA_Center);
        Sign->SetVerticalAlignment(EVRTA_TextCenter);
        const auto& Colour = Entry->GetArrayField(TEXT("colour_srgb"));
        Sign->SetTextRenderColor(FColor(Colour[0]->AsNumber(), Colour[1]->AsNumber(), Colour[2]->AsNumber()));
        Sign->SetCullDistance(18000);
        Sign->SetCastShadow(false);
        Sign->RegisterComponent();
    }
    Region->bGameplayReady = Missing == 0 && Region->SceneryInstances > 0;
    UE_LOG(LogTemp, Display, TEXT("BELMONTE ready=%d scenery=%d plants=%d missing=%d at %s"),
           Region->bGameplayReady, Region->SceneryInstances, Region->PlantInstances, Missing, *Region->GetActorLocation().ToString());
    return Region;
}

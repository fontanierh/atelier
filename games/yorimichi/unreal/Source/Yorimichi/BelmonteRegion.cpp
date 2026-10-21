#include "BelmonteRegion.h"
#include "FoliageSystem.h"
#include "AtelierData.h"
#include "JapanWorld.h"
#include "SeeThrough.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Dom/JsonObject.h"
#include "Materials/MaterialInterface.h"
#include "StaticMeshResources.h"
#include "Serialization/JsonSerializer.h"
#include "ShaderCompiler.h"

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

bool ABelmonteRegion::InClearance(const TSharedPtr<FJsonObject>& Data,double X,double Y)
{
    if(!Data)return false;
    const TArray<TSharedPtr<FJsonValue>>* Segments=nullptr;
    if(Data->TryGetArrayField(TEXT("clearance_segments_m"),Segments))
    {
        const FVector P(X,Y,0.);
        for(const auto& V:*Segments)
        {
            const auto& S=V->AsArray();if(S.Num()!=5)continue;
            const FVector A(S[0]->AsNumber(),S[1]->AsNumber(),0.),B(S[2]->AsNumber(),S[3]->AsNumber(),0.);
            if(FVector::DistSquared(P,FMath::ClosestPointOnSegment(P,A,B))<=FMath::Square(S[4]->AsNumber()))return true;
        }
        return false;
    }
    const TArray<TSharedPtr<FJsonValue>>* B=nullptr;
    return Data->TryGetArrayField(TEXT("clearance_m"),B)&&B->Num()==4&&
        X>=(*B)[0]->AsNumber()&&X<=(*B)[2]->AsNumber()&&Y>(*B)[1]->AsNumber()&&Y<=(*B)[3]->AsNumber();
}

void ABelmonteRegion::Clear(const TSharedPtr<FJsonObject>& WorldData, const FString& Path)
{
    const auto Data = AtelierReadJson(Path);
    if (!WorldData || !Data) return;
    const TSharedPtr<FJsonObject>* Instances = nullptr;
    if (!WorldData->TryGetObjectField(TEXT("instances"), Instances)) return;
    // Island vegetation by default; a region may name more instance prefixes (Brinecove: coastal boulders).
    TArray<FString> Prefixes = {TEXT("Tree"), TEXT("Bush"), TEXT("Grass")};
    const TArray<TSharedPtr<FJsonValue>>* Extra = nullptr;
    if (Data->TryGetArrayField(TEXT("clear_prefixes"), Extra))
        for (const auto& Prefix : *Extra) Prefixes.AddUnique(Prefix->AsString());
    for (auto& Pair : (*Instances)->Values)
    {
        const FString Key(Pair.Key);
        if (!Prefixes.ContainsByPredicate([&Key](const FString& Prefix) { return Key.StartsWith(Prefix); })) continue;
        TArray<TSharedPtr<FJsonValue>> Kept;
        for (const auto& Item : Pair.Value->AsArray())
        {
            const auto& P = Item->AsArray();
            const double X = P[0]->AsNumber(), Y = P[1]->AsNumber();
            if (!InClearance(Data,X,Y)) Kept.Add(Item);
        }
        Pair.Value = MakeShared<FJsonValueArray>(Kept);
    }
}

ABelmonteRegion* ABelmonteRegion::Spawn(AJapanWorld* Landscape, const FString& Path, FName Tag)
{
    const auto Data = AtelierReadJson(Path);
    if (!Landscape || !Data) return nullptr;
    auto* Region = Landscape->GetWorld()->SpawnActor<ABelmonteRegion>();
    if (!Region) return nullptr;
    Region->SetActorLocation(Vector(Data->GetArrayField(TEXT("origin_cm"))));
    Region->GetRootComponent()->SetMobility(EComponentMobility::Static);
    Region->Tags.Add(Tag);
    const auto GondolaClearance=AtelierReadJson(AtelierDataPath(TEXT("gondola/runtime.json")));
    int32 Missing = 0, Outside = 0;
    // The district's extent in metres (world X, north Y), with a 100 m margin.
    const auto& B = Data->GetArrayField(TEXT("bounds_m"));
    const FBox2D Bounds(FVector2D(B[0]->AsNumber() - 100., B[1]->AsNumber() - 100.), FVector2D(B[2]->AsNumber() + 100., B[3]->AsNumber() + 100.));
    auto Inside = [&Bounds](const FVector& P) { return Bounds.IsInside(FVector2D(P.X / 100., -P.Y / 100.)); };
    for (const auto& Value : Data->GetArrayField(TEXT("groups")))
    {
        const auto Entry = Value->AsObject();
        const FString Asset = Entry->GetStringField(TEXT("asset"));
        auto* Mesh = LoadObject<UStaticMesh>(nullptr, *Asset);
        if (!Mesh)
        {
            ++Missing;
            UE_LOG(LogTemp, Error, TEXT("%s missing mesh %s"), *Tag.ToString().ToUpper(), *Asset);
            continue;
        }
        const bool Plant = Entry->GetBoolField(TEXT("plant"));
        auto* Group = UYorimichiFoliageSubsystem::NewInstances(Plant ? static_cast<UObject*>(Landscape) : Region);
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
            else { ++Missing; UE_LOG(LogTemp, Error, TEXT("%s missing material %s"), *Tag.ToString().ToUpper(), *MaterialPath); }
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
            // The source scene's distant hill villages lie kilometres outside the district,
            // where no ground carries them: they would hang in the sky over the whole map.
            if (!Plant && !Inside(Region->GetActorLocation() + Placement.GetLocation())) { ++Outside; continue; }
            // Plant components belong to JapanWorld, so the normal tree settings
            // and LOD swaps apply to this district too.
            if (Plant)
            {
                Placement.AddToTranslation(Region->GetActorLocation());
                const FVector P=Placement.GetLocation();
                if(InClearance(GondolaClearance,P.X/100.,-P.Y/100.))continue;
            }
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
    UE_LOG(LogTemp, Display, TEXT("%s ready=%d scenery=%d plants=%d missing=%d outside=%d at %s"),
           *Tag.ToString().ToUpper(), Region->bGameplayReady, Region->SceneryInstances, Region->PlantInstances, Missing, Outside, *Region->GetActorLocation().ToString());
    return Region;
}

int32 ABelmonteRegion::ReviewPendingShaderJobs()
{
    if (!GShaderCompilingManager) return 0;
    // Pending shader-map finalization can still draw fallback materials.
    return FMath::Max(GShaderCompilingManager->GetNumRemainingJobs(), GShaderCompilingManager->HasShaderJobs() ? 1 : 0);
}

FString ABelmonteRegion::ReviewMeshColours(const FString& Name)
{
    auto* Mesh = LoadObject<UStaticMesh>(nullptr, *(TEXT("/Game/Belmonte/Meshes/") + Name + TEXT(".") + Name));
    if (!Mesh || !Mesh->GetRenderData() || Mesh->GetRenderData()->LODResources.IsEmpty()) return TEXT("");
    const auto& Buffers = Mesh->GetRenderData()->LODResources[0].VertexBuffers;
    const auto& Colours = Buffers.ColorVertexBuffer;
    if (!Colours.GetVertexData() || !Colours.GetNumVertices()) return TEXT("");
    TArray<TSharedPtr<FJsonValue>> Rows;
    const uint32 Stride = FMath::Max(1u, Colours.GetNumVertices() / 32u);
    for (uint32 I = 0; I < Colours.GetNumVertices(); I += Stride)
    {
        const FVector3f P = Buffers.PositionVertexBuffer.VertexPosition(I);
        const FColor C = Colours.VertexColor(I);
        auto Row = MakeShared<FJsonObject>();
        TArray<TSharedPtr<FJsonValue>> Position, RGBA;
        for (float V : {P.X, P.Y, P.Z}) Position.Add(MakeShared<FJsonValueNumber>(V));
        for (uint8 V : {C.R, C.G, C.B, C.A}) RGBA.Add(MakeShared<FJsonValueNumber>(V));
        Row->SetArrayField(TEXT("position_cm"), Position); Row->SetArrayField(TEXT("rgba_bytes"), RGBA);
        Rows.Add(MakeShared<FJsonValueObject>(Row));
    }
    auto Report = MakeShared<FJsonObject>();
    Report->SetStringField(TEXT("mesh"), Name); Report->SetArrayField(TEXT("samples"), Rows);
    FString Output; FJsonSerializer::Serialize(Report, TJsonWriterFactory<>::Create(&Output));
    return Output;
}

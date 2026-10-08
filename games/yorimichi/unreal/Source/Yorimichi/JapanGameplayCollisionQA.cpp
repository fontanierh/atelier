#include "JapanGameplayCollisionQA.h"
#include "JapanGameplayCollision.h"
#include "JapanWorld.h"
#include "Hippodrome.h"
#include "ZeppelinService.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Pawn.h"
#include "Components/StaticMeshComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "EngineUtils.h"
#include "AtelierData.h"
#include "Dom/JsonObject.h"
#include "Components/PrimitiveComponent.h"
#include "Engine/World.h"
#include "Misc/FileHelper.h"
#include "Misc/SecureHash.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

void JapanGameplayCollisionQA::Write(UWorld* World, const TSharedPtr<FJsonObject>& Report)
{
    auto Data = MakeShared<FJsonObject>();
    if (World)
    {
        const auto Query = JapanGameplayCollision::Query(World, SCENE_QUERY_STAT(VehicleIgnoreInventory), false);
        Data->SetNumberField(TEXT("ignored_owners"), Query.GetIgnoredSourceObjects().Num());
        Data->SetNumberField(TEXT("ignored_components"), Query.GetIgnoredComponents().Num());
    }
    TArray<FString> Errors;
    const TArray<FString> Inventory = JapanGameplayCollision::Inventory(World, Errors);
    TArray<TSharedPtr<FJsonValue>> Entries, Failures, Probes;
    for (const FString& Entry : Inventory) Entries.Add(MakeShared<FJsonValueString>(Entry));
    for (const FString& Error : Errors) Failures.Add(MakeShared<FJsonValueString>(Error));
    Data->SetArrayField(TEXT("components"), Entries);
    Data->SetArrayField(TEXT("response_errors"), Failures);
    FTCHARToUTF8 Canonical(*FString::Join(Inventory, TEXT("\n")));
    uint8 Hash[20]; FSHA1::HashBuffer(Canonical.Get(), Canonical.Length(), Hash);
    Data->SetStringField(TEXT("inventory_digest"), BytesToHex(Hash, 20).ToLower());
    // The reference is deliberately NOT the fixed-owner predicate. Unknown fixed
    // blockers must remain visible here, so missing ownership cannot false-pass.
    FCollisionQueryParams Reference(SCENE_QUERY_STAT(VehicleVisibilityReference), false);
    TArray<TSharedPtr<FJsonValue>> Stationary;
    if (World) for (TActorIterator<AActor> It(World); It; ++It)
    {
        if (It->IsA<APawn>() || It->IsA<AZeppelinService>() || It->ActorHasTag(TEXT("LiveTest"))) Reference.AddIgnoredActor(*It);
        TArray<UPrimitiveComponent*> Parts; It->GetComponents(Parts);
        for (const auto* Part : Parts)
        {
            if (It->IsA<AHippodrome>() && Part->GetFName() == TEXT("SM_HD_StartingGate")) Reference.AddIgnoredComponent(Part);
            if (Part->Mobility != EComponentMobility::Stationary || JapanGameplayCollision::IsFixed(Part) ||
                !Part->IsQueryCollisionEnabled() || Part->GetCollisionResponseToChannel(ECC_Visibility) != ECR_Block) continue;
            const auto* Mesh = Cast<UStaticMeshComponent>(Part);
            Stationary.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("%s:%s:%s:%s"), *It->GetClass()->GetName(),
                *Part->GetName(), Mesh && Mesh->GetStaticMesh() ? *Mesh->GetStaticMesh()->GetPathName() : TEXT(""),
                *Part->GetComponentLocation().ToString())));
        }
    }
    Data->SetArrayField(TEXT("excluded_stationary"), Stationary);
    FString Text; TSharedPtr<FJsonObject> Map;
    const TArray<TSharedPtr<FJsonValue>>* Zones = nullptr;
    int32 Hits = 0;
    if (World && FFileHelper::LoadFileToString(Text, *AtelierDataPath(TEXT("map/map.json"))) &&
        FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Map) && Map &&
        Map->TryGetArrayField(TEXT("zones"), Zones))
        for (const auto& Zone : *Zones)
        {
            const auto Z = Zone->AsObject();
            const FVector At = AJapanWorld::ToUE(Z->GetNumberField(TEXT("x")), Z->GetNumberField(TEXT("y")), Z->GetNumberField(TEXT("z")));
            for (bool Complex : {false, true})
            {
                auto Query = JapanGameplayCollision::Query(World, SCENE_QUERY_STAT(VehicleParity), Complex);
                Reference.bTraceComplex = Complex;
                const FVector From = At + FVector(0, 0, 300), To = At - FVector(0, 0, 1800);
                FHitResult Visible, Fixed;
                const bool V = World->LineTraceSingleByChannel(Visible, From, To, ECC_Visibility, Reference);
                const bool G = World->LineTraceSingleByChannel(Fixed, From, To, JapanGameplayCollision::Channel, Query);
                const bool Equal = V == G && (!V || (Visible.GetComponent() == Fixed.GetComponent() &&
                    Visible.Item == Fixed.Item && FVector::Dist(Visible.ImpactPoint, Fixed.ImpactPoint) <= .1 &&
                    Visible.ImpactNormal.Equals(Fixed.ImpactNormal, .001)));
                auto Probe = MakeShared<FJsonObject>();
                Probe->SetStringField(TEXT("key"), Z->GetStringField(TEXT("key")));
                Probe->SetBoolField(TEXT("complex"), Complex);
                Probe->SetBoolField(TEXT("visibility_hit"), V); Probe->SetBoolField(TEXT("fixed_hit"), G);
                Probe->SetBoolField(TEXT("matches"), Equal);
                Probe->SetBoolField(TEXT("unclassified_visibility_hit"), V && !JapanGameplayCollision::IsFixed(Visible.GetComponent()));
                Probe->SetStringField(TEXT("component"), Visible.GetComponent() ? Visible.GetComponent()->GetName() : FString());
                const auto* Mesh = Cast<UStaticMeshComponent>(Visible.GetComponent());
                Probe->SetStringField(TEXT("owner_class"), Visible.GetActor() ? Visible.GetActor()->GetClass()->GetName() : FString());
                Probe->SetStringField(TEXT("mesh_asset"), Mesh && Mesh->GetStaticMesh() ? Mesh->GetStaticMesh()->GetPathName() : FString());
                Probe->SetBoolField(TEXT("instanced"), Cast<UInstancedStaticMeshComponent>(Visible.GetComponent()) != nullptr);
                Probe->SetNumberField(TEXT("item"), Visible.Item);
                Probe->SetNumberField(TEXT("z"), V ? Visible.ImpactPoint.Z : 0.);
                Probe->SetNumberField(TEXT("normal_z"), V ? Visible.ImpactNormal.Z : 0.);
                Probes.Add(MakeShared<FJsonValueObject>(Probe));
                if (V) ++Hits;
            }
        }
    Data->SetArrayField(TEXT("probes"), Probes);
    Data->SetNumberField(TEXT("visibility_hits"), Hits);
    Data->SetStringField(TEXT("scope"), TEXT("Fixed-component response inventory plus map-stop simple/complex traces; not exhaustive triangle coverage"));
    Report->SetObjectField(TEXT("fixed_gameplay_collision"), Data);
}

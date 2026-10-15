#include "CraterCloud.h"

#include "AtelierData.h"
#include "Components/LightComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "ProceduralMeshComponent.h"

namespace
{
    FVector Triple(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key, const FVector& Fallback = FVector::ZeroVector)
    {
        const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
        if (!Object->TryGetArrayField(Key, A) || A->Num() < 2) return Fallback;
        return FVector((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), A->Num() > 2 ? (*A)[2]->AsNumber() : 0.);
    }

    FLinearColor Colour(const FVector& V) { return FLinearColor(V.X, V.Y, V.Z, 1.f); }
}

ACraterCloud::ACraterCloud()
{
    PrimaryActorTick.bCanEverTick = false;
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
    bReplicates = false;
}

ACraterCloud* ACraterCloud::Spawn(UWorld* World, const FString& Path)
{
    const TSharedPtr<FJsonObject> Root = World ? AtelierReadJson(Path) : nullptr;
    const TSharedPtr<FJsonObject>* Envelope = nullptr;
    const TArray<TSharedPtr<FJsonValue>>* Layers = nullptr;
    if (!Root || !Root->TryGetObjectField(TEXT("envelope"), Envelope) || !Root->TryGetArrayField(TEXT("layers"), Layers))
    {
        UE_LOG(LogTemp, Warning, TEXT("CRATER CLOUD missing record %s"), *Path);
        return nullptr;
    }
    UMaterialInterface* Plain = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/CraterPark/Cloud/M_CraterCloud.M_CraterCloud"));
    UMaterialInterface* Veil = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/CraterPark/Cloud/M_CraterCloudVeil.M_CraterCloudVeil"));
    if (!Plain || !Veil)
    {
        UE_LOG(LogTemp, Warning, TEXT("CRATER CLOUD missing materials (/Game/CraterPark/Cloud, unreal.crater_cloud)"));
        return nullptr;
    }
    // Toward the island's sun (setup_project.py's directional light), for the shells' sunlit tops.
    FVector Sun(-.579, .334, .743);
    for (TActorIterator<ADirectionalLight> It(World); It; ++It)
        if (const ULightComponent* Light = It->GetLightComponent()) { Sun = -Light->GetForwardVector(); break; }

    FActorSpawnParameters Parameters;
    Parameters.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    ACraterCloud* Cloud = World->SpawnActor<ACraterCloud>(Triple(Root, TEXT("origin_cm")), FRotator::ZeroRotator, Parameters);
    if (!Cloud) return nullptr;

    const FVector Q = Triple(Root, TEXT("q")), NearFade = Triple(Root, TEXT("near_fade_cm"));
    for (int32 Index = 0; Index < Layers->Num(); ++Index)
    {
        const TSharedPtr<FJsonObject> Layer = (*Layers)[Index]->AsObject();
        if (!Layer) continue;
        const bool bVeil = Layer->GetBoolField(TEXT("veil"));
        const TArray<TSharedPtr<FJsonValue>>& Flat = Layer->GetArrayField(TEXT("vertices"));
        const TArray<TSharedPtr<FJsonValue>>& Indices = Layer->GetArrayField(TEXT("triangles"));
        TArray<FVector> Vertices; Vertices.Reserve(Flat.Num() / 3);
        for (int32 I = 0; I + 2 < Flat.Num(); I += 3)
            Vertices.Add(FVector(Flat[I]->AsNumber(), Flat[I + 1]->AsNumber(), Flat[I + 2]->AsNumber()));
        TArray<int32> Tris; Tris.Reserve(Indices.Num());
        for (const auto& Value : Indices) Tris.Add(int32(Value->AsNumber()));
        if (Vertices.Num() < 3 || Tris.Num() < 3 || Tris.Num() % 3) continue;
        // Smooth normals, each turned outward from the lens's middle (the shells are convex): the material lights the
        // tops and shades the undersides by them, whatever the winding.
        FVector Middle = FVector::ZeroVector;
        for (const FVector& V : Vertices) Middle += V;
        Middle /= Vertices.Num();
        TArray<FVector> Normals; Normals.Init(FVector::ZeroVector, Vertices.Num());
        bool bValid = true;
        for (int32 I = 0; I < Tris.Num(); I += 3)
        {
            const int32 A = Tris[I], B = Tris[I + 1], C = Tris[I + 2];
            if (!Vertices.IsValidIndex(A) || !Vertices.IsValidIndex(B) || !Vertices.IsValidIndex(C)) { bValid = false; break; }
            const FVector Face = FVector::CrossProduct(Vertices[B] - Vertices[A], Vertices[C] - Vertices[A]);
            Normals[A] += Face; Normals[B] += Face; Normals[C] += Face;
        }
        if (!bValid) continue;
        for (int32 I = 0; I < Normals.Num(); ++I)
        {
            FVector N = Normals[I].GetSafeNormal();
            if (FVector::DotProduct(N, Vertices[I] - Middle) < 0.) N = -N;
            Normals[I] = N;
        }

        UMaterialInstanceDynamic* Look = UMaterialInstanceDynamic::Create(bVeil ? Veil : Plain, Cloud);
        Look->SetVectorParameterValue(TEXT("Centre"), Colour(Triple(*Envelope, TEXT("centre_cm"))));
        Look->SetVectorParameterValue(TEXT("Radii"), Colour(Triple(*Envelope, TEXT("radii_cm"))));
        Look->SetVectorParameterValue(TEXT("Q"), Colour(Q));
        Look->SetVectorParameterValue(TEXT("Opacity"), Colour(Triple(Layer, TEXT("opacity"))));
        Look->SetVectorParameterValue(TEXT("NearFade"), Colour(NearFade));
        Look->SetScalarParameterValue(TEXT("Soft"), Root->GetNumberField(TEXT("soft_cm")));
        Look->SetVectorParameterValue(TEXT("StriationSize"), Colour(Triple(Root, TEXT("striation_cm"))));
        Look->SetScalarParameterValue(TEXT("Striation"), Root->GetNumberField(TEXT("striation")));
        Look->SetScalarParameterValue(TEXT("Drift"), Root->GetNumberField(TEXT("drift_cm")));
        Look->SetVectorParameterValue(TEXT("Top"), Colour(Triple(Root, TEXT("top"))));
        Look->SetVectorParameterValue(TEXT("Under"), Colour(Triple(Root, TEXT("under"))));
        Look->SetVectorParameterValue(TEXT("SunDir"), Colour(Sun));
        if (bVeil)
        {
            Look->SetScalarParameterValue(TEXT("Blur"), Root->GetNumberField(TEXT("blur")));
            Look->SetVectorParameterValue(TEXT("Tint"), Colour(Triple(Layer, TEXT("tint"))));
        }

        UProceduralMeshComponent* Shell = NewObject<UProceduralMeshComponent>(Cloud, *FString::Printf(TEXT("Shell_%s"), *Layer->GetStringField(TEXT("name"))));
        Shell->SetupAttachment(Cloud->GetRootComponent());
        Shell->bUseAsyncCooking = false;
        Shell->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Shell->SetCollisionResponseToAllChannels(ECR_Ignore);
        Shell->SetGenerateOverlapEvents(false);
        Shell->SetCanEverAffectNavigation(false);
        Shell->SetCastShadow(false);
        Shell->bAffectDistanceFieldLighting = false;
        Shell->bVisibleInReflectionCaptures = false;
        Shell->bVisibleInRealTimeSkyCaptures = false;
        Shell->bVisibleInRayTracing = false;
        Shell->bReceivesDecals = false;
        // The veil samples the scene behind it, so it goes first; the plain shells then lay their white over it.
        Shell->TranslucencySortPriority = bVeil ? -1 : Index;
        Shell->CreateMeshSection_LinearColor(0, Vertices, Tris, Normals, TArray<FVector2D>(), TArray<FLinearColor>(),
                                             TArray<FProcMeshTangent>(), false);
        Shell->SetMaterial(0, Look);
        Shell->RegisterComponent();
        Cloud->Shells.Add(Shell); Cloud->Looks.Add(Look);
        Cloud->Triangles += Tris.Num() / 3;
    }
    UE_LOG(LogTemp, Display, TEXT("CRATER CLOUD shells %d triangles %d"), Cloud->Shells.Num(), Cloud->Triangles);
    if (Cloud->Shells.IsEmpty()) { Cloud->Destroy(); return nullptr; }
    return Cloud;
}

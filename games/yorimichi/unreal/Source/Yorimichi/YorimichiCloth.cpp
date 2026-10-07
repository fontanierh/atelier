#include "YorimichiCloth.h"
#include "Engine/SkeletalMesh.h"
#if WITH_EDITOR
#include "ChaosCloth/ChaosClothConfig.h"
#include "ClothingAsset.h"
#include "ClothingAssetFactoryInterface.h"
#include "ClothingSystemEditorInterfaceModule.h"
#include "Modules/ModuleManager.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "Rendering/SkeletalMeshModel.h"
#include "SkeletalMeshClothingSystemUtilities.h"
#endif

FString UYorimichiClothLibrary::AddSectionCloth(USkeletalMesh* Mesh, FName SlotName, float MaxDistanceCm)
{
#if WITH_EDITOR
    if (!Mesh || !Mesh->GetImportedModel() || !Mesh->GetImportedModel()->LODModels.Num()) return FString();
    const int32 Material = Mesh->GetMaterials().IndexOfByPredicate([&](const FSkeletalMaterial& M) { return M.MaterialSlotName == SlotName; });
    const TArray<FSkelMeshSection>& Sections = Mesh->GetImportedModel()->LODModels[0].Sections;
    const int32 Section = Sections.IndexOfByPredicate([&](const FSkelMeshSection& S) { return S.MaterialIndex == Material; });
    if (Material == INDEX_NONE || Section == INDEX_NONE)
    {
        UE_LOG(LogTemp, Error, TEXT("Cloth: %s has no LOD 0 section drawn with slot %s"), *Mesh->GetName(), *SlotName.ToString());
        return FString();
    }
    Mesh->Modify();
    // A rerun starts clean: unbind and drop any clothing this mesh carried.
    for (UClothingAssetBase* Old : TArray<UClothingAssetBase*>(Mesh->GetMeshClothingAssets()))
        if (Old) Old->UnbindFromSkeletalMesh(Mesh);
    Mesh->GetMeshClothingAssets().Empty();

    FSkeletalMeshClothBuildParams Params;
    Params.AssetName = SlotName.ToString() + TEXT("_Cloth");
    Params.LodIndex = 0;
    Params.SourceSection = Section;
    Params.PhysicsAsset = Mesh->GetPhysicsAsset();
    FClothingSystemEditorInterfaceModule& Module = FModuleManager::LoadModuleChecked<FClothingSystemEditorInterfaceModule>(TEXT("ClothingSystemEditorInterface"));
    UClothingAssetCommon* Cloth = Cast<UClothingAssetCommon>(Module.GetClothingAssetFactory()->CreateFromSkeletalMesh(Mesh, Params));
    if (!Cloth || !Cloth->LodData.Num())
    {
        UE_LOG(LogTemp, Error, TEXT("Cloth: could not build clothing from %s section %d"), *Mesh->GetName(), Section);
        return FString();
    }
    Mesh->AddClothingAsset(Cloth);   // also gives it its Chaos configs

    // The max distance mask from the pin colour, before binding (the bind reads it to build the skinning data).
    FClothLODDataCommon& Lod = Cloth->LodData[0];
    const TArray<FColor>& Colours = Lod.PhysicalMeshData.VertexColors;
    FPointWeightMap* Distance = Lod.PointWeightMaps.FindByPredicate([](const FPointWeightMap& M) { return M.CurrentTarget == (uint8)EWeightMapTargetCommon::MaxDistance; });
    if (!Distance)
    {
        Distance = &Lod.PointWeightMaps.AddDefaulted_GetRef();
        Distance->Initialize(Lod.PhysicalMeshData.Vertices.Num());
        Distance->CurrentTarget = (uint8)EWeightMapTargetCommon::MaxDistance;
    }
    Distance->bEnabled = true;
    if (Distance->Values.Num() != Colours.Num()) Distance->Values.SetNumZeroed(Colours.Num());
    int32 Free = 0, Pinned = 0;
    for (int32 I = 0; I < Colours.Num(); ++I)
    {
        const float Pin = Colours[I].R / 255.f;
        Distance->Values[I] = (1.f - Pin) * MaxDistanceCm;
        Free += Pin < .01f;
        Pinned += Pin > .99f;
    }
    Cloth->ApplyParameterMasks();

    // A long wool coat: heavier than the default, damped so it settles behind the legs, a little thicker than the skin
    // for its collision, and tethered to its pinned part so it never stretches down.
    if (UChaosClothConfig* Config = Cloth->GetClothConfig<UChaosClothConfig>())
    {
        Config->Density = .6f;
        Config->DampingCoefficient = .08f;
        Config->CollisionThickness = 1.5f;
        Config->FrictionCoefficient = .3f;
        Config->bUseCCD = true;
        Config->bUseSelfCollisions = false;
    }
    if (UChaosClothSharedSimConfig* Shared = Cloth->GetClothConfig<UChaosClothSharedSimConfig>())
    {
        Shared->IterationCount = 2;
        Shared->SubdivisionCount = 2;
    }
    FString Error;
    if (!FSkeletalMeshClothingSystemUtilities::AssignClothingToSection(Mesh, Cloth, 0, Section, 0, &Error))
    {
        UE_LOG(LogTemp, Error, TEXT("Cloth: binding %s to section %d failed: %s"), *Cloth->GetName(), Section, *Error);
        return FString();
    }
    Mesh->MarkPackageDirty();
    return FString::Printf(TEXT("section %d, %d cloth vertices (%d pinned, %d free), max distance %.0f cm, %d collision bodies"),
        Section, Colours.Num(), Pinned, Free, MaxDistanceCm, Mesh->GetPhysicsAsset() ? Mesh->GetPhysicsAsset()->SkeletalBodySetups.Num() : 0);
#else
    return FString();
#endif
}

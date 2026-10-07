#include "YorimichiCloth.h"
#include "Engine/SkeletalMesh.h"
#include "ClothingSystemRuntimeTypes.h"
#include "Components/SkeletalMeshComponent.h"
#if WITH_EDITOR
#include "ChaosCloth/ChaosClothConfig.h"
#include "ClothingAsset.h"
#include "ClothingAssetFactoryInterface.h"
#include "ClothingSystemEditorInterfaceModule.h"
#include "Modules/ModuleManager.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PhysicsEngine/SkeletalBodySetup.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Misc/PackageName.h"
#include "UObject/Package.h"
#include "Rendering/SkeletalMeshModel.h"
#include "SkeletalMeshClothingSystemUtilities.h"
#endif

FString UYorimichiClothLibrary::AddSectionCloth(USkeletalMesh* Mesh, FName SlotName, float MaxDistanceCm, UPhysicsAsset* Colliders)
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
    UPhysicsAsset* Collision = Colliders ? Colliders : Mesh->GetPhysicsAsset();
    Params.PhysicsAsset = Collision;
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
        Section, Colours.Num(), Pinned, Free, MaxDistanceCm, Collision ? Collision->SkeletalBodySetups.Num() : 0);
#else
    return FString();
#endif
}

UPhysicsAsset* UYorimichiClothLibrary::MakeCapsuleColliders(USkeletalMesh* Mesh, const FString& PackagePath, const TArray<FName>& Bones,
    const TArray<FName>& From, const TArray<FName>& To, const TArray<float>& RadiiCm)
{
#if WITH_EDITOR
    if (!Mesh || Bones.Num() != From.Num() || Bones.Num() != To.Num() || Bones.Num() != RadiiCm.Num()) return nullptr;
    const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
    // The reference pose in component space.
    TArray<FTransform> Space;
    Space.SetNum(Ref.GetNum());
    for (int32 I = 0; I < Ref.GetNum(); ++I)
    {
        const int32 Parent = Ref.GetParentIndex(I);
        Space[I] = Parent == INDEX_NONE ? Ref.GetRefBonePose()[I] : Ref.GetRefBonePose()[I] * Space[Parent];
    }
    UPackage* Package = CreatePackage(*PackagePath);
    const FString Name = FPackageName::GetLongPackageAssetName(PackagePath);
    UPhysicsAsset* Asset = FindObject<UPhysicsAsset>(Package, *Name);
    const bool bNew = !Asset;
    if (bNew) Asset = NewObject<UPhysicsAsset>(Package, *Name, RF_Public | RF_Standalone | RF_Transactional);
    Asset->Modify();
    Asset->SkeletalBodySetups.Empty();
    Asset->ConstraintSetup.Empty();
    for (int32 K = 0; K < Bones.Num(); ++K)
    {
        const int32 Bone = Ref.FindBoneIndex(Bones[K]), A = Ref.FindBoneIndex(From[K]), B = Ref.FindBoneIndex(To[K]);
        if (Bone == INDEX_NONE || A == INDEX_NONE || B == INDEX_NONE)
        {
            UE_LOG(LogTemp, Error, TEXT("Cloth colliders: %s has no bone %s, %s or %s"), *Mesh->GetName(), *Bones[K].ToString(), *From[K].ToString(), *To[K].ToString());
            return nullptr;
        }
        const FVector Start = Space[Bone].InverseTransformPosition(Space[A].GetLocation());
        const FVector End = Space[Bone].InverseTransformPosition(Space[B].GetLocation());
        const FVector Axis = End - Start;
        FKSphylElem Capsule;
        Capsule.Center = (Start + End) * .5f;
        Capsule.Rotation = FRotationMatrix::MakeFromZ(Axis.GetSafeNormal()).Rotator();
        // The shape lives in the bone's space, scale included: an FBX in metres imports with its x100 on the root, so
        // the joints above are already divided by it and the radius must be too (Chaos scales the capsule back up).
        Capsule.Radius = RadiiCm[K] / Space[Bone].GetMaximumAxisScale();
        Capsule.Length = Axis.Size();   // already in the bone's scaled units, like Center
        USkeletalBodySetup* Body = NewObject<USkeletalBodySetup>(Asset, NAME_None, RF_Transactional);
        Body->BoneName = Bones[K];
        Body->PhysicsType = PhysType_Kinematic;
        Body->AggGeom.SphylElems.Add(Capsule);
        Asset->SkeletalBodySetups.Add(Body);
    }
    Asset->UpdateBodySetupIndexMap();
    Asset->UpdateBoundsBodiesArray();
    Asset->SetPreviewMesh(Mesh);
    if (bNew) FAssetRegistryModule::AssetCreated(Asset);
    Asset->MarkPackageDirty();
    return Asset;
#else
    return nullptr;
#endif
}

FString UYorimichiClothLibrary::DescribeCloth(USkeletalMesh* Mesh)
{
#if WITH_EDITOR
    if (!Mesh || !Mesh->GetImportedModel() || !Mesh->GetImportedModel()->LODModels.Num()) return TEXT("no mesh");
    FString Out;
    const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
    for (UClothingAssetBase* Base : Mesh->GetMeshClothingAssets())
    {
        const UClothingAssetCommon* Cloth = Cast<UClothingAssetCommon>(Base);
        if (!Cloth || !Cloth->LodData.Num()) continue;
        const FClothPhysicalMeshData& Phys = Cloth->LodData[0].PhysicalMeshData;
        int32 NoWeight = 0, Partial = 0, BadBone = 0;
        for (const FClothVertBoneData& Bone : Phys.BoneData)
        {
            float Sum = 0.f;
            for (int32 I = 0; I < Bone.NumInfluences; ++I)
            {
                Sum += Bone.BoneWeights[I];
                if (!Cloth->UsedBoneNames.IsValidIndex(Bone.BoneIndices[I])) ++BadBone;
            }
            NoWeight += Bone.NumInfluences == 0 || Sum < .01f;
            Partial += Sum >= .01f && Sum < .99f;
        }
        int32 Missing = 0;
        for (const FName& Name : Cloth->UsedBoneNames) Missing += Ref.FindBoneIndex(Name) == INDEX_NONE;
        const FPointWeightMap* Distance = Phys.FindWeightMap(EWeightMapTargetCommon::MaxDistance);
        float Lo = 0.f, Hi = 0.f;
        if (Distance && Distance->Values.Num())
        {
            Lo = Hi = Distance->Values[0];
            for (const float V : Distance->Values) { Lo = FMath::Min(Lo, V); Hi = FMath::Max(Hi, V); }
        }
        FBox3f Box(Phys.Vertices);
        Out += FString::Printf(TEXT("asset %s: %d bones (%d not in skeleton), reference bone %d; physical %d vertices, %d triangles, box %s; "
            "%d without weight, %d partial, %d bad bone indices; max distance map %s %.1f..%.1f cm; "),
            *Cloth->GetName(), Cloth->UsedBoneNames.Num(), Missing, Cloth->ReferenceBoneIndex, Phys.Vertices.Num(), Phys.Indices.Num() / 3,
            *Box.ToString(), NoWeight, Partial, BadBone, Distance ? TEXT("yes") : TEXT("missing"), Lo, Hi);
    }
    const TArray<FSkelMeshSection>& Sections = Mesh->GetImportedModel()->LODModels[0].Sections;
    for (int32 S = 0; S < Sections.Num(); ++S)
    {
        const FSkelMeshSection& Section = Sections[S];
        if (!Section.ClothingData.AssetGuid.IsValid() && !Section.ClothMappingDataLODs.Num()) continue;
        const int32 Entries = Section.ClothMappingDataLODs.Num() ? Section.ClothMappingDataLODs[0].Num() : 0;
        int32 PhysVerts = 0;
        for (UClothingAssetBase* Base : Mesh->GetMeshClothingAssets())
            if (const UClothingAssetCommon* Cloth = Cast<UClothingAssetCommon>(Base); Cloth && Cloth->LodData.Num())
                PhysVerts = Cloth->LodData[0].PhysicalMeshData.Vertices.Num();
        int32 Past = 0, Zero = 0, Skinned = 0;
        float Far = 0.f;
        if (Entries)
            for (const FMeshToMeshVertData& V : Section.ClothMappingDataLODs[0])
            {
                Skinned += V.SourceMeshVertIndices[3] == 0xFFFF;
                Past += V.SourceMeshVertIndices[0] >= PhysVerts || V.SourceMeshVertIndices[1] >= PhysVerts || V.SourceMeshVertIndices[2] >= PhysVerts;
                Zero += V.Weight <= 0.f;
                Far = FMath::Max(Far, FMath::Abs(V.PositionBaryCoordsAndDist.W));
            }
        Out += FString::Printf(TEXT("section %d: %d vertices, cloth asset index %d, %d mapping entries (%d past the physical mesh, %d zero weight, "
            "%d skin-only, largest offset along the normal %.2f cm); "), S, Section.NumVertices, Section.CorrespondClothAssetIndex, Entries, Past,
            Zero, Skinned, Far);
    }
    return Out;
#else
    return FString();
#endif
}

FString UYorimichiClothLibrary::DescribeRunningCloth(USkeletalMeshComponent* Component)
{
    if (!Component) return TEXT("no component");
    FString Out = FString::Printf(TEXT("component %s scale %s; "), *Component->GetComponentTransform().ToString(),
        *Component->GetComponentScale().ToString());
    const TArray<FTransform>& Space = Component->GetComponentSpaceTransforms();
    for (int32 I = 0; I < FMath::Min(4, Space.Num()); ++I)
        Out += FString::Printf(TEXT("bone %d %s: %s; "), I, *Component->GetBoneName(I).ToString(), *Space[I].ToString());
    for (const TPair<int32, FClothSimulData>& Pair : Component->GetCurrentClothingData_GameThread())
    {
        const FClothSimulData& Data = Pair.Value;
        FBox3f Raw(ForceInit);
        FBox Moved(ForceInit);
        int32 Bad = 0;
        for (const FVector3f& P : Data.Positions)
        {
            if (P.ContainsNaN()) { ++Bad; continue; }
            Raw += P;
            Moved += Data.Transform.TransformPosition(FVector(P));
        }
        Out += FString::Printf(TEXT("cloth %d: lod %d, %d positions (%d NaN), raw box %s, moved box %s, transform %s, component relative %s; "),
            Pair.Key, Data.LODIndex, Data.Positions.Num(), Bad, *Raw.ToString(), *Moved.ToString(), *Data.Transform.ToString(),
            *Data.ComponentRelativeTransform.ToString());
    }
    return Out;
}

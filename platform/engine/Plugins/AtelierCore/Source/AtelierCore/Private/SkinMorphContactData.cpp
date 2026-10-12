#include "SkinMorphContactData.h"
#include "Animation/MorphTarget.h"
#include "Engine/SkeletalMesh.h"
#include "Rendering/SkeletalMeshRenderData.h"
#if WITH_EDITOR
#include "SkinnedAssetCompiler.h"
#endif

namespace
{
    int32 RenderVertices(const USkeletalMesh* Asset, int32 LOD)
    {
        const FSkeletalMeshRenderData* Render = Asset ? Asset->GetResourceForRendering() : nullptr;
        return Render && Render->LODRenderData.IsValidIndex(LOD) ? int32(Render->LODRenderData[LOD].GetNumVertices()) : INDEX_NONE;
    }
}

const USkinMorphContactData* USkinMorphContactData::Find(const USkeletalMesh* Asset)
{
    if (const TArray<UAssetUserData*>* Data = Asset ? Asset->GetAssetUserDataArray() : nullptr)
        for (const UAssetUserData* Datum : *Data)
            if (const USkinMorphContactData* Contact = Cast<USkinMorphContactData>(Datum)) return Contact;
    return nullptr;
}

const FSkinMorphContactTarget* USkinMorphContactData::FindTarget(FName Target) const
{
    return Targets.FindByPredicate([Target](const FSkinMorphContactTarget& Captured) { return Captured.Target == Target; });
}

bool USkinMorphContactData::Validate(const USkeletalMesh* Asset, TConstArrayView<FName> Required, FString& Receipt) const
{
    TArray<FString> Problems, Held;
    const FString AssetName = Asset ? Asset->GetPathName() : TEXT("no mesh");
    const int32 Native = RenderVertices(Asset, LOD);
    if (!Asset) Problems.Add(TEXT("no mesh"));
    else if (Mesh.ToSoftObjectPath() != FSoftObjectPath(Asset)) Problems.Add(FString::Printf(TEXT("captured from %s"), *Mesh.ToString()));
    if (LOD != 0) Problems.Add(FString::Printf(TEXT("LOD %d (readers use LOD 0)"), LOD));
    if (Native != VertexCount) Problems.Add(FString::Printf(TEXT("%d vertices captured, the mesh renders %d"), VertexCount, Native));
    TSet<FName> Seen;
    int32 Total = 0;
    for (const FSkinMorphContactTarget& Captured : Targets)
    {
        const FString Name = Captured.Target.ToString();
        bool bSeen = false;
        Seen.Add(Captured.Target, &bSeen);
        if (Captured.Target.IsNone() || bSeen) { Problems.Add(Name + TEXT(" unnamed or repeated")); continue; }
        const UMorphTarget* Morph = Asset ? Asset->FindMorphTarget(Captured.Target) : nullptr;
        if (!Morph) { Problems.Add(Name + TEXT(" is not on the mesh")); continue; }
        const int32 Count = Captured.Vertices.Num();
        if (Captured.Deltas.Num() != Count) { Problems.Add(FString::Printf(TEXT("%s has %d vertices, %d deltas"), *Name, Count, Captured.Deltas.Num())); continue; }
        if (Morph->GetNumDeltasForLOD(LOD) != Count)
            Problems.Add(FString::Printf(TEXT("%s: %d deltas captured, the mesh has %d"), *Name, Count, Morph->GetNumDeltasForLOD(LOD)));
        TBitArray<> Used(false, FMath::Max(VertexCount, 0));
        for (int32 I = 0; I < Count; ++I)
        {
            const int32 Vertex = Captured.Vertices[I];
            if (Vertex < 0 || Vertex >= VertexCount) { Problems.Add(FString::Printf(TEXT("%s: vertex %d out of range"), *Name, Vertex)); break; }
            if (Used[Vertex]) { Problems.Add(FString::Printf(TEXT("%s: vertex %d repeated"), *Name, Vertex)); break; }
            Used[Vertex] = true;
            if (Captured.Deltas[I].ContainsNaN()) { Problems.Add(FString::Printf(TEXT("%s: vertex %d delta not finite"), *Name, Vertex)); break; }
        }
#if WITH_EDITOR
        // The editor still has the imported deltas: they must be these, exactly.
        int32 I = 0;
        for (FMorphTargetDeltaIterator It = Morph->GetDeltaIteratorForLOD(LOD); !It.AtEnd(); ++It, ++I)
            if (I >= Count || Captured.Vertices[I] != int32(It->SourceIdx) || Captured.Deltas[I] != It->PositionDelta)
            {
                Problems.Add(Name + TEXT(" differs from the mesh's deltas"));
                break;
            }
#endif
        Total += Count;
        Held.Add(FString::Printf(TEXT("%s:%d"), *Name, Count));
    }
    for (const FName Target : Required)
    {
        const FSkinMorphContactTarget* Captured = FindTarget(Target);
        if (!Captured || Captured->Vertices.IsEmpty()) Problems.Add(Target.ToString() + TEXT(" required but not captured"));
    }
    Receipt = Problems.IsEmpty()
        ? FString::Printf(TEXT("valid: %s LOD %d, %d vertices, %d targets, %d deltas (%s)"), *AssetName, LOD, VertexCount, Targets.Num(), Total,
                          *FString::Join(Held, TEXT(",")))
        : FString::Printf(TEXT("INVALID for %s: %s"), *AssetName, *FString::Join(Problems, TEXT("; ")));
    return Problems.IsEmpty();
}

USkinMorphContactData* USkinMorphContactLibrary::CaptureSkinMorphContacts(USkeletalMesh* Mesh, const TArray<FName>& Targets, FString& Receipt)
{
#if WITH_EDITOR
    if (!Mesh) { Receipt = TEXT("no mesh"); return nullptr; }
    if (Targets.IsEmpty()) { Receipt = TEXT("no targets named"); return nullptr; }
    USkinnedAsset* const Built[] = {Mesh};
    FSkinnedAssetCompilingManager::Get().FinishCompilation(Built);
    USkinMorphContactData* Data = NewObject<USkinMorphContactData>(Mesh, NAME_None, RF_Transactional);
    Data->Mesh = Mesh;
    Data->LOD = 0;
    Data->VertexCount = RenderVertices(Mesh, 0);
    TArray<FString> Problems;
    for (const FName Name : Targets)
    {
        const UMorphTarget* Morph = Mesh->FindMorphTarget(Name);
        if (!Morph) { Problems.Add(Name.ToString() + TEXT(" is not on the mesh")); continue; }
        FSkinMorphContactTarget& Captured = Data->Targets.AddDefaulted_GetRef();
        Captured.Target = Name;
        for (FMorphTargetDeltaIterator It = Morph->GetDeltaIteratorForLOD(0); !It.AtEnd(); ++It)
        {
            Captured.Vertices.Add(int32(It->SourceIdx));
            Captured.Deltas.Add(It->PositionDelta);
        }
        if (Captured.Vertices.IsEmpty()) Problems.Add(Name.ToString() + TEXT(" has no LOD 0 deltas on the CPU"));
    }
    if (!Problems.IsEmpty())
    {
        Receipt = FString::Printf(TEXT("not captured for %s: %s"), *Mesh->GetPathName(), *FString::Join(Problems, TEXT("; ")));
        return nullptr;
    }
    if (!Data->Validate(Mesh, Targets, Receipt)) return nullptr;
    Mesh->Modify();
    Mesh->AddAssetUserData(Data);
    Mesh->MarkPackageDirty();
    return Data;
#else
    Receipt = TEXT("capture needs the editor's imported deltas");
    return nullptr;
#endif
}

bool USkinMorphContactLibrary::ClearSkinMorphContacts(USkeletalMesh* Mesh)
{
#if WITH_EDITOR
    if (!USkinMorphContactData::Find(Mesh)) return false;
    Mesh->Modify();
    Mesh->RemoveUserDataOfClass(USkinMorphContactData::StaticClass());
    Mesh->MarkPackageDirty();
    return true;
#else
    return false;
#endif
}

bool USkinMorphContactLibrary::ValidateSkinMorphContacts(USkeletalMesh* Mesh, const TArray<FName>& Required, FString& Receipt)
{
    const USkinMorphContactData* Data = USkinMorphContactData::Find(Mesh);
    if (!Data)
    {
        Receipt = FString::Printf(TEXT("INVALID for %s: no contact data"), Mesh ? *Mesh->GetPathName() : TEXT("no mesh"));
        return false;
    }
    return Data->Validate(Mesh, Required, Receipt);
}

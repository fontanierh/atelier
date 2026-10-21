#include "FoliageBuilder.h"
#include "Engine/StaticMesh.h"
#include "StaticMeshAttributes.h"
#include "MeshDescription.h"
#include "StaticMeshCompiler.h"
#include "UObject/GarbageCollection.h"

bool UYorimichiFoliageBuilder::StampSourceRoles(UStaticMesh* Source)
{
    if (!Source || !IsInGameThread()) return false;
    FStaticMeshCompilingManager::Get().FinishCompilation({Source});
    const FMeshDescription* D=Source->GetMeshDescription(0);
    if (!D) return false;
    FStaticMeshConstAttributes A(*D);const auto UV=A.GetVertexInstanceUVs();
    bool Marked=false,Valid=true,Authored=true,Rigid=true;
    if (UV.GetNumChannels()>5)
        for (const auto I:D->VertexInstances().GetElementIDs())
        {
            const FVector2f V=UV.Get(I,5);
            const bool Marker=FMath::IsNearlyEqual(V.Y,73.125f,.01f) || FMath::IsNearlyEqual(V.Y,-72.125f,.01f);
            Marked|=Marker;Valid&=Marker && (V.X==0.f || V.X==1.f || V.X==2.f || V.X==3.f);Authored&=V.X==3.f;Rigid&=V.X==0.f;
        }
    if (Marked && !Valid) return false;
    const FString Prefix=Marked && Rigid?TEXT("FoliageRigid_"):Marked && Authored?TEXT("FoliageAuthored_"):TEXT("FoliageRoles_");bool Changed=false;
    for (auto& Slot:Source->GetStaticMaterials())
    {
        FString Name=Slot.MaterialSlotName.ToString();
        for (const TCHAR* Previous:{TEXT("FoliageRoles_"),TEXT("FoliageAuthored_"),TEXT("FoliageRigid_")})
            if (Name.StartsWith(Previous)) { Name.RightChopInline(FCString::Strlen(Previous));break; }
        const FName Desired(*(Marked?Prefix+Name:Name));
        if (Slot.MaterialSlotName!=Desired) { Slot.MaterialSlotName=Desired;Changed=true; }
    }
    if (Changed) Source->MarkPackageDirty();
    return true;
}

void UYorimichiFoliageBuilder::CollectUnused()
{
    // Python's CollectGarbage only requests a future engine tick. This owner is
    // a synchronous commandlet; saved, unreferenced mesh packages must leave now.
    ::CollectGarbage(RF_NoFlags,true);
}

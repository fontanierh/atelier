#include "SkateCollisionBuilder.h"
#include "SkateCollisionAsset.h"
#include "SkateCollisionWorld.h"
#include "SkateRails.h"
#include "Components/StaticMeshComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "UObject/StrongObjectPtr.h"
#include "UObject/UObjectGlobals.h"

bool USkateCollisionBuilderLibrary::ValidateSurfaceAndScene(UWorld* World,UStaticMesh* FixtureMesh,
    USkateCollisionAsset* Catalog,TArray<FString>& Errors,TArray<FString>& Warnings)
{
    check(IsInGameThread());Errors.Reset();Warnings.Reset();
    if(!World||!FixtureMesh||!Catalog||!Catalog->FindMesh(FixtureMesh))
    {Errors.Add(TEXT("Scene fixture needs a world and a small baked collision mesh"));return false;}
    Catalog->Validate(Errors);if(!Errors.IsEmpty())return false;
    FString Error;if(!SkateValidateCollisionMaterialTransport(Error)){Errors.Add(Error);return false;}
    USkateRailSubsystem* Rails=World->GetSubsystem<USkateRailSubsystem>();
    if(!Rails){Errors.Add(TEXT("Scene fixture requires actual SkateRailSubsystem"));return false;}
    struct FCleanup
    {
        USkateRailSubsystem* Rails;TArray<FSkateRail> Saved;TArray<AActor*> Actors;
        ~FCleanup(){Rails->Rails=MoveTemp(Saved);for(AActor* A:Actors)if(IsValid(A))A->Destroy();}
    } Cleanup{Rails,Rails->Rails,{}};
    TStrongObjectPtr<USkateCollisionAsset> Profiles(NewObject<USkateCollisionAsset>());
    Profiles->Meshes=Catalog->Meshes;Profiles->Revision=Catalog->Revision;
    TStrongObjectPtr<UPhysicalMaterial> Material(NewObject<UPhysicalMaterial>());
    FSkateCollisionSurfaceProfile Profile;Profile.PhysicalMaterial=Material.Get();Profile.PackedSurface=(8<<7)|17;
    Profile.bOverrideContactMaterial=true;Profile.StaticFriction=.375f;Profile.DynamicFriction=.25f;Profile.Restitution=.5f;
    Profiles->SurfaceProfiles.Add(Profile);Profiles->Validate(Errors);if(!Errors.IsEmpty())return false;
    USkateCollisionAsset* Catalogs[]={Profiles.Get()};
    const FVector Centre(10000000.,10000000.,10000000.);const FBox Region(Centre-FVector(2000.),Centre+FVector(2000.));
    // Imported park vertices may use absolute authored coordinates. Place the
    // mesh's actual local bounds centre here, with a bounded uniform extent.
    const FBoxSphereBounds MeshBounds=FixtureMesh->GetBounds();
    const double MeshScale=FMath::Min(1.,500./FMath::Max(MeshBounds.BoxExtent.GetAbsMax(),1.));
    const auto MeshAt=[&](const FVector& Target)
    {return FTransform(FQuat::Identity,Target-MeshBounds.Origin*MeshScale,FVector(MeshScale));};
    FSkateCollisionSceneTracker Tracker;Tracker.ScanPeriodSeconds=0;double Clock=100.;
    Tracker.AcceptSnapshot(World,nullptr,Region,Rails,MakeArrayView(Catalogs),Clock);
    auto Dirty=[&](const TCHAR* Label)
    {
        Clock+=.001;
        if(!Tracker.Poll(World,nullptr,Region,Rails,MakeArrayView(Catalogs),Clock))Errors.Add(FString(TEXT("Scene change missed: "))+Label);
    };
    auto Stable=[&](const TCHAR* Label)
    {
        Clock+=.001;
        if(Tracker.Poll(World,nullptr,Region,Rails,MakeArrayView(Catalogs),Clock))Errors.Add(FString(TEXT("Unchanged scene reported dirty: "))+Label);
    };
    Stable(TEXT("accepted empty region"));
    // A same-count Blueprint replacement must be detected even without a
    // builder revision change. The duplicate retains the complete bake.
    USkateCollisionMeshData* Original=Profiles->Meshes[0];
    TStrongObjectPtr<USkateCollisionMeshData> Replacement(DuplicateObject<USkateCollisionMeshData>(Original,GetTransientPackage()));
    Profiles->Meshes[0]=Replacement.Get();Dirty(TEXT("same-count catalog member replacement"));Stable(TEXT("unchanged replaced catalog member"));
    Profiles->Meshes[0]=Original;Dirty(TEXT("catalog member restoration"));
    ++Profiles->Revision;Dirty(TEXT("catalog rebake revision"));Stable(TEXT("unchanged catalog revision"));
    FActorSpawnParameters Params;Params.ObjectFlags|=RF_Transient;Params.SpawnCollisionHandlingOverride=ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    AActor* StaticActor=World->SpawnActor<AActor>(Params);
    if(!StaticActor){Errors.Add(TEXT("Could not spawn scene fixture actor"));return false;}
    Cleanup.Actors.Add(StaticActor);
    auto* Component=NewObject<UStaticMeshComponent>(StaticActor);StaticActor->SetRootComponent(Component);StaticActor->AddInstanceComponent(Component);
    Component->SetMobility(EComponentMobility::Movable);Component->SetStaticMesh(FixtureMesh);
    Component->SetCollisionEnabled(ECollisionEnabled::QueryOnly);Component->SetCollisionResponseToAllChannels(ECR_Ignore);Component->SetCollisionResponseToChannel(ECC_Pawn,ECR_Block);
    Component->SetWorldTransform(MeshAt(Centre));Component->RegisterComponentWithWorld(World);Component->UpdateBounds();
    Dirty(TEXT("registered/loaded mesh"));Stable(TEXT("registered mesh unchanged"));
    Component->SetWorldTransform(MeshAt(Centre+FVector(37.,0,0)));Component->UpdateBounds();Dirty(TEXT("moved mesh with stationary rider"));
    // Real profile mapping reaches Gather -> optional native material transport.
    Component->SetPhysMaterialOverride(Material.Get());Dirty(TEXT("physical material override"));
    FSkateCollisionSnapshot Snapshot;FSkateCollisionDiagnostics Diagnostics;double Reach=0;
    if(!SkateGatherCollisionWorld(World,nullptr,Centre,Centre,0,nullptr,MakeArrayView(Catalogs),Snapshot,Reach,Diagnostics,Tracker.Generation()))
        Errors.Append(Diagnostics.Errors);
    else
    {
        if(Diagnostics.TriangleCount<=0||Diagnostics.MaterialOverrideCount<=0||Diagnostics.NonzeroSurfaceCount<=0)
            Errors.Add(TEXT("Scene fixture did not produce mapped collision triangles"));
        for(const auto& M:Snapshot.Materials)
            if(M.bOverride&&(M.Surface!=uint16(Profile.PackedSurface)||M.StaticFriction!=Profile.StaticFriction||M.DynamicFriction!=Profile.DynamicFriction||M.Restitution!=Profile.Restitution))
                {Errors.Add(TEXT("UE physical material profile lost packed surface/coefficients"));break;}
        if(!SkateValidateNativeCollisionSnapshot(Snapshot,Error))Errors.Add(Error);
    }
    Component->SetPhysMaterialOverride(nullptr);Dirty(TEXT("physical material override removal"));
    if(SkateGatherCollisionWorld(World,nullptr,Centre,Centre,0,nullptr,MakeArrayView(Catalogs),Snapshot,Reach,Diagnostics,Tracker.Generation()))
    {
        const auto Native=SkateNativeCollisionSnapshot(Snapshot);
        if(!Native.triangle_materials.empty()||!Native.triangle_surfaces.empty())Errors.Add(TEXT("unmapped UE material changed stock defaults"));
    }
    else Errors.Append(Diagnostics.Errors);
    Component->UnregisterComponent();Dirty(TEXT("unregistered/unloaded mesh"));
    Component->RegisterComponentWithWorld(World);Component->UpdateBounds();Dirty(TEXT("reregistered/reloaded mesh"));
    Tracker.AcceptSnapshot(World,nullptr,Region,Rails,MakeArrayView(Catalogs),Clock);Stable(TEXT("AcceptSnapshot does not bump generation"));
    AActor* InstanceActor=World->SpawnActor<AActor>(Params);
    if(!InstanceActor){Errors.Add(TEXT("Could not spawn instance fixture actor"));return false;}
    Cleanup.Actors.Add(InstanceActor);
    auto* Instances=NewObject<UInstancedStaticMeshComponent>(InstanceActor);InstanceActor->SetRootComponent(Instances);InstanceActor->AddInstanceComponent(Instances);
    Instances->SetMobility(EComponentMobility::Movable);Instances->SetStaticMesh(FixtureMesh);
    Instances->SetCollisionEnabled(ECollisionEnabled::QueryOnly);Instances->SetCollisionResponseToAllChannels(ECR_Ignore);Instances->SetCollisionResponseToChannel(ECC_Pawn,ECR_Block);
    Instances->SetWorldTransform(MeshAt(Centre));Instances->RegisterComponentWithWorld(World);
    const int32 Instance=Instances->AddInstance(MeshAt(Centre+FVector(0,200,0)),true);Instances->UpdateBounds();
    Dirty(TEXT("loaded instanced mesh"));
    if(!Instances->UpdateInstanceTransform(Instance,MeshAt(Centre+FVector(0,250,0)),true,true,true))Errors.Add(TEXT("Could not move fixture instance"));
    Instances->UpdateBounds();Dirty(TEXT("moved instance"));
    Instances->RemoveInstance(Instance);Instances->UpdateBounds();Dirty(TEXT("removed instance"));
    FSkateRail Rail;Rail.Id=TEXT("SkateCollisionSceneFixture");Rail.Points={Centre,Centre+FVector(100,0,0)};
    const int32 RailIndex=Rails->Add(MoveTemp(Rail));
    if(RailIndex==INDEX_NONE){Errors.Add(TEXT("Could not add fixture rail"));return false;}
    Dirty(TEXT("added rail"));Rails->Rails[RailIndex].Points[1].Y+=37.;Dirty(TEXT("moved rail endpoint"));
    Rails->Rails.RemoveAt(RailIndex);Dirty(TEXT("removed rail"));
    Component->UnregisterComponent();StaticActor->Destroy();Dirty(TEXT("destroyed mesh"));Stable(TEXT("final unchanged scene"));
    // No physical step, body/force feedback or cooked package mutation occurs here.
    Warnings.Add(TEXT("Scene fixtures prove static/ISM registration, movement and rail changes; kinematic surfaces refresh as snapshots and do not impart platform velocity."));
    return Errors.IsEmpty();
}

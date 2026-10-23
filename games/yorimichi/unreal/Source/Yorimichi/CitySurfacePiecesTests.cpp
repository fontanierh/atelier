#include "CitySurfacePieces.h"
#include "CitySurfaceValidation.h"
#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
#include "Misc/AutomationTest.h"
#include "Engine/StaticMesh.h"
#include "PhysicsEngine/BodySetup.h"
#include "Chaos/TriangleMeshImplicitObject.h"
#include "UObject/StrongObjectPtr.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FCitySurfaceMembershipTest,"Yorimichi.CityPieces.CompleteMembership",
    EAutomationTestFlags_ApplicationContextMask|EAutomationTestFlags::EngineFilter)
bool FCitySurfaceMembershipTest::RunTest(const FString&)
{
    auto Root=MakeShared<FJsonObject>();Root->SetNumberField(TEXT("version"),3);
    Root->SetBoolField(TEXT("complete"),true);Root->SetStringField(TEXT("tag"),TEXT("v1_128m"));
    Root->SetNumberField(TEXT("triangle_limit"),32768);
    auto Sources=MakeShared<FJsonObject>();Root->SetObjectField(TEXT("sources"),Sources);
    for(const FString& Name:JapanCityPieces::Parents())
    {
        auto Source=MakeShared<FJsonObject>();Sources->SetObjectField(Name,Source);
        Source->SetNumberField(TEXT("source_triangles"),2);Source->SetNumberField(TEXT("source_collision_hulls"),1);
        auto Bounds=MakeShared<FJsonObject>();
        Bounds->SetArrayField(TEXT("min"),{MakeShared<FJsonValueNumber>(-2.),MakeShared<FJsonValueNumber>(-4.),MakeShared<FJsonValueNumber>(0.)});
        Bounds->SetArrayField(TEXT("max"),{MakeShared<FJsonValueNumber>(3.),MakeShared<FJsonValueNumber>(5.),MakeShared<FJsonValueNumber>(10.)});
        Source->SetObjectField(TEXT("source_bounds"),Bounds);
        TArray<TSharedPtr<FJsonValue>> Tiles;
        for(int32 I=0;I<2;++I)
        {
            auto Tile=MakeShared<FJsonObject>();Tile->SetStringField(TEXT("name"),FString(Name)+
                FString::Printf(TEXT("_cell_-1_0_Piece%d"),I));
            Tile->SetNumberField(TEXT("triangles"),1);Tile->SetNumberField(TEXT("collision_hulls"),I==0?1:0);
            Tiles.Add(MakeShared<FJsonValueObject>(Tile));
        }
        Source->SetArrayField(TEXT("tiles"),Tiles);
    }
    TMap<FString,TArray<FString>> Paths;
    TMap<FString,FBox> Bounds;
    TestTrue(TEXT("Complete bounded union loads signed cells"),JapanCityPieces::Read(Root,Paths,&Bounds));
    TestEqual(TEXT("All logical placements retained"),Paths.Num(),JapanCityPieces::Parents().Num());
    TestEqual(TEXT("Shared city roster contains all current sources"),JapanCityPieces::Parents().Num(),86);
    TestEqual(TEXT("Logical parent bounds use native handedness"),Bounds.FindChecked(TEXT("HD_Square")).Min,FVector(-200.,-500.,0.));
    const auto Streets=Sources->GetObjectField(TEXT("HD_Streets"));
    Streets->SetNumberField(TEXT("source_triangles"),3);
    TestFalse(TEXT("Missing face refuses whole membership"),JapanCityPieces::Read(Root,Paths,&Bounds));
    TestTrue(TEXT("Failed membership leaves no partial paths"),Paths.IsEmpty());
    TestTrue(TEXT("Failed membership leaves no partial logical bounds"),Bounds.IsEmpty());
    Streets->SetNumberField(TEXT("source_triangles"),2);
    Streets->GetArrayField(TEXT("tiles"))[1]->AsObject()->SetNumberField(TEXT("collision_hulls"),1);
    TestFalse(TEXT("Duplicated whole collision refuses"),JapanCityPieces::Read(Root,Paths));
    Streets->GetArrayField(TEXT("tiles"))[1]->AsObject()->SetNumberField(TEXT("collision_hulls"),0);
    const auto Park=Sources->GetObjectField(TEXT("HD_Park"));
    Sources->RemoveField(TEXT("HD_Park"));
    TestFalse(TEXT("Missing new park family refuses readiness"),JapanCityPieces::Read(Root,Paths));
    TestTrue(TEXT("Missing new family leaves no partial paths"),Paths.IsEmpty());
    Sources->SetObjectField(TEXT("HD_Park"),Park);
    const auto Harbor=Sources->GetObjectField(TEXT("HD_Harbor"));
    Sources->RemoveField(TEXT("HD_Harbor"));
    TestFalse(TEXT("Missing final-cut Harbor refuses readiness"),JapanCityPieces::Read(Root,Paths));
    Sources->SetObjectField(TEXT("HD_Harbor"),Harbor);
    Sources->SetObjectField(TEXT("HD_Foreign"),Park);
    TestFalse(TEXT("Unowned source cannot enter the city handoff"),JapanCityPieces::Read(Root,Paths));
    Sources->RemoveField(TEXT("HD_Foreign"));
    TestTrue(TEXT("Restored complete city inventory loads"),JapanCityPieces::Read(Root,Paths));
    const auto Clock=Sources->GetObjectField(TEXT("HD_ClockHall"));
    const auto ClockTiles=Clock->GetArrayField(TEXT("tiles"));
    auto Small=MakeShared<FJsonObject>();Small->SetStringField(TEXT("name"),TEXT("HD_ClockHall"));
    Small->SetNumberField(TEXT("triangles"),2);Small->SetNumberField(TEXT("collision_hulls"),1);
    Clock->SetArrayField(TEXT("tiles"),{MakeShared<FJsonValueObject>(Small)});
    TestTrue(TEXT("A bounded small source retains its stable logical name"),JapanCityPieces::Read(Root,Paths));
    TestEqual(TEXT("Small source has exactly one native asset"),Paths.FindChecked(TEXT("HD_ClockHall")).Num(),1);
    Clock->SetNumberField(TEXT("source_triangles"),32769);Small->SetNumberField(TEXT("triangles"),32769);
    TestFalse(TEXT("Whole-name shortcut cannot admit an oversized source"),JapanCityPieces::Read(Root,Paths));
    Clock->SetNumberField(TEXT("source_triangles"),2);Clock->SetArrayField(TEXT("tiles"),ClockTiles);
    Clock->GetObjectField(TEXT("source_bounds"))->SetArrayField(TEXT("min"),{MakeShared<FJsonValueNumber>(4.),MakeShared<FJsonValueNumber>(-4.),MakeShared<FJsonValueNumber>(0.)});
    TestFalse(TEXT("Reversed logical bounds refuse readiness"),JapanCityPieces::Read(Root,Paths));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FCitySurfaceCollisionTest,"Yorimichi.CityPieces.CookedQuerySurface",
    EAutomationTestFlags_ApplicationContextMask|EAutomationTestFlags::EngineFilter)
bool FCitySurfaceCollisionTest::RunTest(const FString&)
{
    TStrongObjectPtr<UStaticMesh> Mesh(NewObject<UStaticMesh>());
    Mesh->CreateBodySetup();auto* Body=Mesh->GetBodySetup();
    Body->CollisionTraceFlag=CTF_UseComplexAsSimple;Body->bNeverNeedsCookedCollisionData=false;
    Body->bCreatedPhysicsMeshes=true;Body->bFailedToCreatePhysicsMeshes=false;
    Chaos::FTriangleMeshImplicitObject::ParticlesType Particles;Particles.AddParticles(3);
    Particles.SetX(0,FVector3f(0,0,0));Particles.SetX(1,FVector3f(100,0,0));Particles.SetX(2,FVector3f(0,100,0));
    TArray<Chaos::TVec3<int32>> Faces;Faces.Emplace(0,1,2);TArray<uint16> Materials={0};
    Body->TriMeshGeometries.Add(Chaos::FTriangleMeshImplicitObjectPtr(new Chaos::FTriangleMeshImplicitObject(
        MoveTemp(Particles),MoveTemp(Faces),MoveTemp(Materials))));
    TestTrue(TEXT("Actual cooked face is present"),UCitySurfaceValidation::ValidateCollision(Mesh.Get(),1,false));
    TestFalse(TEXT("Render count cannot hide missing cooked face"),UCitySurfaceValidation::ValidateCollision(Mesh.Get(),2,false));
    Mesh->LODForCollision=1;
    TestFalse(TEXT("Different collision LOD refuses"),UCitySurfaceValidation::ValidateCollision(Mesh.Get(),1,false));
    Mesh->LODForCollision=0;Mesh->ComplexCollisionMesh=NewObject<UStaticMesh>();
    TestFalse(TEXT("External complex surface refuses"),UCitySurfaceValidation::ValidateCollision(Mesh.Get(),1,false));
    Mesh->ComplexCollisionMesh=nullptr;Body->CollisionTraceFlag=CTF_UseDefault;
    TestFalse(TEXT("Implicit project collision policy refuses"),UCitySurfaceValidation::ValidateCollision(Mesh.Get(),1,false));
    Body->CollisionTraceFlag=CTF_UseSimpleAndComplex;
    TestTrue(TEXT("Authored UCX retains explicit simple and complex queries"),UCitySurfaceValidation::ValidateCollision(Mesh.Get(),1,true));
    Body->bFailedToCreatePhysicsMeshes=true;
    TestFalse(TEXT("Failed cooked physics refuses"),UCitySurfaceValidation::ValidateCollision(Mesh.Get(),1,true));
    return true;
}
#endif

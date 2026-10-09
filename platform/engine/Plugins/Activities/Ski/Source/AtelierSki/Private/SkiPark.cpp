#include "SkiPark.h"
#include "SkiSettings.h"
#include "Native/SkiParkShape.h"
#include "ProceduralMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"

struct FSkiParkData
{
    atelier::ski::Park Park;
    double MinX = 0, MaxX = 0, HalfWidth = 0;
};

ASkiPark::ASkiPark()
{
    PrimaryActorTick.bCanEverTick = false;
    Surface = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("Surface"));
    RootComponent = Surface;
    Surface->bUseAsyncCooking = true;
    Surface->bUseComplexAsSimpleCollision = true;
    Surface->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
    Tags.Add(TEXT("SkiPark"));
    static ConstructorHelpers::FObjectFinder<UMaterialInterface> Plain(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
    DefaultMaterial = Plain.Object;
}

ASkiPark::~ASkiPark() = default;

void ASkiPark::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);
    Build();
}

void ASkiPark::BeginPlay()
{
    Super::BeginPlay();
    Build();
}

void ASkiPark::Build()
{
    if (bBuilt) return;
    bBuilt = true;
    Data = MakeUnique<FSkiParkData>();
    const atelier::ski::ParkSpec& Spec = Data->Park.Spec();
    Data->MinX = Spec.startX - Margin;
    Data->MaxX = Spec.finishX + Margin + 20;
    Data->HalfWidth = Spec.halfWidth + Margin;

    // Park x down the fall line is the actor's forward; park y (left) is the actor's -Y. Clockwise from above.
    const int32 Along = FMath::CeilToInt32((Data->MaxX - Data->MinX) * 100.0 / AlongSpacing) + 1;
    const int32 Across = FMath::CeilToInt32(2 * Data->HalfWidth * 100.0 / AcrossSpacing) + 1;
    TArray<FVector> Vertices; TArray<FVector> Normals; TArray<FVector2D> UV; TArray<int32> Triangles;
    Vertices.Reserve(Along * Across); Normals.Reserve(Along * Across); UV.Reserve(Along * Across);
    Triangles.Reserve((Along - 1) * (Across - 1) * 6);
    for (int32 I = 0; I < Along; ++I)
        for (int32 J = 0; J < Across; ++J)
        {
            const double X = FMath::Min(Data->MinX + I * AlongSpacing / 100.0, Data->MaxX);
            const double LocalY = -Data->HalfWidth * 100.0 + J * AcrossSpacing;   // cm, actor space
            const double Y = -LocalY / 100.0;
            const atelier::ski::Vec3 N = Data->Park.Normal(X, Y);
            Vertices.Add(FVector(X * 100.0, LocalY, Data->Park.Height(X, Y) * 100.0));
            Normals.Add(FVector(N.x, -N.y, N.z));
            UV.Add(FVector2D(LocalY / 120.0, X * 100.0 / 800.0));
        }
    for (int32 I = 0; I + 1 < Along; ++I)
        for (int32 J = 0; J + 1 < Across; ++J)
        {
            const int32 A = I * Across + J, B = (I + 1) * Across + J, C = I * Across + J + 1, D = (I + 1) * Across + J + 1;
            Triangles.Append({A, B, C, B, D, C});
        }
    Surface->ClearAllMeshSections();
    Surface->CreateMeshSection(0, Vertices, Triangles, Normals, UV, TArray<FColor>(), TArray<FProcMeshTangent>(), true);
    const USkiSettings* S = GetDefault<USkiSettings>();
    UMaterialInterface* Snow = S->SnowMaterial.IsNull() ? nullptr : S->SnowMaterial.LoadSynchronous();
    if (!Snow && DefaultMaterial)
    {
        UMaterialInstanceDynamic* White = UMaterialInstanceDynamic::Create(DefaultMaterial, this);
        White->SetVectorParameterValue(TEXT("Color"), FLinearColor(.92f, .95f, 1.f));
        Snow = White;
    }
    Surface->SetMaterial(0, Snow);
}

bool ASkiPark::InPark(double LocalX, double LocalY) const
{
    return Data && LocalX >= Data->MinX * 100.0 && LocalX <= Data->MaxX * 100.0 && FMath::Abs(LocalY) <= Data->HalfWidth * 100.0;
}

bool ASkiPark::Sample(double X, double Y, double& OutZ, FVector& OutNormal) const
{
    if (!Data) return false;
    const FVector Origin = GetActorLocation();
    const FQuat Yaw(FVector::UpVector, FMath::DegreesToRadians(GetActorRotation().Yaw));
    const FVector Local = Yaw.UnrotateVector(FVector(X - Origin.X, Y - Origin.Y, 0));
    if (!InPark(Local.X, Local.Y)) return false;
    const double PX = Local.X / 100.0, PY = -Local.Y / 100.0;
    OutZ = Origin.Z + Data->Park.Height(PX, PY) * 100.0;
    const atelier::ski::Vec3 N = Data->Park.Normal(PX, PY);
    OutNormal = Yaw.RotateVector(FVector(N.x, -N.y, N.z));
    return true;
}

FVector ASkiPark::GetStartLocation() const
{
    if (!Data) return GetActorLocation();
    const double X = Data->Park.StartX(), Y = Data->Park.StartY();
    const FVector Local(X * 100.0, -Y * 100.0, Data->Park.Height(X, Y) * 100.0);
    return GetActorLocation() + FQuat(FVector::UpVector, FMath::DegreesToRadians(GetActorRotation().Yaw)).RotateVector(Local);
}

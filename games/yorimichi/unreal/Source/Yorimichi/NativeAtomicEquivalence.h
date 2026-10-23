#pragma once
#include "Kismet/BlueprintFunctionLibrary.h"
#include "NativeAtomicEquivalence.generated.h"

class UStaticMesh;
class UStaticMeshComponent;

/** Read-only bounded saved/render/physics evidence; never generates or substitutes geometry. */
UCLASS()
class YORIMICHI_API UNativeAtomicEquivalence : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Empty text refuses unsupported, missing, nonfinite or unavailable CPU/cooked data. */
    UFUNCTION(BlueprintCallable, Category="Atomic mesh evidence")
    static FString Snapshot(UStaticMesh* Mesh,const FString& Logical,int32 FirstTriangle=0,int32 MaximumTriangles=16384,int32 LODIndex=0);

    /** Query only this component. Radius zero means ray; positive radius means capsule. */
    UFUNCTION(BlueprintCallable, Category="Atomic mesh evidence")
    static FString Probe(UStaticMeshComponent* Component,FVector Start,FVector End,FQuat Rotation,
                         float Radius,float HalfHeight,bool TraceComplex);

    /** Actual fixture/component policy and transform, separate from asset geometry. */
    UFUNCTION(BlueprintCallable, Category="Atomic mesh evidence")
    static FString ComponentPolicy(UStaticMeshComponent* Component);
};

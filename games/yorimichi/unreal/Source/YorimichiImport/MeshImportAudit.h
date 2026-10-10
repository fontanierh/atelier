#pragma once
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MeshImportAudit.generated.h"

class UStaticMesh;

/** Import audit: exports the actual built LOD triangles for source comparison. */
UCLASS()
class YORIMICHIIMPORT_API UMeshImportAudit : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable) static bool DumpMeshTriangles(UStaticMesh* Mesh, FVector Origin, const FString& Path);
};

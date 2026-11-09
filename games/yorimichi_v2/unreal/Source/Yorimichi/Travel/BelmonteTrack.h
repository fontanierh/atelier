#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "BelmonteTrack.generated.h"

class FJsonObject;
class UInstancedStaticMeshComponent;
class UPointLightComponent;
class UPostProcessComponent;
class UStaticMesh;
class UStaticMeshComponent;

/**
 * The Belmonte railway's track (Content/Data/belmonte_track/track.json, tools/belmonte_track_data.py): ballast and rail
 * chunks, the passing loop, turnouts, buffer stops, the tunnels' linings and portals, the viaduct and the grass banks,
 * each a static mesh with its LODs and the collision the Train Builder gave it; sleepers as one hierarchical instanced
 * group per chunk, lamps and small pieces instanced.
 *
 * The tunnels are dark: the lining is soot-black and the sky does not reach in. Their lamps' lights (2700 K, no
 * shadows, about 14 m) are switched on only while the camera is inside that tunnel's volumes or its portals' load
 * boxes, and only within light_range_cm of it; each lining piece carries a post-process box that pins the exposure
 * range (min/max EV), lowers the exposure and the sky's indirect light inside, and the lamps are brightened by as
 * much: near black between lamps, warm pools at each, the portals' daylight bright at the ends.
 */
UCLASS()
class YORIMICHI_API ABelmonteTrack : public AActor
{
    GENERATED_BODY()
public:
    ABelmonteTrack();
    static ABelmonteTrack* Spawn(UWorld* World, const FString& Path);
    virtual void Tick(float DeltaSeconds) override;
    int32 NumLightsOn() const { return LightsOn; }

    /** The track's component builders, shared with the saved railway units (UV2MigrationTravel::MigrateRailwayPieces), so a
     *  saved piece or group is built and collides exactly as Initialize builds it. The caller attaches and registers it.
     *  CullCm is track.json's cull_cm. */
    static UStaticMeshComponent* MakePiece(UObject* Outer, USceneComponent* Parent, const TSharedPtr<FJsonObject>& CullCm,
        const TSharedPtr<FJsonObject>& Piece, UStaticMesh* Mesh);
    /** OnlyRows, when set, builds just those rows of the group (indices into its "instances"); null builds every row. */
    static UInstancedStaticMeshComponent* MakeGroup(UObject* Outer, USceneComponent* Parent, const TSharedPtr<FJsonObject>& Group,
        UStaticMesh* Mesh, const TArray<int32>* OnlyRows = nullptr);
    /** A piece is named by its own name; an instanced group by its mesh and key, "SM_TK_Sleeper#17" (its manifest name). */
    static FString GroupName(const TSharedPtr<FJsonObject>& Group);
    /** One row of a group, "SM_TK_BufferStop#@0" for row 0 of the group with key "" (its manifest name, see railway_fittings.py). */
    static FString RowName(const TSharedPtr<FJsonObject>& Group, int32 Row);
    /** The short mesh name of an asset path: "/Game/BelmonteTrack/SM_TK_Chunk_00.SM_TK_Chunk_00" is "SM_TK_Chunk_00". */
    static FString MeshName(const FString& Asset);

private:
    struct FTunnelBox { FTransform Frame; FVector Half; };
    struct FTunnel
    {
        FString Name;
        TArray<FTunnelBox> Zone;
        TArray<TObjectPtr<UPointLightComponent>> Lights;
    };
    bool Initialize(const FString& Path);
    void UpdateLights();
    TArray<FTunnel> Tunnels;
    UPROPERTY() TArray<TObjectPtr<UPrimitiveComponent>> Parts;
    UPROPERTY() TArray<TObjectPtr<UPointLightComponent>> AllLights;
    UPROPERTY() TArray<TObjectPtr<UPostProcessComponent>> Looks;
    double LightRange = 25000.;
    float NextUpdate = 0.f;
    int32 LightsOn = 0;
    FString Inside;
};

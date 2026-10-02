// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include <memory>
#include "SkateRuntimeAsset.generated.h"

namespace atelier::skate { class GameplayResourceSource; }

/** A native package member. Payload never passes through float/string conversion. */
USTRUCT(BlueprintType)
struct ATELIERSKATE_API FSkateRuntimeResourceRecord
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    FString RelativePath;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    FString Sha256;

    UPROPERTY()
    TArray<uint8> Payload;
};

/** Validation accumulates independent failures, including each package member. */
USTRUCT(BlueprintType)
struct ATELIERSKATE_API FSkateRuntimeAssetValidationReport
{
    GENERATED_BODY()

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    bool bValid = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    bool bSaved = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    bool bRoundTripVerified = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    bool bSemanticLoadSucceeded = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    bool bFileAssetEquivalent = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    bool bSnapshotIntegrityVerified = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    bool bChecksumCorruptionRejected = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    bool bSnapshotOutputRetained = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    bool bSnapshotImmutable = false;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    int32 IntegrityChecks = 0;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    int32 IntegrityChecksPassed = 0;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    int32 ComparedTicks = 0;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    FString FileWordSha256;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    FString AssetWordSha256;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    FString AssetPath;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    FString ManifestSha256;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    FString SourceIdentity;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    int32 RecordCount = 0;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    int32 ClipCount = 0;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    int64 PayloadBytes = 0;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    TArray<FString> Issues;
};

/** Sole cooked native resource bundle. No loose-file mount is needed at runtime. */
UCLASS(BlueprintType)
class ATELIERSKATE_API USkateRuntimeAsset final : public UPrimaryDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    int32 Version = 1;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    int32 ExpectedRecordCount = 3334;

    /** Exact source manifest, including its whitespace and byte order. */
    UPROPERTY()
    TArray<uint8> ManifestBytes;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    FString ManifestSha256;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Skate|Runtime")
    FString SourceIdentity;

    /** Lexicographic native paths; order is serialized and checked explicitly. */
    UPROPERTY()
    TArray<FSkateRuntimeResourceRecord> Records;

    /** Game-thread only. Every member is checked even if earlier members fail. */
    FSkateRuntimeAssetValidationReport Validate(bool bCheckDecodedPayloads = true) const;

    /** Game-thread structural checks and an owned copy; checksums run on the
     * native loader thread before decoding. Output is retained on failure. */
    bool CreateSnapshot(std::shared_ptr<const atelier::skate::GameplayResourceSource>& Output,
        FString& Error) const;

#if WITH_EDITOR
    /** Bounded real-session comparison; authoring files are never a runtime fallback. */
    FSkateRuntimeAssetValidationReport ValidateSourceEquivalence(const FString& BundleDirectory,
        int32 TicksPerStance = 120) const;
#endif

    /** Shared editor/runtime helpers; SHA-256 is platform independent. */
    static FString HashPayload(const TArray<uint8>& Bytes);
    static bool IsValidRelativePath(const FString& Path);
    static bool IsSha256(const FString& Value);
private:
    FSkateRuntimeAssetValidationReport ValidateInternal(bool bCheckDecodedPayloads,
        bool bCheckPayloadHashes = true) const;
};

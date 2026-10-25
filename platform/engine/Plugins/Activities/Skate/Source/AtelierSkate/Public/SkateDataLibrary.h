#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "SkateDataLibrary.generated.h"

/** Editor imports and verification of the typed skating data (USkateMotionData, USkateRuntimeData). */
UCLASS()
class ATELIERSKATE_API USkateDataLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Decode the package's rig, clips and metadata banks into named Unreal properties and save the packages. */
    UFUNCTION(BlueprintCallable, Category="Skate Data") static bool ImportMotion(const FString& PackageFolder, const FString& AssetFolder, FString& Error);
    /** @cc [owner:fontanierh,label:correctness] selected-motion-bank-owner
     * ImportMotionBank MUST save only ExpectedPackage, named Bank_%03d for its
     * selected nonnegative BankIndex, using the original ordered 128-clip chunk
     * and typed conversion. Missing/out-of-range source MUST fail before saving;
     * this entry MUST NOT save the index, scan Content or retire other packages.
     */
    UFUNCTION(BlueprintCallable, Category="Skate Data") static bool ImportMotionBank(const FString& PackageFolder, int32 BankIndex, const FString& ExpectedPackage, FString& Error);
    /** @cc [owner:fontanierh,label:correctness] selected-motion-index-owner
     * ImportMotionIndex MUST save only ExpectedPackage named MotionData, with the
     * original schema, rig, metadata and ordered sibling bank references. Every
     * expected bank MUST already exist with its exact source chunk and survive
     * the production decoder/exhaustive comparison before the index is saved.
     * This entry MUST NOT create missing banks, scan Content or retire packages.
     */
    UFUNCTION(BlueprintCallable, Category="Skate Data") static bool ImportMotionIndex(const FString& PackageFolder, const FString& ExpectedPackage, FString& Error);
    /** Decode the package's settings, graphs, camera, gesture and physical skeleton files into named Unreal properties
     * that encode back to the same bytes, and save the package. */
    UFUNCTION(BlueprintCallable, Category="Skate Data") static bool ImportRuntime(const FString& PackageFolder, const FString& AssetFolder, FString& Error);
    /** @cc [owner:fontanierh,label:correctness] in-memory-skate-verification-parity
     * VerifyToJson MUST run the same exhaustive motion/runtime comparison, twelve
     * production replays, negative and malformed-record controls as Verify, and
     * return its complete finite JSON report without writing a file. Failure MUST
     * leave ReportJson empty. Verify MUST use that same implementation before
     * writing the existing report format to its caller's ReportFile.
     */
    UFUNCTION(BlueprintCallable, Category="Skate Data") static bool VerifyToJson(const FString& PackageFolder, FString& ReportJson, FString& Error);
    /** Fresh editor process: loads USkateSettings::MotionData and RuntimeData through the game's loaders, compares them
     * with the package exhaustively, then replays production sessions against sessions loaded from the package. */
    UFUNCTION(BlueprintCallable, Category="Skate Data") static bool Verify(const FString& PackageFolder, const FString& ReportFile, FString& Error);
};

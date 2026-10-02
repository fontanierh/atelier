#include "SkateProfile.h"

#if WITH_EDITOR
#include "Misc/DataValidation.h"
#endif

FString USkateProfile::GetDifficultyPreset() const
{
    switch (Difficulty)
    {
        case ESkateDifficulty::Easy: return TEXT("easy");
        case ESkateDifficulty::Normal: return TEXT("normal");
        case ESkateDifficulty::Hardcore: return TEXT("hardcore");
        default: return FString();
    }
}

bool USkateProfile::ValidateProfile(TArray<FString>& OutErrors) const
{
    OutErrors.Reset();
    if (GetDifficultyPreset().IsEmpty()) OutErrors.Add(TEXT("Difficulty must be Easy, Normal or Hardcore."));
    if (RuntimeData.IsNull() || !RuntimeData.ToSoftObjectPath().IsValid())
        OutErrors.Add(TEXT("Runtime Data must reference a Skate Runtime Asset."));

    auto Range = [&OutErrors](const TCHAR* Name, float Value, float Minimum, float Maximum)
    {
        if (!FMath::IsFinite(Value) || Value < Minimum || Value > Maximum)
            OutErrors.Add(FString::Printf(TEXT("%s must be finite and between %g and %g."), Name, Minimum, Maximum));
    };
    Range(TEXT("Truck Tightness"), TruckTightness, 0.f, 1.f);
    Range(TEXT("Pop Height Scale"), PopHeightScale, .5f, 2.f);
    Range(TEXT("Air Spin Scale"), AirSpinScale, .5f, 3.f);
    Range(TEXT("Push Speed Scale"), PushSpeedScale, .5f, 2.f);
    Range(TEXT("Push Power Scale"), PushPowerScale, .5f, 3.f);
    Range(TEXT("Vert Assist"), VertAssist, 0.f, 1.f);
    Range(TEXT("Collision Scan Period Seconds"), CollisionScanPeriodSeconds, .05f, 5.f);

    TSet<FSoftObjectPath> CollisionPaths;
    for (int32 Index = 0; Index < CollisionDataCatalog.Num(); ++Index)
    {
        const FSoftObjectPath Path = CollisionDataCatalog[Index].ToSoftObjectPath();
        if (!Path.IsValid()) OutErrors.Add(FString::Printf(TEXT("Collision Data Catalog entry %d must reference a Skate Collision Asset."), Index));
        else if (CollisionPaths.Contains(Path)) OutErrors.Add(FString::Printf(TEXT("Collision Data Catalog contains duplicate entry %d."), Index));
        else CollisionPaths.Add(Path);
    }
    auto OptionalPath = [&OutErrors](const TCHAR* Name, const FSoftObjectPath& Path)
    {
        if (!Path.IsNull() && !Path.IsValid()) OutErrors.Add(FString::Printf(TEXT("%s must be a valid asset path or empty."), Name));
    };
    OptionalPath(TEXT("Deck Mesh"), DeckMesh);
    OptionalPath(TEXT("Truck Mesh"), TruckMesh);
    OptionalPath(TEXT("Wheel Mesh"), WheelMesh);
    for (const FSoftObjectPath& Path : FallSounds) OptionalPath(TEXT("Fall Sound"), Path);
    if (!SoundFolder.IsEmpty() && (!SoundFolder.StartsWith(TEXT("/")) || SoundFolder.Contains(TEXT(".."))))
        OutErrors.Add(TEXT("Sound Folder must be an absolute Unreal content folder."));
    return OutErrors.IsEmpty();
}

FSkateProfileValidationReport USkateProfile::ValidateProfileReport() const
{
    FSkateProfileValidationReport Report;
    Report.bValid = ValidateProfile(Report.Issues);
    return Report;
}

#if WITH_EDITOR
EDataValidationResult USkateProfile::IsDataValid(FDataValidationContext& Context) const
{
    const EDataValidationResult ParentResult = Super::IsDataValid(Context);
    TArray<FString> Errors;
    const bool bValid = ValidateProfile(Errors);
    for (const FString& Error : Errors) Context.AddError(FText::FromString(Error));
    return bValid && ParentResult != EDataValidationResult::Invalid ? EDataValidationResult::Valid : EDataValidationResult::Invalid;
}
#endif

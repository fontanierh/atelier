#include "SkateSettings.h"
#include "HAL/IConsoleManager.h"

namespace
{
    TAutoConsoleVariable<FString> CVarSkateBackend(TEXT("skate.Backend"), TEXT(""),
        TEXT("Skating backend for the next mount: Ride or Native (empty: USkateSettings::Backend)"));
}

USkateSettings::USkateSettings() = default;

ESkateBackend USkateSettings::ActiveBackend()
{
    const FString Name = CVarSkateBackend.GetValueOnGameThread().TrimStartAndEnd();
    if (Name.Equals(TEXT("Ride"), ESearchCase::IgnoreCase)) return ESkateBackend::Ride;
    if (Name.Equals(TEXT("Native"), ESearchCase::IgnoreCase)) return ESkateBackend::Native;
    return GetDefault<USkateSettings>()->Backend;
}

#include "AtelierExit.h"
#include "HAL/PlatformMisc.h"
#include <cstdio>
#include <cstdlib>

#if PLATFORM_MAC
namespace
{
int32 ExitStatus = 0;
void PreserveExitStatus()
{
    // Runs after the ordinary engine shutdown. No UObject, delegate or log is accessed here.
    // UE keeps module code loaded at shutdown; packaged code is monolithic.
    if (ExitStatus) { std::fflush(nullptr); std::_Exit(ExitStatus); }
}
}
#endif

void AtelierRequestExit(int32 Status)
{
#if PLATFORM_MAC
    // Register only on failure so an ordinary shutdown still returns zero.
    if (Status && !ExitStatus)
    {
        if (std::atexit(PreserveExitStatus) != 0)
        {
            UE_LOG(LogTemp, Error, TEXT("Could not register the exit status %d"), Status);
            if (GLog) GLog->Flush();
            std::_Exit(Status);
        }
        ExitStatus = Status;
    }
    FPlatformMisc::RequestExit(false);
#else
    FPlatformMisc::RequestExitWithStatus(false, Status);
#endif
}

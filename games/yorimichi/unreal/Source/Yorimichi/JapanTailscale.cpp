#include "JapanNetwork.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformTime.h"
#include "Misc/Paths.h"
#include "Misc/ScopeExit.h"
#include "SocketSubsystem.h"
#include "IPAddress.h"

namespace
{
FString TailscaleExecutable()
{
    TArray<FString> Candidates;
#if PLATFORM_MAC
    Candidates.Add(TEXT("/Applications/Tailscale.app/Contents/MacOS/Tailscale"));
    Candidates.Add(TEXT("/opt/homebrew/bin/tailscale"));
    Candidates.Add(TEXT("/usr/local/bin/tailscale"));
#elif PLATFORM_WINDOWS
    const FString ProgramFiles = FPlatformMisc::GetEnvironmentVariable(TEXT("ProgramFiles"));
    if (!ProgramFiles.IsEmpty()) Candidates.Add(ProgramFiles / TEXT("Tailscale/tailscale.exe"));
#else
    Candidates.Add(TEXT("/usr/bin/tailscale"));
    Candidates.Add(TEXT("/usr/local/bin/tailscale"));
#endif
    const FString Path = FPlatformMisc::GetEnvironmentVariable(TEXT("PATH"));
    TArray<FString> Directories;
#if PLATFORM_WINDOWS
    Path.ParseIntoArray(Directories, TEXT(";"));
    const TCHAR* Binary = TEXT("tailscale.exe");
#else
    Path.ParseIntoArray(Directories, TEXT(":"));
    const TCHAR* Binary = TEXT("tailscale");
#endif
    for (const FString& Directory : Directories)
        if (!FPaths::IsRelative(Directory)) Candidates.AddUnique(Directory / Binary);
    for (const FString& Candidate : Candidates)
        if (IFileManager::Get().FileExists(*Candidate)) return Candidate;
    return FString();
}

bool ReadTailscaleIPv4(FString& Address)
{
    const FString Executable = TailscaleExecutable();
    if (Executable.IsEmpty()) return false;
    void* Read = nullptr;
    void* Write = nullptr;
    if (!FPlatformProcess::CreatePipe(Read, Write)) return false;
    ON_SCOPE_EXIT { FPlatformProcess::ClosePipe(Read, Write); };
    // Fixed argv, no shell. Capture only `ip -4`, never status/account/credential data.
    FString Program = Executable, Arguments = TEXT("ip -4");
#if PLATFORM_MAC
    if (Executable == TEXT("/Applications/Tailscale.app/Contents/MacOS/Tailscale"))
    {
        // The app binary can otherwise start its GUI from a non-terminal process.
        // env execs the CLI in this same owned child; the game's environment is untouched.
        Program = TEXT("/usr/bin/env");
        Arguments = TEXT("TAILSCALE_BE_CLI=1 /Applications/Tailscale.app/Contents/MacOS/Tailscale ip -4");
    }
#endif
    FProcHandle Process = FPlatformProcess::CreateProc(*Program, *Arguments, false, true, true,
        nullptr, 0, nullptr, Write, nullptr, Write);
    if (!Process.IsValid()) return false;
    ON_SCOPE_EXIT
    {
        if (FPlatformProcess::IsProcRunning(Process)) FPlatformProcess::TerminateProc(Process);
        FPlatformProcess::CloseProc(Process);
    };
    const double Deadline = FPlatformTime::Seconds() + 2.;
    FString Output;
    while (FPlatformProcess::IsProcRunning(Process))
    {
        Output += FPlatformProcess::ReadPipe(Read);
        if (FPlatformTime::Seconds() >= Deadline || Output.Len() > 4096) return false;
        FPlatformProcess::Sleep(.01f);
    }
    Output += FPlatformProcess::ReadPipe(Read);
    int32 Code = -1;
    if (!FPlatformProcess::GetProcReturnCode(Process, &Code) || Code != 0 || Output.Len() > 4096) return false;
    Address = Output.TrimStartAndEnd();
    return JapanNetwork::IsTailnetIPv4(Address);
}
}

bool JapanNetwork::PrivateHostAddress(FString& Address, FString& Error)
{
    Address.Reset(); Error.Reset();
    // Host preflight and the immediately following driver init share this short cache;
    // the actual adapter is still checked every time. Never accept carrier-NAT range alone.
    static FString Verified;
    static double VerifiedAt = -10.;
    const double Now = FPlatformTime::Seconds();
    if (Verified.IsEmpty() || Now - VerifiedAt > 5.)
    {
        Verified.Reset();
        if (!ReadTailscaleIPv4(Verified))
        { Error = TEXT("Start Tailscale and connect it before hosting. The game could not verify its private address."); return false; }
        VerifiedAt = FPlatformTime::Seconds();
    }
    ISocketSubsystem* Sockets = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
    TArray<TSharedPtr<FInternetAddr>> Addresses;
    if (Sockets && Sockets->GetLocalAdapterAddresses(Addresses))
        for (const auto& Candidate : Addresses)
            if (Candidate.IsValid() && Candidate->ToString(false) == Verified)
            { Address = Verified; return true; }
    Verified.Reset();
    Error = TEXT("Tailscale has no matching local network adapter. Reconnect Tailscale and try hosting again.");
    return false;
}

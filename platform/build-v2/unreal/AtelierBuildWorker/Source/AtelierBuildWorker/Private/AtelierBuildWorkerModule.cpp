#include "Modules/ModuleManager.h"
#include "HAL/IPlatformFileOpenLogWrapper.h"
#include "HAL/PlatformFileManager.h"
#include "Misc/ScopeLock.h"

namespace
{
    // Reuse UE's existing synchronized open map. Install once, never at job boundaries.
    class FJobReadLog final : public FPlatformFileOpenLog
    {
    public:
        virtual bool Initialize(IPlatformFile* Inner, const TCHAR*) override
        {
            SetLowerLevel(Inner);
            return Inner != nullptr;
        }
        virtual const TCHAR* GetName() const override { return TEXT("AtelierJobReadLog"); }
        virtual IAsyncReadFileHandle* OpenAsyncRead(const TCHAR* Filename, bool bAllowWrite = false) override
        {
            AddToOpenLog(Filename);
            return GetLowerLevel()->OpenAsyncRead(Filename, bAllowWrite);
        }
        virtual FOpenMappedResult OpenMappedEx(const TCHAR* Filename, EOpenReadFlags Flags = EOpenReadFlags::None, int64 Size = 0) override
        {
            AddToOpenLog(Filename);
            return GetLowerLevel()->OpenMappedEx(Filename, Flags, Size);
        }
        virtual FOpenMappedResult OpenMappedEx2(const TCHAR* Filename, EOpenMappedFlags Flags = EOpenMappedFlags::None, int64 Size = 0) override
        {
            AddToOpenLog(Filename);
            return GetLowerLevel()->OpenMappedEx2(Filename, Flags, Size);
        }
        void Begin()
        {
            FScopeLock Lock(&CriticalSection);
            FilenameAccessMap.Reset();
        }
        TArray<FString> End()
        {
            FScopeLock Lock(&CriticalSection);
            TArray<FString> Files;
            FilenameAccessMap.GenerateKeyArray(Files);
            FilenameAccessMap.Reset();
            for (FString& File : Files)
            {
                File = FPaths::ConvertRelativePathToFull(File);
                FPaths::NormalizeFilename(File);
                FPaths::CollapseRelativeDirectories(File);
            }
            Files.Sort();
            return Files;
        }
    };
    FJobReadLog* GReadLog = nullptr;
}

bool BeginAtelierReadRecording()
{
    if (!GReadLog || FPlatformFileManager::Get().FindPlatformFile(GReadLog->GetName()) != GReadLog)
    {
        return false;
    }
    GReadLog->Begin();
    return true;
}

TArray<FString> EndAtelierReadRecording()
{
    return GReadLog ? GReadLog->End() : TArray<FString>();
}

class FAtelierBuildWorkerModule final : public IModuleInterface
{
public:
    virtual void StartupModule() override
    {
        GReadLog = new FJobReadLog;
        GReadLog->Initialize(&FPlatformFileManager::Get().GetPlatformFile(), TEXT(""));
        FPlatformFileManager::Get().SetPlatformFile(*GReadLog);
    }
    virtual bool SupportsDynamicReloading() override { return false; }
    // Keep the wrapper alive until exit: async handles may outlive module shutdown.
};
IMPLEMENT_MODULE(FAtelierBuildWorkerModule, AtelierBuildWorker)

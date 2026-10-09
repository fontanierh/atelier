#include "SkatePadReader.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformTime.h"
#include "HAL/RunnableThread.h"

#if PLATFORM_MAC
// Unreal compiles C++ as Objective-C++ on Apple platforms; the engine imports GameController the same way.
#include "Mac/MacSystemIncludes.h"
#include <GameController/GameController.h>
#endif

namespace
{
#if PLATFORM_MAC
    /** The current controller's sticks, or false with no extended gamepad. Everything Objective-C stays inside the
     *  pool, so the reader holds no object between polls (manual or automatic reference counting alike). */
    bool PollPad(FSkatePadReading& Out)
    {
        bool bRead = false;
        @autoreleasepool
        {
            GCExtendedGamepad* Pad = GCController.current ? GCController.current.extendedGamepad : nil;
            if (!Pad)
                for (GCController* Any in [GCController controllers])
                    if (Any.extendedGamepad) { Pad = Any.extendedGamepad; break; }
            if (Pad)
            {
                Out.LeftX = Pad.leftThumbstick.xAxis.value; Out.LeftY = Pad.leftThumbstick.yAxis.value;
                Out.RightX = Pad.rightThumbstick.xAxis.value; Out.RightY = Pad.rightThumbstick.yAxis.value;
                bRead = true;
            }
        }
        Out.Time = FPlatformTime::Seconds();
        return bRead;
    }
    constexpr bool bHasReader = true;
#else
    bool PollPad(FSkatePadReading&) { return false; }
    constexpr bool bHasReader = false;
#endif
    TWeakPtr<FSkatePadReader> Shared;
}

TSharedPtr<FSkatePadReader> FSkatePadReader::Acquire()
{
    check(IsInGameThread());
    if (TSharedPtr<FSkatePadReader> Existing = Shared.Pin()) return Existing;
    if (!bHasReader) return nullptr;
    TSharedPtr<FSkatePadReader> Reader(new FSkatePadReader());
    Reader->Ring.SetNum(Capacity);
    Reader->Thread = FRunnableThread::Create(Reader.Get(), TEXT("AtelierSkatePad"), 64 * 1024, TPri_AboveNormal);
    if (!Reader->Thread) return nullptr;
    Shared = Reader;
    return Reader;
}

FSkatePadReader::~FSkatePadReader()
{
    if (Thread) { Thread->Kill(true); delete Thread; }
}

uint32 FSkatePadReader::Run()
{
    while (!bStopping.load())
    {
        FSkatePadReading Reading;
        if (PollPad(Reading))
        {
            FScopeLock Scope(&Lock);
            Ring[Next] = Reading; Next = (Next + 1) % Capacity; Count = FMath::Min(Count + 1, Capacity);
        }
        FPlatformProcess::SleepNoStats(.001f);
    }
    return 0;
}

void FSkatePadReader::Read(double Since, TArray<FSkatePadReading>& Out) const
{
    Out.Reset();
    FScopeLock Scope(&Lock);
    const int32 First = (Next - Count + Capacity) % Capacity;
    for (int32 I = 0; I < Count; ++I)
    {
        const FSkatePadReading& Reading = Ring[(First + I) % Capacity];
        // The newest reading at or before Since stands for the stick at Since; it replaces any older one.
        if (Reading.Time <= Since && Out.Num() == 1) Out[0] = Reading;
        else Out.Add(Reading);
    }
}

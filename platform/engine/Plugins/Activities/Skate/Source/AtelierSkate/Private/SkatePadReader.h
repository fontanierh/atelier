#pragma once
// The player's controller sticks read off the game thread, for the 120 Hz flick reading (FSkateFeel::Flick120Hz). A
// thread polls the game controller every millisecond and keeps the last half second, timestamped with
// FPlatformTime::Seconds. On macOS it reads the GameController framework's current controller: the raw values Unreal's
// Apple controller interface reads once a frame, before the engine's dead zone. Other platforms have no reader
// (Acquire returns null) and the 120 Hz reading reads each frame's sticks instead.
#include "CoreMinimal.h"
#include "HAL/CriticalSection.h"
#include "HAL/Runnable.h"
#include <atomic>

struct FSkatePadReading
{
    double Time = 0;
    float LeftX = 0, LeftY = 0, RightX = 0, RightY = 0;   // GameController's axes: -1..1, up positive
};

class FSkatePadReader final : public FRunnable
{
public:
    /** The shared reader, started by the first rider that asks; it stops when the last reference goes. Null where the
     *  platform has no reader or its thread cannot start. Game thread. */
    static TSharedPtr<FSkatePadReader> Acquire();
    virtual ~FSkatePadReader() override;

    /** The readings after Since, oldest first, preceded by the last one at or before it (the stick held then). */
    void Read(double Since, TArray<FSkatePadReading>& Out) const;

    virtual uint32 Run() override;
    virtual void Stop() override { bStopping.store(true); }

private:
    FSkatePadReader() = default;
    static constexpr int32 Capacity = 512;   // half a second at 1 kHz
    mutable FCriticalSection Lock;
    TArray<FSkatePadReading> Ring;           // Capacity slots; Next is the oldest once full
    int32 Next = 0, Count = 0;
    std::atomic<bool> bStopping{false};
    class FRunnableThread* Thread = nullptr;
};

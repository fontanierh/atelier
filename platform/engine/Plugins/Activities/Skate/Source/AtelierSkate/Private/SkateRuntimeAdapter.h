#pragma once
#include "CoreMinimal.h"
#include "Simulation/GameplayRuntime.h"
#include <future>
#include <memory>
#include <string>
class USkateRuntimeData;

struct FSkateRuntimeLoad
{
    std::shared_ptr<const atelier::skate::RuntimePayloads> Payloads;
    std::string Error;
};
using FSkateRuntimeFuture = std::shared_future<FSkateRuntimeLoad>;

// Game thread, never blocks: starts the asynchronous package load of Path once per process, then encodes it on a task
// thread while the package is held. The encoded files are kept for later sessions; a failure is forgotten, so the next
// request retries.
FSkateRuntimeFuture RequestSkateRuntime(const FSoftObjectPath& Path);
// Game thread: finishes loading Path's package now and starts its encode, for a caller about to wait on the result
// without ticking.
void CompleteSkateRuntime(const FSoftObjectPath& Path);
// Any thread, while the caller keeps Data loaded: the runtime files, each checked against its recorded size and SHA-1.
bool EncodeSkateRuntime(const USkateRuntimeData& Data, atelier::skate::RuntimePayloads& Out, std::string& Error);

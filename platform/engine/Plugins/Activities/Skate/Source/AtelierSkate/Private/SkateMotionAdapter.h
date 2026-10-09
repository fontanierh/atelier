#pragma once
#include "CoreMinimal.h"
#include <future>
#include <memory>
#include <string>
namespace atelier::skate { struct AnimationSource; }
class USkateMotionData;
class USkateMotionBank;
struct FStreamableManager;

struct FSkateMotionLoad
{
    std::shared_ptr<const atelier::skate::AnimationSource> Source;
    std::string Error;
};
using FSkateMotionFuture = std::shared_future<FSkateMotionLoad>;

// The streamable manager the typed skating data loads through.
FStreamableManager& SkateStreamer();
// Game thread, never blocks: starts the asynchronous package load of Path once per process, then decodes it on a task
// thread while the packages are held. The decoded immutable source is kept for later sessions and the packages are
// released; a failure is forgotten, so the next request retries.
FSkateMotionFuture RequestSkateMotion(const FSoftObjectPath& Path);
// Game thread: finishes loading Path's packages now and starts its decode, for a caller about to wait on the result
// without ticking (the async load's completion runs on the game thread).
void CompleteSkateMotion(const FSoftObjectPath& Path);
// Any thread, while the caller keeps Data and Banks loaded: copies typed fields into native animation structures.
bool DecodeSkateMotion(const USkateMotionData& Data, TConstArrayView<const USkateMotionBank*> Banks,
    std::shared_ptr<const atelier::skate::AnimationSource>& Out, std::string& Error);

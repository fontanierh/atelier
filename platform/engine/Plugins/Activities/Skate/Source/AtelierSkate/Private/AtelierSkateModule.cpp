#include "Modules/ModuleManager.h"
#include "UObject/UObjectGlobals.h"

namespace SkateRuntimeDetail
{
    void PruneMeshSurfaceCache();
    void ClearMeshSurfaceCache();
}

class FAtelierSkateModule final : public FDefaultModuleImpl
{
public:
    void StartupModule() override
    {
        PostGC=FCoreUObjectDelegates::GetPostGarbageCollect().AddStatic(&SkateRuntimeDetail::PruneMeshSurfaceCache);
    }

    void ShutdownModule() override
    {
        FCoreUObjectDelegates::GetPostGarbageCollect().Remove(PostGC);
        SkateRuntimeDetail::ClearMeshSurfaceCache();
    }

private:
    FDelegateHandle PostGC;
};

IMPLEMENT_MODULE(FAtelierSkateModule, AtelierSkate)

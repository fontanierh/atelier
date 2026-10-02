#include "Modules/ModuleManager.h"
#include "SkateCookedProbe.h"

class FAtelierSkateModule final : public IModuleInterface
{
public:
    void StartupModule() override { RegisterSkateCookedProbe(); }
    void ShutdownModule() override { UnregisterSkateCookedProbe(); }
};
IMPLEMENT_MODULE(FAtelierSkateModule, AtelierSkate)

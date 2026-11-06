#include "Modules/ModuleManager.h"
#include "V2SaveGuard.h"

/** The editor-only authoring module; it installs the V2 save guard when a write route asks for it. */
class FYorimichiImportModule : public IModuleInterface
{
public:
    virtual void StartupModule() override { UV2SaveGuard::Startup(); }
    virtual void ShutdownModule() override { UV2SaveGuard::Shutdown(); }
};

IMPLEMENT_MODULE(FYorimichiImportModule, YorimichiImport)

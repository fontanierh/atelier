#include "MegaParkLayout.h"
#include "Components/SceneComponent.h"

AMegaParkLayout::AMegaParkLayout()
{
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    RootComponent->SetMobility(EComponentMobility::Static);
}

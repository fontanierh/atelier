#pragma once
#include "CoreMinimal.h"
class UJapanMap;
class SWidget;
TSharedRef<SWidget> MakeJapanAtlasWidget(UJapanMap* Map);
FString JapanAtlasControllerSnapshot(const TSharedRef<SWidget>& Widget);

#pragma once
#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "GlassImpactDataAsset.generated.h"

/** Assign a content-relative directory containing the converter's metadata and binary fields. */
UCLASS(BlueprintType)
class GLASSIMPACTRUNTIME_API UGlassImpactDataAsset : public UDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Glass Impact")
    FString DataDirectory = TEXT("GlassImpactData");
};

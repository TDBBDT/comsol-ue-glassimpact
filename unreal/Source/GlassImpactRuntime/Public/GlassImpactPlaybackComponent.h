#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "GlassImpactPlaybackComponent.generated.h"

class UGlassImpactDataAsset;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class UMeshComponent;
class UTexture2D;
class UNiagaraSystem;
class USoundBase;
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FGlassImpactEvent);

/** Fixed-topology playback only. Fields remain in physical units through one global affine decode. */
UCLASS(ClassGroup=(GlassImpact), meta=(BlueprintSpawnableComponent))
class GLASSIMPACTRUNTIME_API UGlassImpactPlaybackComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    UGlassImpactPlaybackComponent();
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Data") TObjectPtr<UGlassImpactDataAsset> DataAsset;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Data") FString DataDirectory = TEXT("GlassImpactData");
    UPROPERTY(BlueprintReadOnly, Category="Playback") float Duration = 0.02f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Playback", meta=(ClampMin="0.0001")) float PlaybackRate = 0.005f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Material", meta=(ClampMin="0", ClampMax="1")) float DamageThreshold = 0.35f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Material") float CrackWhiteningStrength = 0.9f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Material") float RefractionStrength = 0.25f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Material") float CrackIntensity = 1.0f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Material", meta=(ClampMin="0")) float DisplacementScale = 1.0f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Effects", meta=(ClampMin="0", ClampMax="1")) float ParticleTriggerThreshold = 0.7f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Effects") TObjectPtr<UNiagaraSystem> ImpactParticles;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Effects") TObjectPtr<USoundBase> ImpactSound;
    UPROPERTY(BlueprintReadOnly, Category="Playback") float CurrentTime = 0.0f;
    UPROPERTY(BlueprintReadOnly, Category="Playback") float CurrentMaxDamage = 0.0f;
    UPROPERTY(BlueprintReadOnly, Category="Playback") bool bPlaying = false;
    UPROPERTY(BlueprintReadOnly, Category="Playback") bool bLoaded = false;
    UPROPERTY(BlueprintReadOnly, Category="Playback") FString SourceKind = TEXT("NO DATA");
    UPROPERTY(BlueprintReadOnly, Category="Playback") FString LastError;
    UPROPERTY(BlueprintAssignable) FGlassImpactEvent OnImpact;
    UPROPERTY(BlueprintAssignable) FGlassImpactEvent OnCrackGrowth;
    UPROPERTY(BlueprintAssignable) FGlassImpactEvent OnParticleThreshold;
    UPROPERTY(BlueprintAssignable) FGlassImpactEvent OnFinished;
    UFUNCTION(BlueprintCallable) bool LoadData();
    UFUNCTION(BlueprintCallable) void BindMesh(UMeshComponent* Mesh, UMaterialInterface* Material);
    UFUNCTION(BlueprintCallable) void Play();
    UFUNCTION(BlueprintCallable) void Pause();
    UFUNCTION(BlueprintCallable) void Reset();
    /** Scrub is a preview operation; it does not emit particle/audio/gameplay events. */
    UFUNCTION(BlueprintCallable) void Seek(float Seconds);
    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
private:
    FString ResolvedDirectory, StatePath, DisplacementPath;
    int32 Width = 0, Height = 0, LoadedFrame = INDEX_NONE;
    TArray<double> Times, MaxDamage;
    FVector DisplacementMinCm = FVector::ZeroVector, DisplacementSpanCm = FVector::ZeroVector;
    FVector2D ImpactUV = FVector2D(0.5, 0.5), PlateSizeCm = FVector2D(100, 100);
    bool bImpactSent = false, bGrowthSent = false, bParticlesSent = false, bFinishedSent = false;
    UPROPERTY(Transient) TObjectPtr<UMaterialInstanceDynamic> DynamicMaterial;
    UPROPERTY(Transient) TObjectPtr<UTexture2D> StateA;
    UPROPERTY(Transient) TObjectPtr<UTexture2D> StateB;
    UPROPERTY(Transient) TObjectPtr<UTexture2D> DispA;
    UPROPERTY(Transient) TObjectPtr<UTexture2D> DispB;
    bool Fail(const FString& Message);
    bool UploadFrame(const FString& Filename, int32 Frame, UTexture2D* Texture);
    void UpdateFrame();
    void ApplyParameters(float Alpha);
};

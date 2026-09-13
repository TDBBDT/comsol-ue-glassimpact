#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GameFramework/HUD.h"
#include "GameFramework/GameModeBase.h"
#include "GlassImpactDemoActor.generated.h"
class UProceduralMeshComponent;
class UGlassImpactPlaybackComponent;
class UCameraComponent;
class UMaterialInterface;

UCLASS()
class GLASSIMPACTRUNTIME_API AGlassImpactDemoActor : public AActor
{
    GENERATED_BODY()
public:
    AGlassImpactDemoActor();
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<UProceduralMeshComponent> GlassMesh;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<UProceduralMeshComponent> FrameMesh;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<UProceduralMeshComponent> GasketMesh;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<UProceduralMeshComponent> TrimMesh;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly) TObjectPtr<UGlassImpactPlaybackComponent> Playback;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) TObjectPtr<UMaterialInterface> GlassMaterial;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) TObjectPtr<UMaterialInterface> WireMaterial;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) TObjectPtr<UMaterialInterface> FrameMaterial;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) TObjectPtr<UMaterialInterface> GasketMaterial;
    UPROPERTY(EditAnywhere, BlueprintReadWrite) TObjectPtr<UMaterialInterface> TrimMaterial;
    UPROPERTY(BlueprintReadOnly) bool bWireframe = false;
    UPROPERTY(BlueprintReadOnly) FString ViewName = TEXT("OBLIQUE");
    UFUNCTION(BlueprintCallable) void TogglePlayback();
    UFUNCTION(BlueprintCallable) void ResetPlayback();
    UFUNCTION(BlueprintCallable) void ToggleWireframe();
    UFUNCTION(BlueprintCallable) void CameraOblique();
    UFUNCTION(BlueprintCallable) void CameraFront();
    UFUNCTION(BlueprintCallable) void CameraSide();
    UFUNCTION(BlueprintCallable) void Faster();
    UFUNCTION(BlueprintCallable) void Slower();
    UFUNCTION(BlueprintCallable) void ToggleDisplacementScale();
    virtual void OnConstruction(const FTransform& Transform) override;
    virtual void Tick(float DeltaTime) override;
protected:
    virtual void BeginPlay() override;
private:
    UPROPERTY() TObjectPtr<AActor> ViewCamera;
    void BuildPlate();
    void BuildFixture();
    void SetCamera(const FVector& Offset, const FString& Name);
    int32 CaptureFrames = 0;
    FString CapturePath;
};

UCLASS()
class GLASSIMPACTRUNTIME_API AGlassImpactHUD : public AHUD
{
    GENERATED_BODY()
public: virtual void DrawHUD() override;
};

UCLASS()
class GLASSIMPACTRUNTIME_API AGlassImpactGameMode : public AGameModeBase
{
    GENERATED_BODY()
public: AGlassImpactGameMode();
};

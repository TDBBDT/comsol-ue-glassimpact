#include "GlassImpactPlaybackComponent.h"
#include "GlassImpactDataAsset.h"
#include "Components/MeshComponent.h"
#include "Engine/Texture2D.h"
#include "HAL/PlatformFileManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Dom/JsonObject.h"
#include "Kismet/GameplayStatics.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"
#include "Sound/SoundBase.h"

UGlassImpactPlaybackComponent::UGlassImpactPlaybackComponent() { PrimaryComponentTick.bCanEverTick = true; }
bool UGlassImpactPlaybackComponent::Fail(const FString& Message)
{
    LastError = Message; bLoaded = false; bPlaying = false;
    UE_LOG(LogTemp, Error, TEXT("GlassImpact: %s"), *Message); return false;
}
bool UGlassImpactPlaybackComponent::LoadData()
{
    Pause(); bLoaded = false; LastError.Reset(); LoadedFrame = INDEX_NONE;
    const FString Dir = DataAsset ? DataAsset->DataDirectory : DataDirectory;
    ResolvedDirectory = FPaths::IsRelative(Dir) ? FPaths::Combine(FPaths::ProjectContentDir(), Dir) : Dir;
    FString Text;
    if (!FFileHelper::LoadFileToString(Text, *FPaths::Combine(ResolvedDirectory, TEXT("metadata.json")))) return Fail(TEXT("Cannot read metadata.json in ") + ResolvedDirectory);
    TSharedPtr<FJsonObject> Json;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Json) || !Json.IsValid()) return Fail(TEXT("Invalid metadata JSON"));
    double Version = 0, Count = 0, DeclaredDuration = 0;
    FString DType, ByteOrder, Mapping, Units, StateFile, DispFile;
    if (!Json->TryGetNumberField(TEXT("version"), Version) || Version != 1 ||
        !Json->TryGetNumberField(TEXT("frame_count"), Count) || Count < 2 || Count > 4096 || Count != FMath::FloorToDouble(Count) ||
        !Json->TryGetNumberField(TEXT("duration_seconds"), DeclaredDuration) ||
        !Json->TryGetStringField(TEXT("dtype"), DType) || DType != TEXT("float16") ||
        !Json->TryGetStringField(TEXT("byte_order"), ByteOrder) || ByteOrder != TEXT("little") ||
        !Json->TryGetStringField(TEXT("coordinate_mapping"), Mapping) || Mapping != TEXT("plate_local_xy_to_ue_local_xy_m_to_cm") ||
        !Json->TryGetStringField(TEXT("source_units"), Units) || Units != TEXT("SI") ||
        !Json->TryGetStringField(TEXT("source_kind"), SourceKind) || (SourceKind != TEXT("synthetic") && SourceKind != TEXT("comsol")) ||
        !Json->TryGetStringField(TEXT("state_file"), StateFile) ||
        !Json->TryGetStringField(TEXT("displacement_file"), DispFile)) return Fail(TEXT("Unsupported or incomplete metadata contract"));
    auto ReadNumbers = [&Json](const TCHAR* Key, TArray<double>& Out, int32 Expected)->bool
    {
        const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
        if (!Json->TryGetArrayField(Key, Values) || Values->Num() != Expected) return false;
        Out.Reset(); for (const auto& V : *Values) { double N; if (!V->TryGetNumber(N) || !FMath::IsFinite(N)) return false; Out.Add(N); } return true;
    };
    TArray<double> Resolution, Minimum, Maximum, Impact, Size;
    if (!ReadNumbers(TEXT("texture_resolution"), Resolution, 2) || !ReadNumbers(TEXT("times_seconds"), Times, int32(Count)) ||
        !ReadNumbers(TEXT("max_damage_per_frame"), MaxDamage, int32(Count)) || !ReadNumbers(TEXT("displacement_min_m"), Minimum, 3) ||
        !ReadNumbers(TEXT("displacement_max_m"), Maximum, 3) || !ReadNumbers(TEXT("impact_uv"), Impact, 2) || !ReadNumbers(TEXT("plate_size_m"), Size, 2)) return Fail(TEXT("Missing, nonfinite, or inconsistent metadata arrays"));
    Width = int32(Resolution[0]); Height = int32(Resolution[1]);
    if (Width < 2 || Height < 2 || Width > 4096 || Height > 4096 || Width != Resolution[0] || Height != Resolution[1]) return Fail(TEXT("Invalid texture dimensions"));
    if (FMath::Abs(Times[0]) > 1e-9 || Times.Last() <= 0 || FMath::Abs(DeclaredDuration - Times.Last()) > 1e-7) return Fail(TEXT("Timeline must start at zero and match duration"));
    for (int32 I=0; I<Times.Num(); ++I)
    {
        if ((I && Times[I] <= Times[I-1]) || MaxDamage[I] < 0 || MaxDamage[I] > 1 || (I && MaxDamage[I] + 1e-6 < MaxDamage[I-1])) return Fail(TEXT("Timeline/damage is invalid or heals"));
    }
    for (int32 I=0; I<3; ++I) if (Maximum[I] < Minimum[I]) return Fail(TEXT("Inverted displacement range"));
    if (FMath::Abs(Size[0]-1) > 1e-6 || FMath::Abs(Size[1]-1) > 1e-6) return Fail(TEXT("MVP demo requires the 1 m by 1 m plate"));
    for (double V : Impact) if (V < 0 || V > 1) return Fail(TEXT("Impact UV outside plate"));
    // Only simple relative filenames may be supplied by the metadata document.
    if (FPaths::GetCleanFilename(StateFile) != StateFile || FPaths::GetCleanFilename(DispFile) != DispFile || StateFile.Contains(TEXT(":")) || DispFile.Contains(TEXT(":"))) return Fail(TEXT("Field filenames must not escape data directory"));
    StatePath = FPaths::Combine(ResolvedDirectory, StateFile); DisplacementPath = FPaths::Combine(ResolvedDirectory, DispFile);
    const int64 ExpectedBytes = int64(Count) * Width * Height * 8;
    auto& PF = FPlatformFileManager::Get().GetPlatformFile();
    if (PF.FileSize(*StatePath) != ExpectedBytes || PF.FileSize(*DisplacementPath) != ExpectedBytes) return Fail(TEXT("Binary field size does not match frame dimensions"));
    DisplacementMinCm = FVector(Minimum[0], Minimum[1], Minimum[2]) * 100;
    DisplacementSpanCm = FVector(Maximum[0]-Minimum[0], Maximum[1]-Minimum[1], Maximum[2]-Minimum[2]) * 100;
    ImpactUV = FVector2D(Impact[0], Impact[1]); PlateSizeCm = FVector2D(Size[0], Size[1]) * 100;
    Duration = float(Times.Last());
    auto CreateTexture = [this]()
    {
        UTexture2D* T = UTexture2D::CreateTransient(Width, Height, PF_FloatRGBA);
        if (T) { T->SRGB = false; T->NeverStream = true; T->Filter = TF_Bilinear; T->AddressX = TA_Clamp; T->AddressY = TA_Clamp; T->UpdateResource(); }
        return T;
    };
    StateA = CreateTexture(); StateB = CreateTexture(); DispA = CreateTexture(); DispB = CreateTexture();
    if (!StateA || !StateB || !DispA || !DispB) return Fail(TEXT("Failed to allocate float16 textures"));
    bLoaded = true; Reset();
    if (!bLoaded) return false;
    UE_LOG(LogTemp, Display, TEXT("GLASS_DATA_LOADED source=%s frames=%d resolution=%dx%d duration=%g"), *SourceKind, Times.Num(), Width, Height, Duration);
    return bLoaded;
}
bool UGlassImpactPlaybackComponent::UploadFrame(const FString& Filename, int32 Frame, UTexture2D* Texture)
{
    TUniquePtr<IFileHandle> File(FPlatformFileManager::Get().GetPlatformFile().OpenRead(*Filename));
    const int64 Bytes = int64(Width) * Height * 8;
    if (!File || !File->Seek(Bytes * Frame)) return Fail(TEXT("Cannot seek field frame"));
    uint8* Buffer = new uint8[Bytes];
    if (!File->Read(Buffer, Bytes)) { delete[] Buffer; return Fail(TEXT("Truncated field frame")); }
    FUpdateTextureRegion2D* Region = new FUpdateTextureRegion2D(0, 0, 0, 0, Width, Height);
    Texture->UpdateTextureRegions(0, 1, Region, Width * 8, 8, Buffer,
        [](uint8* Data, const FUpdateTextureRegion2D* R) { delete[] Data; delete R; });
    return true;
}
void UGlassImpactPlaybackComponent::BindMesh(UMeshComponent* Mesh, UMaterialInterface* Material)
{
    if (!Mesh || !Material) return;
    DynamicMaterial = UMaterialInstanceDynamic::Create(Material, this); Mesh->SetMaterial(0, DynamicMaterial);
    if (bLoaded) UpdateFrame();
}
void UGlassImpactPlaybackComponent::ApplyParameters(float Alpha)
{
    if (!DynamicMaterial) return;
    DynamicMaterial->SetTextureParameterValue(TEXT("StateA"), StateA); DynamicMaterial->SetTextureParameterValue(TEXT("StateB"), StateB);
    DynamicMaterial->SetTextureParameterValue(TEXT("DispA"), DispA); DynamicMaterial->SetTextureParameterValue(TEXT("DispB"), DispB);
    DynamicMaterial->SetScalarParameterValue(TEXT("FrameAlpha"), Alpha);
    DynamicMaterial->SetScalarParameterValue(TEXT("DamageThreshold"), FMath::Clamp(DamageThreshold, 0.f, 1.f));
    DynamicMaterial->SetScalarParameterValue(TEXT("CrackWhiteningStrength"), CrackWhiteningStrength);
    DynamicMaterial->SetScalarParameterValue(TEXT("RefractionStrength"), RefractionStrength);
    DynamicMaterial->SetScalarParameterValue(TEXT("CrackIntensity"), CrackIntensity);
    DynamicMaterial->SetScalarParameterValue(TEXT("DisplacementScale"), DisplacementScale);
    DynamicMaterial->SetVectorParameterValue(TEXT("DisplacementMin"), FLinearColor(DisplacementMinCm.X, DisplacementMinCm.Y, DisplacementMinCm.Z));
    DynamicMaterial->SetVectorParameterValue(TEXT("DisplacementSpan"), FLinearColor(DisplacementSpanCm.X, DisplacementSpanCm.Y, DisplacementSpanCm.Z));
    DynamicMaterial->SetVectorParameterValue(TEXT("TexelSize"), FLinearColor(1.f/Width, 1.f/Height, 0, 0));
}
void UGlassImpactPlaybackComponent::UpdateFrame()
{
    if (!bLoaded) return;
    int32 Frame = 0; while (Frame < Times.Num()-2 && CurrentTime >= Times[Frame+1]) ++Frame;
    if (LoadedFrame != Frame)
    {
        if (!UploadFrame(StatePath, Frame, StateA) || !UploadFrame(StatePath, Frame+1, StateB) ||
            !UploadFrame(DisplacementPath, Frame, DispA) || !UploadFrame(DisplacementPath, Frame+1, DispB)) return;
        LoadedFrame = Frame;
    }
    const float Alpha = FMath::Clamp(float((CurrentTime-Times[Frame])/(Times[Frame+1]-Times[Frame])), 0.f, 1.f);
    CurrentMaxDamage = FMath::Lerp(float(MaxDamage[Frame]), float(MaxDamage[Frame+1]), Alpha);
    ApplyParameters(Alpha);
}
void UGlassImpactPlaybackComponent::Play()
{
    if (!bLoaded && !LoadData()) return;
    if (CurrentTime >= Duration) Reset();
    bPlaying = true;
    if (!bImpactSent) { bImpactSent = true; OnImpact.Broadcast(); }
}
void UGlassImpactPlaybackComponent::Pause() { bPlaying = false; }
void UGlassImpactPlaybackComponent::Reset()
{
    bPlaying = false; CurrentTime = 0; bImpactSent = bGrowthSent = bParticlesSent = bFinishedSent = false;
    UpdateFrame();
}
void UGlassImpactPlaybackComponent::Seek(float Seconds) { bPlaying = false; CurrentTime = FMath::Clamp(Seconds, 0.f, Duration); UpdateFrame(); }
void UGlassImpactPlaybackComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
    if (!bPlaying || !bLoaded) return;
    CurrentTime = FMath::Min(Duration, CurrentTime + FMath::Max(0.f, DeltaTime) * FMath::Max(0.0001f, PlaybackRate));
    UpdateFrame();
    if (!bLoaded) return;
    if (!bGrowthSent && CurrentMaxDamage >= DamageThreshold) { bGrowthSent = true; OnCrackGrowth.Broadcast(); }
    if (!bParticlesSent && CurrentMaxDamage >= ParticleTriggerThreshold)
    {
        bParticlesSent = true; OnParticleThreshold.Broadcast();
        const FVector Location = GetOwner()->GetActorTransform().TransformPosition(FVector((ImpactUV.X-0.5)*PlateSizeCm.X, (ImpactUV.Y-0.5)*PlateSizeCm.Y, 0));
        if (ImpactParticles) UNiagaraFunctionLibrary::SpawnSystemAtLocation(this, ImpactParticles, Location);
        if (ImpactSound) UGameplayStatics::PlaySoundAtLocation(this, ImpactSound, Location);
    }
    if (CurrentTime >= Duration && !bFinishedSent) { bPlaying = false; bFinishedSent = true; OnFinished.Broadcast(); }
}

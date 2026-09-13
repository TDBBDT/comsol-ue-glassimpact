#include "GlassImpactDemoActor.h"
#include "GlassImpactPlaybackComponent.h"
#include "ProceduralMeshComponent.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/InputComponent.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Materials/MaterialInterface.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "UnrealClient.h"

namespace
{
// A closed square ring swept around a beveled cross-section. Every corner is a
// genuine 45-degree miter shared geometrically by its adjacent faces; there are
// no intersecting box ends and no independent world-space transforms.
void BuildBeveledRing(UProceduralMeshComponent* Mesh, float OuterHalf, float InnerHalf,
    float MinZ, float MaxZ, float Bevel)
{
    check(OuterHalf > InnerHalf && InnerHalf > 0.f);
    check(MaxZ > MinZ && Bevel > 0.f);
    check(2.f * Bevel < FMath::Min(OuterHalf - InnerHalf, MaxZ - MinZ));
    const TArray<FVector2D> Profile = {
        {InnerHalf+Bevel, MinZ}, {OuterHalf-Bevel, MinZ},
        {OuterHalf, MinZ+Bevel}, {OuterHalf, MaxZ-Bevel},
        {OuterHalf-Bevel, MaxZ}, {InnerHalf+Bevel, MaxZ},
        {InnerHalf, MaxZ-Bevel}, {InnerHalf, MinZ+Bevel}
    };
    const FVector2D Corners[] = {{-1,-1},{1,-1},{1,1},{-1,1}};
    const FVector2D Outward[] = {{0,-1},{1,0},{0,1},{-1,0}};
    TArray<FVector> Vertices, Normals;
    TArray<FVector2D> UV;
    TArray<int32> Triangles;
    TArray<FLinearColor> Colors;
    TArray<FProcMeshTangent> Tangents;
    for (int32 P=0; P<Profile.Num(); ++P)
    {
        const FVector2D A=Profile[P], B=Profile[(P+1)%Profile.Num()];
        const FVector2D Delta=B-A;
        for (int32 Side=0; Side<4; ++Side)
        {
            const FVector2D C0=Corners[Side], C1=Corners[(Side+1)%4];
            const FVector Q[] = {
                {C0.X*A.X,C0.Y*A.X,A.Y}, {C1.X*A.X,C1.Y*A.X,A.Y},
                {C1.X*B.X,C1.Y*B.X,B.Y}, {C0.X*B.X,C0.Y*B.X,B.Y}
            };
            const FVector Normal=FVector(Outward[Side].X*Delta.Y,
                Outward[Side].Y*Delta.Y,-Delta.X).GetSafeNormal();
            const FVector Tangent=(Q[1]-Q[0]).GetSafeNormal();
            const FVector2D FaceUV[]={{0,0},{1,0},{1,1},{0,1}};
            const int32 Base=Vertices.Num();
            for (int32 V=0; V<4; ++V)
            {
                Vertices.Add(Q[V]); Normals.Add(Normal); UV.Add(FaceUV[V]);
                Colors.Add(FLinearColor::White); Tangents.Add(FProcMeshTangent(Tangent,false));
            }
            // UE front faces use clockwise winding viewed from the outside.
            if (FVector::DotProduct(FVector::CrossProduct(Q[1]-Q[0],Q[2]-Q[0]),Normal)>0)
                Triangles.Append({Base,Base+2,Base+1,Base,Base+3,Base+2});
            else Triangles.Append({Base,Base+1,Base+2,Base,Base+2,Base+3});
        }
    }
    Mesh->CreateMeshSection_LinearColor(0,Vertices,Triangles,Normals,UV,Colors,Tangents,false);
}
}

AGlassImpactDemoActor::AGlassImpactDemoActor()
{
    PrimaryActorTick.bCanEverTick = true;
    GlassMesh = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("GlassPlate"));
    RootComponent = GlassMesh;
    GlassMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    GlassMesh->SetCastShadow(false);
    GlassMesh->SetBoundsScale(1.5f);
    FrameMesh = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("Frame"));
    GasketMesh = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("Gasket"));
    TrimMesh = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("FrontTrim"));
    for (UProceduralMeshComponent* Part : {FrameMesh.Get(), GasketMesh.Get(), TrimMesh.Get()})
    {
        Part->SetupAttachment(GlassMesh);
        Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Part->SetCastShadow(true);
    }
    Playback = CreateDefaultSubobject<UGlassImpactPlaybackComponent>(TEXT("Playback"));
}
void AGlassImpactDemoActor::BuildPlate()
{
    constexpr int32 N=129;
    TArray<FVector> Vertices, Normals; TArray<FVector2D> UV;
    TArray<int32> Triangles; TArray<FLinearColor> Colors; TArray<FProcMeshTangent> Tangents;
    Vertices.Reserve(N*N); Normals.Reserve(N*N); UV.Reserve(N*N);
    for (int32 J=0; J<N; ++J) for (int32 I=0; I<N; ++I)
    {
        const float U=float(I)/(N-1), V=float(J)/(N-1);
        Vertices.Add(FVector((U-.5f)*100, (V-.5f)*100, 0)); UV.Add(FVector2D(U,V));
        Normals.Add(FVector(0,0,1)); Colors.Add(FLinearColor::White); Tangents.Add(FProcMeshTangent(1,0,0));
    }
    for (int32 J=0; J<N-1; ++J) for (int32 I=0; I<N-1; ++I)
    {
        const int32 A=J*N+I, B=A+1, C=A+N, D=C+1;
        Triangles.Append({A,C,B,B,C,D});
    }
    GlassMesh->CreateMeshSection_LinearColor(0, Vertices, Triangles, Normals, UV, Colors, Tangents, false);
}
void AGlassImpactDemoActor::BuildFixture()
{
    // The 100 cm glass extends 1 cm under the frame on all four sides.
    // The visible +Z face is verified again in the runtime transform log.
    BuildBeveledRing(FrameMesh,54.f,49.f,-2.4f,1.4f,.25f);
    BuildBeveledRing(GasketMesh,50.f,48.8f,-.03f,.42f,.05f);
    BuildBeveledRing(TrimMesh,53.70f,53.35f,1.34f,1.55f,.08f);
    if (FrameMaterial) FrameMesh->SetMaterial(0,FrameMaterial);
    if (GasketMaterial) GasketMesh->SetMaterial(0,GasketMaterial);
    if (TrimMaterial) TrimMesh->SetMaterial(0,TrimMaterial);
}
void AGlassImpactDemoActor::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform); BuildPlate(); BuildFixture();
    if (GlassMaterial) GlassMesh->SetMaterial(0, GlassMaterial);
}
void AGlassImpactDemoActor::BeginPlay()
{
    Super::BeginPlay();
    BuildFixture();
    UE_LOG(LogTemp,Display,TEXT("GLASS_FIXTURE_LOCAL plate=100x100 frame_outer=108x108 frame_aperture=98x98 glass_overlap=1cm gasket_aperture=97.6x97.6 attached_to_plate=1"));
    const FVector FrontNormal=GetActorTransform().TransformVectorNoScale(FVector::UpVector);
    UE_LOG(LogTemp,Display,TEXT("GLASS_FIXTURE_FRONT normal_world=%s camera_side_dot=%.3f"),
        *FrontNormal.ToString(),FVector::DotProduct(FrontNormal,FVector(0,-1,0)));
    if (!GlassMaterial) GlassMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/GlassImpact/M_GlassImpact.M_GlassImpact"));
    if (!WireMaterial) WireMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/GlassImpact/M_GlassWire.M_GlassWire"));
    Playback->LoadData(); Playback->BindMesh(GlassMesh, GlassMaterial);
    auto* Cam = GetWorld()->SpawnActor<ACameraActor>(); ViewCamera = Cam;
    Cam->GetCameraComponent()->FieldOfView = 38;
    Cam->GetCameraComponent()->bConstrainAspectRatio = false;
    Cam->GetCameraComponent()->PostProcessSettings.bOverride_AutoExposureMethod = true;
    Cam->GetCameraComponent()->PostProcessSettings.AutoExposureMethod = EAutoExposureMethod::AEM_Manual;
    Cam->GetCameraComponent()->PostProcessSettings.bOverride_AutoExposureBias = true;
    Cam->GetCameraComponent()->PostProcessSettings.AutoExposureBias = 1.0f;
    Cam->GetCameraComponent()->PostProcessSettings.bOverride_AutoExposureApplyPhysicalCameraExposure = true;
    Cam->GetCameraComponent()->PostProcessSettings.AutoExposureApplyPhysicalCameraExposure = false;
    CameraOblique();
    APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
    if (PC)
    {
        EnableInput(PC); PC->SetViewTarget(Cam); PC->bShowMouseCursor = false;
        InputComponent->BindKey(EKeys::SpaceBar, IE_Pressed, this, &AGlassImpactDemoActor::TogglePlayback);
        InputComponent->BindKey(EKeys::R, IE_Pressed, this, &AGlassImpactDemoActor::ResetPlayback);
        InputComponent->BindKey(EKeys::W, IE_Pressed, this, &AGlassImpactDemoActor::ToggleWireframe);
        InputComponent->BindKey(EKeys::One, IE_Pressed, this, &AGlassImpactDemoActor::CameraOblique);
        InputComponent->BindKey(EKeys::Two, IE_Pressed, this, &AGlassImpactDemoActor::CameraFront);
        InputComponent->BindKey(EKeys::Three, IE_Pressed, this, &AGlassImpactDemoActor::CameraSide);
        InputComponent->BindKey(EKeys::Equals, IE_Pressed, this, &AGlassImpactDemoActor::Faster);
        InputComponent->BindKey(EKeys::Hyphen, IE_Pressed, this, &AGlassImpactDemoActor::Slower);
        InputComponent->BindKey(EKeys::D, IE_Pressed, this, &AGlassImpactDemoActor::ToggleDisplacementScale);
    }
    // Reproducible unattended screenshot hook; the default interactive scene stays paused.
    if (FParse::Value(FCommandLine::Get(), TEXT("GlassCapture="), CapturePath))
    {
        float Time = Playback->Duration; FParse::Value(FCommandLine::Get(), TEXT("GlassTime="), Time); Playback->Seek(Time);
        FString View; FParse::Value(FCommandLine::Get(), TEXT("GlassView="), View);
        if (View == TEXT("front")) CameraFront(); else if (View == TEXT("side")) CameraSide();
        if (FParse::Param(FCommandLine::Get(), TEXT("GlassWire"))) ToggleWireframe();
        if (FParse::Param(FCommandLine::Get(), TEXT("GlassExaggerate"))) ToggleDisplacementScale();
    }
}
void AGlassImpactDemoActor::SetCamera(const FVector& Offset, const FString& Name)
{
    ViewName=Name;
    if (!ViewCamera) return;
    const FVector Target=GetActorLocation()+FVector(0,0,-8); ViewCamera->SetActorLocation(Target+Offset);
    ViewCamera->SetActorRotation((-Offset).Rotation());
}
void AGlassImpactDemoActor::CameraOblique() { SetCamera(FVector(140,-425,45), TEXT("OBLIQUE")); }
void AGlassImpactDemoActor::CameraFront() { SetCamera(FVector(0,-430,0), TEXT("FRONT / UV")); }
void AGlassImpactDemoActor::CameraSide() { SetCamera(FVector(315,-394,34), TEXT("SIDE / DEFLECTION")); }
void AGlassImpactDemoActor::TogglePlayback() { if (Playback->bPlaying) Playback->Pause(); else Playback->Play(); }
void AGlassImpactDemoActor::ResetPlayback() { Playback->Reset(); }
void AGlassImpactDemoActor::ToggleWireframe() { bWireframe=!bWireframe; Playback->BindMesh(GlassMesh, bWireframe ? WireMaterial : GlassMaterial); }
void AGlassImpactDemoActor::Faster() { Playback->PlaybackRate=FMath::Min(1.f,Playback->PlaybackRate*2); }
void AGlassImpactDemoActor::Slower() { Playback->PlaybackRate=FMath::Max(.0001f,Playback->PlaybackRate*.5f); }
void AGlassImpactDemoActor::ToggleDisplacementScale()
{
    const bool WasPlaying = Playback->bPlaying;
    Playback->DisplacementScale = Playback->DisplacementScale == 1.f ? 10.f : 1.f;
    Playback->Seek(Playback->CurrentTime);
    if (WasPlaying) Playback->Play();
}
void AGlassImpactDemoActor::Tick(float DeltaTime)
{
    Super::Tick(DeltaTime);
    if (!CapturePath.IsEmpty())
    {
        ++CaptureFrames;
        if (CaptureFrames==160) { FScreenshotRequest::RequestScreenshot(CapturePath, true, false); UE_LOG(LogTemp, Display, TEXT("GLASS_CAPTURE_REQUEST %s"), *CapturePath); }
        if (CaptureFrames==185) UKismetSystemLibrary::QuitGame(this, nullptr, EQuitPreference::Quit, true);
    }
}
void AGlassImpactHUD::DrawHUD()
{
    Super::DrawHUD(); if (!Canvas || FParse::Param(FCommandLine::Get(),TEXT("GlassNoOverlay"))) return;
    AGlassImpactDemoActor* Demo = nullptr;
    for (TActorIterator<AGlassImpactDemoActor> It(GetWorld()); It; ++It) { Demo=*It; break; }
    if (!Demo) return;
    const UGlassImpactPlaybackComponent* P=Demo->Playback.Get();
    // Keep the experimental area free: one slim heading and a two-line footer.
    const float Margin=24.f, Width=Canvas->SizeX-2*Margin;
    const float Scale=FMath::Clamp(Canvas->SizeX/1440.f,.72f,1.15f);
    const FLinearColor Panel(.010f,.021f,.034f,.88f), Teal(.34f,.86f,.81f), Text(.84f,.92f,.95f);
    DrawRect(Panel,Margin,20,Width,44);
    DrawRect(Teal,Margin,20,3,44);
    const FString SourceLabel = !P->bLoaded ? TEXT("NO VALIDATED DATA") :
        (P->SourceKind == TEXT("synthetic") ? TEXT("SYNTHETIC / NOT A COMSOL RESULT") : TEXT("COMSOL / SEE DATA PROVENANCE"));
    DrawText(FString::Printf(TEXT("GLASS IMPACT   |   %s   |   %s"),*Demo->ViewName,*SourceLabel),
        Text,Margin+16,32,GEngine->GetSmallFont(),Scale);
    const float FooterY=Canvas->SizeY-84.f;
    DrawRect(Panel,Margin,FooterY,Width,64);
    DrawRect(Teal,Margin,FooterY,3,64);
    DrawText(FString::Printf(TEXT("%s  |  %.3f / %.3f ms  |  damage %.3f  |  speed %.4fx  |  %s  |  displacement x%.0f"),
        P->bPlaying ? TEXT("PLAYING") : TEXT("PAUSED"),P->CurrentTime*1000,P->Duration*1000,
        P->CurrentMaxDamage,P->PlaybackRate,Demo->bWireframe ? TEXT("WIREFRAME") : TEXT("GLASS"),P->DisplacementScale),
        Teal,Margin+16,FooterY+10,GEngine->GetSmallFont(),Scale);
    DrawText(TEXT("SPACE Play/Pause   R Reset   1 Oblique   2 Front   3 Side   W Wireframe   D Displacement x1/x10   +/- Speed"),
        Text,Margin+16,FooterY+35,GEngine->GetSmallFont(),Scale);
    if (!P->LastError.IsEmpty()) DrawText(P->LastError,FLinearColor::Red,Margin+16,76,GEngine->GetSmallFont(),Scale);
}
AGlassImpactGameMode::AGlassImpactGameMode() { DefaultPawnClass=nullptr; HUDClass=AGlassImpactHUD::StaticClass(); }

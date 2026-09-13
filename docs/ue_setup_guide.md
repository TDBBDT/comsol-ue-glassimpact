# UE 5.6 导入、材质与多视角演示

这是独立的 `GlassImpact.uproject`，不依赖、不修改土体项目。初始演示必须显示 **SYNTHETIC**；此时的裂纹是用于验证数据通路的合成场，不是 COMSOL 断裂求解结果。网格不分离，粒子/声音默认未分配。

## 构建和生成演示场景

需要 Windows、UE 5.6、Visual Studio C++ 工具链、Windows SDK。运行时模块依赖 Core、CoreUObject、Engine、InputCore、Json、RenderCore、RHI、ProceduralMeshComponent、Niagara；编辑器资产脚本使用 PythonScriptPlugin 和 EditorScriptingUtilities。

在 `GlassImpact` 目录打开 PowerShell，按本机安装位置修改 `$engine`：

```powershell
$engine = 'D:/Users/Epic/Install/UE_5.6'
$project = (Resolve-Path './unreal/GlassImpact.uproject').Path
$setup = (Resolve-Path './unreal/ContentInstructions/setup_demo.py').Path
& "$engine/Engine/Build/BatchFiles/Build.bat" GlassImpactEditor Win64 Development $project -WaitMutex -NoHotReloadFromIDE
New-Item -ItemType Directory -Force './unreal/Content/GlassImpactData'
Copy-Item './data/processed/synthetic_demo/metadata.json' './unreal/Content/GlassImpactData/'
Copy-Item './data/processed/synthetic_demo/state.rgba16f' './unreal/Content/GlassImpactData/'
Copy-Item './data/processed/synthetic_demo/displacement.rgba16f' './unreal/Content/GlassImpactData/'
& "$engine/Engine/Binaries/Win64/UnrealEditor-Cmd.exe" $project -run=pythonscript "-script=$setup" -unattended -nop4 -nosplash -AllowCommandletRendering
& "$engine/Engine/Binaries/Win64/UnrealEditor.exe" $project
```

如果转换器输出目录不同，只调整以上源目录。脚本只生成 `/Game/GlassImpact` 下的资产；重运行会重建演示地图、复用已有材质。修改 HLSL 后，在命令行追加 `-RebuildGlassMaterials` 才会重建材质图。在别处保存自己的手工修改。二进制数据不通过编辑器的“导入纹理”按钮导入，由组件按元数据读取。打包配置将 `GlassImpactData` 作为 NonUFS 原始文件带入。

默认地图 `GlassImpactDemo` 有竖直玻璃板、一体倒角框、贴合密封条、短支柱与圆角底座，采用连续渐变背景及三盏方向灯。框、玻璃、胶条和窄饰条共享 Actor 变换；100 cm 玻璃压入 98 cm 开口，每边 1 cm。相机使用 38° 水平视野，注视点低于玻璃中心 8 cm，为底座和屏幕信息留白。详见 [装配与构图修正](composition_refinement.md)。原始玻璃坐标 XY 平面通过 UE Roll=-90° 立起：局部 +Y 指向世界 +Z，局部法线指向世界 -Y。Python 创建旋转必须使用命名参数 `ue.Rotator(pitch=0,yaw=0,roll=-90)`，不能依赖位置参数顺序。

正视摄像机位于世界 Y 负侧、朝 +Y 看，摄像机屏幕右向为世界 -X。因此 **U 增大在这台摄像机中朝屏幕左侧，V 增大朝上**；这与 Python 预览中 X 朝右的绘图约定存在观看方向差异，不是纹理被错误上下翻转。验证 UV 时临时用 `BaseColor=float3(U,V,0)` 的无光照调试材质：U=1/V=0 红角应在屏幕左下，U=0/V=1 绿角应在右上，中心 `(0.5,0.5)` 应与玻璃几何中心重合。可再导出一个位于 `(U,V)=(0.25,0.75)` 的非对称测试标记确认位置。验证后恢复原材质，不要为迎合截图朝向修改物理数据的行序。

按 Play/PIE 进入演示。初始状态暂停在零时刻。键盘：

| 输入 | 操作 |
|---|---|
| Space | 播放/暂停；结束后再次播放从零开始 |
| R | 复位到零，清除本次播放的事件锁存 |
| 1 / 2 / 3 | 对准中心的斜视、正视、侧视 |
| W | 玻璃材质 / 三角网格线框切换 |
| D | 位移显示倍率 x1 / x10，HUD 明确标记 |
| + / - | 加速 / 减速 |

默认 `PlaybackRate=0.005`：0.02 s 物理过程约用 4 s 展示。**这只是播放慢动作**；HUD 时间仍为真实物理毫秒。32 帧只是数据采样数；UE 每帧按真实时间间隔插值相邻两帧，不能以固定“纹理帧/FPS”代替物理时间。

## 组件与 Blueprint

`UGlassImpactDataAsset` 保存 Content 相对数据目录，也接受明确绝对目录用于开发。`UGlassImpactPlaybackComponent` 暴露 DataAsset、Duration（从元数据读取）、PlaybackRate、DamageThreshold、CrackWhiteningStrength、RefractionStrength、CrackIntensity、DisplacementScale、ParticleTriggerThreshold、Play/Pause/Reset/Seek。

在其他关卡中：

1. 建立 Data Asset，父类选 `GlassImpactDataAsset`，DataDirectory 为 `GlassImpactData`。
2. 用有 UV0 的密网格玻璃模型添加 Playback 组件；本演示使用 129×129 顶点，固定 32768 个三角形。一个只有四顶点的平面无法显示空间变化的 WPO。
3. BeginPlay：组件 `LoadData` → 检查返回值 → `BindMesh`，传玻璃 Mesh 和当前 `M_GlassImpactStudio`。若使用 DemoActor，FrameMaterial / GasketMaterial / TrimMaterial 分别指定 `MI_FrameAnodized`、`MI_GasketRubber`、`MI_BevelEdge`；当前测试关卡已经设置。
4. 交互事件调用 `Play`；需要倒带使用 `Reset` 后 `Play`。`Seek` 是无副作用的预览，不发粒子和音效事件。
5. 绑定 `OnImpact`、`OnCrackGrowth`、`OnParticleThreshold`、`OnFinished`。每次播放每类事件最多一次；Pause/Play 不重复触发，Reset 重新解锁。
6. 默认 **ImpactParticles / ImpactSound 均为空**。自行指定 Niagara System、SoundBase 后，组件在阈值事件处于冲击 UV 对应世界位置播放它们。或只绑定事件，由 Blueprint 管理对象池；不要同时保留自动资产槽和重复的 Blueprint 播放逻辑。

当前触发指标是元数据逐帧 `max_damage_per_frame` 的时间线性插值。若空间最大值位置改变，它是混合场最大值的保守上界，并非冲击点损伤或断裂能。该阈值只控制演示特效，不作为物理破坏判据。初始合成样例保持同一冲击区域，避免混淆。

## 材质节点与精度

脚本会实际创建、连接并保存两个材质。HLSL 源码在 `unreal/Shaders`，以 Custom 节点内联，不要求安装 Engine 全局 Shader 插件。

| 参数 / 节点 | 连接与意义 |
|---|---|
| `StateA`、`StateB` | TextureObject；RGBA=damage、归一化主应力、等效应力、能量 |
| `DispA`、`DispB` | TextureObject；RGBA=归一化局部 u/v/w、coverage |
| `FrameAlpha` | 由 `(t-tA)/(tB-tA)` 计算，同时控制全部物理场 |
| FieldBlend Custom | 两纹理同 UV0、LOD0 线性插值；损伤不做逐帧归一化 |
| Crack | `smoothstep(DamageThreshold, DamageThreshold+0.1, d)`，乘 coverage 和强度；不是裂纹几何重建 |
| BaseColor / Emissive | 裂纹区域发白，弱补光保证可见 |
| Roughness | 当前 Studio 材质完整 0.035 → 裂纹 0.64 |
| Opacity | 当前 Studio 材质完整 0.07 → 裂纹 0.78；此为渲染参数，不是损伤物理量 |
| Normal | 相邻 UV 采样损伤梯度构造切线法线扰动，强度系数 0.25，属美术表现 |
| Refraction | 当前 Studio 材质 `1 + strength*lerp(0.008,0.10,crack)`，演示 strength=0.08；不是玻璃光学标定 |
| DisplacementMin/Span | 所有帧共用的三个分量范围，米×100后以厘米传材质 |
| Displacement Custom | `(min + encoded*span)*coverage*displayScale`，玻璃边界 UV=0/1 强制 WPO=0 |
| TransformVector | **Local → World**，再接 World Position Offset；不能直接把局部 w 接世界 Z |

纹理为无 mip、clamp、bilinear、`PF_FloatRGBA`，关闭 sRGB。采样器读取半精度线性数据，范围存在 JSON 中。全部场同一 coverage，缺测区域不外推；裂纹与位移被 coverage 屏蔽。玻璃本身在无覆盖区域仍可渲染为完整玻璃，不能把它解释为真实完整状态。

`M_GlassWire` 是真正三角形线框材质，青色完整、橙色损伤；它显示**表面网格**随 WPO 变形，并非实体内部有限元网格或碎块切割面。线框与玻璃使用同一位移解码。放大模式是为了肉眼检查小位移，截图必须保留 HUD 倍率。

129×129 网格在低分辨率或侧面压缩投影下，线条会重叠成青色密区。检查单元应使用正面/斜视、高分辨率并在原始像素比例查看；不要据此误认为网格被填充。`docs/ue-captures/wire_oblique.png` 是 2560×1800、关闭后处理抗锯齿的实际线框截图，显示1.935 ms和x10位移倍率。此设置是可视检查设置，不能代表常规画质或帧率。

COMSOL 的物理板厚为 8 mm；此渲染原型为**单张、零视觉厚度、双面显示的细分表面**。当前导出指南选择板底受拉面；双面渲染重复这一个被选择表面的场，不进行厚度方向求最大值，不代表两侧损伤相同。未实现厚度分辨的折射、崩边或内部裂面。

## 数据检查与限制

组件拒绝缺失字段、错误版本/数据类型/字节序/坐标映射、非递增时间、非零起始时间、维数错误、倒置位移范围、损伤最大值下降、二进制长度不符。完整 NaN、节点、损伤不可逆、哈希核验由 Python 验证器完成；UE 不在每帧重复扫描全部 512² 数据做完整科学验证。

两种场只保留相邻两个帧纹理：512² RGBA16F × 4 ≈ 8 MiB GPU 数据，另有上传暂存和渲染资源开销；并未一次把整段 128 MiB 数据加载到 GPU。当前磁盘读取和上传准备是同步的，帧索引变化时读四个帧缓冲；在慢磁盘或1×速度时可能卡顿。**60 FPS 是目标，未完成硬件帧时间基准，不能宣称已稳定达到。**后续可用异步预取/环形缓冲优化，保持当前数据协议。

初版不处理真实碰撞网格变形、接触响应、双面厚度场、碎片分离、自动 Niagara 碎玻璃资源、裂纹声音资产或 Runtime COMSOL。材质显示裂纹不等于网格已形成物理裂面。来源真实性应查看 `source.json` 和 `metadata.json`。

## 可复现截图

使用生成后的地图和数据，命令可以无人值守输出带 HUD 的 UE 渲染截图；运行约160渲染帧后抓图并退出：

```powershell
$out = Join-Path (Get-Location) 'docs/ue-captures'
New-Item -ItemType Directory -Force $out
& "$engine/Engine/Binaries/Win64/UnrealEditor-Cmd.exe" $project /Game/GlassImpact/Maps/GlassImpactDemo -game -RenderOffscreen -ForceRes -ResX=1280 -ResY=900 -unattended -nosplash -nosound "-GlassCapture=$out/glass_front.png" -GlassView=front '-GlassTime=0.02' '-ExecCmds=t.MaxFPS 10,DisableAllScreenMessages'
& "$engine/Engine/Binaries/Win64/UnrealEditor-Cmd.exe" $project /Game/GlassImpact/Maps/GlassImpactDemo -game -RenderOffscreen -ForceRes -ResX=1280 -ResY=900 -unattended -nosplash -nosound "-GlassCapture=$out/wire_side.png" -GlassView=side -GlassWire -GlassExaggerate '-GlassTime=0.00193548' '-ExecCmds=t.MaxFPS 10,DisableAllScreenMessages'
& "$engine/Engine/Binaries/Win64/UnrealEditor-Cmd.exe" $project /Game/GlassImpact/Maps/GlassImpactDemo -game -RenderOffscreen -ForceRes -ResX=2560 -ResY=1800 -unattended -nosplash -nosound "-GlassCapture=$out/wire_oblique.png" -GlassWire -GlassExaggerate '-GlassTime=0.00193548' '-ExecCmds=t.MaxFPS 10,r.PostProcessAAQuality 0,r.BloomQuality 0,DisableAllScreenMessages'
```

必须检查输出图确实有玻璃、正确时间/倍率、SYNTHETIC 标签，且日志有 `GLASS_DATA_LOADED`，没有材质编译错误或数据错误。构建通过只代表 C++ 编译通过，不等于材质、播放、视觉或性能全部通过。

PowerShell 中含小数的参数必须整项加引号，例如 `'-GlassTime=0.02'`，否则可能被拆成 `-GlassTime=0 .02`，错误地截取零时刻。截图使用 10 FPS 限速只是为了给首次着色器加载留下时间，**不用于性能评测**。

# 数据格式与坐标映射 v1

本项目的初始样例全部是 **SYNTHETIC（人工构造的流程测试数据）**。放射线图案由 Python 显式生成，没有求解接触、相场、断裂或玻璃材料方程。数据通过验证只说明格式、插值、编码和播放一致，不代表物理正确。

## 1. 可运行入口

在 `GlassImpact` 根目录创建 Python 3.9+ 环境并安装：

```powershell
python -m pip install -e .
python tools/generate_synthetic.py --output data/samples/my_synthetic --frames 32 --grid 65
python -m validator --input data/samples/my_synthetic
python -m converter --input data/samples/my_synthetic --output data/processed/my_run --config config/glass_impact.yaml
python -m validator --processed data/processed/my_run
python -m unittest discover -s tests -v
```

现有样例路径为 `data/samples/synthetic`，处理结果为 `data/processed/synthetic_demo`。生成器和转换器拒绝覆盖非空输出目录；重新计算时使用新目录。转换失败可能留下不完整输出，但没有成功生成的 `metadata.json`，不得导入 UE。

本机使用已存在的依赖完成验证，无需修改系统安装：

```powershell
$env:PYTHONPATH = 'tools;../work/plot-deps'
& D:/python/python.exe -m converter --input data/samples/synthetic --output data/processed/new_run --config config/glass_impact.yaml
```

依赖为 NumPy、Matplotlib（只用其中的三角剖分，不求解有限元）和 Pillow。所附 `.yaml` 使用合法 YAML 的 JSON 子集，标准库即可读取；任意常规 YAML 可选安装 `.[yaml]`。

## 2. 原始输入契约

优先使用长表 CSV。一个文件可包含全部时刻，也可每帧一个按时间排序的文件；帧内节点行顺序可不同。列名必须是：

```text
time_s,node_id,x_m,y_m,z_m,u_m,v_m,w_m,sigma1_Pa,von_mises_Pa,damage,strain_energy_J_m3
```

| 字段 | 约定 |
|---|---|
| `time_s` | 物理秒，第一帧严格为 0，后续时间组严格递增，可以非等间隔 |
| `node_id` | 整数，跨时刻保持同一材料点含义，每帧不可重复 |
| `x_m,y_m,z_m` | 固定参考坐标，投影面 `z_m=0`；不是变形后的空间坐标 |
| `u_m,v_m,w_m` | 玻璃局部参考轴下位移，米；带符号 |
| `sigma1_Pa` | 第一主应力，Pa，可正可负；在 sidecar 中写明应力张量类型与拉压符号 |
| `von_mises_Pa` | 非负等效应力，Pa；辅助显示，不作为脆性破坏的唯一判据 |
| `damage` | 无量纲，0 完整、1 损伤，所有帧使用此固定范围 |
| `strain_energy_J_m3` | 非负应变能密度，J/m³；写清所选能量定义 |

允许以 `%` 或 `#` 开头的注释行。COMSOL 自带表头通常不等于本契约，需要在导出模板中设置或重命名。不可把不同厚度层的相同 XY 节点混在同一个数据集。首版仅支持固定参考节点，不支持自适应重网格后沿用变化的节点 ID。

同目录必须有 `source.json`，至少包含：

```json
{
  "source_kind": "comsol",
  "domain_topology": "single_convex_plate_without_holes",
  "coordinate_provenance": "Selected front surface in reference coordinates; translated to local mapping plane z=0",
  "field_definitions": {
    "u_m": "Local X displacement, m",
    "v_m": "Local Y displacement, m",
    "w_m": "Local normal displacement, m",
    "sigma1_Pa": "Record the actual COMSOL expression and stress measure here",
    "von_mises_Pa": "Record the actual COMSOL expression here",
    "damage": "Record solved damage variable; 0 intact, 1 damaged",
    "strain_energy_J_m3": "Record actual energy density expression and reference/current volume convention"
  }
}
```

真实结果还应写入 COMSOL 版本、模型与参数文件 SHA256、网格与求解设置、选取的边界编号、冲击参数、损伤变量实际表达式、求解日志和物理验证报告位置。`source_kind=comsol` 仅记录来源，不自动授予物理验证通过。

可选 VTK/VTU：安装 `pip install -e '.[vtk]'`。每文件一帧，`points` 是参考坐标，`point_data` 必须含整数 `node_id` 以及上表七个物理字段，`field_data['time_s']` 必须是一个数值。单元数据必须先明确投影至所选表面节点；不能默认当节点数据读取。适配代码已提供，当前本机未安装 meshio，**VTK 路径尚未执行验证**；首版已实际验证 CSV 路径。此版本不支持 `.pvd` 聚合列表。

## 3. 验证与插值

读取时拒绝缺列、重复列、空字段、NaN/Inf、重复节点、重复时间组、时间倒序、缺帧节点、参考坐标漂移、多层重复 XY、损伤超出 `[0,1]` 和明显损伤回落。浮点误差容限默认 `1e-8`；即使原始回落在容限内，若经过半精度量化放大为可检测的损伤回退，转换仍失败。**不会用累计最大值掩盖裂纹愈合。**

XY 节点只构建一次 Delaunay 三角剖分；每个输出 texel 只构建一次三角形索引与重心权重，所有时刻及物理量共用。三角形内采用分片线性插值，保持线性场精确性和非负权重，不使用可能过冲的高阶样条。

CSV 没有有限元单元拓扑，此方法不声称重建原始有限元插值阶次。`source.json` 必须明确声明连续、无孔、单块凸玻璃板；有孔、切口或分离表面的输入会被拒绝。即使读取 VTK，当前也使用同一 XY 重建规则。后续支持破碎或缺口时需要保留单元拓扑与域掩膜，不能让 Delaunay 跨孔连线。

输出网格超出节点凸包时 `coverage=0`，所有编码通道填 0。禁止最近邻外推。UE 必须用 coverage 门控解码后的位移与材质效果：归一化零值本身可能解码为非零物理最小值。对于完整方板，coverage 应为 1；异常空洞需检查导出的边界点。

## 4. XY → UV0 → UE

默认玻璃局部参考平面为 XY，法向 +Z，范围 `[-0.5,0.5]² m`：

```text
U = (x - origin_x) / size_x
V = (y - origin_y) / size_y
x(texel i) = origin_x + (i + 0.5) * size_x / width
y(texel j) = origin_y + (j + 0.5) * size_y / height
UE local position [cm] = 100 * COMSOL plate-local reference position [m]
UE local displacement [cm] = 100 * [u,v,w] [m]
```

COMSOL 通常使用右手坐标，UE 使用左手坐标约定。这里显式构造 UE 玻璃网格，使局部 X、Y、Z 与上述数据轴的几何方向对应；不能因此对任意导入网格一概声称无需轴变换。UE 面片绕序、法向和背面显示由网格定义。若导入模型的局部轴不同，应记录并应用一个确定的基变换；位移是向量，也必须使用同一变换。WPO 先解码局部位移，再通过 Actor 的局部到世界向量变换，避免旋转玻璃后位移仍沿世界 Z。

二进制与数据 PNG 的第 0 行都是 `y_min`，UV0 的 `(0,0)` 对应该角。自定义 UE 运行时上传按此约定不再翻转。普通图片查看器将第一行放在屏幕顶部，所以数据 PNG 看上去上下颠倒是预期的；**只有预览 GIF/PNG 为展示翻转了 Y**，不得拿预览图替代数据输入。自带示例左右不对称的射线可用于方向核对；单独对称中心冲击无法发现上下翻转。

边界节点的位移在合成数据中严格为 0。纹理采样点位于半个 texel 内，UV 边缘用 clamp 时会采到内部值；UE 夹持边界顶点应将 WPO 明确门控为 0，或使用固定边界顶点标志。不要为图像好看修改原始边界物理量。

中心冲击验证：COMSOL 点 `(0,0)` → UV `(0.5,0.5)` → UE 板中心。512 是偶数，中心位于四个 texel 中间；不要要求某一个 texel 恰好在冲击点。可在 UE 放中心标记，检查最大损伤位置位于中心邻近区域，再用不对称小位移校验 +X/+Y/+Z。

## 5. 处理后二进制与元数据

两个文件均为无文件头、小端 IEEE754 float16，数组形状 `[frame_count,height,width,4]`，C row-major。一个 texel 为 8 字节，帧偏移 `frame_index * width * height * 8`。

| 文件 | R | G | B | A |
|---|---|---|---|---|
| `state.rgba16f` | damage，固定 0–1 | 第一主应力全局归一化 | von Mises 全局归一化 | 应变能密度全局归一化 |
| `displacement.rgba16f` | u 全局归一化 | v 全局归一化 | w 全局归一化 | coverage，0 或 1 |

全局范围来自全部输入节点和全部时间：`encoded=(physical-min)/(max-min)`。每一帧使用相同 min/max，禁止逐帧拉伸范围。恒定通道编码为 0，解码为 minimum。damage 不使用 min/max 再归一化，因此不会把第一帧微小噪声拉满为裂纹。元数据同时保留真实 SI 极值、单位、三个分量独立范围、SHA256、参考面来源、采样约定及实际半精度往返误差上界。

`max_damage_per_frame` 取**最终 float16 编码后的**纹理最大值，和 UE 实际采样数据一致，用于门限事件。元数据 `times_seconds` 是唯一物理时间表，`duration_seconds=times[-1]`；32/64 是输出帧数，与 COMSOL 内部求解步数无关。

32 帧、512²、两份 RGBA16F 二进制共 **128 MiB**；磁盘保存完整序列，UE 同时保留相邻两帧的 state/disp，共约 8 MiB 纹理像素数据，不计驱动与 CPU 缓存。此 MVP 未压缩，是为避免依赖导入器和纹理压缩改变数据。

## 6. 精度和格式选择

| 格式 | 优点 | 限制 | 本项目用途 |
|---|---|---|---|
| 8 位 PNG | 小、通用、可浏览 | 只有 256 级，容易让应力/微位移和阈值抖动 | 仅截图、预览，不保存主物理量 |
| 16 位灰度 PNG | 无损、damage 误差约 `1/131070` | 每张单通道；普通 UE 导入配置可能转为其他格式 | 输出 `damage_png16` 供核查/离线资源，数据行不翻转 |
| EXR half/float | HDR、多通道、适合精度数据 | 依赖编解码器；UE 仍须确认导入压缩、sRGB、mips | 未来 DCC/离线管线互换，当前不输出 |
| float32/64 数组 | 可保存真实单位，高精度直接比较 | 较大；不能当标准材质图片直接拖入 | 建议作为研究归档、后续损失验证格式 |
| RGBA16F 二进制 + JSON | 格式简单、UE 原样上传、固定精度 | 自定义加载器，必须核验尺寸/哈希/端序 | 当前正式播放格式 |
| 运行时纹理 / Render Target | 可绑定动态材质、逐帧更新 | 需要精度/过滤/更新线程配置；不是磁盘格式 | 当前相邻帧采样，PF_FloatRGBA、线性、clamp、无 mips |

float16 的 damage 在大值区单次舍入误差约 `2.44e-4`；归一化位移的物理误差为舍入误差乘以全序列范围。实际最大误差逐通道写入 `validation.max_half_encoding_error_SI`。若这不满足真实裂纹阈值/位移精度需求，升级格式版本与 UE 纹理类型到 float32，不能仅改文件后缀。

## 7. 物理时间与渲染时间

给定物理播放时间 `t`，从 `times_seconds` 找相邻两帧 `t0,t1`，`alpha=(t-t0)/(t1-t0)`。状态和位移采样以相同 alpha 插值；损伤输入不可逆且权重非负，因此不会因帧混合造成裂纹后退。显色阈值平滑属于渲染，不修改 damage。

0.02 秒过程在正常 60 FPS 下仅约 1.2 个显示帧，无法辨认裂纹传播。展示时将播放时长设为约 3.2 秒（约 160 倍慢动作），清楚显示“物理时间 / 展示时间”；也允许恢复 1× 物理速度。元数据保持 0.02 秒，不为配合效果改写物理时间。非均匀输出帧不能直接用 `t/duration*(N-1)` 算索引。

## 8. 真实 COMSOL 替换步骤

1. 按建模指南完成模型求解和独立物理验证，保留模型、参数、日志、网格与求解收敛证据。
2. 选一个连续玻璃参考表面，输出相同节点 ID 的所有时刻。如果用上下表面最大损伤，要明确处理规则并确保与位移参考面一致，不能静默叠加节点。
3. 转成上述字段名和 SI 单位；将真实损伤变量定义统一为 `0=完整/1=损伤`，不随帧调整符号或范围。
4. 建立新的 `data/raw/comsol_case01/source.json`，填真实来源，不复用 synthetic 标记或生成器说明。
5. 执行 raw validator，修正任何愈合、缺点、非有限值或坐标漂移。转换器不会替求解器修正物理错误。
6. 转换到新的 processed 目录，执行 processed validator，检查预览中的中心、方向、裂纹时序及位移符号。
7. 检查 `validation.max_half_encoding_error_SI` 是否满足你的物理尺度；若不满足，先改数据格式版本，再改 UE 加载器。
8. 将 UE DataAsset 指向新元数据，保留原始物理时刻并设置合适慢放速度，逐帧与 COMSOL 选点曲线比较。转换成功后仍需在 UE 实机检查材质、法线、折射与性能。

当前未提供真实裂纹开口宽度。damage 只是等效裂纹指标；不能把视觉白线宽度或 `damage * 常数` 报成物理裂纹宽度。需要真实开口量时在 COMSOL 中定义开口积分/位移跳跃并扩展协议。

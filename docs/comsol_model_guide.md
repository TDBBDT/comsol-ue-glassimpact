# COMSOL 6.3：玻璃板中心冲击建模指南

本指南是**待在 COMSOL 中执行、校准和验证的建模方案**，不是求解结果。当前项目样例是 `synthetic`。没有生成或声称求解成功的玻璃 `.mph`。以下尺寸、材料及冲击参数用于建立首个试算；它们不能保证出现目标中的放射状裂纹。

## 1. 模块依赖与路线

本机检测到 COMSOL 6.3，但**本项目尚未验证可签出的模块许可**。安装目录和过去土体模型运行成功，不能证明本项目全部功能可用。在 COMSOL 的 Licensed and Used Products 页面及 Model Wizard 中检查下表，并保存实际版本、模块与许可检查结果；不导出许可证文件。

| 路线 | 所需能力/建议模块组合 | 能得到什么 | 局限与本项目选择 |
|---|---|---|---|
| 相场断裂，推荐 | COMSOL + Structural Mechanics + Nonlinear Structural Materials；6.3 的部分相同功能也由 Geomechanics 提供，须检查实际节点 | 无须预先指定裂纹路径；位移与损伤双向耦合 | 3D、接触、动态裂纹同时求解很昂贵；采用 6.3 隐式瞬态路线 |
| 连续损伤，最低可行物理替代 | Solid Mechanics + Damage；通常仍需 Nonlinear Structural Materials 或 Geomechanics | Rankine 拉伸损伤、刚度下降、连续位移 | 必须采用 Crack Band/Implicit Gradient 正则化；损伤带不等于已解析的锐利裂缝 |
| Cohesive Zone | Structural Mechanics 接触/黏结/脱黏功能；以本机 Adhesion/Decohesion 节点可用性为准 | 已知界面的牵引—分离、耗能及开口量 | 裂纹必须沿预置界面；界面数和路径偏置明显 |
| 预定义路径 | 可用的弹性固体或壳模型 + 外部材质路径 | 最快验证位移和动画管线 | 路径不是 COMSOL 自发预测；必须标记 `synthetic`/派生美术数据，不能冒充断裂仿真 |

若只有核心产品或弹性求解能力，最低闭环是“弹性位移 + 明确标注的合成裂纹”，并不是最低物理断裂模型。用 PDE 自行实现相场和历史变量可以减少对预置节点的依赖，但需要独立验证弱式、不可逆约束和切线；不作为本轮最快实现。Java API 属于 COMSOL 自动化；只有选用 MATLAB 自动化时才另需 MATLAB 和 LiveLink for MATLAB。[模块接口表](https://doc.comsol.com/6.3/doc/com.comsol.help.sme/sme_introduction.02.02.html)、[非线性结构材料产品说明](https://www.comsol.com/nonlinear-structural-materials-module)。

这里使用 **Phase-Field Damage**，不是用于气液界面的 Phase Field。6.3 已有动态分叉示例；不要照搬 6.4 新增的 *Phase-Field Damage, Explicit Dynamics* 界面名称。[6.3 更新说明](https://www.comsol.com/release/6.3/nonlinear-structural-materials-module)。

## 2. 几何、参数与模型维度

参数文件见 [`../comsol/parameters/glass_A1.json`](../comsol/parameters/glass_A1.json)，可导入的 COMSOL 参数文本见 [`../comsol/parameters/glass_A1_parameters.txt`](../comsol/parameters/glass_A1_parameters.txt)。所有新增值均为未校准的试算假设。

| 参数 | 初值 | 解释 |
|---|---:|---|
| 板宽、板高、厚度 | 1 m、1 m、0.008 m | 用户目标；玻璃总质量约 20 kg |
| E、ν、ρ | 70 GPa、0.22、2500 kg/m³ | 普通钠钙玻璃的工程起始假设，最终替换为供应商/试验数据 |
| 断裂能 Gc | 8 J/m² | 未校准；不能同时随意指定与之不一致的 KIC |
| AT1 长度 lint | 2 mm | 计算探索尺度，并非已确定的材料常数 |
| 球半径、等效密度 | 25 mm、7850 kg/m³ | 刚性钢球假设；质量 0.51378 kg |
| 初速度 | (0,0,−1) m/s | 初始动能 0.25689 J，可能不足以致裂 |
| 初始表面间隙 | 0.01 mm | 预计首次接触约 10 μs；避免初始穿透 |
| 主试算结束时间 | 2 ms | 先检查接触和裂纹萌生；之后扩展到 20 ms 振动尾段 |
| 交付帧数 | 64 | 输出采样数；绝不是内部求解步数 |

采用 3D 实体：玻璃范围 `x,y∈[−0.5,0.5]`、`z∈[−0.004,0.004] m`，球心 `(0,0,0.004+R+gap)`。四个竖直侧面全固定，正反大面自由，仅上表面与球接触。四边全夹持只是本工况假设；实际框架可能有柔度和滑移。

二维平面应力/平面应变不能再现垂直板面的弯曲冲击；轴对称不能同时表示方板和非轴对称放射分叉。壳模型适合快速验证整体弯曲及接触，但本指南的 3D 相场并不能直接套到壳厚度上。壳损伤必须明确上/下表面或厚度层；本轮不把壳结果称为 3D 裂纹。

玻璃由缺陷控制破坏。完美对称几何、均匀材料和网格可能形成对称损伤圈，网格扰动也可能人为选出径向裂纹。若需要缺陷，请加入独立、可重复的材料缺陷场，并记录位置、尺度、强度与随机种子；不能暗中预画径向裂纹后称其为预测。

## 3. 方程、损伤定义及精度约束

小应变下 `ε=(∇u+∇uᵀ)/2`，动量方程为 `ρ ü = ∇·σ + b`。接触运动和板转动采用几何非线性；若变形较大，应在材料坐标中使用 `ρ₀ ü = Div(P)+b₀`，不能混用 Cauchy 应力、参考体积和当前体积能量。

示意能量为

```text
Ψ(ε,φ) = g(φ) Ψ₀⁺(ε) + Ψ₀⁻(ε)
g(φ) ≈ (1−φ)² + η             （实际采用节点的残余刚度实现）
Γ_l = ∫ [w(φ) + lint² |∇φ|²] / (c_w lint) dV
E_fracture = Gc Γ_l
AT1: w(φ)=φ, c_w=8/3
```

`φ=0` 完整、`φ=1` 相场裂纹。**CSV 的 damage 本项目统一取 φ 本身**，并在 `source.json` 标记 `phase_field_phi`。COMSOL 的刚度损伤函数常为 `d_comsol(φ)=1−(1−φ)²`；它与 φ 不相同。不要混着导出，也不要为了让最后一帧达到 1 做逐帧拉伸。残余刚度使应力求解不至于完全奇异，不表示物理裂纹已经恢复承载能力。[相场耦合节点](https://doc.comsol.com/6.3/doc/com.comsol.help.sme/sme_ug_multiphysics.18.72.html)。

用拉伸/压缩分裂防止纯压缩被当成张开裂纹。推荐各向同性线弹性下的 `Spectral decomposition, strain`，并检查碰撞区强压缩响应；它比纯体积划分更昂贵。这里的 von Mises 应力只供诊断/显示，**不是玻璃脆性破坏判据**。

AT1 在理想均匀拉伸中的萌生应力量级为 `sqrt(3 E Gc/(8 lint))`。代入本试算约 **10.25 MPa**。若目标强度 45 MPa，同一理想关系给出 lint≈0.104 mm，网格和时间代价会大幅增加。因此 2 mm 只能作为未校准探索值，不能拿它的断裂阈值预测真实窗玻璃。Gc 与平面应变韧度关系 `Gc=KIC²/E'`、`E'=E/(1−ν²)`；本参数对应 KIC≈0.767 MPa√m。这些关系是初始一致性检查，不是材料认证。

不可逆条件：每个材料点 `φ̇≥0`，或离散形式 `φ_n≥φ_(n−1)`。内置损伤耦合通过随加载历史更新的驱动力状态量处理加载/卸载；保留完整耦合和历史状态。仅把当前能量写成 `max(当前能量,常数阈值)` 并不等于历史最大值。自编 PDE 必须实现 `H_n=max(H_(n−1),Ψ⁺_n)`，或变分不等式约束，同时验证卸载无愈合。[损伤模型理论](https://doc.comsol.com/6.3/doc/com.comsol.help.sme/sme_ug_theory.06.036.html)。

## 4. GUI 复现顺序

先在 Application Libraries 打开 `Nonlinear_Structural_Materials_Module/Damage/dynamic_crack_branching`（或对应 Geomechanics 库），复现官方小型基准、能量曲线和分叉。它是预裂纹平面拉伸试件，不能作为“方板球冲击已成功”的证据。以下是将相同求解机制用于独立玻璃项目的步骤。

1. **新建模型**：Model Wizard → 3D → Structural Mechanics → Phase-Field Damage → Time Dependent。保存到本项目 `comsol/models/GlassImpact_A1_input.mph`；不要覆盖土体工程。
2. **参数**：Global Definitions → Parameters → Load from File，导入参数文本。建立 named selections `GlassDomain`、`SphereDomain`、`ClampedSides`、`ImpactTop`、`ExportBottom`；按位置确认，不依赖易变的边界编号。
3. **几何**：Block 长宽厚 `L,L,h`，位置 `−L/2,−L/2,−h/2`；Sphere 半径 R，球心见上。Finalize 选 **Form Assembly**，保留两个独立物体。建立 Contact Pair：球表面 source、玻璃上表面 destination。两面不能选反或同时选入固定侧面。
4. **玻璃材料**：Blank Material 输入 E、ν、ρ。Solid Mechanics → Linear Elastic Material 只选 GlassDomain。先取消任何人为阻尼，热、塑性、重力均关闭。这样初始能量来自球的动能。
5. **惯性与初值**：在 Solid Mechanics 根节点将 Structural Transient Behavior 改为 **Include inertial terms**。预置 Phase-Field Damage 的默认值是 Quasistatic，必须手动改。玻璃 u/v/w 和速度均为 0。[接口默认值](https://doc.comsol.com/6.3/doc/com.comsol.help.sme/sme_ug_multiphysics.18.49.html)。
6. **刚球**：Solid Mechanics → Rigid Material 选择 SphereDomain，质量由密度和体积得到。刚体自己的 Initial Values 中给中心速度 `(0,0,-v0)`、角速度 0。不要只修改玻璃所在的默认 Initial Values；刚体有独立节点。保持 Z 自由运动，不施加向下的规定运动；否则它是执行器压入，能量输入不再是固定初始动能。[刚体初值](https://doc.comsol.com/6.3/doc/com.comsol.help.sme/sme_ug_solid.07.050.html)。
7. **约束与接触**：ClampedSides → Fixed Constraint。Pairs → Contact 选择所建 pair，先用无摩擦 **Penalty**；显示接触压力/间隙，检查接触力作用反作用。默认 penalty 先试算，随后至少做 0.5×/2× 灵敏度。若使用 `Penalty, dynamic`，需另记录耗散并勾选 Compute viscous contact dissipation；该法可能改变玻璃获得的冲击能，不能用它的数值阻尼“调出好看的裂纹”。[接触设置](https://doc.comsol.com/6.3/doc/com.comsol.help.sme/sme_ug_solid.07.120.html)、[动态接触](https://doc.comsol.com/6.3/doc/com.comsol.help.sme/sme_ug_modeling.05.148.html)。
8. **相场域**：Phase Field in Solids 与 Multiphysics → Phase-Field Damage 都仅选 GlassDomain；球不参与损伤。Parent material 选玻璃 Linear Elastic Material；默认相场变量名 phi。Initial Values=0，外边界维持 No Flux。
9. **AT1 参数**：Phase Field Model → Potential 选 User defined，`Q=3*phi/8`，内部长度 lint，结构张量各向同性系数 `3/4`。参数文件已定义 `Wc0=3*Gc/(16*lint)`；耦合的 Crack driving force 选 User defined，`max(pfdmg1.Ws0,Wc0)*lint/Gc`；Damage evolution 选 Quadratic，Maximum damage=`1-eta`。这些表达式要求默认耦合名 `pfdmg1`；重命名后用本机 Replace Expression 确认。采用上述拉压分裂。这一步参考 6.3 官方 AT1 示例，不需要预裂纹边界。[官方示例与完整步骤](https://doc.comsol.com/6.3/doc/com.comsol.help.models.nsm.dynamic_crack_branching/models.nsm.dynamic_crack_branching.pdf)。
10. **上下界**：如出现 φ 越界，在 Phase Field Model 下添加 Bounds，启用下界 0、上界 1；从默认罚参数开始并记录越界量。Bounds 的 0/1 限制本身不等于防愈合，应另做完整卸载测试。不要用求解后 `cummax` 掩盖物理/历史变量错误。[Bounds 节点](https://doc.comsol.com/6.3/doc/com.comsol.help.sme/sme_ug_phase_field.16.05.html)。
11. **求解前分级验证**：另存“弹性无损伤”试验，先检查球质量、接触时刻、速度、板中心 w 和能量；再在完整耦合模型试算裂纹。做比较时保留两份 case 和 source sidecar。

球冲击下可能先在背面产生弯曲拉裂，也可能形成接触锥裂纹/环裂纹。不能为了满足“中心先破、径向扩展”的展示预期，把不同表面的最大损伤拼成一个没有物理位置的场。

## 5. 网格与求解设置

**不要把 512×512 渲染纹理当成有限元网格。** 1 m 板上一个像素约 1.953 mm；真实细裂缝会小于一个像素。相场带宽由 lint 控制，材质白边只能是另行标注的视觉强化。

初始规划为：玻璃裂纹可能经过的区域 `h_FE≤lint/4=0.5 mm`，沿厚度同样充分分辨；在接触区还需分辨实际接触斑，可细到 0.1–0.25 mm，并以接触斑至少数个单元为准。可采用映射面网格 + swept 厚度层，或检查质量的四面体。位移二阶、相场一阶可作为探索组合，记录离散阶次并做网格比较。

全板用 0.5 mm 网格意味着约 400 万个面单元、16 层厚度，模型规模很大。只加密中心圆域时，**验证范围仅限裂纹仍在该细区内**；损伤前沿进入粗网格即暂停并扩大细区重算。不得靠粗区把裂纹人为挡住。1 m 目标保留，但先做小试件基准和全板无损伤弯曲验证，估算内存/时间后再运行全板断裂。改变 lint 应重新校准，不能仅当加速旋钮。

Study → Time Dependent 勾选几何非线性；Show Default Solver 后使用隐式 Generalized-α。初次联调建议相对容差 `1e-4`，位移尺度 `1e-3 m`、相场尺度 1、位移绝对容差 `1e-8 m`、相场 `1e-6`；能量审核时再收紧。起始步 `2e-8 s`，最大步 `1e-7 s` 为待验证起点。

时间上限来自**动态精度**，不是声称隐式法有显式 CFL 稳定限制：玻璃波速为数千 m/s，应以最小重要单元的波穿越时间和接触上升时间为尺度。即使只输出 64 帧，也可能需要数万内部步。优先让求解器自适应且限制最大步；裂纹突跳处允许继续减小。再将最大步减半，与基准比较萌生时刻、裂纹前沿、峰值接触力、能量和残余位移。

先尝试 Fully Coupled + Direct（PARDISO，如可用）、每次 Newton 迭代更新 Jacobian；困难时采用位移/接触与相场分组的 Segregated 迭代，但每个时间步必须收敛耦合残差，不能只交替一次。若失败，依次检查域和初值、穿透、缩小时间步、改善网格，再调 Newton 阻尼。相场黏性是可选正则化：默认不人为加入；添加时记录时间常数并做趋零敏感性，不能把它当物理慢动作。[COMSOL 损伤求解建议](https://doc.comsol.com/6.3/doc/com.comsol.help.sme/sme_ug_modeling.05.102.html)。

保存密集求解历史用于验证，再挑选 32–64 个代表时刻交付 UE；首次检查可以在 Study 的输出时间填 `range(0,t_end/63,t_end)`。前期接触与快速扩展需要更密输出，尾段可稀。非均匀 times 必须原样进入 metadata。若 64 帧漏掉裂纹扩展，应增加导出帧数/调整采样；不要在 Python 编造新的裂纹前沿。

## 6. 能量、不可逆与结果检查

分别建立玻璃体积积分、球刚体能量、接触面积分及固定边界反力。使用本机 Replace Expression 查找实际变量，不猜测版本相关内部名称。保存每项表达式、单位、积分域、参考/当前体积定义。

本算例无外部驱动、无重力，理想总系统初始能量为 `K0=0.5*m*v0²`。检查

```text
R(t) = [K_glass + K_sphere + U_elastic + E_fracture
        + D_material + D_contact + U_contact_penalty]
       − [K0 + W_external]
```

只计实际启用的项，所有项以初始值作一致零点；接触 penalty 储能和耗散依所用算法选择。**接触功对“球+板”整体是内部交换，不能再作为外部输入加一次。** 固定夹边理想位移为 0，所以反力虽然非零，做功为 0。若改规定球位移，必须加入驱动功；若加入重力，加入相应势能或功，二者不能重复。

裂纹能用 `Gc*pfs.gcl` 的玻璃域体积分（默认名称下）作核查，单位 J；整体模型不要照搬二维对称示例的 ×2、任意厚度系数。耗散不足/失衡不能以逐帧调整材质遮罩弥补。

建议筛查表：初始场为 0；刚球质量/动能吻合；接触前无接触力；接触无不可接受穿透；动能和耗散非负；每个材料点 φ 降幅≤数值容差；卸载后裂纹保留；未破区域弹性回振可解释；总能量残差随时间步及网格加密降低。暂以 |R|/K0≤5% 作进入数据管线的**工程筛查门槛**，不是准确性证明。报告还必须包含网格/时间敏感性和材料校准状态。

## 7. 导出表面和变量

第一版固定导出**背面 ExportBottom（物理 z=−h/2）**，用于捕捉板弯曲背面拉裂。将参考坐标 Z 统一平移为 `z_m=Z+h/2=0`，u/v/w 不作平移。此决定记录在 sidecar；之后改导出面须建立新数据集，不能与旧面混合。对实体全体积数据，请先在 COMSOL 选表面，再送二维转换器。

在 Results → Export → Data 选择对应 Surface dataset、一个时刻、未变形材料坐标、CSV/文本、完整精度。按下表顺序导出，保存为 `frame_000.txt` 等；关闭可改变场的结果平滑/恢复或明确记录。坐标必须是参考 X/Y/Z，不是位移后的 x/y/z。

| 导出列 | 选择/定义 | 单位 |
|---|---|---|
| x,y,z | 材料参考坐标 X/Y/Z | m |
| u,v,w | Displacement field 分量 | m |
| sigma1 | 最大/第一主 Cauchy 应力，明确使用损伤后的应力 | Pa |
| von_mises | 损伤后的 von Mises 应力 | Pa |
| damage | `phi`；声明 `phase_field_phi` | 1 |
| strain_energy | 当前可恢复弹性应变能密度，声明参考/当前体积 | J/m³ |

应力与能量表达式用 **Replace Expression** 从树中选择，并抄到 [`../comsol/export_templates/source.json`](../comsol/export_templates/source.json)。不把同名但意义不同的“未损伤应力”混入。若需要裂纹开口，需沿裂纹法向积分位移梯度或用 CZM 的界面分离量；`phi*lint` 不是物理裂纹宽度。本版本不伪造宽度通道，可另存带定义的派生指标。

本项目标准 CSV 第一行为：

```csv
time_s,node_id,x_m,y_m,z_m,u_m,v_m,w_m,sigma1_Pa,von_mises_Pa,damage,strain_energy_J_m3
```

COMSOL 的原生导出可能有 `%` 注释、没有 node_id，或一次输出多个时刻的宽表。**不要只改扩展名。** 本项目提供 [`../comsol/export_templates/canonicalize_export.py`](../comsol/export_templates/canonicalize_export.py) 将每时刻的固定十列数值表转为标准长表，并通过参考坐标排序生成稳定的采样点 ID；这些 ID 是交换点 ID，不冒称 COMSOL 网格内部节点号。表面节点重复或混合多层时会拒绝，需回 COMSOL 使用唯一表面采样点重新导出。也可用固定坐标点表插值导出，均需记录采样方式。

## 8. 自动化与本机待办

本轮优先交付 GUI 复现步骤及可测试的导出适配器。未提供未经本机确认节点名称的“自动生成真实裂纹”Java 程序。GUI 模型通过基准和卸载验证后，可用 File → Save As → Model File for Java 导出实际节点调用，参数化几何、初速和导出循环；批量运行前每个 case 都保留输入模型 hash、模型源码、COMSOL 版本、求解日志和能量检查。MATLAB 路线只作为有对应许可时的替代。

必须在本机完成：模块签出、官方断裂基准、接触弹性基准、完整 A1 试算、网格/时间/长度尺度敏感性、不可逆与能量检查、真实数据导出。32–64 帧、512×512、UE 60 FPS 是管线/渲染目标，不构成有限元验证结论。真实数据替换流程见 [real_data_replacement.md](real_data_replacement.md)。

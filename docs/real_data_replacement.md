# 用真实 COMSOL 数据替换 synthetic 样例

本流程只替换独立 GlassImpact 项目的数据。现有 `synthetic` 样例保留用于回归测试，不改其来源标签；不改土体项目和旧 GitHub 仓库。

## 1. 先完成模型和物理检查

执行 [COMSOL 建模指南](comsol_model_guide.md)，保存输入/求解模型、版本、模块、参数、求解日志、输出时刻、表面选择、能量与不可逆报告。需要区分 `comsol`（真实求解来源）与 `physical_validation`（是否通过校准/数值验证）；真实求解也可能是未验证试算。

不得把合成 CSV 的 `source_kind` 改成 `comsol`。未损伤的弹性结果应如实输出 damage=0，不能临时叠加程序生成的径向线后继续标记纯 COMSOL 断裂。若制作混合美术版本，应另存并逐通道记录来源；当前 MVP 单一来源管线应继续标为 synthetic。

## 2. 从 COMSOL 导出同一参考表面

导出固定背面参考 `Z=−0.004 m`，按导出模板顺序生成 `frame_000.txt`、`frame_001.txt` 等。每个文件只包含一个时刻，字段为 SI：

```text
x_m y_m z_m u_m v_m w_m sigma1_Pa von_mises_Pa damage strain_energy_J_m3
```

上行只用于说明；数据文件非数值说明行须以 `%` 或 `#` 开头。没有内部时间列，时间来自 manifest。要使用逗号数据将 `delimiter` 改为 `comma`；不要把 COMSOL 的多时刻宽表交给此适配器。

推荐在 `data/raw/comsol_A1_export/` 放置原始文件、填写后的 `source.json` 和 `frame_manifest.json`。模板位于 `comsol/export_templates/`。将 manifest 中的帧名/时间补全；源表面和映射偏移保持一致。模板默认背面 `z_offset_m=+0.004`；如果选上表面，必须同时改为 `−0.004` 并更新 provenance，不能混用上下两面。映射后的 z=0，位移分量不变。

填写所有字段定义和本机实际表达式，填写 `model_sha256`；将 `template_only` 改为 false，`model_status` 改为真实状态，并如实记录各项物理审核是否完成。`damage` 推荐直接导出相场 phi（完整0、损坏1），不要把刚度损失函数与 phi 混用。固定采样点即可，ID 由适配器产生；它们不是 COMSOL 内部节点号。

## 3. 生成标准 CSV，再转换

以下命令在 GlassImpact 根目录执行。使用新输出目录，避免覆盖样例；若目录已存在，请改 case 名称。

```powershell
python comsol/export_templates/canonicalize_export.py --manifest data/raw/comsol_A1_export/frame_manifest.json --output data/raw/comsol_A1
python -m converter --input data/raw/comsol_A1 --output data/processed/comsol_A1 --config config/glass_impact.yaml
```

先按项目 README 安装包，才能在根目录调用 `python -m converter`。适配器检验固定参考坐标、重复点、单面、数值与时间；主转换器再检验场范围、不可逆、缺失字段与覆盖，并固定全时域归一化。检测到 damage 下降时回 COMSOL 查历史/导出设置，不能用逐点历史最大滤波掩盖愈合。

当前二维插值假定 `domain_topology="single_convex_plate_without_holes"`。裂缝不会从本轮固定网格删除，所以此假定适用；若后续产生孔洞、碎片或非凸表面，必须改为带单元拓扑的投影，不能让 Delaunay 跨洞插值。

CSV 是默认方案。可选 VTK 输入需要安装项目的 vtk 可选依赖，逐帧提供同样字段；严格的字段/时间编码以 [data_mapping.md](data_mapping.md) 为准。不要把完整 3D VTK 体积直接送入二维纹理转换器。

## 4. 进入 UE 前对照

检查 metadata 的 source_kind、64帧的真实 times、位移SI范围、应力Pa范围、coverage、hash，以及预览里的起裂时刻和中心 UV=(0.5,0.5)。挑选至少初始、首次损伤、扩展中、末帧四个时刻，与 COMSOL 同一表面、同一色标逐点比较。对左下/右下/左上三个非对称采样点分别比较位移，排除转置或Y翻转。

半精度纹理保存的是全序列统一归一化值；元数据保留原始SI量程。若关键损伤前沿被512网格漏采，先提高采样或纹理分辨率检查，不靠调归一化补救。材质白边/法线是视觉派生值，真实量仍从数据读出。

## 5. 切换 UE 数据并验收

按 [UE 安装说明](ue_setup_guide.md) 让 DataAsset/播放组件指向新的 `metadata.json`；保持相同玻璃本地XY范围、UV0及位移解码。先保留物理位移倍率1，检查正面、斜视和侧面，再切线框看固定拓扑下的形变。摄像机始终看向玻璃中心。

统一时间为 `t_physics = elapsed_game_seconds * PlaybackRate`，以 metadata 的相邻真实 times 插值，不能用简单 `frame_index / FPS` 替代非均匀时间。以20ms物理过程播放1秒为例，PlaybackRate=0.02。界面应同时显示物理毫秒和演示秒；声音/粒子阈值按同一时间更新，每轮触发一次，Reset 重置事件状态。

完成后将画面来源标识改为 **COMSOL / validation status**（仅在确认真实数据加载后），同时保留表面选择、是否慢放和位移倍率。真实求解但未校准的数据应显示“COMSOL 未校准试算”，不能显示“实测”。需要在本机 UE 验证材质导入、图形设置、透明折射、所有视角和阈值声音/Niagara资源；缺少已绑定资源时只验证事件，不能声称声音/颗粒已经呈现。

## 6. 一次试算的交付清单

- 输入模型与求解日志、参数、模块/版本、模型与原始表格 hash。
- 相场/刚度损伤定义、应力定义、导出表面与坐标映射说明。
- 能量、不可逆、时间步/网格/长度尺度对比；失败项如实保留。
- 标准 CSV + source.json、processed 输出 + metadata、独立预览。
- UE 同时刻多角度截图：正面、斜视、侧面、线框；当前帧物理时间和来源可见。

本轮完成的是 synthetic 数据和可替换接口。满足以上步骤后才可把某个 case 记为真实 COMSOL→UE 闭环。

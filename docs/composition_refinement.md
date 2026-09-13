# 玻璃与边框装配及构图修正

本轮修改实验场景的装配、材质、灯光和相机，不改变预计算物理场。数据来源仍为 synthetic。

## 原因与修正

- 旧玻璃半宽 50 cm，旧框内沿为 `52 − 1.75 = 50.25 cm`，四边存在 2.5 mm 实际间隙。
- 旧棋盘位于玻璃后方 48 cm，宽 140 cm。斜视时形成另一块明显偏移的矩形，容易被误认为歪斜的玻璃。
- 四根独立方块的端部重叠、平色材质和拥挤的相机共同强化了粗糙感。

现在由 `AGlassImpactDemoActor` 同时构造玻璃、闭合倒角环框、密封条和细窄前沿。它们共享局部原点与旋转；玻璃仍是同一张 129×129 顶点的物理场显示网格。

| 装配项 | 尺寸 |
|---|---|
| 原始玻璃 | 100×100 cm |
| 主框外尺寸 | 108×108 cm |
| 主框净开口 | 98×98 cm |
| 玻璃压入主框 | 每边 1 cm |
| 主框截面深度 | 局部 Z = −2.4 到 1.4 cm |
| 主框倒角 | 2.5 mm |
| 密封条净开口 | 97.6×97.6 cm |
| 密封条深度 | 局部 Z = −0.03 到 0.42 cm，包覆玻璃 Z=0 表面 |

环框在四角连续连接，密封条与玻璃接触。上述夹框为显示装配，没有重求 COMSOL 的支撑边界。

## 画面设置

移除大棋盘和悬浮中心方块，改为连续渐变背景、短支柱及圆角底座。主框采用带粗糙度的金属材质，密封条使用暗色橡胶；减小裂纹法线扰动和局部折射拉扯。

相机使用 38° 水平视野，斜视俯角较小；正面用于检查平行和接缝，斜视用于观察框深度与胶条。标题只占顶部细栏，时间、倍率与操作位于底栏。

## 验证

几何尺寸及实际世界坐标朝向由场景生成脚本检查，输出 [fixture_geometry_audit.json](fixture_geometry_audit.json)。运行日志另记录 `GLASS_FIXTURE_LOCAL` 和 `GLASS_FIXTURE_FRONT`。C++ 已通过 UE 5.6 编译，最终场景生成通过，0 错误、0 警告。

已检查实际 UE 的 [正面](ue-captures/composition_front.png)、[斜视](ue-captures/composition_oblique.png) 和 [侧视](ue-captures/composition_side.png) 截图：正面四边端正、四角闭合，斜视和侧视中玻璃、胶条与框保持同一装配关系，没有原来的透光缝。裂纹和上下信息栏可见，未遮挡实验面。运行日志显示 front normal=(0,−1,0)，camera-side dot=1；数据加载和材质运行无错误。

画面里的裂纹仍是合成演示；材质精修不代表真实断裂求解完成。材质生成使用 [UE 5.6 MaterialEditingLibrary](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/MaterialEditingLibrary?application_version=5.6)。

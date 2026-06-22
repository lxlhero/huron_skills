---
name: floorplan-blender-render
description: 从建筑平面图纸(JPG)到Blender 3D模型到Web GLB渲染的完整工作流。覆盖Claude vision图纸分析、Blender Python建模、GLB导出、Three.js前端集成、材质调优。适用于多楼层别墅/住宅户型3D可视化。
version: 0.1.0
tags:
  - blender
  - threejs
  - floorplan
  - glb
  - architecture
  - vision
  - mcp
---

# 平面图到3D渲染工作流

适用场景：有建筑平面图纸（JPG/PNG），需要转成可在浏览器中交互的3D户型模型。

## 工作流总览

```
Phase 0: 准备 — 收集所有楼层的JPG图纸
Phase 1: AI图纸分析 — Claude vision 逐张提取房间尺寸/墙体/门窗
Phase 2: Blender建模 — Python脚本批量构建3D墙体/地板/门窗
Phase 3: GLB导出 — 导出为Web可用格式
Phase 4: 前端集成 — Three.js加载GLB + 家具拖放
Phase 5: 材质调优 — 根据用户反馈调整墙体颜色/透明度
```

---

## Phase 1：AI图纸分析

### Claude CLI 调用方式

```bash
# 注意：不能用管道传JPG二进制，必须用文件路径让Claude的Read工具读取
claude -p "Read the image at /path/to/floorplan.jpg. ..." \
  --output-format text \
  --add-dir /path/to/image/dir
```

### Prompt 模板

```
Read the image at <path>. This is the <floor> floor plan.
Extract ALL room labels, ALL dimension numbers (in mm), and describe the wall layout.
Output structured data:
1) Building outer dimensions (width x depth in mm)
2) Every room: name, x position, z position, width, depth (all in meters, convert from mm)
   Use origin at building center.
3) Wall types (exterior vs interior)
4) Door/window positions
5) Stair/elevator locations
```

### 关键注意事项

- **不要** `cat image.jpg | claude -p` — Claude 无法解析管道中的二进制数据
- **必须** `--add-dir` 包含图片目录，让 Claude 能通过 Read 工具访问
- 坐标原点设在建筑中心，方便后续 Blender/Three.js 对齐

---

## Phase 2：Blender 建模

### 环境要求

- Blender 运行中 + Blender MCP 已连接
- 通过 `mcp_blender_execute_blender_code` 执行 Python

### 建模脚本模板

```python
import bpy, os

# 1. 清空旧场景
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for mat in bpy.data.materials:
    bpy.data.materials.remove(mat)

# 2. 创建材质
def make_material(name, color, roughness=0.65, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*color, alpha)
    bsdf.inputs['Roughness'].default_value = roughness
    if alpha < 1.0:
        mat.blend_method = 'BLEND'
    return mat

M_Exterior = make_material('M_Exterior', (0.52, 0.50, 0.46), 0.70)
M_Interior = make_material('M_Interior', (0.65, 0.63, 0.58), 0.65)
M_Floor    = make_material('M_Floor',    (0.76, 0.73, 0.66), 0.55)
M_Glass    = make_material('M_Glass',    (0.72, 0.82, 0.92, 0.3), 0.05)
M_Door     = make_material('M_Door',     (0.55, 0.42, 0.29), 0.30)

# 3. 构建墙体（包围盒法）
# 外墙：沿建筑周长连续，厚 0.25m，高 2.8m
# 内墙：房间分隔，厚 0.15m，高 2.8m
# 每个墙段 = 一个 Cube，位置在墙中心

def add_wall(name, px, py, pz, w, h, d, material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(px, py, pz))
    obj = bpy.context.object
    obj.name = name
    obj.scale = (w/2, h/2, d/2)  # Cube默认2x2x2
    bpy.ops.object.transform_apply(scale=True)
    if obj.data.materials:
        obj.data.materials[0] = material
    else:
        obj.data.materials.append(material)

# 外墙示例（建筑宽7.475m，深11.25m，中心原点）
# add_wall('ExtWall_W', -3.74, 0, 1.65, 0.25, 2.8, 11.25, M_Exterior)

# 4. 地板（每个房间独立，方便后续改色/更换）
def add_floor(name, px, pz, w, d, material):
    bpy.ops.mesh.primitive_plane_add(size=1, location=(px, pz, 0.25))
    obj = bpy.context.object
    obj.name = name
    obj.scale = (w/2, d/2, 1)
    bpy.ops.object.transform_apply(scale=True)
    obj.data.materials.append(material)

# 5. 窗户（玻璃平板）
def add_window(name, px, py, pz, w, h, d):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(px, py, pz))
    obj = bpy.context.object
    obj.name = name
    obj.scale = (w/2, h/2, d/2)
    bpy.ops.object.transform_apply(scale=True)
    obj.data.materials.append(M_Glass)

# 6. 灯光和相机
bpy.ops.object.light_add(type='SUN', location=(8, 5, 10))
bpy.context.object.data.energy = 3
bpy.ops.object.camera_add(location=(-3, -8, 6.25))
bpy.context.object.rotation_euler = (1.1, 0, 0.4)

# 7. 保存 .blend
bpy.ops.wm.save_as_mainfile(filepath='/path/to/villa_1F.blend')
```

### 关键约定

| 项目 | 值 |
|------|-----|
| 外墙厚度 | 0.25m |
| 内墙厚度 | 0.15m |
| 层高 | 2.8m |
| 坐标原点 | 建筑几何中心 |
| 地板 Y 坐标 | 0.25m |
| 墙体 Y 中心 | 1.65m（= 2.8/2 + 0.25） |
| 窗户 Y 中心 | 1.95m（离地1m + 窗高1.2m/2 + 0.25） |

---

## Phase 3：GLB 导出

```python
bpy.ops.object.select_all(action='DESELECT')
for obj in bpy.data.objects:
    if obj.type == 'MESH' and obj.name != 'Ground':  # 排除地面参考平面
        obj.select_set(True)

bpy.ops.export_scene.gltf(
    filepath='/path/to/output.glb',
    export_format='GLB',
    use_selection=True,
    export_materials='EXPORT'
)
```

### 导出要点

- **Selection-only**：只导出建筑网格，排除 Ground、Camera、Light
- **GLB 格式**：单个二进制文件，Three.js `useGLTF` 直接加载
- 文件通常 50-60KB（无家具的建筑壳）

---

## Phase 4：前端 Three.js 集成

### React + @react-three/fiber 模式

```jsx
// 1. Import
import { useGLTF } from '@react-three/drei'

// 2. 按楼层动态加载
function BlenderScene({ floor, furniture, ... }) {
  const gltf = useGLTF(`/models/villa_${floor}.glb`)
  
  return (
    <group>
      <ambientLight intensity={0.45} color="#fff5eb" />
      <directionalLight position={[8, 15, 3]} intensity={0.9} castShadow />
      
      {/* 建筑壳 */}
      <primitive object={gltf.scene} position={[0, 0, 0]} />
      
      {/* 家具层（动态叠加） */}
      {furniture.map(item => <FurnitureModel key={item.id} ... />)}
      
      <OrbitControls
        maxPolarAngle={Math.PI / 2.1}  // 防止翻到底部
        minDistance={3}
        maxDistance={30}
        target={[0, 0, 1.5]}
        enableDamping
      />
    </group>
  )
}
```

### 文件部署

- GLB 文件放在 `frontend/public/models/villa_<floor>.glb`
- Vite 开发服务器自动 serve `public/` 目录
- 前端通过 `/models/villa_1F.glb` 路径加载

---

## Phase 5：材质调优

### 经验值

```
外墙材质：RGB (0.52, 0.50, 0.46), Roughness 0.70, Alpha 1.0
内墙材质：RGB (0.65, 0.63, 0.58), Roughness 0.65, Alpha 1.0
地板材质：RGB (0.76, 0.73, 0.66), Roughness 0.55
玻璃材质：RGB (0.72, 0.82, 0.92), Roughness 0.05, Alpha 0.3
门材质：  RGB (0.55, 0.42, 0.29), Roughness 0.30
```

### 调色原则

- 墙体颜色逐渐加深：先 (0.88,0.86,0.83) → 反馈"太透明" → (0.72,0.70,0.66) → "再深" → (0.52,0.50,0.46)
- Alpha 必须为 1.0（用户不喜欢透明墙）
- Roughness 0.65-0.70（避免过于光滑的反光）

### 常见反馈对应方案

| 用户反馈 | 解决方案 |
|----------|----------|
| "墙太透明了看不舒服" | Alpha → 1.0, 加深 Base Color |
| "再深一点" | 进一步降低 RGB（0.1-0.15 步进） |
| "盖子不要/挡视线" | 移除 Ceiling 对象，不导出天花板 |
| "户型外面有个茶几很丑" | 检查并清空数据库 preset 家具 |
| "初始应该是空户型" | 删除 furniture_placements 表中的预置数据 |

---

## 楼层数据一致性

### 必须保持跨楼层一致

- **楼梯井位置**：所有楼层在同一 x,z 坐标
- **电梯井位置**：同上
- **外墙轮廓**：同一建筑，各层外墙对齐
- **原点**：统一使用建筑几何中心

### 从 Claude 分析中提取的数据结构

```
Building: width=7.475m, depth=11.25m, wall_height=2.8m
Rooms:
  - name: 厨房, x=-3.74, z=3.62, w=2.08, d=2.0, ext_walls: [N,W]
  - name: 客餐厅, x=-1.66, z=-3.22, w=5.39, d=6.42, ext_walls: [S,E]
  ...
```

---

## 陷阱记录

1. **Claude CLI 管道传图失败** — `cat img.jpg | claude -p` 会收到"raw JPEG binary"错误。必须用 `--add-dir` + 文件路径。

2. **Blender 旧场景残留** — 每次建模前必须 `bpy.ops.object.select_all(action='SELECT')` + `delete()`，否则新老对象混杂。

3. **GLB 包含灯光/相机** — 导出时须 `use_selection=True` 排除非建筑对象，否则前端灯光冲突。

4. **前端 GLB 路径不能硬编码** — 必须用模板字符串 `` `/models/villa_${floor}.glb` ``。

5. **OrbitControls 翻到底部** — 设 `maxPolarAngle={Math.PI / 2.1}` 限制相机不下穿地板。

6. **家具预置数据污染** — SQLite `furniture_placements` 表可能有测试数据，部署前清空。

7. **多个楼层并行分析** — 用 `terminal(background=true, notify_on_complete=true)` 同时跑多个 Claude 分析，不用 delegate_task（后者 timeout 短）。

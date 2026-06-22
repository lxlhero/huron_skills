# Villa Floor Plan Measurements

Extracted by Claude vision from JPG architectural drawings.
Source images: `/Users/huron/code/ai_lab/house_work/house_design/`

Coordinate origin: building geometric center. X = width axis, Z = depth axis.
All units in meters unless noted. Wall thickness: exterior 0.25m, interior 0.15m.
Floor height: 2.8m.

## 1F (Ground Floor)
Image: `22f94fd1a1b0e060ba9569215a61cb14.jpg`
Building: 7.475m × 11.25m
11 spaces: living room, dining room, kitchen, etc.

Key dimensions (mm from drawing): 3320, 3830, 6505, 1080, 9970, 4630, etc.

Material: ME exterior (0.52,0.50,0.46), MI interior (0.65,0.63,0.58)

## B2 (Basement 2)
Image: `540d08230b94a4d956282432a88d12fe.jpg`
Building: ~7.48m × 11.225m (right extension beyond standard depth)
5 spaces: 阳台及茶桌, 大厅/主娱乐区, 楼梯间, 观光电梯, 底部空间/停车

Depth chain: left side 9045mm, right side 11225mm
Width chain: 3330 + 240 + 1395 + 240 + 2275 = 7480mm

Room layout (center coords, w×d):
- 阳台及茶桌: (-2.08, -0.79) w3.33×d3.01
- 大厅: (+1.58, -0.91) w4.32×d7.23
- 楼梯: (-2.50, +1.00) w1.88×d1.47
- 电梯: (+0.50, +1.20) ~1.5m²
- 底部空间: (-1.84, +3.74) w5.21×d1.58

## B1 (Basement 1)
Image: `48551352b7db9b8fb75fad213c864327.jpg`
Building: 7.475m × 11.255m (matches 1F contour)
5 spaces: 茶室, 钢化玻璃区, 观光电梯, 操作间, 车库

Width chain: 3405 + 240 + 3830 = 7475mm

Room layout:
- 茶室: (-2.035, -3.063) w3.405×d5.13
- 钢化玻璃区: (+1.823, -4.760) w3.83×d1.735 (glass wall area, needs window glass)
- 电梯: (+1.823, +0.050) ~1.5m²
- 操作间: (-2.035, +3.733) w3.405×d3.79
- 车库: (+1.823, +3.490) w3.83×d3.795

## 2F (Second Floor)
Image: `c8b1536d1cf4cf9e79f8c0be80a1033a.jpg`
Building: L-shape, ~10.79m wide
6 spaces: 北卧室, 铁艺衣柜/落衣架, 楼梯核心, 观光电梯, 主卧, 卫生间

Room layout (approximate):
- 北卧室: (-3.00, -5.50) w4.8×d3.0
- 衣帽间: (-3.30, -1.50) w3.32×d4.81
- 楼梯: (-0.50, -0.80) w3.32×d4.81
- 电梯: (+2.80, -0.80) ~1m²
- 主卧: (+2.90, +2.50) w3.74×d4.81
- 卫生间: (-4.50, +2.50) w1.0×d3.0

## 3F (Third Floor)
Image: `98ef69d523bf2d0c6371d7cf5f8a0779.jpg`
Building: L-shape, ~13.2m × 7.66m
8 spaces: 上层露台/大房间, 楼梯间, 观光电梯, 卫生间/砖砌浴缸, 洗衣机区, 成品衣柜, 卧室, 壁龛

Annotation values (mm): 2060, 4049, 1317, 1000, 1550, 2432, 832

Room layout:
- 上层露台: (0, -2.77) w13.2×d2.06
- 楼梯: (-2.5, +0.5) ~3m²
- 电梯: (+1.5, +0.2) ~1.4m²
- 卫生间: (-5.0, +2.0) w1.0×d3.1
- 洗衣区: (-4.2, +2.0) ~0.8m²
- 衣柜: (-1.2, +2.4) w2.0×d2.432
- 卧室: (+3.3, +1.6) w4.049×d3.7
- 壁龛: (-5.8, +3.2) w0.8×d0.832

## GLB Export Sizes
| Floor | GLB Size |
|-------|----------|
| B2    | 13 KB    |
| 2F    | 16 KB    |
| B1    | 19 KB    |
| 3F    | 21 KB    |
| 1F    | 54 KB    |

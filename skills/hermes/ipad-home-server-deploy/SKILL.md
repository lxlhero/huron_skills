---
name: ipad-home-server-deploy
description: Deploy a FastAPI+React PWA on a home Mac, expose it to iPad via Tailscale Funnel. Covers architecture, GZip, code-splitting, auth, error handling, cache invalidation, and common pitfalls.
---

# iPad 家庭服务部署实战

> 把 Mac 上的 FastAPI+React 应用通过 Tailscale Funnel 暴露给 iPad，实现 PWA"类原生 App"体验。
> 案例项目：装修管家（house_design_app），React 19 + Vite 8 + FastAPI + SQLite。

---

## 架构总览

```
  iPad (Safari/PWA)             Mac (宿主机)
  ┌──────────────┐            ┌─────────────────┐
  │ PWA 全屏打开  │  HTTPS    │ uvicorn :8765    │
  │ 用户名+密码   │◄──────────│ ├ /api/* → 业务   │
  └──────────────┘  Funnel    │ └ /*    → React  │
                              │ GZip + 代码分割  │
                              └─────────────────┘
```

核心原则：**单端口、单域名、零成本、零运维**。

---

## 一、公网暴露：Tailscale Funnel

### 为什么选 Tailscale Funnel

| 方案 | 域名 | 成本 | 适合 |
|------|------|------|------|
| Tailscale Funnel | `xxx.ts.net` 永久固定 | ¥0 | ⭐ 首选 |
| CF Tunnel + 域名 | 自定义域名 | ~¥7/年 | 进阶 |
| trycloudflare | 每次重启随机变 | ¥0 | ❌ 不适合生产 |

### 安装和配置

```bash
# 1. 安装（需 sudo，手动执行）
brew install --cask tailscale

# 2. 启动并登录（弹出浏览器授权 GitHub/Google）
tailscale up

# 3. 验证
tailscale status
# 输出: 100.x.x.x  macbook-pro  yourname@  macOS  -

# 4. 开启 Funnel（需先在管理台启用）
#    访问 https://login.tailscale.com/f/funnel 开通
tailscale funnel --bg 8765

# 输出域名就是公网地址:
# https://macbook-pro.tailXXXXX.ts.net
```

### 常见坑

- Funnel 首次使用需在 Tailscale 管理台手动启用（免费）
- 域名里的 `tailXXXXX` 段是 tailnet 标识，和登录账号名不一定相同
- 域名永久不变，即使 Mac 重启、网络切换
- 走 DERP 中继，日本/新加坡节点延迟 +40~80ms

---

## 二、Python 环境坑

在 Mac 上 `pip` 可能指向损坏的旧 Python，务必找到正确的 Python：

```bash
which python3          # 可能返回多个
which pip3             # 可能已损坏
conda info --envs      # 如果有 conda
```

**教训**：始终用绝对路径的 Python 和 pip：

```bash
/Users/xxx/miniconda3/bin/python -m uvicorn ...
/Users/xxx/miniconda3/bin/pip install -r requirements.txt
```

**在启动脚本中**，如果使用后台进程，`PATH` 可能不同，必须用绝对路径。

`caffeinate` 命令在某些 shell 环境中不可用（非交互式 bash），使用时注意 fallback。

---

## 三、单端口：FastAPI serve 前端静态文件

### 原理

开发模式双端口（Vite :5173 + uvicorn :8765），生产模式合二为一。

```python
# backend/app/main.py
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")

# 显式根路由（SPA 入口）
@app.get("/")
async def serve_root():
    with open(os.path.join(STATIC_DIR, "index.html"), "r") as f:
        return HTMLResponse(content=f.read())

# SPA 通配路由（必须在所有 /api/* 路由之后）
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    if full_path.startswith("api/"):  # 安全守卫
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    file_path = os.path.join(STATIC_DIR, full_path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    # SPA fallback
    with open(os.path.join(STATIC_DIR, "index.html"), "r") as f:
        return HTMLResponse(content=f.read())
```

### 关键点

- StaticFiles mount 必须在所有 API 路由之后，否则吞噬 /api/* 请求
- 显式注册 `/` 路由比依赖通配更可靠
- 加双重安全守卫防止 `/api/` 路径被 SPA fallback 拦截
- 生产模式判断：`os.path.isdir(STATIC_DIR)` 存在 → 挂载前端

---

## 四、性能优化

### GZip 压缩（必须）

构建产物 1.6MB → gzip 后 ~460KB → 启用中间件后实际传输 460KB。

```python
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

**效果**：1.6MB → 450KB（72% 减少），iPad 加载从 30 秒 → 5~10 秒。

### 代码分割（强烈推荐）

首屏只加载必要代码，重页面按需加载：

```jsx
import { lazy, Suspense } from 'react'

const FloorPlan = lazy(() => import('./pages/FloorPlan'))  // Three.js ~1MB
const Items = lazy(() => import('./pages/Items'))
const Import = lazy(() => import('./pages/Import'))

// 路由中包裹 Suspense
<Route path="floorplan" element={
  <Suspense fallback={<PageLoading />}><FloorPlan /></Suspense>
} />
```

**效果**：首屏 457KB → 183KB（60% 减少），FloorPlan 只在点击时加载 268KB。

### index.html 预加载占位

JS 下载期间展示 loading 动画，避免白屏：

```html
<div id="root">
  <div id="app-loading">
    <div class="icon">🏠</div>
    <div class="spinner"></div>
    <div>装修管家加载中…</div>
  </div>
</div>
<style>/* spinner CSS */</style>
```

React 挂载后 `#root` 内容被替换，占位自动消失。

---

## 五、认证：最简 JWT

### 后端（FastAPI 中间件）

```python
# auth.py
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

HOUSE_USER = os.getenv("HOUSE_USER", "mama")
HOUSE_PASS = os.getenv("HOUSE_PASS", "change-me-please")
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))

class AuthMiddleware(BaseHTTPMiddleware):
    PUBLIC_PATHS = {"/api/auth/login", "/api/health"}

    async def dispatch(self, request, call_next):
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)
        token = request.headers.get("Authorization", "").replace("Bearer ", "") \
                or request.cookies.get("house_token", "")
        if not token or not verify_token(token):
            return JSONResponse(status_code=401, content={"detail": "请先登录"})
        return await call_next(request)
```

### 前端

```js
// api.js
async function request(url, options = {}) {
  const token = localStorage.getItem('house_token') || ''
  const res = await fetch(`${API}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }
  })
  if (res.status === 401) {
    localStorage.removeItem('house_token')
    window.location.href = '/login'
  }
  return res.json()
}
```

### 凭据永久存储

用 `.env` + `python-dotenv` 自动加载，避免每次设环境变量：

```
# backend/.env
HOUSE_USER=malingling
HOUSE_PASS=941102
```

注意：`.env` 需加入 `.gitignore`。

---

## 六、错误处理模式

### 白屏的原因和修复

React 组件中 **未捕获的异常** 会导致白屏（React 19 尤其严格）。

**模式：加载 → 错误 → 重试**

```jsx
const [loading, setLoading] = useState(true)
const [error, setError] = useState(null)

useEffect(() => {
  fetchData()
    .then(data => { setData(data); setError(null) })
    .catch(err => setError(err.message))
    .finally(() => setLoading(false))
}, [])

if (error) return <ErrorView message={error} onRetry={fetchData} />
if (loading) return <LoadingSpinner />
return <ContentView data={data} />
```

### 常见白屏原因

| 原因 | 症状 | 修复 |
|------|------|------|
| API 调用没带 token → 401 | 白屏 / 永远转圈 | 所有 fetch 加 `Authorization` header |
| API 500 | 白屏 | 查后端日志 `NameError` / `ImportError` |
| Promise 无 catch | 永远 loading | `.finally(() => setLoading(false))` |
| 懒加载 chunk 404 | 白屏 | 检查 dist 文件存在，清 CDN/浏览器缓存 |
| 浏览器缓存旧 JS | 白屏 | 清缓存 + SW 版本号升级（`house-v1` → `house-v2`） |

### 超时处理

```jsx
const controller = new AbortController()
const timeout = setTimeout(() => controller.abort(), 15000)

fetch(url, { signal: controller.signal })
  .catch(err => {
    if (err.name === 'AbortError') setError('网络超时，请检查网络后刷新')
  })
  .finally(() => clearTimeout(timeout))
```

---

## 七、缓存失效

构建后 JS 文件名变化（hash），但浏览器/Service Worker 可能缓存旧 HTML。

**修复**：

1. Service Worker 版本号升级：
   ```js
   const CACHE_NAME = 'house-v2';  // 每次大更新 +1
   ```

2. iPad 用户操作：
   - Safari：长按刷新 → "重新载入而不使用缓存"
   - Chrome：设置 → 隐私 → 清除浏览数据 → 缓存的图片和文件
   - PWA 主屏幕：设置 → Safari → 高级 → 网站数据 → 删域名

---

## 八、进程管理

### 启动脚本必须包含清理逻辑

```bash
# 先杀旧进程
OLD_PID=$(lsof -ti:8765 2>/dev/null)
if [ -n "$OLD_PID" ]; then
  kill -9 $OLD_PID 2>/dev/null
  sleep 1
fi
# 再启动新进程
```

### Mac 休眠策略

合盖休眠 → 服务不可达。修复：
- 系统设置 → 电池 → 选项 → 开启"防止自动睡眠"
- 或用 `caffeinate -i` 包裹 uvicorn（部分环境不可用）

### 开机自启（LaunchAgent）

```xml
<!-- ~/Library/LaunchAgents/com.xxx.plist -->
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
```

`launchctl load ~/Library/LaunchAgents/com.xxx.plist` 注册。

注意：Hermes Agent 的沙箱环境可能无法执行 `launchctl`，需用户手动执行。

---

## 九、检查清单

部署前确认：

- [ ] `pip install -r requirements.txt` 用正确的 Python
- [ ] `.env` 文件存在且包含 `HOUSE_USER` / `HOUSE_PASS`
- [ ] `python-dotenv` 在 requirements.txt 中
- [ ] `frontend/dist/` 已构建（`npm run build`）
- [ ] 后端启动：`python -m uvicorn app.main:app --host 0.0.0.0 --port 8765`
- [ ] `curl http://localhost:8765/api/health` 返回 200
- [ ] `curl http://localhost:8765/` 返回 HTML（非 404）
- [ ] 所有 API 调用带 `Authorization: Bearer <token>` header
- [ ] GZipMiddleware 已注册
- [ ] 所有页面有 error/loading 状态处理
- [ ] Service Worker 缓存版本号已更新
- [ ] Tailscale Funnel 已启用：`tailscale funnel --bg 8765`
- [ ] iPad 清缓存后测试

---

## 十、踩坑记录

1. **pip 损坏**：`/usr/local/bin/pip` 指向已卸载的 Python 3.7 → 用 conda base 的 pip 绝对路径
2. **端口冲突**：旧 uvicorn 进程残留 → 启动脚本先 `lsof -ti:8765 | xargs kill -9`
3. **BudgetConfig NameError**：dashboard.py 少 import → 查日志 `NameError: name 'BudgetConfig' is not defined`
4. **版本管理白屏**：fetch 没带 token → 401 → 未处理的异常导致组件崩溃
5. **iPad 白屏**：SW 缓存旧 HTML（引用已删除的旧 JS hash）→ 升级 SW 版本号 + 清缓存
6. **Funnel 延迟高**：DERP 中继可能绕日本/新加坡 → GZip + 代码分割弥补
7. **caffeinate 不可用**：某些 shell 环境 PATH 不完整 → 直接 uvicorn 启动，靠系统设置防休眠
8. **launchctl 沙箱限制**：Hermes Agent 无法执行 → 让用户手动 `launchctl load`
9. **加载永远转圈**：Promise.all 无 catch → 加 `.finally(() => setLoading(false))`
10. **login 接口 500**：`python-dotenv` 未安装 → 但 auth.py 有 try/except 保护，使用默认值即可

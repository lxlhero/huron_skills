# Deploy Template (Chinese)

```markdown
# <项目中文名> Demo 平台 - 部署说明

## 系统要求

- 操作系统：Windows 10+ / macOS 12+ / Linux
- Docker Desktop（[下载地址](https://www.docker.com/products/docker-desktop/)）
- 可用磁盘空间：≥ 2GB

## 部署步骤

### 第一步：导入镜像

```bash
docker load -i <项目中文名>-镜像.tar.gz
```

### 第二步：启动服务

```bash
docker run -d \
  -p 3000:80 \
  -v <project>-data:/app/data \
  --name <project>-demo \
  <image-name>:latest
```

### 第三步：访问平台

打开浏览器访问：**http://localhost:3000**

- 默认账号：admin
- 默认密码：任意密码即可登录（演示环境）

## 常用操作

### 停止服务
```bash
docker stop <project>-demo
```

### 启动服务
```bash
docker start <project>-demo
```

### 重启服务
```bash
docker restart <project>-demo
```

### 查看日志
```bash
docker logs <project>-demo
```

## 数据说明

- 所有数据存储在 Docker volume `<project>-data` 中
- 停止/删除容器不会丢失数据
- 备份数据：`docker cp <project>-demo:/app/data ./data-backup/`

## 升级指南

1. `docker stop <project>-demo`
2. `docker rm <project>-demo`
3. 执行新版本部署步骤
4. 数据自动保留（volume 已存在不会重建）

## 常见问题

**Q: 端口 3000 已被占用？**
修改 `-p 3000:80` 为其他端口，如 `-p 8080:80`，然后访问 http://localhost:8080

**Q: 容器无法启动？**
检查日志：`docker logs <project>-demo`

**Q: 数据会丢失吗？**
不会。数据存储在独立 volume 中，删除容器不会影响数据。

---

技术支持：请联系项目负责人获取帮助。
```

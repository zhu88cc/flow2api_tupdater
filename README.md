# Flow2API Token Updater v2.0

多 Profile 管理版 - Docker + noVNC + Playwright

## 特性

- 🖥️ **Web 管理界面** - 可视化管理多个 Google 账号
- 🔐 **密码保护** - 管理界面和 VNC 都需要密码
- 👥 **多 Profile 支持** - 每个账号独立浏览器 profile
- 🔄 **持久化登录** - 重启不丢失登录状态
- ⏰ **定时自动同步** - 批量提取并推送 Token

## 一键部署

```bash
git clone https://github.com/genz27/flow2api.git && cd flow2api/docker-vnc && docker compose up -d --build
```

部署后访问: `http://你的IP:8080`

## 更新升级

```bash
cd ~/token-updater/flow2api && git pull && cd docker-vnc && docker compose down && docker compose build --no-cache && docker compose up -d
```

## 密码配置

| 服务 | 环境变量 | 默认值 | 说明 |
|------|----------|--------|------|
| 管理界面 | `ADMIN_PASSWORD` | `admin123` | Web 管理界面登录密码 |
| VNC | `VNC_PASSWORD` | `flow2api` | noVNC 远程桌面密码 |

修改密码：编辑 `.env` 文件或 `docker-compose.yml`

```bash
# 创建 .env 文件
cat > .env << EOF
ADMIN_PASSWORD=你的强密码
VNC_PASSWORD=你的VNC密码
FLOW2API_URL=http://你的Flow2API地址:8000
CONNECTION_TOKEN=从Flow2API后台获取
EOF
```

## 端口说明

| 端口 | 用途 |
|------|------|
| 8080 | Web 管理界面 |
| 6080 | noVNC 远程桌面 |
| 5900 | VNC 端口 (可选) |

## 使用流程

1. 访问 `http://你的IP:8080` 登录管理界面
2. 点击「新建 Profile」创建账号
3. 点击「登录」按钮，在 VNC 中完成 Google 登录
4. 点击「同步」将 Token 推送到 Flow2API

## API 接口

```bash
# 登录
POST /api/login {"password": "xxx"}

# Profile 管理
GET    /api/profiles
POST   /api/profiles {"name": "account1"}
DELETE /api/profiles/{id}

# 操作
POST /api/profiles/{id}/launch  # 启动浏览器
POST /api/profiles/{id}/login   # 打开登录页
POST /api/profiles/{id}/sync    # 同步 Token
POST /api/sync-all              # 同步全部
```

## 目录结构

```
docker-vnc/
├── profiles/     # 浏览器数据 (持久化)
├── data/         # SQLite 数据库
├── logs/         # 日志
└── docker-compose.yml
```

## 安全建议

1. 修改默认密码 `ADMIN_PASSWORD` 和 `VNC_PASSWORD`
2. 使用防火墙限制 6080/8080 端口访问
3. 建议配合 Nginx 反向代理 + HTTPS

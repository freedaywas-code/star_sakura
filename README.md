# 星漫

一个按前后端分离整理的动漫画廊/约稿平台项目。前端保留为静态 HTML，后端使用 Django + Django REST framework。

## 一键运行

推荐使用根目录的跨平台启动脚本，Windows、macOS、Linux 都一样：

```bash
python run.py
```

Windows 也可以双击或运行：

```bat
start.bat
```

macOS/Linux 也可以运行：

```bash
sh start.sh
```

它会自动完成：

- 创建 `.venv` 虚拟环境
- 安装 `backend/requirements.txt`
- 生成并执行数据库迁移
- 启动 Django 后端
- 启动前端静态页面服务

启动后访问：

- 前端页面：`http://127.0.0.1:5173`
- 后端 API：`http://127.0.0.1:8000`
- 健康检查：`http://127.0.0.1:8000/api/health/`

默认管理员账号：

- 用户名：`admin`
- 密码：`admin123456`

前端权限规则：

- 未登录时会进入独立登录/注册页面，不能发布或编辑作品。
- 原页面自带画作归属 `admin`。
- 普通用户只能发布新作品，并编辑/删除自己发布的新作品。
- 只有管理员可以修改或删除原页面自带画作。
- 登录界面支持“登录 / 注册”切换，注册需要用户名、邮箱、邮箱密码、用户密码和确认密码。
- 画作图片点击会放大预览；编辑/删除按钮只对创作者或管理员显示。
- “我”页面可以编辑性别、生日、个性签名，查看自己发布的画作和提交的作画委托，并支持切换账号。
- “我”页面可以查看粉丝和关注列表；作品作者、评论者及委托参与者均可进入公开个人主页并发起私信。
- 未互关时，每位用户向同一对象最多发送 3 条私信（双方方向分别计数）；互相关注后不限条数，取消互关后恢复历史累计限制。
- 委托大厅支持画师报价、更新或撤回报价；发布者可比较报价并选定画师，也可搜索指定画师发送定向邀请。
- 定向邀请只能由受邀画师接受或拒绝；成交后会自动关闭该委托的其他报价和邀请。
- AI 助手在同一个会话中同时负责日常聊天与站内检索，会根据当前问题和前文自动决定是否检索真实在售作品、匹配可承接的开放委托，或为用户本人的开放委托基于画师公开资料匹配候选人；预算条件作为硬过滤，不会用超出预算的结果凑数。
- AI 返回的作品、委托和画师候选项均来自当前站内真实数据；结果卡可打开委托详情或画师公开主页。画师匹配只是基于公开资料的参考，不代表对方必然有档期或接单。
- AI 不会泄露其他用户的报价、邀请留言或成交价，也不会代用户执行报价、邀请、选中画师等操作。
- AI 平台问答覆盖账号与密码、站内搜索、作品互动、关注与私信、委托报价与邀请、智能体模型设置等已有功能。未配置模型时仍提供连贯的基础聊天和本地检索，不会把兴趣语境中的“粉丝”误判成站内粉丝功能。
- AI 助手会显示当前回复来源：`联网 AI`、`站内本地回答` 或 `联网失败 · 本地回答`；明确条件没有匹配结果时不会再用无关作品凑数。
- 每位用户都可以在“我 → 设置 → 智能体模型”中选择站点官方模型，或接入自己的 OpenAI-compatible 模型；无论选择哪一种，都会复用同一套聊天、站内检索、候选数据校验和平台问答能力。
- “我”页面底部的设置可修改用户密码：必须输入旧密码，新密码至少 8 位；当前不支持邮箱验证码找回。

如果依赖已经安装过，可以跳过安装：

```bash
python run.py --skip-install
```

只启动后端：

```bash
python run.py --no-frontend
```

自定义端口：

```bash
python run.py --backend-port 9000 --frontend-port 3000
```

## Docker 运行

如果电脑上有 Docker，可以用容器运行后端：

```bash
copy backend\.env.example backend\.env
cd docker
docker compose up --build
```

macOS/Linux 请将第一行换成 `cp backend/.env.example backend/.env`。Docker 会读取根目录下的 `backend/.env`，请按需填写数据库和 AI 配置。

后端地址：

```text
http://127.0.0.1:8000
```

前端是静态文件，可以直接打开：

```text
frontend/index.html
```

也可以回到根目录用：

```bash
python run.py --no-frontend
```

## 生产与高并发优化

项目现在提供 `configs.settings.prod` 生产配置，并在 Docker 部署中使用 Postgres、Redis 和 Gunicorn：

- Postgres 替代 SQLite，支持更高并发写入和更稳定的数据持久化。
- Redis 用于缓存与限流计数，降低公开列表接口对数据库的压力。
- Gunicorn 使用多 worker + 多线程运行 Django，避免生产环境使用 `runserver`。
- 登录、匿名访问和写操作都配置了 DRF 限流，防止接口被高频请求拖垮。
- 下单、接单、点赞、定制状态流转使用事务与行锁，避免并发覆盖数据。
- 上传图片增加了格式与大小限制，默认最大 5MB。

生产环境建议至少设置：

```env
DJANGO_SETTINGS_MODULE=configs.settings.prod
DJANGO_SECRET_KEY=replace-with-a-long-random-secret
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=example.com,www.example.com
CORS_ALLOWED_ORIGINS=https://example.com,https://www.example.com
CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
DATABASE_ENGINE=postgresql
POSTGRES_DB=star_sakura
POSTGRES_USER=star_sakura
POSTGRES_PASSWORD=replace-with-a-strong-password
POSTGRES_HOST=db
POSTGRES_PORT=5432
REDIS_URL=redis://redis:6379/1
SECURE_SSL_REDIRECT=true
SECURE_HSTS_SECONDS=31536000
PUBLIC_API_CACHE_TIMEOUT=30
DRF_ANON_THROTTLE_RATE=120/min
DRF_USER_THROTTLE_RATE=1200/min
DRF_LOGIN_THROTTLE_RATE=10/min
DRF_WRITE_THROTTLE_RATE=120/min
AI_CREDENTIAL_ENCRYPTION_KEY=replace-with-a-stable-fernet-key
AI_DNS_TIMEOUT=5
AI_DNS_MAX_CONCURRENCY=2
AI_CUSTOM_MAX_CONCURRENCY=4
AI_OFFICIAL_MAX_CONCURRENCY=4
DRF_AI_SETTINGS_THROTTLE_RATE=30/min
DRF_AI_SETTINGS_TEST_THROTTLE_RATE=5/min
```

## 手动运行后端

```bash
cd backend
python -m venv ../.venv
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe manage.py makemigrations
..\.venv\Scripts\python.exe manage.py migrate
..\.venv\Scripts\python.exe manage.py runserver
```

macOS/Linux 使用：

```bash
cd backend
python3 -m venv ../.venv
../.venv/bin/python -m pip install -r requirements.txt
../.venv/bin/python manage.py makemigrations
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py runserver
```

## 环境变量

复制示例文件后可按需修改：

```bash
copy backend\.env.example backend\.env
```

macOS/Linux：

```bash
cp backend/.env.example backend/.env
```

常用配置：

- `DJANGO_SECRET_KEY`：Django 密钥
- `DJANGO_DEBUG`：是否开启调试模式
- `DJANGO_ALLOWED_HOSTS`：允许访问的主机名，用逗号分隔
- `CORS_ALLOW_ALL_ORIGINS`：开发阶段允许跨域
- `SQLITE_NAME`：SQLite 数据库文件路径
- `AI_API_KEY`：平台官方 AI 服务密钥；留空时 AI 助手使用站内数据执行本地推荐
- `AI_API_BASE`：平台官方 OpenAI-compatible API 地址，默认使用智谱开放平台
- `AI_MODEL`：平台官方模型名称，默认 `glm-4-flash`
- `AI_CREDENTIAL_ENCRYPTION_KEY`：用于加密用户自定义模型密钥的稳定 Fernet 密钥；开发环境留空时从 `DJANGO_SECRET_KEY` 派生，生产环境必须单独配置并妥善备份
- `AI_API_TIMEOUT`：上游 AI 请求超时秒数
- `AI_DNS_TIMEOUT`：解析自定义模型域名的最长等待秒数
- `AI_DNS_MAX_CONCURRENCY`：每个后端进程同时执行的模型域名解析上限
- `AI_CUSTOM_MAX_CONCURRENCY`：每个后端进程同时调用用户自定义模型的上限
- `AI_OFFICIAL_MAX_CONCURRENCY`：每个后端进程同时调用官方模型的上限
- `AI_MAX_INPUT_LENGTH`：单条用户消息最大字符数
- `AI_MAX_OUTPUT_LENGTH`：单次模型输出最大字符数
- `DRF_AI_CHAT_THROTTLE_RATE`：每位用户调用 AI 对话接口的频率限制
- `DRF_AI_SETTINGS_THROTTLE_RATE`：每位用户读取或修改模型设置的频率限制
- `DRF_AI_SETTINGS_TEST_THROTTLE_RATE`：每位用户测试模型连接的频率限制

不要把真实 `AI_API_KEY` 或 `AI_CREDENTIAL_ENCRYPTION_KEY` 提交到仓库。`backend/.env` 已被 Git 忽略，适合保存本机配置。生产环境不要随意更换凭据加密密钥，否则已保存的用户模型密钥将无法解密。
可使用 `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` 生成生产环境的 Fernet 密钥，然后仅保存到部署环境变量或未纳入 Git 的 `backend/.env`。
“官方模型”使用服务器 `backend/.env` 中的 `AI_API_*` 配置；“自定义模型”只接受公网 HTTPS 的 OpenAI-compatible Chat Completions 接口，用户密钥在后端加密保存且接口永不回传明文。连接私网、localhost、带 URL 凭据或查询参数的地址会被拒绝，以避免服务器端请求伪造风险；更换 API 服务主机或端口时必须重新输入密钥，旧服务商密钥不会被转发到新地址。
配置第三方 AI 服务后，当前对话内容、用户偏好标签以及候选作品、委托和画师的公开资料会被发送给该服务用于生成回复；未配置模型时所有检索与推荐均在本地完成。测试连接会向所选服务发起一次最小模型请求，可能产生少量供应商用量。
`run.py`、Docker 以及直接运行 `manage.py`/IDE 调试都会读取 `backend/.env`。如果 AI 页面显示“未连接模型”，可以直接点击该状态跳转到“我 → 设置 → 智能体模型”；使用官方模型时请确认 `backend/.env` 存在且 `AI_API_KEY` 不为空，再重启服务。

## 项目结构

```text
star_sakura/
├── backend/
│   ├── apps/
│   │   ├── users/
│   │   ├── artworks/
│   │   ├── orders/
│   │   ├── custom/
│   │   ├── reviews/
│   │   └── recommendations/
│   ├── common/
│   ├── configs/
│   ├── media/
│   ├── static/
│   ├── manage.py
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── docker/
│   ├── docker-compose.yml
│   └── .env.example
├── run.py
├── start.bat
├── start.sh
├── .gitignore
└── README.md
```

## 主要接口

- `POST /api/users/register/`：注册
- `POST /api/users/login/`：登录，返回 JWT
- `GET /api/users/me/`：当前用户信息
- `GET /api/users/profiles/{用户名或ID}/`：公开个人主页
- `POST|DELETE /api/users/profiles/{用户名或ID}/follow/`：关注或取消关注
- `GET /api/users/followers/`：我的粉丝
- `GET /api/users/following/`：我关注的人
- `GET /api/users/messages/conversations/`：私信会话与未读数
- `GET|POST /api/users/messages/{用户名或ID}/`：读取或发送私信
- `POST /api/users/messages/{用户名或ID}/read/`：标记会话已读
- `GET /api/artworks/?search=关键词`：画作搜索
- `POST /api/artworks/`：发布画作
- `POST /api/orders/`：下单购买
- `POST /api/orders/{id}/accept/`：卖家接单
- `POST /api/custom/`：提交线上定制
- `GET|POST|DELETE /api/custom/{id}/bids/`：查看、提交/更新或撤回报价
- `POST /api/custom/{id}/select-bid/`：发布者选中报价
- `GET|POST /api/custom/{id}/invitations/`：查看或发送定向邀请
- `POST /api/custom/{id}/respond-invitation/`：受邀画师接受或拒绝
- `GET /api/custom/artists/?search=关键词`：搜索可邀请画师
- `POST /api/custom/{id}/set_progress/`：更新定制进度
- `POST /api/recommend/chat/send/`：发送 AI 消息并返回完整响应
- `POST /api/recommend/chat/stream/`：发送 AI 消息并通过 SSE 流式返回
- `GET /api/recommend/chat/history/?conversation_id=UUID`：读取指定 AI 会话历史
- `POST /api/recommend/chat/new/`：创建新的 AI 会话
- `POST /api/recommend/chat/clear/`：清空指定 AI 会话
- `GET /api/recommend/chat/conversations/`：查看当前用户的 AI 会话列表
- `GET|PUT|DELETE /api/recommend/settings/`：读取、保存或重置当前用户的模型来源与自定义配置；密钥只写入、不回传
- `POST /api/recommend/settings/test/`：测试当前已选模型的连接状态
- `GET /api/reviews/`：查看评价

统一返回格式：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

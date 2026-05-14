# 星野樱的动漫工作室

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
- “我”页面底部的设置可以通过旧密码或邮箱密码修改用户密码。

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
cd docker
docker compose up --build
```

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

## 项目结构

```text
star_sakura/
├── backend/
│   ├── apps/
│   │   ├── users/
│   │   ├── artworks/
│   │   ├── orders/
│   │   ├── custom/
│   │   └── reviews/
│   ├── common/
│   ├── configs/
│   ├── media/
│   ├── static/
│   ├── manage.py
│   └── requirements.txt
├── frontend/
│   └── index.html
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
- `GET /api/artworks/?search=关键词`：画作搜索
- `POST /api/artworks/`：发布画作
- `POST /api/orders/`：下单购买
- `POST /api/orders/{id}/accept/`：卖家接单
- `POST /api/custom/`：提交线上定制
- `POST /api/custom/{id}/accept/`：接定制单
- `POST /api/custom/{id}/set_progress/`：更新定制进度
- `GET /api/reviews/`：查看评价

统一返回格式：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

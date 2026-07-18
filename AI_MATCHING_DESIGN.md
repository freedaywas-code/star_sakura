# AI 辅助画师匹配功能设计文档

## 1. 需求分析

### 1.1 背景
当前平台的定制委托流程中，需求方发布委托后需要手动搜索和邀请画师，效率较低且难以精准匹配。通过引入 AI 辅助匹配功能，系统可以根据需求方的描述、参考图等信息，自动分析并推荐最适合的画师，提升委托匹配效率和成功率。

### 1.2 功能目标
- **智能推荐**：AI 根据委托需求（描述、参考图、类型、预算）自动推荐合适的画师
- **风格匹配**：基于画师已发布作品的画风、标签、技能进行相似度分析
- **精准匹配**：综合考虑画风契合度、技能匹配度、历史接单情况等多维度因素

### 1.3 使用场景
1. **发布委托时**：需求方提交委托后，系统自动展示 AI 推荐的画师列表
2. **委托详情页**：需求方可随时触发 AI 重新匹配
3. **邀请画师时**：提供 AI 推荐作为参考

---

## 2. 技术方案

### 2.1 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 Frontend                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ 发布委托页面    │  │ 委托详情页面    │  │ 邀请画师页面    │ │
│  │ (触发匹配)      │  │ (查看推荐)      │  │ (AI推荐列表)    │ │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │
└───────────┼────────────────────┼────────────────────┼──────────┘
            │                    │                    │
            ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                        后端 Backend                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │            AI Matching Service                          │   │
│  │  ┌──────────────────┐  ┌────────────────────────────┐  │   │
│  │  │ Prompt 构建模块   │  │ 画师特征提取模块           │  │   │
│  │  │ - 需求描述解析    │  │ - 作品风格分析             │  │   │
│  │  │ - 参考图分析      │  │ - 技能标签提取             │  │   │
│  │  │ - 匹配条件生成    │  │ - 历史接单记录             │  │   │
│  │  └────────┬─────────┘  └──────────────┬─────────────┘  │   │
│  │           │                           │                 │   │
│  │           ▼                           ▼                 │   │
│  │  ┌─────────────────────────────────────────────────┐    │   │
│  │  │           AI 推理模块                            │    │   │
│  │  │  - 调用大模型进行智能匹配                         │    │   │
│  │  │  - 返回匹配结果和置信度                          │    │   │
│  │  └──────────────────────┬──────────────────────────┘    │   │
│  │                         │                               │   │
│  │                         ▼                               │   │
│  │  ┌─────────────────────────────────────────────────┐    │   │
│  │  │           结果处理模块                            │    │   │
│  │  │  - 验证画师有效性                                │    │   │
│  │  │  - 补充画师作品信息                              │    │   │
│  │  │  - 按匹配度排序                                  │    │   │
│  │  └─────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌──────────────────┐  ┌──────────────────┐                   │
│  │ CustomRequest    │  │ Artwork          │                   │
│  │ (委托模型)        │  │ (作品模型)        │                   │
│  └──────────────────┘  └──────────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
              ┌───────────────────────┐
              │   AI Service (LLM)   │
              │  智谱 glm-4-flash     │
              │  glm-4.6v-flash(视觉)│
              └───────────────────────┘
```

### 2.2 核心模块设计

#### 2.2.1 画师特征提取模块

**功能**：从数据库中提取画师的特征信息，用于 AI 匹配

**数据来源**：
| 数据来源 | 表名 | 字段 | 用途 |
|---------|------|------|------|
| 用户信息 | users.User | username, bio, profile | 基本信息、技能标签 |
| 用户作品 | artworks.Artwork | category, tags, image | 作品风格、标签 |
| 接单记录 | custom.CommissionBid | amount, status | 接单历史、报价范围 |

**特征提取逻辑**：
```python
# 画师特征结构
{
    "id": 1,
    "username": "artist_name",
    "display_name": "艺术家名称",
    "bio": "简介",
    "skills": ["Photoshop", "Procreate", "水彩"],
    "styles": ["日系", "赛博朋克", "古风"],
    "categories": ["原创角色", "插画"],
    "tags": ["魔法少女", "机甲"],
    "price_range": {"min": 500, "max": 5000},
    "work_count": 15,
    "completed_count": 10
}
```

#### 2.2.2 Prompt 构建模块

**构建策略**：
1. **需求描述解析**：提取关键词、风格偏好、主题、细节要求
2. **参考图分析**：使用视觉模型分析参考图的风格特征（如启用）
3. **委托类型匹配**：结合委托类型筛选擅长该类型的画师
4. **预算过滤**：根据预算范围过滤报价匹配的画师

**Prompt 模板**：
```
你是一位专业的动漫委托匹配顾问，请根据以下委托需求和画师信息，推荐最适合的画师。

## 委托需求
- 标题: {title}
- 类型: {type_label}
- 描述: {description}
- 预算: {budget}
- 参考图: {has_reference_image}

## 匹配要求
1. 优先匹配画风、风格与需求契合的画师
2. 考虑画师的技能标签与需求的相关性
3. 综合评价匹配度，返回 0-100 的置信度分数
4. 最多推荐 10 位画师，按匹配度从高到低排序

## 画师列表
{artists_json}

## 输出格式
请严格按照 JSON 格式输出，不要包含其他文字：
[
  {"artist_id": 数字ID, "confidence": 匹配度(0-100), "reason": "匹配理由"}
]
```

#### 2.2.3 AI 推理模块

**调用流程**：
1. 构建包含需求信息和画师列表的 Prompt
2. 调用大模型（glm-4-flash）进行推理
3. 解析返回的 JSON 结果
4. 验证结果有效性

**调用参数**：
- `model`: `glm-4-flash`（无图）/ `glm-4.6v-flash`（有图）
- `temperature`: 0.3（降低随机性，提高匹配稳定性）
- `max_tokens`: 2000
- `response_format`: JSON

#### 2.2.4 结果处理模块

**处理步骤**：
1. **有效性验证**：验证 AI 返回的 artist_id 是否存在且为活跃用户
2. **信息补充**：从数据库查询画师的详细信息（头像、作品、技能等）
3. **排序优化**：按置信度排序，同时考虑画师的接单活跃度
4. **去重处理**：确保推荐列表中无重复画师

---

## 3. 数据库设计

### 3.1 无需新增表

本功能基于现有数据模型实现，无需新增数据库表。

### 3.2 数据查询优化

为提升匹配效率，建议在以下场景添加查询优化：

| 优化项 | 说明 |
|--------|------|
| 画师作品统计索引 | 在 Artwork 表上添加 owner + category 组合索引 |
| 活跃画师缓存 | 使用 Redis 缓存活跃画师列表，减少数据库查询 |
| 匹配结果缓存 | 对相同委托的匹配结果进行短期缓存（如 5 分钟） |

---

## 4. API 接口设计

### 4.1 接口概览

| 接口 | 方法 | 路径 | 功能 | 权限 |
|------|------|------|------|------|
| AI 匹配推荐 | POST | `/api/custom/{id}/ai-match/` | 为指定委托推荐画师 | 仅委托发布者/管理员 |
| 一键邀请推荐画师 | POST | `/api/custom/{id}/ai-match/invite/` | 邀请 AI 推荐的前 N 位画师 | 仅委托发布者/管理员 |

### 4.2 接口详细设计

#### 4.2.1 AI 匹配推荐

**请求路径**：`POST /api/custom/{id}/ai-match/`

**请求参数**：
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| limit | int | 否 | 返回推荐数量，默认 10，最大 20 |
| refresh | bool | 否 | 是否强制刷新缓存，默认 false |

**请求示例**：
```json
{
  "limit": 5,
  "refresh": false
}
```

**成功响应**：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "custom_request_id": 123,
    "recommendations": [
      {
        "artist": {
          "id": 1,
          "username": "artist_demo",
          "display_name": "Demo Artist",
          "avatar": "/media/avatars/demo.jpg",
          "bio": "专注日系插画创作",
          "skills": ["Procreate", "Photoshop"]
        },
        "confidence": 92,
        "reason": "画风偏向日系动漫风格，擅长原创角色设计，与委托需求高度契合",
        "sample_works": [
          {"id": 456, "title": "作品标题", "image": "/media/artworks/2024/01/sample.jpg", "category": "原创角色"}
        ],
        "price_range": {"min": 800, "max": 3000}
      }
    ],
    "matched_at": "2024-01-15T10:30:00Z",
    "total_candidates": 45
  }
}
```

**失败响应**：
```json
{
  "code": 403,
  "message": "Only the requester or admin can request AI matching.",
  "data": null
}
```

#### 4.2.2 一键邀请推荐画师

**请求路径**：`POST /api/custom/{id}/ai-match/invite/`

**请求参数**：
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| count | int | 是 | 邀请前 N 位推荐画师，最大 5 |
| message | string | 否 | 邀请消息，默认使用系统模板 |

**请求示例**：
```json
{
  "count": 3,
  "message": "您好，您的画风与我的委托需求非常匹配，期待与您合作！"
}
```

**成功响应**：
```json
{
  "code": 200,
  "message": "success",
  "data": {
    "custom_request_id": 123,
    "invited_count": 3,
    "invitations": [
      {
        "id": 789,
        "artist_username": "artist_demo",
        "amount": 1500.00,
        "status": "pending"
      }
    ],
    "failed_count": 0,
    "failed_reasons": []
  }
}
```

---

## 5. 前端交互设计

### 5.1 发布委托页面

**交互流程**：
1. 需求方填写委托信息（标题、类型、描述、预算、参考图）
2. 点击"发布"按钮提交委托
3. 发布成功后，自动触发 AI 匹配
4. 页面跳转至委托详情页，展示 AI 推荐的画师列表

### 5.2 委托详情页面

**交互元素**：
- **AI 推荐卡片区域**：展示推荐画师列表
  - 每位画师显示：头像、昵称、匹配度（百分比+进度条）、匹配理由、代表作品缩略图
  - 操作按钮："邀请"、"查看主页"
- **重新匹配按钮**：需求方可手动触发重新匹配
- **匹配时间提示**：显示上次匹配时间

**设计参考**：
```
┌─────────────────────────────────────────────────────────────┐
│  🤖 AI 智能推荐画师                                          │
│  上次匹配：2024-01-15 10:30                                 │
│  [重新匹配]                                                  │
├─────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 👤 artist_demo                                        │  │
│  │    匹配度：92% ██████████░░                           │  │
│  │    推荐理由：画风偏向日系动漫风格...                    │  │
│  │    [作品预览] [邀请] [查看主页]                        │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 👤 artist_2                                           │  │
│  │    匹配度：85% █████████░░░                           │  │
│  │    ...                                                │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 邀请画师页面

**交互优化**：
- 在搜索结果上方显示"AI 推荐"标签
- 将 AI 推荐的画师优先展示
- 显示匹配度标记

---

## 6. 实现步骤

### 6.1 后端实现

#### Step 1: 创建匹配服务模块

在 `backend/apps/custom/` 目录下创建 `matching.py`：

```python
# backend/apps/custom/matching.py
"""AI 画师匹配服务"""
import json
import re
from urllib import error, request as urlrequest

from django.conf import settings
from django.contrib.auth import get_user_model

from apps.artworks.models import Artwork
from apps.custom.models import CommissionBid, CustomRequest


User = get_user_model()


def _extract_artist_features(user):
    """提取画师特征"""
    profile = user.profile if isinstance(user.profile, dict) else {}
    artworks = list(user.artworks.filter(is_available=True).select_related("owner"))
    
    categories = set()
    tags = set()
    prices = []
    
    for artwork in artworks:
        if artwork.category:
            categories.add(artwork.category)
        if isinstance(artwork.tags, list):
            tags.update(artwork.tags)
        if artwork.price > 0:
            prices.append(float(artwork.price))
    
    completed_bids = CommissionBid.objects.filter(
        artist=user,
        status=CommissionBid.Status.SELECTED
    ).count()
    
    return {
        "id": user.id,
        "username": user.username,
        "display_name": profile.get("displayName") or user.username,
        "bio": user.bio[:200] if user.bio else "",
        "skills": profile.get("skills", [])[:10] if isinstance(profile.get("skills"), list) else [],
        "styles": list(categories),
        "tags": list(tags)[:20],
        "price_range": {
            "min": min(prices) if prices else 0,
            "max": max(prices) if prices else 0
        },
        "work_count": len(artworks),
        "completed_count": completed_bids
    }


def _build_prompt(custom_request, artists):
    """构建 AI 匹配 Prompt"""
    prompt = f"""你是一位专业的动漫委托匹配顾问。请根据以下委托需求，从提供的画师列表中推荐最合适的画师。

## 委托需求
- 标题: {custom_request.title}
- 类型: {custom_request.type_label or '未指定'}
- 描述: {custom_request.description[:800]}
- 预算: {custom_request.budget_note or str(custom_request.budget)}
- 是否有参考图: {'是' if custom_request.reference_image else '否'}

## 匹配要求
1. 优先匹配画风、风格与需求描述相符的画师
2. 考虑画师的技能标签与需求的相关性
3. 综合评价匹配度，返回 0-100 的置信度分数
4. 最多推荐 10 位画师，按匹配度从高到低排序
5. 匹配理由需简洁明了，说明推荐依据

## 画师列表
{json.dumps(artists, ensure_ascii=False, default=str)}

## 输出格式
请严格按照 JSON 格式输出，不要包含任何其他文字：
[
  {{"artist_id": 数字ID, "confidence": 匹配度(0-100), "reason": "匹配理由"}}
]"""
    return prompt


def _call_ai(prompt):
    """调用大模型进行匹配"""
    api_key = settings.AI_API_KEY
    api_base = settings.AI_API_BASE.rstrip("/")
    
    if not api_key:
        raise ValueError("AI API Key 未配置")
    
    messages = [
        {"role": "system", "content": "你是一位专业的动漫委托匹配顾问，擅长根据画风、技能和需求进行精准匹配。"},
        {"role": "user", "content": prompt}
    ]
    
    request_payload = {
        "model": settings.AI_MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2000
    }
    
    payload = json.dumps(request_payload).encode("utf-8")
    http_request = urlrequest.Request(
        f"{api_base}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    
    try:
        with urlrequest.urlopen(http_request, timeout=settings.AI_REQUEST_TIMEOUT) as response:
            result = json.loads(response.read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"].strip()
        return content
    except error.HTTPError as exc:
        detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
        raise ValueError(f"AI 服务拒绝请求: {detail}")
    except (error.URLError, TimeoutError):
        raise ValueError("无法连接 AI 服务，请稍后重试")
    except (KeyError, ValueError, json.JSONDecodeError):
        raise ValueError("AI 返回数据格式错误")


def _parse_ai_result(content):
    """解析 AI 返回结果"""
    try:
        match = re.search(r"\[[\s\S]*\]", content)
        if match:
            data = json.loads(match.group())
        else:
            data = json.loads(content)
        return data
    except json.JSONDecodeError:
        raise ValueError("无法解析 AI 返回的匹配结果")


def _get_sample_works(artist_id, limit=3):
    """获取画师代表作品"""
    works = Artwork.objects.filter(
        owner_id=artist_id,
        is_available=True
    ).order_by("-created_at")[:limit]
    
    return [{
        "id": work.id,
        "title": work.title,
        "image": work.image.url if work.image else "",
        "category": work.category or "原创作品"
    } for work in works]


def match_artists(custom_request, limit=10):
    """执行 AI 画师匹配"""
    active_artists = User.objects.filter(
        is_active=True,
        artworks__isnull=False
    ).distinct()[:50]
    
    artists = [_extract_artist_features(user) for user in active_artists]
    
    if not artists:
        return {"recommendations": [], "total_candidates": 0}
    
    prompt = _build_prompt(custom_request, artists)
    ai_response = _call_ai(prompt)
    raw_results = _parse_ai_result(ai_response)
    
    artist_map = {a["id"]: a for a in artists}
    valid_results = []
    
    for result in raw_results[:limit]:
        artist_id = result.get("artist_id")
        if artist_id not in artist_map:
            continue
        
        artist_info = artist_map[artist_id]
        user = User.objects.filter(id=artist_id, is_active=True).first()
        if not user:
            continue
        
        valid_results.append({
            "artist": {
                "id": user.id,
                "username": user.username,
                "display_name": artist_info["display_name"],
                "avatar": user.avatar.url if user.avatar else "",
                "bio": artist_info["bio"],
                "skills": artist_info["skills"]
            },
            "confidence": result.get("confidence", 0),
            "reason": result.get("reason", ""),
            "sample_works": _get_sample_works(artist_id),
            "price_range": artist_info["price_range"]
        })
    
    return {
        "recommendations": sorted(valid_results, key=lambda x: x["confidence"], reverse=True),
        "total_candidates": len(artists)
    }
```

#### Step 2: 添加视图方法

在 `CustomRequestViewSet` 中添加 AI 匹配相关的 action 方法：

```python
# backend/apps/custom/views.py - 在文件末尾添加

@action(detail=True, methods=["post"])
def ai_match(self, request, pk=None):
    custom_request = self.get_object()
    self._ensure_requester_or_admin(custom_request)
    
    try:
        limit = int(request.data.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    limit = min(max(limit, 1), 20)
    
    try:
        result = match_artists(custom_request, limit=limit)
        result["custom_request_id"] = custom_request.id
        result["matched_at"] = timezone.now().isoformat()
        return ok(result)
    except ValueError as exc:
        return fail(str(exc), code=503, status=503)


@action(detail=True, methods=["post"], url_path="ai-match/invite")
def ai_match_invite(self, request, pk=None):
    custom_request = self.get_object()
    self._ensure_requester_or_admin(custom_request)
    self._ensure_open(custom_request)
    
    try:
        count = int(request.data.get("count", 3))
    except (TypeError, ValueError):
        count = 3
    count = min(max(count, 1), 5)
    
    message = request.data.get("message", "")[:1000]
    if not message:
        message = f"您好，AI 推荐您来承接我的委托「{custom_request.title}」，期待与您合作！"
    
    try:
        result = match_artists(custom_request, limit=count)
    except ValueError as exc:
        return fail(str(exc), code=503, status=503)
    
    invited = []
    failed = []
    
    with transaction.atomic():
        bids, invitations = self._lock_candidates(custom_request)
        existing_artist_ids = {bid.artist_id for bid in bids} | {inv.artist_id for inv in invitations}
        
        for rec in result["recommendations"]:
            artist_id = rec["artist"]["id"]
            
            if artist_id in existing_artist_ids:
                failed.append(f"画师 @{rec['artist']['username']} 已在报价或邀请列表中")
                continue
            if artist_id == custom_request.requester_id:
                failed.append("不能邀请自己")
                continue
            
            artist = User.objects.filter(id=artist_id, is_active=True).first()
            if not artist:
                failed.append(f"画师 ID {artist_id} 不存在或已禁用")
                continue
            
            amount = custom_request.budget if custom_request.budget > Decimal("0") else Decimal("500")
            
            invitation = CommissionInvitation(
                custom_request=custom_request,
                artist=artist,
                invited_by=request.user,
                amount=amount,
                message=message,
                status=CommissionInvitation.Status.PENDING
            )
            invitation.save()
            invited.append({
                "id": invitation.id,
                "artist_username": artist.username,
                "amount": str(invitation.amount),
                "status": invitation.status
            })
            existing_artist_ids.add(artist_id)
    
    return ok({
        "custom_request_id": custom_request.id,
        "invited_count": len(invited),
        "invitations": invited,
        "failed_count": len(failed),
        "failed_reasons": failed
    })
```

#### Step 3: 更新视图导入

在 `views.py` 顶部添加导入：

```python
from .matching import match_artists
```

### 6.2 前端实现

#### Step 1: 添加 API 调用方法

在 `frontend/app.js` 中添加 AI 匹配相关的 API 调用：

```javascript
// AI 匹配相关 API
const aiMatchApi = {
  // 获取 AI 推荐画师
  getRecommendations: async (commissionId, options = {}) => {
    const response = await fetch(`/api/custom/${commissionId}/ai-match/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      },
      body: JSON.stringify(options)
    });
    return response.json();
  },
  
  // 一键邀请推荐画师
  inviteRecommended: async (commissionId, count = 3, message = '') => {
    const response = await fetch(`/api/custom/${commissionId}/ai-match/invite/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      },
      body: JSON.stringify({ count, message })
    });
    return response.json();
  }
};
```

#### Step 2: 添加 AI 匹配 UI 组件

在 `frontend/index.html` 的委托详情面板中添加 AI 推荐区域：

```html
<!-- 在 commissionDetail 内添加 -->
<div class="ai-match-panel" id="aiMatchPanel">
  <div class="ai-match-head">
    <div>
      <span class="ai-match-kicker">AI RECOMMENDATION</span>
      <h4>智能推荐画师</h4>
      <p id="aiMatchHint">AI 根据委托需求和画师作品特征匹配推荐</p>
    </div>
    <button class="commission-btn secondary compact" id="aiMatchRefreshBtn">重新匹配</button>
  </div>
  <div class="ai-match-loading" id="aiMatchLoading" hidden>
    <span class="loading-spinner"></span>
    <span>AI 正在分析委托需求，寻找最合适的画师...</span>
  </div>
  <div class="ai-match-results" id="aiMatchResults"></div>
  <div class="ai-match-empty" id="aiMatchEmpty" hidden>
    <p>暂无推荐结果</p>
    <button class="submit-btn" id="aiMatchTriggerBtn">开始 AI 匹配</button>
  </div>
</div>
```

#### Step 3: 添加样式

在 `frontend/styles.css` 中添加 AI 匹配相关样式：

```css
/* AI 匹配面板 */
.ai-match-panel {
  margin-top: 24px;
  padding: 20px;
  background: var(--card-bg);
  border-radius: 12px;
}

.ai-match-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.ai-match-kicker {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--accent-color);
}

.ai-match-head h4 {
  margin: 4px 0 2px;
  font-size: 18px;
}

.ai-match-hint {
  font-size: 13px;
  color: var(--text-muted);
}

.ai-match-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 30px;
  color: var(--text-muted);
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border-color);
  border-top-color: var(--accent-color);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.ai-match-results {
  display: grid;
  gap: 16px;
}

.ai-match-card {
  display: flex;
  gap: 16px;
  padding: 16px;
  background: var(--surface-bg);
  border-radius: 8px;
  border: 1px solid var(--border-color);
  transition: all 0.2s;
}

.ai-match-card:hover {
  border-color: var(--accent-color);
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}

.ai-match-avatar {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--accent-color);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
}

.ai-match-avatar img {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: cover;
}

.ai-match-info {
  flex: 1;
  min-width: 0;
}

.ai-match-info h5 {
  margin: 0 0 4px;
  font-size: 14px;
}

.ai-match-info p {
  margin: 4px 0;
  font-size: 12px;
  color: var(--text-muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ai-match-confidence {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.confidence-bar {
  flex: 1;
  height: 6px;
  background: var(--border-color);
  border-radius: 3px;
  overflow: hidden;
}

.confidence-fill {
  height: 100%;
  background: var(--accent-color);
  border-radius: 3px;
  transition: width 0.5s ease;
}

.confidence-text {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent-color);
  min-width: 40px;
  text-align: right;
}

.ai-match-samples {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.ai-match-sample {
  width: 48px;
  height: 48px;
  border-radius: 6px;
  background: var(--border-color);
  overflow: hidden;
}

.ai-match-sample img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.ai-match-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ai-match-empty {
  text-align: center;
  padding: 30px;
  color: var(--text-muted);
}
```

#### Step 4: 添加交互逻辑

在 `frontend/app.js` 中添加 AI 匹配的交互逻辑：

```javascript
// AI 匹配交互
async function loadAiRecommendations(commissionId) {
  const panel = document.getElementById('aiMatchPanel');
  const loading = document.getElementById('aiMatchLoading');
  const results = document.getElementById('aiMatchResults');
  const empty = document.getElementById('aiMatchEmpty');
  
  if (!panel) return;
  
  loading.hidden = false;
  results.innerHTML = '';
  empty.hidden = true;
  
  try {
    const response = await aiMatchApi.getRecommendations(commissionId, { limit: 5 });
    
    if (response.code === 200 && response.data?.recommendations?.length > 0) {
      renderAiRecommendations(response.data.recommendations);
    } else {
      empty.hidden = false;
    }
  } catch (error) {
    console.error('AI 匹配失败:', error);
    empty.hidden = false;
  } finally {
    loading.hidden = true;
  }
}

function renderAiRecommendations(recommendations) {
  const container = document.getElementById('aiMatchResults');
  container.innerHTML = recommendations.map(rec => `
    <div class="ai-match-card">
      <div class="ai-match-avatar">
        ${rec.artist.avatar 
          ? `<img src="${rec.artist.avatar}" alt="${rec.artist.display_name}">`
          : rec.artist.display_name.charAt(0)}
      </div>
      <div class="ai-match-info">
        <h5>${rec.artist.display_name} <small>@${rec.artist.username}</small></h5>
        <p>${rec.reason}</p>
        <div class="ai-match-confidence">
          <div class="confidence-bar">
            <div class="confidence-fill" style="width: ${rec.confidence}%"></div>
          </div>
          <span class="confidence-text">${rec.confidence}%</span>
        </div>
        ${rec.sample_works?.length > 0 ? `
          <div class="ai-match-samples">
            ${rec.sample_works.map(w => `
              <div class="ai-match-sample">
                ${w.image ? `<img src="${w.image}" alt="${w.title}">` : ''}
              </div>
            `).join('')}
          </div>
        ` : ''}
      </div>
      <div class="ai-match-actions">
        <button class="commission-btn compact" onclick="inviteArtist('${commissionId}', ${rec.artist.id})">邀请</button>
        <button class="commission-btn secondary compact" onclick="openUserProfile(${rec.artist.id})">查看</button>
      </div>
    </div>
  `).join('');
}

// 绑定重新匹配按钮事件
document.getElementById('aiMatchRefreshBtn')?.addEventListener('click', () => {
  loadAiRecommendations(commissionId);
});

document.getElementById('aiMatchTriggerBtn')?.addEventListener('click', () => {
  loadAiRecommendations(commissionId);
});
```

---

## 7. 性能优化

### 7.1 缓存策略

| 缓存项 | 缓存时间 | 缓存键 | 说明 |
|--------|----------|--------|------|
| 活跃画师列表 | 1 小时 | `ai:artists:active` | 减少数据库查询 |
| 画师特征缓存 | 2 小时 | `ai:artist:features:{id}` | 避免重复计算 |
| 匹配结果缓存 | 5 分钟 | `ai:match:{commission_id}` | 避免频繁调用 AI |

### 7.2 请求限流

| 限流场景 | 限流规则 | 说明 |
|----------|----------|------|
| AI 匹配调用 | 每用户 5 次/分钟 | 防止滥用 AI 服务 |
| 一键邀请调用 | 每委托 1 次/5 分钟 | 防止频繁邀请 |

### 7.3 异步处理（可选优化）

对于复杂的匹配请求，可考虑使用 Celery 异步处理：

```python
# tasks.py - 异步匹配任务
from celery import shared_task

@shared_task
def async_match_artists(commission_id):
    custom_request = CustomRequest.objects.get(pk=commission_id)
    result = match_artists(custom_request)
    # 可将结果存入缓存或发送通知
    return result
```

---

## 8. 安全考虑

### 8.1 权限控制

| 操作 | 权限要求 |
|------|----------|
| 获取 AI 匹配结果 | 委托发布者、管理员 |
| 一键邀请推荐画师 | 委托发布者、管理员 |
| 重新匹配 | 委托发布者、管理员 |

### 8.2 输入验证

- 对 AI 返回的 artist_id 进行有效性验证
- 过滤已报价/已邀请的画师，避免重复操作
- 限制邀请数量（最大 5 位），防止骚扰

### 8.3 数据隐私

- AI 只获取画师公开信息（用户名、作品标签、技能）
- 不传递画师隐私数据（邮箱、联系方式）
- 匹配过程在服务端完成，不暴露原始数据给前端

---

## 9. 测试方案

### 9.1 单元测试

```python
# backend/apps/custom/tests_matching.py
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.custom.matching import (
    _extract_artist_features,
    _build_prompt,
    _parse_ai_result
)


User = get_user_model()


class MatchingTests(TestCase):
    def test_extract_artist_features(self):
        """测试画师特征提取"""
        user = User.objects.create_user(username='test_artist', password='123456')
        user.bio = 'Test bio'
        user.profile = {'displayName': 'Test Artist', 'skills': ['Photoshop']}
        user.save()
        
        features = _extract_artist_features(user)
        
        self.assertEqual(features['id'], user.id)
        self.assertEqual(features['username'], 'test_artist')
        self.assertEqual(features['display_name'], 'Test Artist')
        self.assertEqual(features['bio'], 'Test bio')
        self.assertEqual(features['skills'], ['Photoshop'])
    
    def test_parse_ai_result(self):
        """测试 AI 结果解析"""
        content = '[ {"artist_id": 1, "confidence": 95, "reason": "test"} ]'
        result = _parse_ai_result(content)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['artist_id'], 1)
        self.assertEqual(result[0]['confidence'], 95)
```

### 9.2 API 测试

| 测试场景 | 请求 | 预期结果 |
|----------|------|----------|
| 无权限调用 | POST /api/custom/1/ai-match/ | 403 拒绝访问 |
| 正常匹配 | POST /api/custom/1/ai-match/ | 200 返回推荐列表 |
| 无活跃画师 | POST /api/custom/1/ai-match/ | 200 空推荐列表 |
| 一键邀请 | POST /api/custom/1/ai-match/invite/ | 200 返回邀请结果 |

---

## 10. 部署与配置

### 10.1 环境变量配置

```env
# AI 服务配置（已有）
AI_API_KEY=your_api_key
AI_API_BASE=https://open.bigmodel.cn/api/paas/v4
AI_MODEL=glm-4-flash
AI_REQUEST_TIMEOUT=45

# AI 匹配限流配置（新增）
DRF_AI_MATCH_THROTTLE_RATE=5/min
```

### 10.2 限流配置

在 `backend/common/throttling.py` 或配置文件中添加：

```python
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_RATES': {
        'ai_chat': '20/min',
        'ai_match': '5/min',  # 新增
        'anon': '120/min',
        'user': '1200/min',
        'write': '120/min',
        'login': '10/min',
    }
}
```

---

## 11. 注意事项

1. **AI 匹配依赖网络**：需要确保 AI API 服务正常可用
2. **匹配结果仅供参考**：最终选择由需求方决定
3. **定期更新模型**：根据用户反馈调整 Prompt 模板和匹配策略
4. **监控 API 调用**：关注 AI 服务费用和调用频率
5. **异常处理**：AI 服务不可用时应提供降级方案（如基于标签的简单匹配）
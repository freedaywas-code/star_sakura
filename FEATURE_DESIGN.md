# AI画师智能匹配功能设计文档

## 一、功能概述

### 1.1 功能定位
在星漫平台的"约稿交易"模块中，新增 AI 智能匹配功能。需求方发布约稿需求后，系统通过 AI 分析平台内画师的历史作品风格特征，自动推荐最适合该需求的画师，提升约稿匹配效率和成功率。

### 1.2 用户故事
> 作为需求方，当我发布一个约稿需求时，我希望系统能自动推荐风格匹配的画师，而不是我逐个浏览画师主页筛选。

> 作为画师，我希望我的作品风格能被系统准确识别，从而获得更精准的约稿邀请。


## 二、核心流程

1. 需求方填写约稿需求单
   - 需求描述（文本）
   - 参考图（可选，上传1-3张）
   - 风格标签（多选：日系/厚涂/Q版/写实/水墨等）
   - 预算范围

2. 点击「AI智能匹配」按钮

3. 系统执行匹配算法
   - 需求特征提取（文本/图像 → 风格向量）
   - 画师作品库检索（遍历平台画师及其作品）
   - 相似度计算（需求向量 vs 画师风格向量）

4. 返回 Top 10 推荐画师列表
   - 匹配度评分（百分比显示）
   - 推荐理由（一句话解释为什么匹配）
   - 画师作品缩略图预览
   - 一键发起定向约稿邀请

5. 需求方查看画师主页 → 确认并发起约稿


## 三、技术方案

### 3.1 技术架构

- 前端：Vue/React（现有框架）
- 后端：Node.js/Java/Python（现有技术栈）
- AI 服务层：
  - 文本编码模型：sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
  - 图像特征提取：CLIP / ResNet50
  - 风格向量库：Milvus / Faiss（初期可用 numpy 替代）
- 数据层：现有数据库 + 新增表

### 3.2 匹配算法

输入：需求文本 D、参考图 I（可选）、风格标签 T
输出：推荐画师列表 S = [(画师1, 匹配度), (画师2, 匹配度), ...]

Step 1: 特征提取
  - 文本特征 V_d = TextEncoder(D) → 512维向量
  - 图像特征 V_i = ImageEncoder(I)（若有）→ 512维向量
  - 需求综合向量 V_req = weighted_concat(V_d, V_i, T)

Step 2: 画师风格建模
  - 对每个画师，计算其所有作品的风格向量 → 聚合为画师风格向量
  - V_artist = mean([V_work1, V_work2, ...])

Step 3: 相似度计算
  - cosine_similarity(V_req, V_artist) → 匹配度分数 [0, 1]

Step 4: 综合排序
  - 最终得分 = 0.6 × 风格匹配度 + 0.2 × 响应率 + 0.2 × 好评率

### 3.3 相似度计算公式

风格匹配度 = cosine_similarity(V_req, V_artist)
           = (V_req · V_artist) / (||V_req|| × ||V_artist||)

综合得分 = 0.6 × 风格匹配度 + 0.2 × 响应率 + 0.2 × 好评率


## 四、接口设计

### 4.1 AI匹配接口

POST /api/match/ai-recommend
请求头: Authorization: Bearer {token}

请求体:
{
    "demand_id": 12345,
    "reference_images": ["url1", "url2"],
    "style_tags": ["日系", "厚涂"],
    "top_k": 10,
    "budget_range": {
        "min": 100,
        "max": 500
    }
}

响应体:
{
    "code": 200,
    "data": {
        "recommendations": [
            {
                "artist_id": 1001,
                "artist_name": "星野画师",
                "avatar": "https://...",
                "match_score": 92.5,
                "match_reason": "擅长日系厚涂风格，与您的需求高度匹配",
                "sample_works": ["url1", "url2"],
                "price_range": "200-400",
                "response_rate": 95,
                "rating": 4.8
            }
        ],
        "total": 10,
        "match_timestamp": "2026-07-18T15:30:00Z"
    }
}

### 4.2 画师风格画像接口

GET /api/artist/:id/style-profile

响应:
{
    "code": 200,
    "data": {
        "artist_id": 1001,
        "style_tags": ["日系", "厚涂", "赛璐璐"],
        "style_vector": [0.12, -0.34, ...],
        "style_description": "擅长温暖色调的日系厚涂风格，笔触细腻",
        "representative_works": [...]
    }
}


## 五、数据库设计（新增表）

### 5.1 画师风格画像表 artist_style_profile

CREATE TABLE artist_style_profile (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    artist_id BIGINT NOT NULL UNIQUE,
    style_vector BLOB,
    style_tags JSON,
    style_description TEXT,
    representative_work_ids JSON,
    updated_at DATETIME,
    INDEX idx_artist_id (artist_id)
);

### 5.2 匹配记录表 match_record

CREATE TABLE match_record (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    demand_id BIGINT NOT NULL,
    requester_id BIGINT NOT NULL,
    match_result JSON,
    match_algorithm VARCHAR(50),
    match_duration INT,
    created_at DATETIME,
    INDEX idx_demand_id (demand_id),
    INDEX idx_requester_id (requester_id)
);

### 5.3 用户反馈表 match_feedback

CREATE TABLE match_feedback (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    match_record_id BIGINT NOT NULL,
    artist_id BIGINT NOT NULL,
    is_contacted BOOLEAN,
    is_hired BOOLEAN,
    user_rating TINYINT,
    created_at DATETIME,
    INDEX idx_match_record (match_record_id)
);


## 六、改动范围 & 工作量评估

| 模块 | 改动内容 | 预估工时 |
|------|----------|----------|
| 前端 | 需求表单新增匹配按钮 + 匹配结果页面 | 2天 |
| 后端 | 新增匹配接口 + 异步任务队列 | 2天 |
| AI服务 | 模型部署 + 风格向量生成 + 相似度计算 | 3天 |
| 数据库 | 新增3张表 + 数据迁移脚本 | 0.5天 |
| 画师画像 | 为已有画师作品生成风格向量（离线任务） | 1天 |
| 测试 | 功能测试 + 匹配效果评估 | 1天 |
| 合计 | | 9.5天 |


## 七、风险与应对

| 风险 | 应对措施 |
|------|----------|
| AI模型推理速度慢（>3秒） | 异步任务 + 轮询 / 模型量化加速 / 结果缓存 |
| API调用费用超预算 | 设置每日/每月调用限额 / 优先开源模型 / 监控告警 |
| 新画师作品未及时入库 | 作品发布时同步触发风格向量生成（增量更新） |
| 匹配效果不符合预期 | 用户反馈机制 / 人工筛选补充 / 埋点追踪转化率 |


## 八、后续优化方向

| 阶段 | 优化内容 |
|------|----------|
| V1.0（本期） | 基础匹配功能上线，支持文本+标签匹配 |
| V1.1 | 加入参考图匹配，提升匹配精度 |
| V1.2 | 引入用户反馈数据，优化排序权重 |
| V2.0 | 个性化推荐（根据需求方历史偏好） |


## 九、验收标准

- [ ] 需求方可以在发布约稿时点击「AI智能匹配」
- [ ] 系统能在 5 秒内返回 Top 10 推荐画师
- [ ] 每个推荐结果包含匹配度百分比和推荐理由
- [ ] 支持一键跳转画师主页并发起约稿
- [ ] 匹配记录保存到数据库，可追溯
- [ ] 新增画师作品后，风格画像在 10 分钟内更新
- [ ] API 响应时间 P95 < 500ms（不含AI推理）
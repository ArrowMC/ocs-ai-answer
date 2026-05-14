# OCS AI 智能题库

基于自定义 AI 大模型的 OCS 网课助手题库后端服务。将 OCS 发来的题目和选项整理后发送给 AI 大模型作答，回答结果持久化存储于 SQLite 数据库，下次遇到相同题目直接返回缓存，避免重复调用 AI。

## 目录

- [架构概览](#架构概览)
- [功能特性](#功能特性)
- [快速开始](#快速开始)
- [配置详解](#配置详解)
- [支持的 AI 平台](#支持的-ai-平台)
- [导入 OCS](#导入-ocs)
- [API 参考](#api-参考)
- [数据库设计](#数据库设计)
- [缓存与失效策略](#缓存与失效策略)
- [题目类型与答案格式](#题目类型与答案格式)
- [部署指南](#部署指南)
- [故障排查](#故障排查)
- [开发](#开发)

---

## 架构概览

```
OCS 网课助手                    本服务                        AI 大模型
    │                           │                              │
    ├── 发送题目 + 选项 ────────►│                              │
    │                           ├── 计算指纹(SHA-256)           │
    │                           ├── 查询 SQLite 缓存            │
    │                           │   ├── 命中 → 直接返回         │
    │                           │   └── 未命中 ↓               │
    │                           ├── 构建提示词 ────────────────►│
    │                           │                              ├── 推理作答
    │                           │◄─────── 返回 JSON 答案 ──────┤
    │                           ├── 解析答案                    │
    │                           ├── 写入 SQLite                │
    │◄────── 返回答案 ──────────┤                              │
```

## 功能特性

- **AI 智能作答**：自动将题目、选项、题目类型整理为结构化提示词，发送给 AI 大模型推理
- **答案持久化缓存**：回答过的题目存入 SQLite，下次相同题目毫秒级返回，节省 AI 调用费用
- **自动缓存失效**：题目标题、类型、选项任一变化时，指纹发生变化，自动识别为新题目并重新查询 AI —— 解决"不同平台选项不同、答案不能死记"的问题
- **强制刷新**：提供 `/reload` 接口，当怀疑 AI 答案有误时可强制重新推理并更新缓存
- **多模型支持**：兼容 OpenAI API 格式，支持 OpenAI / DeepSeek / 通义千问 / 智谱 / ollama 本地模型等
- **零前端依赖**：纯后端 API 服务，一个 Python 进程即可运行

## 快速开始

### 1. 环境要求

- Python 3.10+
- pip

### 2. 安装依赖

```bash
cd ocs-ai-answer
pip install -r requirements.txt
```

### 3. 配置 API Key

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env，填入你的 AI API 密钥
# Windows 下用记事本打开 .env 编辑即可
```

最小配置（使用 OpenAI）：

```env
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=sk-your-api-key-here
AI_MODEL=gpt-4o-mini
```

### 4. 启动服务

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 5000
```

看到以下输出说明启动成功：

```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:5000
```

### 5. 验证服务

```bash
# 健康检查
curl http://localhost:5000/health
# 返回: {"status":"ok"}

# 测试查询
curl "http://localhost:5000/query?title=1+2等于多少&options=A.1%0AB.2%0AC.3%0AD.4&type=single"
# 返回: {"code":0,"data":{"question":"1+2等于多少","answer":"C"},"msg":"success (ai)"}
```

### 6. 导入 OCS

在 OCS 软件的「外部题库配置」中粘贴下方 JSON（详见 [导入 OCS](#导入-ocs) 章节）。

---

## 配置详解

所有配置通过 `.env` 文件或环境变量设置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AI_BASE_URL` | `https://api.openai.com/v1` | AI API 基础地址 |
| `AI_API_KEY` | — | **必填**。AI 平台的 API Key |
| `AI_MODEL` | `gpt-4o-mini` | 模型名称 |
| `AI_TEMPERATURE` | `0.3` | 生成温度（0-2），越低答案越确定 |
| `AI_MAX_TOKENS` | `500` | 单次回复最大 token 数 |
| `AI_TIMEOUT` | `30` | AI API 请求超时（秒） |
| `SERVER_HOST` | `0.0.0.0` | 服务监听地址 |
| `SERVER_PORT` | `5000` | 服务监听端口 |
| `DATABASE_PATH` | `./data/questions.db` | SQLite 数据库文件路径 |

### Temperature 说明

- `0.0 - 0.3`：答案最稳定、确定，适合客观题
- `0.5 - 0.7`：有一定随机性
- `0.8 - 1.0`：创意性较强，不推荐用于答题

建议使用 `0.3` 或更低值以确保答案一致性。

---

## 支持的 AI 平台

任何兼容 OpenAI `/chat/completions` 接口的平台均可使用。

### OpenAI

```env
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AI_MODEL=gpt-4o-mini
```

推荐模型：`gpt-4o-mini`（性价比高）、`gpt-4o`（准确率更高）

### DeepSeek

```env
AI_BASE_URL=https://api.deepseek.com
AI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AI_MODEL=deepseek-chat
```

### 通义千问（阿里云）

在阿里云百炼平台开通服务后：

```env
AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
AI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AI_MODEL=qwen-turbo
```

可选模型：`qwen-turbo`、`qwen-plus`、`qwen-max`

### 智谱 AI (GLM)

```env
AI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
AI_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AI_MODEL=glm-4-flash
```

### ollama（本地模型，无需联网）

适用于本地运行的开源模型，隐私性强、零调用费用：

```bash
# 先安装并启动 ollama
ollama serve
ollama pull qwen2.5
```

```env
AI_BASE_URL=http://localhost:11434/v1
AI_API_KEY=ollama
AI_MODEL=qwen2.5
```

推荐本地模型：`qwen2.5`（7B 以上）、`llama3`、`deepseek-r1`

> **注意**：本地模型受限于硬件性能，推理速度较慢，准确率可能不及云端大模型。

### 其他兼容平台

只要平台提供 OpenAI 兼容的 `/chat/completions` 端点即可使用。将 `AI_BASE_URL` 设为平台的 API 地址，`AI_MODEL` 设为对应模型名。

---

## 导入 OCS

### 配置 JSON

在 OCS 软件的设置中找到「外部题库配置」，粘贴以下 JSON：

```json
[
  {
    "name": "AM共享智能题库",
    "homepage": "http://localhost:5000/",
    "url": "http://localhost:5000/query",
    "method": "get",
    "type": "GM_xmlhttpRequest",
    "contentType": "json",
    "data": {
      "token": "your-secret-token-here",
      "title": "${title}",
      "options": "${options}",
      "type": "${type}"
    },
    "handler": "return (res)=>res.code === 0 ? [res.data.question, res.data.answer] : undefined"
  }
]
```

### 各字段说明

| 字段 | 值 | 说明 |
|------|-----|------|
| `name` | `"AI智能题库"` | 在 OCS 中显示的题库名称，可自定义 |
| `homepage` | 服务地址 | 题库主页，仅用于展示 |
| `url` | `.../query` | 请求地址。占位符 `${title}` `${options}` `${type}` 会被 OCS 自动替换 |
| `method` | `"get"` | HTTP 方法。`get` 将参数附加在 URL 后；`post` 将参数放入请求体 |
| `type` | `"GM_xmlhttpRequest"` | 请求方式。**必须用 `GM_xmlhttpRequest`**：OCS 运行在 HTTPS 页面，浏览器会阻止 `fetch` 访问 HTTP 服务（混合内容限制），油猴 API 可绕过此限制 |
| `contentType` | `"json"` | 响应数据类型。`json` 表示自动解析为 JSON 对象传给 handler |
| `data` | 参数映射 | 发送给题库的参数。`token` 为鉴权凭据，需与服务端 `.env` 中 `AUTH_TOKEN` 一致（不设则无需）。`${title}` = 题目标题, `${options}` = 选项(换行分隔), `${type}` = 题型 |
| `handler` | 解析函数 | 处理响应的 JS 函数字符串。返回值 `[question, answer]` 告诉 OCS 题目和答案 |

### 远程部署

如果服务部署在云服务器上（如 `http://your-server.com:5000`），将配置中的 `localhost` 替换为服务器 IP 或域名：

```json
"url": "http://your-server.com:5000/query",
"type": "GM_xmlhttpRequest"
```

使用 `GM_xmlhttpRequest` 类型可从浏览器跨域访问远程服务器（需要 OCS 脚本的 `@connect` 授权）。

### 多题库组合

OCS 支持配置多个题库，按顺序查询。可以将本 AI 题库放在其他题库后面作为兜底：

```json
[
  { "...": "其他题库配置" },
  {
    "name": "AI智能题库",
    "url": "http://localhost:5000/query",
    "...": "..."
  }
]
```

OCS 会按顺序查询，第一个返回有效答案的题库结果将被使用。因此建议将专用题库放前面，AI 题库放最后作为兜底。

---

## API 参考

### 通用格式

所有接口响应均为 JSON，包含三个字段：

```json
{
  "code": 0,
  "data": { "question": "题目标题", "answer": "A" },
  "msg": "success (cached)"
}
```

### 状态码

| 状态码 | 含义 | 触发场景 |
|--------|------|----------|
| `0` | 成功 | 正常获取到答案（缓存命中或 AI 推理成功） |
| `1` | AI 未配置 | `AI_API_KEY` 为空（调用前检查） |
| `2` | AI 接口错误 | API 超时、5xx 错误、网络不通、API Key 无效 |
| `3` | 答案解析失败 | AI 返回的内容不是合法 JSON、无法提取答案 |
| `4` | 无效输入 | `title` 为空 |

### GET /health

健康检查，可用于监控服务是否存活。

**请求：**
```
GET /health
```

**响应：**
```json
{"status":"ok"}
```

### GET/POST /query

查询题目答案。优先从数据库缓存返回，缓存未命中时调用 AI。

**请求：**

```
GET /query?title=题目&options=A.选项A\nB.选项B\nC.选项C&type=single
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | string | 是 | 题目标题（会去除首尾空白） |
| `options` | string | 否 | 选项文本，以 `\n` 分隔，如 `"A. 正确\nB. 错误"` |
| `type` | string | 否 | 题目类型：`single`、`multiple`、`judgement`、`completion` |

**响应（成功 - 缓存命中）：**
```json
{
  "code": 0,
  "data": { "question": "马克思主义中国化的重要理论成果是？", "answer": "A" },
  "msg": "success (cached)"
}
```

**响应（成功 - AI 推理）：**
```json
{
  "code": 0,
  "data": { "question": "马克思主义中国化的重要理论成果是？", "answer": "A" },
  "msg": "success (ai)"
}
```

**响应（AI 未配置）：**
```json
{
  "code": 2,
  "data": null,
  "msg": "AI_API_KEY is not configured"
}
```

**响应（无效输入）：**
```json
{
  "code": 4,
  "data": null,
  "msg": "Title is required"
}
```

### GET/POST /reload

强制 AI 重新推理，更新缓存。参数同 `/query`。适用于：

- 怀疑之前的 AI 答案有误，想用当前模型重新作答
- 题目内容相同但答案标准变化

**请求：**
```
GET /reload?title=题目&options=A.选项A\nB.选项B&type=single
```

**响应：** 格式同 `/query`，但始终调用 AI（不走缓存），并更新数据库中的缓存记录。

### GET /stats

获取缓存统计信息，用于了解题库使用情况。

**请求：**
```
GET /stats
```

**响应：**
```json
{
  "code": 0,
  "data": {
    "total": 1523,
    "hit_count": 1201,
    "miss_count": 322
  },
  "msg": "success"
}
```

| 字段 | 说明 |
|------|------|
| `total` | 数据库中缓存的题目总数 |
| `hit_count` | 本次进程运行期间的缓存命中次数 |
| `miss_count` | 本次进程运行期间的 AI 调用次数 |

> 注意：`hit_count` 和 `miss_count` 是内存计数器，重启后清零。

---

## 数据库设计

### 表结构

SQLite 数据库，单表 `questions`：

```sql
CREATE TABLE questions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint   TEXT    NOT NULL UNIQUE,    -- SHA-256(title|type|options)
    title         TEXT    NOT NULL,           -- 原始题目标题
    options       TEXT    DEFAULT '',         -- 原始选项文本
    type          TEXT    NOT NULL DEFAULT '',-- single / multiple / judgement / completion
    answer        TEXT    NOT NULL,           -- 答案，如 "A" / "A#C" / "填空文本"
    options_hash  TEXT    DEFAULT '',         -- SHA-256(options) 用于变化检测
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    query_count   INTEGER NOT NULL DEFAULT 1 -- 该题被查询的总次数
);
```

### 关键设计

- **`fingerprint` 作为唯一键**：`SHA-256(title|type|options)` 确保相同的题目 + 类型 + 选项组合只存一条记录，有唯一索引加速查询
- **`options_hash` 独立存储**：方便后续分析选项变化情况（如发现某平台更新了选项）
- **`query_count` 查询计数**：每次缓存命中自动 +1，可用于分析高频题目
- **`updated_at` 自动更新**：每次缓存命中或 AI 重新作答时自动刷新时间戳

---

## 缓存与失效策略

### 指纹生成算法

```
fingerprint = SHA-256(trim(title) + "|" + trim(type) + "|" + trim(options))
```

三个输入均先 `trim()` 去除首尾空白，然后用 `|` 连接后计算 SHA-256。

### 什么情况下会缓存命中？

三者**完全相同**时命中缓存：

- 题目标题相同
- 题目类型相同
- 选项文本相同（包括顺序、措辞）

### 什么情况下会缓存失效（重新调用 AI）？

任一要素变化都会导致指纹不同 → 缓存未命中 → 自动重新调用 AI：

| 变化场景 | 示例 | 结果 |
|----------|------|------|
| **标题变化** | "1+2=?" → "1+2等于多少" | 新指纹，重查 AI |
| **类型变化** | `single` 变为 `multiple` | 新指纹，重查 AI |
| **选项变化** | A.正确/B.错误 → A.对/B.错 | 新指纹，重查 AI |
| **选项顺序变化** | A/B/C → C/B/A | 新指纹，重查 AI |
| **新增/删除选项** | 4 个选项 → 5 个选项 | 新指纹，重查 AI |

这正是为了解决用户提出的核心问题：

> "一些平台的选项会发生变化，不可死记选项记忆"

通过将选项内容纳入指纹计算，平台选项一旦变化，缓存自动失效，AI 会基于新选项重新作答，不会错误地返回旧答案。

### 手动失效

使用 `/reload` 接口可强制重新推理并更新缓存，无需修改题目内容。

### 性能说明

- SQLite 单表设计，指纹哈希索引查询速度极快（< 1ms）
- 缓存命中时完全不调用 AI，零费用、低延迟
- 每个题目组合仅调用一次 AI，后续全部走缓存

---

## 题目类型与答案格式

### single（单选题）

AI 被要求从给定选项中选出唯一正确答案，返回单个字母。

```
问题: 中国的首都是？
类型: single
选项:
  A. 上海
  B. 北京
  C. 广州
  D. 深圳

AI 返回: "B"
数据库存储: B
```

### multiple（多选题）

AI 被要求选出所有正确选项，用 `#` 连接。OCS 的 handler 解析时会按 `#` 拆分。

```
问题: 以下哪些是哺乳动物？
类型: multiple
选项:
  A. 狗
  B. 鲨鱼
  C. 猫
  D. 鳄鱼

AI 返回: "A#C"
数据库存储: A#C
```

### judgement（判断题）

判断题视为特殊的单选题。AI 会将"正确/对/是/True"映射为 A，"错误/错/否/False"映射为 B。如果选项不是标准 A/B 格式，则根据实际选项内容匹配。

```
问题: 地球是圆的
类型: judgement
选项:
  A. 正确
  B. 错误

AI 返回: "A"
数据库存储: A
```

### completion（填空题）

AI 被要求返回精确的填空文本，而非选项字母。

```
问题: 中国的首都是____
类型: completion
选项: (无)

AI 返回: "北京"
数据库存储: 北京
```

---

## 部署指南

### 本地运行（个人使用）

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 5000
```

绑定 `127.0.0.1` 仅本机可访问，更安全。导入 OCS 时使用 `http://localhost:5000/query`。

### 局域网共享

让同一局域网内的其他设备也能使用：

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 5000
```

其他设备上 OCS 的配置中使用该机器的局域网 IP（如 `http://192.168.1.100:5000/query`）。

### 云服务器部署

**使用 systemd 管理进程（Linux）：**

创建 `/etc/systemd/system/ocs-ai-answer.service`：

```ini
[Unit]
Description=OCS AI Question Bank
After=network.target

[Service]
Type=simple
User=www
WorkingDirectory=/opt/ocs-ai-answer
ExecStart=/usr/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 5000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable ocs-ai-answer
sudo systemctl start ocs-ai-answer

# 查看状态
sudo systemctl status ocs-ai-answer

# 查看日志
sudo journalctl -u ocs-ai-answer -f
```

**使用 Nginx 反向代理（可选）：**

```nginx
server {
    listen 80;
    server_name ai-tiku.example.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Docker 部署（可选）

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]
```

```bash
docker build -t ocs-ai-answer .
docker run -d -p 5000:5000 --env-file .env ocs-ai-answer
```

### 安全注意事项

- `.env` 文件包含 API Key，**不要**提交到 Git 仓库（已在 `.gitignore` 中排除）
- 绑定 `0.0.0.0` 时确保防火墙限制访问来源，避免 API Key 被滥用
- 建议在云服务器上使用 Nginx 反向代理 + 限流
- 定期更换 API Key

---

## 故障排查

### 启动报错 `ModuleNotFoundError`

依赖未安装，运行：

```bash
pip install -r requirements.txt
```

### AI 调用返回 `code: 2, msg: "AI_API_KEY is not configured"`

`.env` 文件中的 `AI_API_KEY` 未填写。检查：
1. 是否复制了 `.env.example` 为 `.env`
2. `.env` 中 `AI_API_KEY=` 后面是否有值

### AI 调用返回 `code: 2, msg: "AI API error (status 401)"`

API Key 无效。检查：
1. `.env` 中的 `AI_API_KEY` 是否正确
2. API Key 是否过期或被吊销
3. 对应平台是否还有余额

### AI 调用超时

默认超时 30 秒。如果是本地模型（ollama）或网络较慢，在 `.env` 中调大超时：

```env
AI_TIMEOUT=60
```

### AI 返回答案不准确

1. 检查 `AI_MODEL` 是否使用了推理能力足够的模型
2. 调低 `AI_TEMPERATURE`（如 `0.1`）以获得更确定的答案
3. 在对应题目上使用 `/reload` 接口强制重新推理

### 数据库文件被锁定

同一时间只有一个进程可以写入 SQLite。如果出现锁定错误：
- 确保没有多个服务实例同时运行
- 重启服务

---

## 开发

### 项目结构

```
ocs-ai-answer/
├── app/
│   ├── __init__.py          # 包标记
│   ├── main.py              # FastAPI 入口，CORS 中间件，生命周期管理
│   ├── config.py            # pydantic-settings 配置管理
│   ├── models.py            # 请求/响应数据模型
│   ├── database.py          # SQLite 数据库初始化与 CRUD
│   ├── ai_client.py         # AI API 异步 HTTP 客户端
│   ├── prompt_builder.py    # 提示词模板 + AI 回复解析器
│   ├── router.py            # API 路由（/query /reload /stats /health）
│   └── utils.py             # SHA-256 指纹、选项解析
├── data/                    # SQLite 数据库文件（运行时生成）
├── .env.example             # 配置模板
├── .gitignore
├── requirements.txt
└── README.md
```

### 添加新的 AI 平台支持

本服务以 OpenAI API 格式为标准。如果目标平台完全兼容 OpenAI 的 `/chat/completions` 接口，只需配置 `.env` 即可使用，无需修改代码。

如果平台 API 格式差异较大（如不同的请求体结构），修改 `app/ai_client.py` 中的 `query_ai()` 函数即可适配。

### 调整提示词

修改 `app/prompt_builder.py` 中的 `SYSTEM_PROMPT` 变量可以调整 AI 的答题行为。提示词采用结构化指令，明确告知 AI 不同题型的答案格式要求。

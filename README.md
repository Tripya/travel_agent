# Travel Agent 智能旅行规划助手

这是一个面向学习和面试展示的 AI 旅行规划项目。项目采用前后端分离架构，前端负责收集用户旅行需求和展示结果，后端负责调用大模型、地图工具和 LangGraph 工作流生成结构化行程。

当前版本已将核心规划链路改写为 LangGraph 工作流，同时保留原有 HelloAgents 相关代码作为对照参考，方便学习不同 Agent 架构的实现方式。

## 项目亮点

- 前后端分离：Vue 3 + TypeScript 前端，FastAPI 后端。
- LangGraph 工作流：将旅行规划拆分为景点搜索、天气查询、酒店搜索、行程生成、结果校验和修复等节点。
- LangChain 模型集成：通过 `langchain-openai` 接入 OpenAI 兼容模型。
- 高德地图 MCP 工具：用于 POI 搜索、天气查询、路线规划等地图能力。
- 结构化输出：使用 Pydantic 模型约束最终返回的 `TripPlan`。
- 结果页能力完整：支持每日行程、预算、天气、地图标记、景点图片、编辑行程和导出 PDF/图片。

## 技术栈

### 后端

- Python 3.10+
- FastAPI
- LangGraph
- LangChain / langchain-openai
- Pydantic
- HelloAgents
- 高德地图 MCP 服务 `amap-mcp-server`
- Uvicorn

### 前端

- Vue 3
- TypeScript
- Vite
- Ant Design Vue
- Axios
- 高德地图 JavaScript API
- html2canvas
- jsPDF

## 项目结构

```text
helloagents-trip-planner/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   └── trip_planner_agent.py      # 原 HelloAgents 版本，作为学习对照
│   │   ├── api/
│   │   │   ├── main.py                    # FastAPI 应用入口
│   │   │   └── routes/
│   │   │       ├── trip.py                # 行程规划 API
│   │   │       ├── map.py                 # 地图相关 API
│   │   │       └── poi.py                 # POI 与图片相关 API
│   │   ├── graphs/
│   │   │   └── trip_graph.py              # LangGraph 行程规划工作流
│   │   ├── models/
│   │   │   └── schemas.py                 # Pydantic 请求/响应模型
│   │   ├── services/
│   │   │   ├── amap_service.py            # 高德地图 MCP 封装
│   │   │   ├── llm_service.py             # 原 LLM 服务封装
│   │   │   └── unsplash_service.py        # 景点图片服务
│   │   └── config.py                      # 环境变量与配置管理
│   ├── requirements.txt
│   └── run.py
├── frontend/
│   ├── src/
│   │   ├── services/
│   │   │   └── api.ts                     # 前端 API 调用
│   │   ├── types/
│   │   │   └── index.ts                   # TypeScript 类型定义
│   │   └── views/
│   │       ├── Home.vue                   # 旅行需求表单页
│   │       └── Result.vue                 # 行程结果展示页
│   ├── package.json
│   └── vite.config.ts
├── LANGGRAPH_REWRITE.md                   # LangGraph 改写说明
└── README.md
```

## 当前架构

前端提交旅行需求后，后端通过 FastAPI 接收请求，并交给 LangGraph 工作流生成行程。

```text
Vue 表单
  -> POST /api/trip/plan
  -> FastAPI
  -> LangGraphTripPlanner
      -> search_attractions
      -> get_weather
      -> search_hotels
      -> generate_plan
      -> validate_plan
      -> repair_plan, 当校验失败时触发一次
  -> TripPlanResponse
  -> Vue 结果页展示
```

核心实现位于：

```text
backend/app/graphs/trip_graph.py
```

API 入口位于：

```text
backend/app/api/routes/trip.py
```

## LangGraph 工作流说明

`TripGraphState` 是整个工作流的状态对象，保存以下信息：

- 用户原始请求 `TripRequest`
- 景点搜索结果
- 天气查询结果
- 酒店搜索结果
- 大模型原始输出
- 校验后的 `TripPlan`
- 错误信息
- 修复次数

工作流节点职责：

```text
search_attractions  搜索目的地相关景点
get_weather         查询目的地天气
search_hotels       搜索住宿相关信息
generate_plan       调用大模型生成结构化行程
validate_plan       使用 Pydantic 校验 TripPlan
repair_plan         当 JSON 或字段校验失败时修复输出
```

这样设计的好处是：流程显式、状态可追踪、错误可恢复，比单个黑盒 Agent 更适合工程化和面试讲解。

## 环境变量

后端需要配置以下变量：

```env
AMAP_API_KEY=你的高德地图 Web 服务 API Key
LLM_API_KEY=你的大模型 API Key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_ID=gpt-4o-mini
```

前端需要配置：

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_AMAP_WEB_JS_KEY=你的高德地图 Web JS API Key
```

## 后端启动

项目根目录下已推荐使用 `.venv` 虚拟环境。

### Windows PowerShell

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

安装依赖：

```powershell
python -m pip install -r backend\requirements.txt
```

启动后端：

```powershell
python backend\run.py
```

也可以不激活虚拟环境，直接运行：

```powershell
.\.venv\Scripts\python.exe backend\run.py
```

后端默认地址：

```text
http://localhost:8000
```

API 文档：

```text
http://localhost:8000/docs
```

## 前端启动

```bash
cd frontend
npm install
npm run dev
```

前端默认地址：

```text
http://localhost:5173
```

## 主要 API

```text
POST /api/trip/plan        生成旅行计划
GET  /api/trip/health      检查旅行规划服务
GET  /api/map/poi          搜索 POI
GET  /api/map/weather      查询天气
POST /api/map/route        规划路线
GET  /api/poi/photo        获取景点图片
```

## 前端页面说明

首页 `Home.vue`：

- 输入目的地城市
- 选择开始日期和结束日期
- 自动计算旅行天数
- 选择交通方式
- 选择住宿偏好
- 勾选旅行偏好
- 填写额外需求
- 提交生成旅行计划

结果页 `Result.vue`：

- 展示行程概览
- 展示预算明细
- 展示每日景点、餐饮和酒店
- 展示天气信息
- 使用高德地图展示景点标记和路线
- 支持编辑景点顺序和内容
- 支持导出图片和 PDF

## 面试讲解思路

可以从以下角度介绍这个项目：

1. 项目是一个 AI Travel Planner，采用 Vue + FastAPI 的前后端分离架构。
2. 原版本使用 HelloAgents 顺序调用多个 Agent，新版本将核心流程改成 LangGraph 状态机。
3. LangGraph 将复杂任务拆成多个节点，每个节点只负责一个明确职责。
4. LangChain 负责接入 OpenAI 兼容模型，LangGraph 负责任务编排和状态流转。
5. 使用 Pydantic 对 LLM 输出做结构化校验，避免错误 JSON 直接返回前端。
6. 当校验失败时，工作流会进入 `repair_plan` 节点尝试修复；仍失败则返回 fallback 行程，保证接口可用性。
7. 前端结果页不仅展示文本，还结合地图、图片、预算和导出能力，形成完整用户体验。

一句话总结：

```text
这个项目展示了如何把一个普通旅行规划应用，升级为可观测、可校验、可恢复的 LangGraph 多步骤 Agent 工作流。
```

## 学习路线

建议按以下顺序阅读代码：

1. `frontend/src/views/Home.vue`：理解用户输入如何形成请求。
2. `frontend/src/services/api.ts`：理解前端如何调用后端。
3. `backend/app/models/schemas.py`：理解请求和响应数据结构。
4. `backend/app/api/routes/trip.py`：理解 API 如何调用规划器。
5. `backend/app/graphs/trip_graph.py`：重点阅读 LangGraph 工作流。
6. `frontend/src/views/Result.vue`：理解结果如何展示、编辑和导出。

## 常见问题

### 为什么保留 HelloAgents 代码？

保留 `backend/app/agents/trip_planner_agent.py` 是为了学习对比。你可以比较两种实现：

- HelloAgents 版本：更像顺序调用多个 Agent。
- LangGraph 版本：更像显式状态机，适合复杂工作流。

### 为什么需要 Pydantic 校验？

LLM 输出具有不确定性，可能出现字段缺失、类型错误或 JSON 格式错误。Pydantic 可以把“模型输出”约束成前端可安全使用的数据结构。

### 为什么需要 fallback？

地图工具、模型接口、网络请求都有可能失败。fallback 可以保证后端接口不直接崩溃，前端仍能拿到一个可展示的基础行程。

## License

CC BY-NC-SA 4.0


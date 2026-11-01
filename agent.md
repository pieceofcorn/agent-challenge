# 未来 Agent 接入契约

本文维护数据模型与接口契约。第一阶段 Notice v1 及下列 Python 服务接口已实现。任务 2.1 按用户自主选择授权完成设计审查，具体分析契约见后文；工具执行循环和分析持久化仍未实现。调用方通过服务读取通知，不直接操作采集器或数据库。

## 通知模型 v1

| 字段 | 类型与含义 |
| --- | --- |
| `id` | string，稳定唯一标识，更新内容时保持不变 |
| `source_id` | string，数据源标识 |
| `title` | string，标题 |
| `url` | string 或 null，原文链接；无可靠链接时为空 |
| `published_at` | string 或 null，带时区的 ISO 8601 发布时间 |
| `first_seen_at` | string，首次发现时间 |
| `fetched_at` | string，最近一次成功采集到该通知的时间 |
| `summary` | string 或 null，摘要 |
| `content` | string 或 null，可获得的正文文本 |
| `category` | string，来源分类 |
| `content_hash` | string，规范化有效内容的变化指纹，不包含采集时间 |
| `metadata` | JSON object，必要的来源元数据 |

- 采集时间统一使用 UTC。发布时间无法确定时区时设为 null，原始日期保存在 `metadata`，不得直接当作北京时间。
- 身份识别优先使用规范化原文链接；无可靠链接时使用稳定指纹，并明确指纹组成。同一身份重复采集只更新原记录，保留首次发现时间。
- 身份指纹与 `content_hash` 职责分离。有效内容变化时更新正文及指纹；缺失字段不得无故清空已有有效内容。
- JSON 导出格式为 `{"schema_version": "1", "notices": [...]}`，字段和空值规则与模型一致。

## Python 服务层

以下为契约签名；配置与数据库依赖由服务实例统一持有。

```python
fetch_notices(*, source_ids: list[str] | None = None) -> FetchResult
list_notices(*, source_id: str | None = None,
             since: datetime | None = None,
             limit: int = 50, offset: int = 0) -> list[Notice]
get_notice(notice_id: str) -> Notice | None
get_notice_content(notice_id: str) -> NoticeContent | None
```

- `source_ids=None` 采集全部已启用来源；未知来源标识报参数错误。
- `FetchResult` 包含运行标识、起止时间及逐源结果；逐源记录状态、读取/新增/更新/未变数量和错误类别、摘要。无条目与请求失败必须可区分。
- `since` 按 `fetched_at` 筛选，边界包含；传入时间必须带时区。查询按 `fetched_at` 降序、`id` 升序稳定排列。
- `NoticeContent` 包含 `id`、`url`、`content`、`metadata`。记录不存在返回 None；存在但无正文时返回对象且 `content=null`。
- 单源采集失败写入运行结果并继续；参数错误、配置错误和服务级存储错误显式抛出，不伪装成空结果。

未来 Agent 的功能范围由 `require.md` 限定，本文不定义决策、推送或用户事项接口。

## 第二阶段扩展说明

### 任务 2.1 输入与入口

Notice v1、原查询签名和 schema_version=1 导出不变。分析单独返回，不覆盖来源分类或正文。入口为：

~~~python
AnalysisService(notices, *, client=None, clock=utcnow)
analyze_notice(notice_id, *, preferences=None, as_of=None) -> dict
PulseService.from_config(path="config.toml", *, read_only=False)
~~~

分析经 notices.get_notice 读取快照。CLI analyze 使用只读服务，SQLite 以 mode=ro 打开，不建表或同步来源；只读服务拒绝 fetch_notices，原服务默认行为不变。不存在通知不调用模型；存储错误与无记录分开返回。

preferences 为 null，或仅有 interests、keywords、focus_areas 三个字段的对象；每个值为最多 40 个非空字符串，每项最多 200 字符。只能由用户显式提供，不推断背景；全部空数组视为无可用偏好。--preferences 指定本地 JSON；文件缺失按无偏好，格式错误显式报错。

as_of 为带时区 datetime，默认程序时钟。输入快照为通知 id/source_id/title/url/published_at/summary/content/category 与实际偏好；不发送采集时间或 API Key。输入哈希排除 fetched_at，模型请求随输入附带 Schema。缺正文保持 null，不补采、下载附件或自由联网。单次输入 JSON 超过 64000 字符时拒绝，不静默截断。

### 模型输出 Schema

可执行定义位于 [analysis_models.py](seu_pulse/analysis_models.py) 的严格 Pydantic AnalysisOutput 及其嵌套模型，MODEL_OUTPUT_SCHEMA 由 model_json_schema 生成，不另行手写维护。所有对象字段必需且不接受额外字段；非空字符串拒绝纯空白，各数组最多 40 项。表中 ? 允许 JSON null，不能用空字符串或缺字段表达未知。

| 字段 | 类型及含义 |
| --- | --- |
| category | Decision，value 为 competition/lecture/research/activity/academic_affairs/exchange/scholarship/other/null |
| importance | Decision，value 为 high/medium/low/null，仅依据内容的影响、后果或机会价值 |
| relevance | Decision，value 为 high/medium/low/null，依据通知与显式偏好；无偏好只能为 null |
| action_required | Decision，value 为 true/false/null，通知是否包含明确行动，不断言用户有资格或必须参与 |
| events | Event[]?，保留不同活动及地点 |
| registration_deadlines | Deadline[]?，保留不同报名截止点，不用活动开始替代 |
| limitations | {field:string, reason:string}[]，解释未知或信息缺口 |

嵌套结构如下，列出字段均须存在：

~~~text
Decision = {value, reason:string, evidence:Evidence[]}
Evidence = {field:string, quote:string}
Event = {label:string, time:TimeRange?, location:Location?, evidence:Evidence[]}
TimeRange = {raw_text:string, start:TimePoint?, end:TimePoint?, evidence:Evidence[]}
TimePoint = {date:string?, time:string?, utc_offset:string?}
Location = {mode:online|offline|hybrid|null, name:string?, evidence:Evidence[]}
Deadline = {label:string, raw_text:string, at:TimePoint?, evidence:Evidence[]}
~~~

other 表示内容明确但不属其他类别，null 表示不能判断，不能混用。Decision 即使未知也需非空理由。数组 null 表示未明确或不能判断；[] 用于明确不适用，需在 limitations 解释。未知时间、地点本身用 null；部分时间可保留对象与 raw_text，未知组成部分用 null。

Evidence.field 只允许 notice.title/notice.summary/notice.content 和 preferences.interests/preferences.keywords/preferences.focus_areas；quote 必须是对应字符串或偏好数组某项的连续原文子串。时间 raw_text 须完整包含于本对象的一条 quote，不可拼接多个引用伪造连续原文。已知判断需通知证据；已知相关性还需偏好证据；重要性、类别和行动判断不接受偏好证据替代内容。活动、时间和地点同样需要证据，非空地点 name 须能在引用中找到。报名截止不包括公示、异议或申诉期限；活动数组不重复记录报名窗口。校验检查引用存在性与时间归一化依据，不能证明判断语义完全正确，仍需人工评估。

### 时间与紧迫性

- date 为有效 YYYY-MM-DD，原文须明确完整年月日；不从标题年份、发布时间或采集时间推断。不完整日期、相对日期和暂不支持格式保留原文与 null。
- time 为 HH:mm 或 HH:mm:ss，保留精度；只归一化明确数字 24 小时时刻，不补 00:00/23:59。utc_offset 为 Z 或 ±HH:MM，须有明确数字偏移、UTC/GMT 或原文明示“北京时间/中国标准时间”的依据；后者映射为 +08:00。不因校园地点或系统时区填充。
- raw_text 须在引用中连续存在，并覆盖归一化组成部分依据；完整时间区间结束不得早于开始。原文无效日期可保留 raw_text，但 date 须为 null。
- 仅报名截止的日期、时刻、时区完整可靠时由程序转 UTC，计算 urgency.v1：剩余时间 <=0 为 expired；0..24 小时（含 24）为 high；24..72 小时（含 72）为 medium；超过 72 小时为 low。缺任何组成部分则 level=null。
- 每个报名截止点分别生成 {deadline_index, deadline_at_utc, level, reason}。截止数组为 null 时 urgency=null，为空时为 []；不强行合成整体优先级，模型不得输出 urgency。

### 程序封装与错误

输出含 analysis_schema_version="1"、status、notice_id、notice_content_hash、input_hash、preferences_hash、prompt_hash、analyzed_at、as_of、analysis、urgency、model_info、framework_info、model_requests、warnings、error。framework_info={name,version} 记录实际框架与安装版本，当前为 pydantic-ai/2.54.0。分析版本与 Notice 导出版本分开；prompt_hash 覆盖系统指令、输出 Schema 与格式示例，model_requests 取框架 RunUsage 的请求次数，不证明请求已产生计费；配置错误尚未请求模型时为 0。

status 为 success / insufficient_information / failed。缺正文且部分输出通过校验时为 insufficient_information；无偏好仅影响相关性和 warnings，不单独令整体失败。失败时 analysis/urgency 为 null，error={code,message}；其他情况 error=null。时间由程序生成 UTC ISO 字符串。无通知时相关哈希为 null，不伪造内容指纹。

model_info={provider, requested_model, returned_model, model_version, request_id}；requested_model 当前为 deepseek-flash，返回标识和请求 ID 取实际响应；无法确认的版本为 null，不把文档中别名底层版本当实际回包版本。input_hash 覆盖输入数据快照，不等同于保存快照；完整持久化由任务 2.3 定义。

最多两次模型请求（初次 + 一次输出修正），由 Pydantic AI 的输出重试预算与 UsageLimits(request_limit=2) 共同限制，程序不再叠加外层重试。每次 HTTP 超时 60 秒、max_tokens=4096、响应上限 512 KiB，外层 asyncio.wait_for 设为 2*timeout+5 秒。SDK 网络重试为零，鉴权、网络与限流失败不隐式重试。严格校验原始输出参数 JSON，不以抽取片段、补字段、类型强转或规则猜测修复；Pydantic 验证后仍校验原文证据、时间和空值。新增框架错误 code 为 model_request_limit/model_framework，原有 notice_not_found/notice_read/input_limit/invalid_output、credential_config/model_unavailable、model_auth/model_network/model_rate_limit/model_http/model_redirect/model_response_limit/model_blank/model_incomplete 继续区分。

模型通过 Pydantic AI Agent、OpenAIChatModel、DeepSeekProvider 和官方 OpenAI 兼容 SDK 请求官方 HTTPS Chat Completions；使用非流式非思考模式。输出为 ToolOutput(AnalysisOutput, name="notice_analysis", strict=False)，不启用 DeepSeek beta strict 或原生 JSON Schema 模式。notice_analysis 仅编码最终结果，不执行业务操作；框架校验失败通过 ModelRetry 在同一 Agent 中修正。未注册 get_notice_detail/get_user_preferences 或其他业务、Shell、文件和自由联网工具，不能据此验收任务 2.2。

密钥优先读进程 DEEPSEEK_API_KEY，否则只读 --env-file 文件同名项（默认 .env）。文件须为仅当前用户可读的常规文件，不执行 shell 或展开变量，不向结果/日志写密钥。HTTP 客户端拒绝重定向并限制响应体，禁用 SDK 自动重试，不继承其他 OpenAI 项目的组织/项目身份；不配置外部追踪或 Agent workspace，关闭框架横幅以保持 CLI JSON 输出。

### 任务 2.2 工具循环契约

`analyze` 保留上述 2.1 行为。`agent-analyze` 使用同一输出 Schema 和证据/紧迫性校验，但在同一个 Pydantic AI Agent 中注册两个业务工具。默认初始输入只有通知列表字段（正文为 null）和偏好可用性，不提前读偏好文件；可显式包含初始正文或初始偏好，让模型选择无需工具。正文/工具返回均为不可信数据，不能授权新操作。工具只能访问本次指定通知和调用者指定的偏好配置，不接受 SQL、路径、URL 或 Shell 参数。

| 工具 | 参数（禁止额外字段、强制类型） | 返回 |
| --- | --- | --- |
| get_notice_detail | {notice_id:string}，只接受本次通知 ID | {status, notice}；status=ok/missing_content/not_found/read_error/notice_changed/input_limit/timeout；notice 为必要来源字段、原文正文，失败时 null |
| get_user_preferences | {} | {status, preferences}；status=ok/missing/read_error/input_limit/timeout；缺失或失败时 preferences=null |

通知工具读取已有 SQLite，不采集、不下载、不访问网站；每次在工作线程新建只读连接，不跨线程复用原连接。读取的 content_hash 必须等于初始版本，变化即失败，防止混用两个版本。偏好仅由已有严格 JSON 读取器验证。工具返回大小受 64000 字符上下文限制，超限不截断、不编造；已读取结果在单次运行内缓存，重复请求仍计入次数。读取超时后忽略迟到结果，后台只读线程可能稍后结束，不保证强制终止底层系统调用。

默认预算：模型请求最多 6 次（包含输出修正）、业务工具请求最多 4 次（含重复和非法请求，最终 notice_analysis 不计入）、单次 HTTP 60 秒、单次工具读取 5 秒、整个异步运行 180 秒；均可配置正数，工具次数允许 0。一次响应批量请求超预算时整批不执行。未知工具、非法参数或越界通知 ID 立即失败，不交给任意执行器；SDK 重试为零，结构/证据输出最多修正一次。网络、鉴权、预算及整体超时明确终止，保留已发生的调用。

程序只用初始已提供和实际工具返回的信息校验证据；未读取正文不能引用隐藏正文。工具返回必须回传到同一个 Agent 的后续请求，才允许其生成最终分析；禁止在同一响应里同时请求业务工具和最终输出。成功读取后更新 input_hash/preferences_hash，prompt_hash 另覆盖工具指令与预算；不改 Notice v1 或 analysis_schema_version。缺正文或工具读取失败后仍有合法部分分析时为 insufficient_information，warnings 明示失败；无偏好仍令相关性未知。通知版本变化为 failed，analysis/urgency=null。模型仍自行决定重要性和相关性，紧迫性仍由程序计算。

`agent_trace` 独立记录 trace_version、初始可见字段与输入哈希、预算、模型请求序号、业务工具名、经过校验的通知 ID 参数、实际执行/缓存状态、结果状态/摘要哈希、耗时、下一次请求反馈标记及终止原因；call_id 也是哈希，避免模型自由生成的标识夹带原文。不记录原始正文、偏好值、文件路径、密钥、模型推理或任意非法参数。调用记录只能证明程序观察到的请求和执行，不能证明模型内部思考。

### 后续存储

NoticeAnalysis 持久化对象、SQLite 分析表和写入接口由任务 2.3 定义；当前不建分析表，不把失败或信息不足结果当成功分析入库。

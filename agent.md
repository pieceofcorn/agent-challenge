# 未来 Agent 接入契约

本文维护数据模型与接口契约。第一阶段 Notice v1 及下列 Python 服务接口已在代码中实现；这不表示已有 Information Agent。未来调用方仅依赖本服务层，不直接操作采集器或数据库。第二阶段扩展尚待设计确认，不能作为已实现接口调用。

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

**状态：待设计确认，尚未实现。** 本节只记录分析对象的语义需求，不是 NoticeAnalysis 最终 Schema、数据库表结构或函数签名。完整功能与验收见 [第二阶段需求](require.md#第二阶段需求单-agent-信息理解与智能决策)，任务顺序和状态见 [tasks.md](tasks.md)。

### 分析结果与通知的关系

- 需要一个与原通知关联的独立 NoticeAnalysis 数据对象，能够追溯通知 ID、输入内容、分析时间和实际模型信息；具体字段、版本关联和重复分析策略待设计审查。
- Notice v1 的字段、ID、content_hash、时间与空值规则继续有效，现有服务签名和 schema_version=1 导出格式不变。分析不能覆盖通知标题、正文或来源分类。
- Notice.category 目前表示来源分类，Agent 的内容分类属于分析结果，不把两者混用。正文为空是已存在的合法情况，不能因分析需要就填入模型猜测的正文。

### 分析字段的语义约束

分析应表达内容类别、重要性、用户相关性、是否需要行动、活动时间、报名截止时间、活动地点及判断理由。重要性和相关性分别使用高、中、低的语义，证据不足时保留未知；是否需要行动同样须区分无法确定与不需要。类别枚举、字段名、类型和嵌套结构都待 Schema 审查。

未知事实使用经确认的空值约定，不编造日期、地点、截止时间或用户偏好。活动时间与报名截止时间须分开，原文时间描述和可确定时区是提取依据，不能用通知采集时间补全。最终时间表达、区间、时区和未知值规则须在任务 2.1 中确认。

### 模型输出与程序计算

Agent 根据内容判断重要性，结合显式偏好判断相关性，并给出理由。紧迫性由程序依据可靠截止时间和当前时间计算，不接受 LLM 自行提供的紧迫性结论替代程序计算；阈值及边界待设计确认。模型输出须经 Schema 校验，校验失败的结果不能作为有效分析持久化。

### 工具与存储边界

get_notice_detail 和 get_user_preferences 是第二阶段要求的两个只读工具名称，当前尚无这两个工具接口或执行循环。现有 get_notice_content 可提供已存正文读取能力，能否及如何封装为工具需经设计确认；它不会主动补采正文。偏好存储方式和读取格式尚未确定。

工具参数与返回 Schema、Agent 执行入口、NoticeAnalysis 最终 Schema、SQLite 分析表和持久化函数签名均不在此预设。任务 2.1 完成设计审查后，按已确认方案逐项更新具体契约；接口生效及验证状态必须与实际实现一致。分析写入由程序控制，Agent 不直接写原始通知或数据库。

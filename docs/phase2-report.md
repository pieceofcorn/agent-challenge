# SEU-Pulse 第二阶段项目报告

本报告建立于 2026-11-01，持续记录第二阶段设计、实现与验证。**第 1～10 节保留最初文档准备时的核查快照**，其中“尚未实施”等措辞指当时；后续实际操作按第 11 节起的记录追溯，最新实现与验证见后续各节。开发任务和完成状态只在 [tasks.md](../tasks.md) 维护。

## 1. 阶段目标与范围

第二阶段为“单 Agent 信息理解与智能决策”，在第一阶段采集、存储和查询能力上增加 Information Agent。完整功能和验收集中定义于 [require.md](../require.md#第二阶段需求单-agent-信息理解与智能决策)，本报告不重复维护需求清单。

整体数据流：校园信息采集 → SQLite 通知数据库 → Information Agent → 工具调用与信息补充 → 结构化分析结果 → 数据校验与持久化。按任务 2.1、2.2、2.3 顺序推进，先审查任务 2.1 的最小架构和输出 Schema。多 Agent、RAG、推送等不属于本阶段范围。

## 2. 第一阶段成果复用分析

以下结论来自本次对指定项目文件和既有证据的只读核查，不表示第二阶段已经开发。

| 文件或能力 | 可复用成果 | 第二阶段仍缺少的能力 |
| --- | --- | --- |
| pyproject.toml、setup.cfg | 前者声明 setuptools/wheel 构建配置；后者声明包、Python >=3.10、Python 3.10 的 tomli、可选 Crawl4AI 及 CLI 入口 | 未声明模型 SDK、Agent 框架或 Pydantic AI 依赖 |
| seu_pulse/models.py | Notice、NoticeContent、FetchResult 等 dataclass；UTC、身份及内容指纹实现 | NoticeAnalysis 与输出 Schema 未实现；现有“模型”指通知数据模型，不是 LLM |
| seu_pulse/service.py | PulseService 的采集、列表、按 ID 读取、已存正文读取、导出和运行状态 | 无 Agent 分析入口、工具注册或执行循环；get_notice_content 只读已存正文，不负责补采 |
| seu_pulse/storage.py | sources、notices、runs、source_runs 四类表，事务、去重和通知查询 | 无分析结果表或分析持久化实现 |
| seu_pulse/cli.py | fetch、list、get、export、runs，get 支持 --content-only | 无 Agent 或通知分析命令 |
| config.toml、seu_pulse/config.py | 来源、数据库、RSSHub 和请求参数配置 | 无用户偏好或模型 API 配置 |
| tests/ 与第一阶段证据 | 静态核查有 36 个测试方法；既有日志记录 36 项通过，真实来源结果与第一阶段报告一致 | 无 Agent、模型接入、工具执行循环或分析评估测试 |

历史最终数据由既有 `data/final-live-verification.json`、`data/final-notices.json` 及测试日志交叉核对：两个来源各 14 条，共 28 条，12 条有文本正文；第二轮新增 0、未变 28，成功来源 2、失败 0。本次未重新运行测试或采集，未打开服务实例，也未写数据库。详细历史与时间、证据路径保留在 [第一阶段报告](phase1-report.md)及 [tasks.md 第一阶段最终结果](../tasks.md#获准联网后的最终结果)。

## 3. 技术选型与决策

| 项目 | 当前可验证状态 | 后续决策要求 |
| --- | --- | --- |
| Python、SQLite、dataclass、服务层和 CLI | 已实现，沿用第一阶段成果 | 优先复用，不为第二阶段重建采集系统 |
| HTTPX、BeautifulSoup | 第一阶段需求优先方案；实际使用已获准复用的 urllib/HTMLParser 等效实现 | 本次不更换采集栈 |
| 模型 API、模型版本、SDK | 受检代码和依赖中没有已接入或实测通过的方案 | 在任务 2.1 核对实际可用方案及验证依据，不能写成已选定 |
| Agent 框架、Pydantic AI | 未发现项目依赖或实现 | 是否引入框架待任务 2.1 设计审查，不预设品牌或技术栈 |
| 分析 Schema 与校验库 | 待设计确认，未实现 | 经审查后再更新 agent.md 具体契约 |

本次文档核查同时澄清两点：实际依赖声明位于 setup.cfg，不能仅凭 pyproject.toml 判断依赖；原 agent.md 的开头曾写“不代表接口已经实现”，与现有服务方法不一致，现仅修正状态说明，原 Notice v1、服务签名和导出规则保留。未发现第一阶段最终数量或测试证据与给定历史标准冲突。

## 4. Agent 整体架构

待任务 2.1 设计审查。仅确认项目需求中的职责划分：服务层提供原通知，单 Agent 做内容理解和按需请求工具，程序执行允许的工具、校验结果、计算紧迫性，并在任务 2.3 落地持久化。具体模块、模型调用方式、Agent 入口和循环实现尚未确定。

后续实际决策应记录选择依据、可复用接口、权限边界、失败处理和修改文件；不能仅凭架构草案把执行循环标为已实现。

## 5. 通知结构化理解

任务 2.1 尚未实施。字段语义和三类判断的职责见 [require.md](../require.md#任务-21-通知结构化理解)，分析契约为 [agent.md 中的待确认扩展](../agent.md#第二阶段扩展说明)。NoticeAnalysis 的最终字段、类型、枚举、时间与空值规则均未定稿。

后续记录：经审查的 Schema、实际模型和版本、输入上下文、程序计算字段、校验和错误处理方案、变更文件、实际测试命令及结果。

## 6. Tool Calling 与执行循环

任务 2.2 尚未实施。get_notice_detail 与 get_user_preferences 目前是需求名称，没有已注册工具、参数或返回 Schema。既有正文查询可作为封装候选；用户偏好读取能力尚不存在。

后续记录：经确认的工具契约、真实的模型决策与工具执行记录、结果回传和继续分析、终止条件、权限校验、工具失败和循环边界测试。具体函数签名和框架机制不在本次预设。

## 7. 分析结果持久化

任务 2.3 尚未实施。需要独立 NoticeAnalysis 关联原通知，保存有效分析、分析时间和实际模型信息；最终对象 Schema、SQLite 表、更新策略及服务函数待设计确认。当前数据库不新增分析表，Notice v1 和原 JSON 导出保持兼容。

后续记录：确认的关联与版本规则、迁移或建表方案、持久化实现文件、校验失败处理、读写及兼容性检查结果。

## 8. 测试方案与评估结果

第二阶段尚无测试结果或评估分数。计划在相同可用信息范围下，以 10～15 条真实通知和显式偏好对比 Agent 与简单规则基线，逐样本检查分类、时间、未知值编造、重要性、工具调用及偏好遵守。第一阶段现有 28 条中只有 12 条有文本正文，样本选择须考虑正文缺失与来源类别覆盖，不把全部记录当成完整正文样本。

后续分别记录离线测试、真实模型 API 验证和评估；来源、人工参考、评分口径、模型版本、固定评估时刻、实际命令、逐样本结果和失败案例都须有依据。第一阶段 36 项历史测试不等于第二阶段测试通过，本次未重跑业务测试。

## 9. 阶段验收情况

尚未开展第二阶段验收。任务 2.1、2.2、2.3 的需求已进入文档，代码、具体分析契约、真实模型接入、工具执行循环、分析结果持久化与评估均尚未实施。第一阶段报告及原始验收记录独立保留。

后续每完成一个任务，依据 require.md 验收标准在 tasks.md 更新进度，并在本报告相应章节记录实际采用的方案、关键决策、修改文件、测试命令、结果与遗留问题；本报告不重复维护任务勾选清单。

## 10. 遗留问题与后续工作

先开展任务 2.1 的设计审查，确认可用模型 API 与模型版本、是否采用 Agent 框架、Schema 校验方式、输出字段及时间/空值规则。用户偏好配置格式、任务 2.2 的具体工具契约与执行循环、任务 2.3 的持久化契约随后依确认方案细化，不在文档准备时提前锁定。

第一阶段仍存在无正文条目、其他来源未完全验证及 Git diff 条件不足等限制，保留原报告和任务记录，不在本次改写成已解决。当前目录不是有效 Git 工作树，本次使用修改前快照与文档检查核对变更，未初始化或改动 Git 元数据。


## 11. 2026-11-01 开工核查、模型文档与版本管理操作

本次重新读取七份项目文件，并检查模型、服务、存储、依赖声明和虚拟环境。Python 为 3.10.12；系统未提供 python 命令，现有 .venv/bin/python 可用，安装元数据包含 seu-pulse 0.1.0、tomli 1.0.3、setuptools 59.6.0 和 wheel 0.37.1。未安装新依赖，未重跑业务测试或采集，未实例化会同步来源配置的 PulseService，未写数据库。

历史文件核对结果：final-notices.json 保持 Notice v1，两个来源各 14 条、共 28 条，12 条有文本正文；final-live-verification.json 的第二轮新增 0、更新 0、未变 28。两个最终测试日志均记录 36 项通过，属于历史结果。现有通知含一个报名、笔试、复试并存的样本，Schema 审查需处理多个时间及正文未明确时区的情况；这里未预定字段或更改 agent.md 契约。

用户提出采用 DeepSeek Flash。经 Firecrawl 读取[官方首次调用文档](https://api-docs.deepseek.com/)，请求模型名为 deepseek-flash，用户粘贴的 (1) 是脚注，文档说明该别名当前由 DeepSeek-V4.1-Flash-1017 提供服务；deepseek-v4-pro 是另一个模型。OpenAI 与 Anthropic 兼容基址均与用户所给地址一致。这些是官方文档确认，项目模型接入仍为未验证；没有凭据或模型推理 POST 请求，不能据文档标记为实测可用。

[官方 JSON Output 文档](https://api-docs.deepseek.com/guides/json_mode/)要求 json_object 格式，并说明可能出现空白 content，故仍需本地字段、时间、证据与空值校验。[官方 Tool Calls 文档](https://api-docs.deepseek.com/guides/tool_calls/)可作为任务 2.2 的接口依据；尚未据此实现工具循环。通过 Firecrawl 对两处 API 基址进行未鉴权只读探测均返回 HTTP 401，属于缺少认证的探测结果，不是本项目模型请求验证或网络故障结论。未请求或保存用户密钥。

随后用户明确授权初始化 Git、配置 GitHub 并检查敏感文件。初始化前实际 .git 路径不存在，与早期报告的“空目录”历史状态不同；执行 git init --initial-branch=main 和 origin 配置，未删除任何 Git 数据。沙箱内 GitHub 请求连接失败，获准沙箱外 ls-remote 及 fetch 成功；远端 main 的 69a7cb4 初始提交仅有 README.md。本地尚未建立提交，后续应承接远端历史。未执行 add、commit、push、checkout、merge、reset 或删除文件。

本次修改限于 .gitignore、README.md、tasks.md 与本报告，记录忽略规则、GitHub 登录和 DeepSeek 密钥存放方法。data/ 全部 60 个原文件保留并忽略，不复制含通知正文或联系人信息的运行数据到提交清单；源码、文档、公共配置和离线 fixture 可纳入版本控制。文本扫描的三处 URL 凭据均位于 example.test 测试，未发现真实 API Key、GitHub Token 或私钥；二进制文件未作文本扫描，均被 data/ 规则排除。认证检查不读取或打印凭据值，实际 GitHub 写权限需用户登录后核对，未以匿名读取成功代替认证成功。

实际检查命令包括 git rev-parse --is-inside-work-tree、git ls-remote --symref、git fetch --no-tags origin main、git ls-tree -r --name-only origin/main、git ls-files --others --exclude-standard、git check-ignore -v 及基于文件路径/行号的脱敏文本扫描。用户需要执行的身份、认证与密钥存放命令集中见 README；进度只在 tasks.md 勾选。首次 Commit + Push 继续等待用户确认，未将本次 Git 配置视为任务 2.1 功能交付。


## 12. 本地凭据配置复核

用户完成 GitHub 登录后，通过 gh api repos/pieceofcorn/agent-challenge 只读取仓库名称和 permissions.push，返回 pieceofcorn/agent-challenge 与 true。沙箱内连接被拒绝，获准沙箱外核验成功；没有执行推送。随后用户完成提交身份和密钥存放，复核 user.name/user.email 均已配置；仅记录配置是否存在，不写入个人邮箱。

.env 为项目根目录的常规文件，权限 600，单个 DEEPSEEK_API_KEY 项非空，未发现占位文字；git check-ignore 确认忽略，git ls-files 确认未跟踪。检查只返回格式与状态，不显示或记录密钥值。该结论不代表密钥可用或模型已接通；未发送模型推理请求，项目仍无 .env 自动加载实现。检查时暂存区为空，本地 HEAD 尚无提交；未执行 Commit 或 Push。任务勾选仅维护于 tasks.md。

## 13. 用户授权自主执行后的基线复验

用户随后明确授权自行决定每次 Commit/Push，并授权常规技术和实现选择，仅在重大风险、重大返工或持续失败且原因不明时等待决定。AGENTS.md 据此更新执行规则，前述等待首次提交确认的段落保留为当时的历史记录。

首次提交前重新执行 `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -v`，36 项测试在 1.971 秒内全部通过；`.venv/bin/python -m compileall -q seu_pulse scripts tests` 退出码 0。本轮是第一阶段回归复验，没有调用模型 API 或重新采集。原有 60 个 data/ 文件记录 SHA-256，后续按同一批路径复核，避免历史证据被覆盖。

获取最新远端后，使用 `git branch --track main origin/main` 与 `git read-tree HEAD` 建立远端历史基线，仅写 Git 引用、配置和索引，不 checkout 工作文件。远端既有 69a7cb4 提交及 README 保留；首次项目提交在其上追加，不建立无关根历史。任务 2.1 将先完成并记录设计审查，再据用户最新授权实施，不把已存放密钥视为模型验证通过。

首次项目提交 e58f155（chore: import SEU-Pulse baseline and development docs）已推送，远端 main 从 69a7cb4 前进到该提交。暂存内容再次逐文件检查，不含 .env、配置中的真实密钥或 data/；34 个项目文件纳入版本控制。差异检查修正 pyproject.toml 文件末尾多余空行，未改变构建语义。新回归日志独立保存为 data/git-baseline-tests-20261101.log，原有 60 个 data/ 文件哈希均未变化。

## 14. 任务 2.1 设计审查与取舍

依据用户最新的常规选择自主授权，由 Codex 完成设计审查并确认低风险实现方案，随后更新 agent.md 具体契约。任务 2.2 的真正工具循环和任务 2.3 的分析存储仍分开实施。此次单次通知理解组件不作为完整 Agent 的验收结果。

最小架构选择：现有服务增加可选只读打开方式；analysis_models.py 集中模型输出 Schema 与严格校验；model_client.py 以标准库 urllib/json 实现 DeepSeek 非流式 Chat Completions 适配与本地密钥读取；analysis.py 组织输入快照、有限修正、结果封装及程序紧迫性计算；CLI 增加 analyze。无需引入未经项目验证的 SDK、Agent 框架或 Pydantic AI，也不复用带校园 robots/重定向策略的采集客户端来发送模型密钥。

自审重点包括：同一通知多个活动与截止点、偏好缺失不等于低相关性、重要性不依赖紧迫性、原文未明确的年份/时区保持未知、模型字段不能注入程序计算字段、正文和偏好引用必须能在实际输入中找到，以及读取通知不应改写生产数据库。选择活动与报名截止数组、带来源字段的原文证据、时间组成部分与原文并存、每个截止点分别计算紧迫性。24/72 小时阈值及恰好到期的边界由程序统一执行；完整规则只在 agent.md 维护。

错误与预算审查：首次请求和最多一次结构修正，单次请求 60 秒、输出 4096 tokens；鉴权/网络/限流错误直接返回失败，不隐藏重试。空白响应、截断、无效 JSON/字段/证据均不能变成成功分析。缺正文允许返回可校验的部分分析，但标为信息不足。模型 API、响应模型标识及输出行为将在真实请求后分别记录，不预设返回的模型版本。

## 15. 任务 2.1 实现与独立验证

实现新增 analysis_models.py、model_client.py、analysis.py、tests/test_analysis.py 及 scripts/verify_analysis_live.py。现有 storage/service 仅增加可选只读打开方式，默认采集行为保持兼容；CLI 增加 analyze，原 Notice v1 与原 JSON 导出不增加分析字段。不增加依赖、分析表或工具注册。具体调用、偏好 JSON 和验证命令已写入 README，输出与错误契约只在 agent.md 维护。

首轮新增离线用例发现 fixture 的全角冒号与第一阶段 NFKC 规范化后的正文不同，导致逐字证据校验拒绝引用；修正测试输入以匹配实际通知快照，没有放宽校验。随后 51 项（36 项历史回归与 15 项新增）通过。后续又补充密钥请求头注入的阻断测试；最终测试结果单独记录如下，未用首次失败结果作为通过依据。

真实验证分为两类。原计划将三条已有通知发送到官方 DeepSeek，执行环境自动审批拒绝：既有授权没有具体覆盖这批潜在非公开内容的外发，且正文可能含公开联系人信息。该操作没有执行，不能记录成模型请求失败、网络失败或真实通知分析通过；已向用户说明原因并请求具体授权。该三条真实通知验证仍未开展。

采用安全替代：verify_analysis_live.py 的 --synthetic 仅发送脚本内手写合成文本，不读取校园通知库或用户偏好；通过用户配置的密钥调用真实官方 API，模拟输入不冒充真实采集。首轮证据为 data/phase2-model-synthetic-20261101-01.json：完整样本两次均因 events 类型不符而失败，缺正文样本通过校验且标为信息不足，共三次请求。该失败文件保留。JSON Output 本身没有保证业务 Schema，这是本地严格校验必须保留的实际证据。

补充明确的数组要求和格式示例后，第二轮证据 data/phase2-model-synthetic-20261101-02.json 于 UTC 2026-10-31T19:30:22.070938+00:00（北京时间 11 月 1 日）保存：完整样本 success，缺正文样本 insufficient_information；各一次请求，无错误。完整样本分类 lecture，原文 UTC 报名截止归一化为 2026-11-03T12:00:00+00:00，程序计算为 medium；无偏好相关性为 null。实际返回模型名均为 deepseek-flash，具体版本未返回，保留 null，不以官方文档中的底层版本补填。第二轮另存了未校验的模型 content 与请求 ID，均在忽略目录，不保存认证头或思考链。

以上结论为“真实模型 API 实测可用（合成输入）”，不是“真实校园通知端到端已验证”。没有进行真实通知工具调用、10～15 条样本评估、规则基线打分或分析结果入库。真实通知仍需具体外发授权，任务 2.2 与 2.3 的剩余范围独立保留。

最终回归命令为 `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -v`，52 项在 2.351 秒内全部通过（原有 36 项完整保留，新增 16 项覆盖严格字段/证据、未知值、日期时区、紧迫性边界、偏好、只读库、CLI、网络与鉴权失败、有限修正及请求头注入）。compileall 退出码 0，31 个 Markdown 相对链接和对应锚点有效，git diff --check 通过。

现有 .venv 的 pyvenv.cfg 为 include-system-site-packages=true，本轮 pip check 失败原因为系统 PyGObject 依赖 pycairo 缺失，与本项目依赖无关；未安装或修改系统组件。使用既有构建工具离线构建新 wheel 到 data/phase2-wheels/seu_pulse-0.1.0-py3-none-any.whl（SHA-256 55b0148cc38673cbf45eea0fc80b790ff19e242791da1a1e212312ec4366c3f9），未覆盖 data/wheels 的历史产物。干净虚拟环境仅安装此 wheel 与既有 tomli wheel，pip check 返回 No broken requirements found，安装后的 analyze --help 正常。

独立环境以 Python -I 先导入安装包，并确认模块路径位于该环境的 site-packages 后再加载仓库测试，52 项在 2.313 秒内全部通过。日志为 data/phase2-isolated-tests-20261101.log；使用安装包而不是当前目录源码完成复验。上述测试和合成 API 请求没有重新采集来源或修改原始通知；原有数据文件哈希在提交前继续核对。未实现或暗示主动推送、任意工具执行或分析结果入库。

## 16. 任务 2.1 版本交付

功能提交为 92bd26f061832844e5c7b988a0d6ab1fea9bd6e3（feat: add structured notice analysis with DeepSeek），普通推送将远端 main 从 e58f155 前进到该提交；Git 返回成功，本地 HEAD 与 origin/main 一致。功能提交涉及 13 个文件，39 个当前版本文件逐个扫描暂存内容，未发现本机真实密钥、GitHub Token 或私钥，.env 与 data/ 未跟踪。第一阶段 Notice v1 契约块、原任务归档及原有 60 个数据文件通过原值/哈希比较，均未改变。

推送后按用户流程更新本节与 tasks.md；记录只描述已发生的验证和交付。任务 2.2/2.3 继续保留为未实施，自动审批拒绝的真实通知外发没有重试、绕行或冒充合成验证。模型接口已以合成输入验证；真实通知的外发授权仍为单独待办。

## 17. 获得具体授权后的三条真实通知验证

用户明确回复“允许”，授权此前列出的吴院拟录取公示、计算机拔尖班报名通知及因公出境管理通知发送到官方 DeepSeek；没有扩大来源、通知 ID 或用户偏好范围。首轮 data/phase2-analysis-live-20261101-01.json 为两个 failed/invalid_output、一个 insufficient_information，共五次请求，数据库哈希相同。公示通知误把异议期限作为报名截止，且修正时补出了当前时间片段没有的年份；报名通知出现 raw_text 超出其引用、修正响应省略嵌套 evidence 等问题。校验器正确拒绝，未视为有效分析。该失败文件原样保留。

完善系统指令中的期限语义与嵌套结构要求；修正请求保留上一条模型答案并返回安全、具体的字段要求，不再仅给不充分的字段路径。加强 raw_text 必须落在单条 quote 的规则，拒绝拼接两条引用。新增两项回归：嵌套修正接收原答案/必需字段反馈，以及引用拼接攻击。54 项测试在 2.120 秒通过，未放宽年份、时区或证据要求。

第二轮 data/phase2-analysis-live-20261101-02.json 于 UTC 2026-11-01T04:40:15.712264+00:00 保存，三条各一次请求，返回模型均为 deepseek-flash，数据库前后哈希相同：

| 真实通知 | ID 前缀 | 状态及人工核对 |
| --- | --- | --- |
| 吴院拟录取公示 | 7dc01ff718ca | success；academic_affairs，中重要性；异议行动与报名截止分开，无报名截止，不补公示片段缺失年份 |
| 计算机拔尖班报名 | b1db4af52ab3 | success；academic_affairs，高重要性；保留宣讲、笔试、复试三个时间及报名截止 2026-08-31 20:00。原文无时区，utc_offset 与程序紧迫性保持 null |
| 因公出境管理 | c5ba1846f797 | insufficient_information；无正文，重要性、行动和时间未知，不编造政策细节 |

三条均无用户偏好，相关性均为 null。只核查这三条的接口、结构、证据和未知值表现，不计算分类准确率或冒充任务 2.3 评估，也未进行工具调用或分析入库。生产数据库只读，先前证据文件继续保留。

验证期间用户追加“引入 Pydantic AI”。将迁移前的真实结果作为对照保留，随后实施框架接入。官方当前安装文档要求 Python 3.11+；PyPI 官方元数据给出当前 2.64.0 要求 >=3.11，而兼容本项目 Python 3.10.12 的最新稳定版为 2.54.0（Requires-Python >=3.10）。已下载其官方 wheel 核查接口；尚未因下载或文档核对声称框架实测通过。

## 18. Pydantic AI 实际接入与验证

按用户明确要求，将 setup.cfg 的运行依赖固定为 pydantic-ai-slim[openai]==2.54.0，仅安装所需提供方依赖，不改系统 Python。选型核对了[官方安装说明](https://pydantic.dev/docs/ai/overview/install/)、[结构化输出与校验说明](https://pydantic.dev/docs/ai/core-concepts/output/)及 [PyPI 元数据](https://pypi.org/pypi/pydantic-ai-slim/json)，并读取实际下载的 2.54.0 wheel 源码和签名，避免直接套用新版文档。实装版本为 Pydantic AI 2.54.0、Pydantic 2.14.2、OpenAI SDK 3.42.0、httpx2 2.14.0。

analysis_models.py 以严格 Pydantic BaseModel 定义结构，配置 extra=forbid/strict=True；MODEL_OUTPUT_SCHEMA 由模型生成，保留原字段、未知值及证据语义。DeepSeekClient 使用 Pydantic AI Agent、OpenAIChatModel、DeepSeekProvider 与 ToolOutput(AnalysisOutput, name=notice_analysis, strict=False)。该输出工具只承载最终 JSON 参数，不读取通知或偏好，不执行 Shell、文件或自由联网；未注册任务 2.2 的两个业务工具，因此不作为 2.2 验收。

原文证据、日期/时区、重复 JSON key 和原始参数 JSON 格式仍由本地严格检查；接入框架 output_validator 并用 ModelRetry 反馈。输出重试最多一次、UsageLimits(request_limit=2)，AnalysisService 不再叠加生产路径的外层修正；SDK 网络重试为零。框架版本与真实请求数进入程序封装，模型的未知具体版本仍为 null。请求继续固定到官方 DeepSeek，显式使用 max_tokens、关闭思考/流式及重定向，限制 512 KiB 响应，不继承其他 OpenAI 组织/项目身份，不配置外部追踪；关闭默认横幅保持 CLI JSON 输出。

迁移中保留失败：提示式 JSON 输出的 data/phase2-pydantic-live-20261101-01.json 为 success/failed/insufficient_information，共五次请求。报名通知仍重复构造一个无完整连续原文依据的截止，严格校验拒绝。随后采用框架官方默认推荐的 ToolOutput 结构化输出方式，保留原语义与请求上限，而非放宽证据规则。该变化不提供业务工具权限。

最终框架真实证据为 data/phase2-pydantic-live-20261101-02.json，于 UTC 2026-11-01T05:12:07.896834+00:00 保存。仍只处理已获授权的三条通知：公示 success/一次请求，拔尖班 success/两次请求（含一次框架修正），缺正文通知 insufficient_information/一次请求；总四次，实际模型均为 deepseek-flash，框架标识 pydantic-ai/2.54.0。报名通知保留三个活动和一个报名截止，原文没有时区，因此 UTC 截止与紧迫性为 null；无偏好相关性均为 null。数据库前后哈希相同；失败、迁移前对照和本轮数据文件均未覆盖。

离线验证新增七项框架级用例：真实 Agent/严格输出模型、嵌套结构修正、语义证据修正、两次请求边界、重复键/代码围栏拒绝、未知时区防补全、未注册工具无执行器。SDK 传输测试改用 MockTransport 检查官方端点、输出工具、max_tokens、网络/鉴权错误及响应边界；原有 36 项第一阶段测试未删除或替换。完整 61 项在开发环境 2.939 秒通过，compileall 与差异检查通过。

执行环境诊断与产品错误分开记录：最小 asyncio.to_thread 探测在当前受限沙箱中超时退出 124，同一无文件/网络操作的探测获准沙箱外立即返回成功；纯异步 FunctionModel 在沙箱内也通过。据此定位为沙箱线程唤醒限制，未当作 DeepSeek 网络失败或版本不兼容。框架离线测试获准在沙箱外执行，所有模型/HTTP 均为 fixture、FunctionModel 或 MockTransport，不外发真实数据。初期 FunctionModel 名称断言及嵌套网络异常分类问题已由固定模拟模型标识和保留安全异常链分类修正；未注册工具请求归为 invalid_output，未执行任何工具。

构建新的 data/pydantic-ai-wheels/seu_pulse-0.1.0-py3-none-any.whl，SHA-256 为 6715dd1229fa7580e2b63203409d75a3688b14214bce72eee81b4be6adf99b65；该目录另保存公开依赖 wheel，未覆盖旧产物。干净环境完全离线安装，pip check 无依赖缺失，安装后的 analyze --help 正常。以 Python -I 先确认实际导入 site-packages 中的安装包，再运行 61 项测试，3.106 秒全部通过；日志 data/phase2-pydantic-isolated-tests-20261101.log。旧 .venv 继承系统包的 PyGObject/pycairo 问题不作为项目依赖故障处理，未修改系统组件。

用户询问修改沙箱权限后，按官方 OpenAI 文档核对本机 Codex CLI 0.166.0 和用户配置：sandbox_workspace_write.network_access 已为 true，但当前运行会话仍被下发为联网受限，不能据配置值声称运行策略已经改变。用户确认从 VS Code 的 WSL Ubuntu 内置终端启动，已给出 codex --approve-for-me -c 'sandbox_workspace_write.network_access=true' resume --last 的恢复方式；待当前交付保存后由用户恢复，再在沙箱内复测。没有编辑用户全局安全配置或绕过现有执行策略。

用户随后补充失败中止要求，已更新仓库现有 AGENTS.md，并通过差异检查；不在数据契约或本报告重复维护执行规则。沙箱生效检查留待用户恢复后进行，没有继续重复受限环境中的失败探测。

本轮规则提交 89651ea 与框架功能提交 6c67bcb 已普通推送，功能推送后 HEAD 与 origin/main 一致。提交前扫描全部 40 个版本文件，无真实密钥、Token 或私钥，.env/data 未跟踪；本轮开始前已有的 65 个数据文件哈希未变，Notice v1 契约块及第一阶段任务归档原文未变。新 wheel 的 12 个模块逐字节匹配当前源码。按用户流程，在推送成功后补记交付记录；未运行任务 2.2/2.3 或更改全局沙箱策略。

## 19. 恢复会话后的默认沙箱验证（2026-11-01）

用户要求先验证联网与 asyncio 线程唤醒，再实施 2.2。本轮在默认沙箱（无提权）执行最小 asyncio.wait_for(asyncio.to_thread(...), timeout=5) 探测，外层 timeout 10s，返回 ASYNCIO_THREAD_OK，退出码 0；urllib 请求 https://api.github.com（timeout=15）返回 HTTP 200，退出码 0。此前限制的历史诊断仍保留，本轮不再沿用“当前沙箱不可联网”的结论，也未修改全局配置。

开工 main 与 origin/main 同步，HEAD be1db6f；Python 3.10.12、Pydantic AI 2.54.0，复用现有依赖。开发前对 data/ 的 99 个现有文件建立 SHA256 快照用于保全检查，不输出密钥。遵循执行规则，未进行无关修改或部署。

## 20. 任务 2.2 最小设计与接口依据

常规选择按用户既有自主授权实施：保留 analyze 入口，新增 agent-analyze；复用 AnalysisService、严格 Schema、证据校验和程序紧迫性，只扩展同一个 Pydantic AI Agent 的工具集合、可见上下文与执行记录。模型按需选择读取当前通知或调用者指定的显式偏好，不固定预取两个工具。具体参数、返回状态和预算统一维护于 agent.md，进度仅记 tasks.md。

通过 read-docs 技能检索官方工具/usage 文档 https://pydantic.dev/docs/ai/llms-full.txt ，确认模型请求与成功工具调用是不同预算；同时实际检查已安装 2.54.0 的 Tool、RunContext、Agent、UsageLimits 签名。本项目另外在模型响应接收处限制业务工具请求（包含重复/非法请求），防止只统计成功执行而绕过预算。未依赖最新文档中可能较晚加入的能力。

读取 SQLite 在独立线程的新只读连接中进行；模型不接触数据库连接、路径或凭据。读取超时忽略迟到结果，不声称强制杀死底层调用。证据只校验模型实际获得的上下文，运行记录只保留状态和哈希。保留任务 2.3 的分析持久化及 10～15 条评估边界；真实联网验证仅使用此前明确获准的三条通知。

## 21. 任务 2.2 实现与验证记录

新增 seu_pulse/information_agent.py 与 agent_tools.py，分别编排可见输入/结果封装和两个只读工具/预算/执行记录；复用 analysis.py 的输出校验与紧迫性，model_client.py 的同一 Agent 注册实际业务工具，cli.py 增加 agent-analyze。原 analyze 的两次请求限制、Notice v1、采集/查询接口与数据库结构保留。模型只获得当前通知 ID 和可用性提示，不能决定文件路径、数据库操作或联网目标。读取超时使用受控后台只读线程，忽略迟到结果；并不强制终止系统调用。调用标识在最终实现中同样只存哈希。

新增 tests/test_information_agent.py 的 18 项测试，真实运行 Pydantic AI FunctionModel、HTTP MockTransport 序列化与临时 SQLite，未调用真实模型。覆盖初始充分而无工具、需要正文/显式偏好、已加载偏好直接输出、隐藏正文不能被引用、缺失/读取失败/消失/版本变化、非法工具名和参数、其他通知 ID、重复缓存、整批超预算拒绝、模型次数边界、业务工具与最终输出混合拒绝、工具与总运行超时、迟到结果不进入上下文、敏感调用 ID 哈希、只读兼容与 UTC 零偏移。

开发首轮 17 项测试有两处夹具错误：恰好 24 小时应为 high（误写 medium），RSSHub 测试来源需要配置服务地址；修正后通过，日志 phase22-tool-tests-01/02-20261101.log 均保留。新增 UTC 回归时，夹具 JSON 默认 Unicode 转义导致中文替换未生效，03 日志保留该错误；修正为 ensure_ascii=False 后 04 日志 18 项通过（0.427 秒）。这些均为明确的测试夹具问题，没有把失败改写成通过。

完整离线回归 `.venv/bin/python -m unittest discover -v`：79 项通过，2.622 秒，日志 data/phase22-final-tests-20261101.log。独立安装最终 wheel 后再运行 79 项通过，2.627 秒，日志 data/phase22-final-isolated-tests-20261101.log；导入并检查所有加载的 13 个 seu_pulse 模块确实来自 site-packages，排除测试误用工作树代码，干净环境 pip check 无缺失。环境 /tmp/seu-pulse-phase22-install.CqgyWR/venv；开发 .venv 原有系统依赖问题未擅改。CLI 主帮助和 agent-analyze 帮助通过。

运行/构建/复验命令已写入 README。data/phase22-wheels/ 保留初版构建，最终代码的独立安装产物另存 data/phase22-final-wheels/，不覆盖第一阶段、任务 2.1 或本轮早期产物。源码、测试、契约与说明纳入版本管理，所有运行证据及原文仍在忽略目录。

## 22. 任务 2.2 真实模型证据与边界

全部 API 验证在默认沙箱内完成，无提权、无新依赖、无新增采集来源。合成输入为脚本手写通知；偏好模式为明确标识的科研讲座测试兴趣，不代表用户偏好。所有文件使用新名称保留，每份包含模型实际返回、请求数、工具状态、结果哈希及反馈序号。

| 本地证据 | 实际输入与结果 | 模型请求 / 实际工具 |
| --- | --- | --- |
| data/phase22-synthetic-live-20261101-01.json | 合成通知，默认隐藏正文；完整条 success，空正文条 insufficient_information | 3/2 次；各调用一次 get_notice_detail，反馈均进入第 2 次请求 |
| data/phase22-synthetic-preferences-live-20261101-01.json | 合成全文与可读测试偏好；首条 failed，次条信息不足；保留失败 | 2/2 次；首条未调用工具，次条调用正文与偏好并回传 |
| data/phase22-synthetic-preferences-live-20261101-02.json | 修正后合成偏好复验；完整条 success，空正文条 insufficient_information | 2/2 次；完整条自主选择 get_user_preferences，状态 ok、反馈请求 2；空正文条选择正文工具 |
| data/phase22-synthetic-initial-live-20261101-01.json | 初始已提供合成正文、无偏好；完整条成功，空正文条信息不足 | 1/1 次；均未调用业务工具，证明不固定预取 |
| data/phase22-notices-live-20261101-01.json | 仅使用此前获准的三条真实通知；两条 success，一条 insufficient_information | 各 2 次；各实际调用 get_notice_detail，状态 ok/ok/missing_content，反馈均进入第 2 次请求 |

首轮合成偏好失败定位为既有时间校验器只接受原文 UTC 对应的 Z，却拒绝等价 +00:00；模型一次修正仍保留 +00:00，程序如实失败，未降低未知时区约束。现增加对显式 UTC/GMT 的 +00:00 等价支持并加入回归，同时确认 +01:00 仍拒绝。工具提示另明确“偏好配置尚未读取”不同于“未配置”，未强制程序预取所有工具。第二轮通过，没有反复重试至超过三次规则。

真实三条依次为：吴院二次选拔拟录取公示（145 字正文）、计算机拔尖班报名通知（1280 字正文）、因公出境管理通知（正文缺失）。原始 ID/来源链接与 content_hash 在上述本地 JSON；第一、二条正文工具返回原文，第三条明确 missing_content。数据库前后 SHA256 相同，未写原通知或分析表；没有外发其他通知或实际个人偏好。实际返回模型标识均为 deepseek-flash，具体版本未知仍为 null。

数据保全检查：开发前 99 个 data/ 文件逐个 SHA256 对比无变化；第一阶段 tasks.md 归档与 HEAD 原文一致，phase1-report.md、Notice v1、采集/存储模块未改。候选版本文件共 44 个，检查实际 .env 密钥及凭据模式无命中；.env 权限仍 600，.env 和 data/ 未被跟踪。完整原文和未校验响应仅留本地，不能把 GitHub 备份误认为运行证据备份。

本轮实测证明受限工具执行循环，不证明模型语义完全正确。用户相关性只在合成显式偏好与离线夹具验证，真实通知未配置偏好仍未知；时区/年份不明确仍保留 null。任务 2.3 的分析对象持久化、10～15 条人工参考及规则基线评估不在本轮范围。

## 23. 任务 2.2 版本交付

功能提交 ec6f2bb（feat: add bounded read-only information agent tools）已普通推送至 origin/main，继承 be1db6f，未强制推送或覆盖远端历史。最终 wheel SHA256 为 a44f570ad8c1d5491f4ebe077746bfedd3c3e548180669849f589217d5f6afed，14 个包内源码模块与工作树一致；compileall、差异空白、文档本地链接、44 个候选文件的实际密钥/凭据模式检查及 99 个旧证据文件保全检查通过。交付文档另澄清 agent.md 引言和 2.1 入口范围，避免把 2.1 不注册工具的说明误读为 2.2 尚未实现。

用户随后要求阅读相关文档与接口、了解进度后继续。已再次核对 require.md 的任务 2.3、agent.md 的现有分析/工具契约与 Storage 接口；后续按 tasks.md 推进持久化设计和评估准备，不将既有三条外发授权自动扩大为其他真实通知。

## 24. 任务 2.3 设计自审与评估准备

在任务 2.2 交付后按用户“阅读相关文档与接口，了解开发进度后继续”及既有常规自主决策授权推进。复读 require.md 任务 2.3/阶段验收、agent.md、Storage/AnalysisService/InformationAgent/CLI 接口。选择独立分析 SQLite，避免改写已有采集数据库及其历史验收哈希；程序显式 --save 才写，模型继续只有两个只读工具。每次 UUID 追加，保留实际可见输入与原内容最小快照，用于区别版本和公平规则比较；失败尝试单独标记，不能变成有效分析。具体结构、事务与接口只维护在 agent.md。

从现有 28 条中选择 15 条候选：所有 12 条有正文通知，加上因公出境管理、纪念馆志愿讲解员、五校书院交流三条无正文通知。来源为既有两个官方栏目，无新增采集；清单在 docs/phase23-evaluation-review.md，本地 ID/内容指纹/正文情况在 data/phase23-evaluation-manifest-20261101.json。候选覆盖交流项目、选拔、公示、说明会、招募和缺正文，但独立竞赛/科研/奖学金类别不足，不以合成通知填充真实样本。尚无人工签审参考。

旧授权只覆盖三条，已向用户提出其余候选向官方 DeepSeek 外发的具体范围，说明可能含公开联系人、无真实个人偏好、原始材料仅本地保存。待明确回复前不外发新增通知；持久化、离线回归和本地参考草稿可独立继续。

## 25. 任务 2.3 本轮实现、离线验证及未完成项

新增 analysis_store.py：NoticeAnalysis/AnalysisAttempt 和独立 AnalysisStore，analysis_attempts 保存所有合法执行封装，notice_analyses 仅关联有效/明确部分结果。每次 UUID 追加，事务中写入，外键/状态约束阻止失败成为有效分析；保存时重算源内容、可见输入/偏好哈希、严格 Schema/原文证据与程序紧迫性，读取时也验证 JSON 与关系索引一致。source_snapshot 排除非必要 metadata/采集时间；analysis.py 暴露防外部修改的输入/原内容快照。CLI 增加显式 --save/--analysis-db、analysis-list/get；原 analyze/agent-analyze 默认不保存，原通知库始终只读，拒绝向已有非分析库建表。

新增 evaluation.py、prepare_evaluation.py 与 evaluate_notices.py：规则基线不调用模型，关键词只作比较，不替代 Agent 判断；缺年份/时区/时刻不补造。准备程序仅本地读取，真实运行固定 SQLite 的本轮原内容版本，模型按需读取真实记录的内存快照，基线使用模型最终可见的同一 input_snapshot。逐例原始输出/结果/输入/哈希/失败单独保存，三例连续相同错误停止；固定 UTC as_of。评分必须有逐条 approved 和非空人工 reviewer，未签审草稿拒绝评分；只统计明确标注字段，执行失败按已标注字段失败计分，不隐去失败。分类/重要性/偏好/行动、报名和活动时间点、未知路径、工具必要性与实际执行/回传分别计分，不把机械证据校验通过称为语义正确。

12 项新存储测试首轮通过，日志 data/phase23-store-tests-01-20261101.log：追加历史、内容变化、缺通知、部分输出、失败分类、模型版本未知、无效 Schema/哈希/证据/紧迫性/UTC 拒绝、事务回滚、只读/无创建、原数据库拒绝、存储损坏检出和 CLI。8 项评估测试首轮有一处夹具共享可变时间点造成预期一起被修改，已保留 01 日志；深复制预期后 02 日志通过。后续补充 Z/+00:00 等价、未知路径拼写检查及实际三次失败中止，完整测试已覆盖。

最终 `.venv/bin/python -m unittest discover -v`：99 项，3.852 秒，通过，data/phase23-final-tests-20261101.log。独立 wheel 环境 /tmp/seu-pulse-phase23-install.S4qT8h/venv：99 项，4.020 秒，通过，data/phase23-isolated-tests-20261101.log；全部加载的 15 个项目模块确来自 site-packages，pip check 无缺失。compileall 通过。wheel 保存在 data/phase23-wheels/，SHA256 cc712e4f7478a9935454b323a49525b49568a8ccd36ba59ec6be6886f98f91de，未覆盖早期构建；具体命令已更新 README。

真实结果持久化证据为 data/phase23-replayed-live-analysis-20261101.db/json：读取此前 data/phase22-notices-live-20261101-01.json 的三条获准结果，逐条重建同一输入/原内容快照，保存后读回封装完全相等，状态 success/success/insufficient_information，原通知数据库哈希未变。本次是历史真实结果的保存回放，新增 API 请求为 0，不宣称已重新调用模型或完成 15 条评估。

本地真实准备材料有两份，均保留：data/phase23-evaluation-preparation-20261101-01/ 和 02/。最终 02 版为 15 条原文/链接/版本和规则预览、四项判断空参考列表、未知路径、待核对时间与工具必要性表单；所有 reviewer=null、review_status=draft，无虚构的人工签审。15 条的正文 12/缺正文 3 来自现有数据库，本轮未重新请求原网站，也未向模型外发新增通知；来源时效与类别覆盖不能超出第一阶段既有实采证据。

截至本轮记录，新增 15 条外发授权提问仍无回复，不以等待时间当作同意。任务 2.3 持久化及比较程序可以审查、运行和提交，但真实逐条模型评估/人工参考/评分与第二阶段验收仍未完成；tasks.md 保持相应未勾选项。没有部署、删除历史、初始化仓库或新增通知源。

提交前复核：51 个候选版本文件通过实际 .env 密钥、GitHub Token/私钥模式检查，无命中；.env 仍为 600 且未跟踪，data/ 未跟踪。开发开始前 99 个旧证据文件 SHA256 均未变，第一阶段归档、报告及 Notice/Storage/PulseService 模块未改。最终 wheel 的 16 个源码模块与工作树逐字一致，文档本地链接、差异和编译检查通过。实际 CLI analysis-list/get 读取回放库成功，输出保存在 data/phase23-cli-list-20261101.json 和 data/phase23-cli-get-20261101.json（本地含原文，不上传）。本轮授权范围内实现可以提交，15 条外发及人工参考的未完成状态不改变。

版本交付：d4c50e7（feat: persist analysis history and prepare reviewed evaluations）已普通推送至 origin/main，推送后 HEAD 与远端跟踪引用均为 d4c50e73a282b1f8b1f4a9d4772de6f719cd3748，工作区干净。随后仅追加交付记录；15 条外发问题仍待用户回复，未把部分交付标记成任务 2.3 或第二阶段全部验收。

## 26. 十五条真实通知评估外发获准

用户对“是否允许将候选的 15 条通知发送至官方 DeepSeek 评估，可能含公开联系人、不发送真实个人偏好”的问题明确回复“可以”。本轮授权覆盖已列出的这 15 条标题/摘要/可用正文；不扩大为其他通知、其他来源或个人偏好。使用 data/phase23-evaluation-preparation-20261101-02/samples.json，固定 as_of=2026-11-01T00:00:00Z、preferences=null，在默认沙箱内运行现有评估程序。原数据与历史失败保留，新输出使用独立目录；人工参考仍待核对，不以模型输出或规则预览冒充人工正确率。

## 27. 十五条首轮实测、规则对比与来源核对

实际命令：`.venv/bin/python -m scripts.evaluate_notices run --bundle data/phase23-evaluation-preparation-20261101-02/samples.json --output data/phase23-evaluation-live-20261101-01`。程序退出码1，15/15均执行完毕，未触发三次相同错误中止：10条success、3条insufficient_information、2条failed（invalid_output），共38次框架模型请求，未把技术通过计为正确率。两条失败分别为爱丁堡线上说明会和UT Austin课程项目，首轮原始响应及修正均完整保留，未重跑覆盖。

正文工具15次均实际执行并反馈到同一Agent第2次请求，12次ok、3次missing_content；没有偏好工具调用，所有可用分析相关性均为null，未声称真实个人偏好遵守已充分评估。实际返回模型标识为deepseek-flash，具体版本均未知为null；所有紧迫性条目的level均为null（原文没有可靠完整偏移），不从校园地点或英国时间推断时区。

分析库 data/phase23-evaluation-live-20261101-01/analyses.db 实际保存15条尝试，其中13条有效/明确部分结果和2条失败尝试，逐条读取与case JSON封装、输入快照完全一致；两条失败analysis_id=null。原通知库前后SHA256均为589cb43563b57f5143095165d4def50a3bf7b67e41582a956eecf18ddc553ec9。每例基线输入哈希等于实际input_snapshot哈希，重新运行确定性基线也与保存值完全一致，未让基线看到Agent未取得的数据。

两条输出失败的真实原因：第10条首次缺events[0].evidence，修正后在raw只含点分时刻时输出冒号时间，违反现有H:mm契约；第12条首次地点名称缺乏连续原文依据，修正后补入原文未完整给出的区间结束年份。程序正确拒绝而非当有效分析保存。没有通过放宽模型输出校验使评估“全过”。

逐样本对比和可审查参考在 docs/phase23-evaluation-review.md。来源核对发现第11/14条把学院行政审核列为学生报名截止；第11条也将公示/录取结果作为活动，并将不同的奖学金申请与网申目标合并。第13条确已在limitations说明原文校内4月21日/4月14日不一致，但仍保留前者为确定日期，是否应改为未知需人工确认，不能说其完全漏报。第13/15条都有原文明示的项目开始日期，却因误认为区间端点需成对完整而漏提开始日期；现有Schema允许端点独立未知，不要求两端同时归一化。规则基线则易受背景中的竞赛/奖学金/讲座关键词影响，并把历史报名描述当当前行动。这些是来源核对观察，尚非人工正确率结论。

参考草稿 data/phase23-reference-codex-draft-20261101-01.json 和 data/phase23-reference-codex-draft-20261101-02.json 保留两个版本；02版给出15条类别/重要性/行动候选、完整时间判断建议、工具口径及28段经过连续子串核对的原文依据。全部review_status=draft、reviewer=null，具体参考后于模型输出形成，明确标为探索性、非预先冻结盲测。复试分段、说明会去重及缴费/奖学金目标等口径已提出具体建议供人工确认。用户的“可以”只落实已提问的外发授权，尚无人工参考签审；已另按require.md的“人工参考判断和评分口径应先明确”请求核对，未自动改成approved。

草稿文档生成曾在写出02版参考后因局部变量run未定义停止，诊断保留于data/phase23-review-generation-01.log；修正生成器后复用逐字相同的已有草稿，不覆盖原文件。15条draft均被评分入口拒绝，真实CLI评分尝试返回2且没有产生scores文件；不能以自动草稿对Agent/基线算正式正确率。独立竞赛/科研/奖学金类别覆盖仍不足，真实偏好亦未提供，保留这些验收边界。

## 28. 本轮评分兼容改动与回归

只扩展evaluation.py的人工参考表达：可显式列出accepted_deadline_points/accepted_event_points的多个方案，用于人工认可的活动分段或未知表示；不得与单值参考同时使用，不默认混同null/空数组，不改变模型运行Schema、提示、输出校验或本轮38次请求的数据。新增回归检验没有显式认可时不把null当[]、未知点不能冒充空列表、未签审拒绝、失败预测计失败及非法/矛盾参考拒绝。未用参考选项掩盖本轮语义缺陷。

开发环境100项测试通过（3.501秒），日志data/phase23-after-live-tests-20261101.log；独立wheel环境 /tmp/seu-pulse-phase23-review.KJpdXY/venv 的100项通过（2.928秒），data/phase23-review-isolated-tests-20261101.log，全部15个加载项目模块确来自site-packages，pip check通过。compileall通过。新wheel位于data/phase23-review-wheels/，SHA256=822b668bc2b0f098f3f165cea459e8be262b73bccedfeee54f0b0399dfb6fbd2，保留之前所有构建。运行/审查指引已同步README与agent.md。

本轮真实调用、持久化和来源核对已留证；正式参考、评分及第二阶段人工验收仍待回复，tasks.md保留相关未完成项。本轮不再外发通知或对失败样本自动重试，也未部署或修改通知库。

提交前核对：本轮开始前224个data/既有文件SHA256均未变；第一阶段归档、报告、Notice/Storage/PulseService保持原文。新wheel16个源码模块与工作树一致；51个版本文件通过实际密钥与凭据模式检查，无命中，未跟踪.env/data/。本地文档链接及git diff --check通过。原始首轮模型文件、参考01/02草稿和局部文档生成失败均保留，仅推送源码、测试和不含原文联系人信息的审查摘要。

版本交付：6f53047（feat: record live evaluation and support reviewed time alternatives）已普通推送至origin/main，推送后HEAD与origin/main均为6f530479cdc778e9c91748c456986d8ad2c47268，工作区干净。评估实际完成于UTC 2026-11-01 15:09:30，固定评估时刻仍为2026-11-01T00:00:00Z；会话日期已切换至北京时间2026-11-02，不重命名历史证据或改变as_of。人工参考问题尚未回复，本轮没有正式评分或阶段验收结论。

## 29. 产品逻辑纠正与参考重整（2026-11-02）

用户明确纠正：Agent不决定学生是否行动或转为待办；需全量理解事项，分别表达主体/目的与各类时间，再独立判断应用内展示资格、按显式偏好判断重要/普通，由程序计算Deadline紧急程度，待办加入与否始终归学生。本轮明确限定为产品/数据结构/评估/15条参考的梳理，暂停原action yes/no签审和评分，确认后才能冻结，不开发前端、重要页面、待办、消息或日历。

先复读AGENTS.md、require.md、agent.md、tasks.md、README、既有报告和源文，检查Git、依赖及Python环境（3.10.12、Pydantic AI 2.54.0）；工作区起点干净，未安装/修改依赖，未验证新的模型/框架能力。此前100项测试仍是旧v1历史结果，不属于本轮修正版验证。

需求修正集中于require.md；agent.md明确旧v1兼容/历史性质，并指向docs/phase23-data-structure-proposal.md的待确认建议。建议分NoticeUnderstanding（分类与所有事项事实）、NoticeJudgments（推送资格/个性化重要性）和程序TemporalAssessment，事项含类型、主体职责、目的、对象/条件/费用/要求/地点、开始/结束/多种Deadline、证据、缺失及冲突。不出现全通知action_required或待办决定字段。原文要求不等于用户必须执行；重要通知持续等待学生决定的交互规则只记边界，不实现界面或状态机代码。

时间建议不采用旧72小时规则。未过期剩余不超过24小时为非常紧急，较紧急上界不填；过期、无截止和未知截止独立于等级。精确截止等于as_of建议作为due_now但列待确认。日期/年度候选全部明确早于评估时刻时，参考可给出保守日历过期/历史关系而不伪造时区、23:59或精确倒计时；具体程序尚未实现。第13条两个冲突候选均为2025年，均已过期，但统一截止仍未知；课程历史性不证明学生实际参加，结束年份未完整给出也不补。

docs/phase23-evaluation-review.md已重新组织，撤回按“主体是学院/公示/异议/历史”直接排除的旧参考。九个评价维度分别为分类、事项完整性、信息准确性、时间/Deadline、主体/目的、推送资格、个性化重要性、紧急程度、工具/证据；不混成action accuracy，也不再仅对无标签时间点集合评分。没有真实偏好的15条个性化重要性均null/不可评，展示政策未定时推送资格亦null；合成偏好用例建议独立报告，旧relevance验证不当作新重要性验证。

逐条源文重读形成本地data/phase23-matters-reference-draft-20261102-01.json、data/phase23-matters-reference-draft-20261102-02.json、data/phase23-matters-reference-draft-20261102-03.json三个连续草稿（均保留，未冻结）；03版为15条事项提纲，146个切分候选及32条项目资料，reviewer=null。条目数不是已经冻结的完整性分母，需先确认事项匹配/等价拆分单位。第11条的学生申请、学院审核、缴费、外方网申、KTH/校级奖学金分别独立，公示/提名/录取/入学及学分/出国审核也保留；第3条复试可合并或分列，候考与现场核验独立；第10条8场本科+1场PGT共9场，点分13.00原样，独立首场13:00有独立证据且不重复计数；第13条保留所有具体日期、审核/公示、冲突及历史项目手续。地点/费用/对象/条件/要求均按源文资料呈现，不把共同费用或资格默认施加给学院执行者，不编造附件或个人资格。

旧审查稿另保存在data/phase23-product-review-before/phase23-evaluation-review.md，并可查Git历史；旧参考JSON、首轮38次模型输出、工具反馈、数据库、两条校验失败和全部历史证据未改。对旧报告中审核/公示/历史事项的限定视角，本节明确按新需求纠正，而不抹去当时记录。

本轮仅文档和新参考材料变化，业务源码、scripts、测试、构建配置/依赖、Notice v1和第一阶段报告均无差异；未调用模型、重采网页、执行旧score或最终正确率、重跑业务测试。采用只读材料核验，核对279处逐字证据引用（含复用上下文）与69条时间原文、15条draft状态、无真实偏好/推送答案、第10条9场、第11条各类型、第13条冲突与过期候选及文档表格/相对链接/锚点。开始前279个data文件逐一SHA256未变，第一阶段任务归档及第一阶段需求原文一致。初次require.md补丁因“当作”文字不匹配未应用，核对原行后修正成功，未覆盖其他文件或循环重试。

当前只提交待确认草稿，旧签审请求暂停，不把此前的模型外发授权当作新产品或参考认可。待确认包括推送资格政策、较紧急边界、截止等于as_of，以及事项结构/拆分与参考；确认前保持draft，不改可执行契约或编码，不冻结、不评分。

草稿提交前检查：52个候选版本文件通过实际.env密钥、GitHub Token/私钥模式检查，无命中；.env仍为600且未跟踪，data/未跟踪。新审查稿15个编号均存在，旧“建议行动/内容重要性”参考列已移除；Markdown表格、链接/锚点及git diff --check通过。只读核对输出保存在data/phase23-product-review-audit-20261102.log。未新增或重跑业务测试，因此不把历史100项当成本轮新验证。

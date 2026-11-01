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

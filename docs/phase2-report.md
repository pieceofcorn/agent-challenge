# SEU-Pulse 第二阶段项目报告

**尚未实施，处于开发准备阶段。** 本报告建立于 2026-11-01，仅记录本次文档准备的代码核查结论与后续报告结构；未编写第二阶段业务代码，未调用模型 API，未开展 Agent 测试或评估。开发任务和完成状态以 [tasks.md](../tasks.md) 为准。

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

# Git/GitHub 版本管理准备

2026-11-01：按用户新增授权执行本地仓库初始化和远程配置；用户随后授权自主决定 Commit、Push 及常规技术选择。本节只记录版本管理进度，第二阶段任务状态独立保留。

- [x] 检查 Git 元数据：初始化前 .git 不存在，git rev-parse 返回不是 Git 仓库；未删除或覆盖已有 Git 数据。
- [x] 初始化本地 main 并设置 origin=https://github.com/pieceofcorn/agent-challenge.git；未暂存、提交或推送。
- [x] 完善 .gitignore，检查 .env、本地配置、虚拟环境、缓存及 data/ 的忽略结果。
- [x] 检查 data/：60 个文件，共 1410195 字节，全部保留本地；历史采集/验收证据与运行数据库、导出、wheel 区分说明，不整体上传。
- [x] 文本敏感信息检查：扫描 85 个文本文件，无真实密钥命中；3 处 URL 凭据命中均在 example.test 测试中。9 个二进制文件未作为文本扫描，均在已忽略的 data/。
- [x] 远程只读连接和历史检查：沙箱内连接失败，获准沙箱外 ls-remote/fetch 成功；origin/main 为 69a7cb4c7d03882191fc3a5a9d782521add1b9c5，远端只有 README.md。
- [x] 检查本机身份和认证条件，写入 README 配置命令；检查时 user.name/user.email 未配置、gh 未安装，未发现凭据助手、GH_TOKEN/GITHUB_TOKEN 或常见凭据文件。
- [x] 用户已完成 GitHub 认证与 Git 提交身份配置；gh api 返回该仓库 permissions.push=true，user.name/user.email 均已配置。
- [x] 核对本地 .env：常规文件、权限 600，单个 DEEPSEEK_API_KEY 项非空且无占位文字，已忽略且未跟踪；未显示或记录密钥值，未调用模型 API。
- [x] 用户授权自主提交与推送；本地 main 已承接 origin/main 的 69a7cb4 初始提交，未覆盖工作文件或删除数据。
- [x] 首次提交前重跑 36 项离线测试及 compileall，全部通过；业务代码未变，未将历史测试冒充本轮结果。
- [x] 首次项目提交 e58f155 已普通推送到 origin/main，继承远端 69a7cb4；34 个文件纳入版本控制，.env 与 data/ 排除。
- [x] 按用户要求更新 AGENTS.md 的失败中止规则，差异检查通过；规则仅维护于该执行规则文件。

版本管理准备期间，任务 2.1 只进行了核查；随后按用户自主选择授权完成设计审查并实施。官方文档确认、离线测试及真实模型验证在 phase2-report.md 分开记录，原始版本管理记录保留为历史。

# 第二阶段：单 Agent 信息理解与智能决策

开发顺序为 2.1 → 2.2 → 2.3。任务 2.1 已按用户自主选择授权完成设计、实现和验收；2.2、2.3 未实施。需求以 [require.md](require.md) 为准，契约见 agent.md，实际开发记录写入 [第二阶段报告](docs/phase2-report.md)。

## 任务 2.1：通知结构化理解

状态：任务 2.1 及用户追加的 Pydantic AI 接入均已完成。Pydantic AI 2.54.0 实际承担结构化输出与受限修正，开发及独立安装环境各 61 项测试通过；三条已获外发授权的真实通知为两条 success、一条 insufficient_information，数据库未变。10～15 条真实通知评估仍属任务 2.3。

- [x] 检查代码复用与输入边界：复用 PulseService/Notice/content_hash，缺正文保留信息不足；偏好仅接受显式 interests/keywords/focus_areas，不建立画像。
- [x] 设计最小架构：服务只读、模型适配、Schema/证据校验与程序紧迫性；按用户追加要求采用 Pydantic AI 2.54.0 与严格 Pydantic 模型。DeepSeek 实际回包 deepseek-flash，模型具体版本未知；最初无框架方案保留在报告及 Git 历史中。
- [x] 确定完整 Schema，使用多个活动/报名截止数组及原文证据，未知为 null；类别、重要性、相关性、行动与时间地点分开表达。
- [x] 按用户最新自主选择授权完成设计审查并确认方案，随后更新 agent.md 具体分析契约；设计依据见 phase2-report.md 第 14 节。
- [x] 实现通知理解、严格校验、程序紧迫性和只读 analyze；无正文标为信息不足，无偏好相关性未知，校验或执行失败不伪装为有效分析。
- [x] 开发环境 52 项测试（2.351 秒）与独立 wheel 环境 52 项（2.313 秒）通过；compileall、独立 pip check、CLI 帮助、文档链接与差异检查通过。真实 API 合成验证及首轮失败均保留，未将其冒充真实通知评估。
- [x] 功能提交 92bd26f（feat: add structured notice analysis with DeepSeek）已普通推送到 origin/main；推送后本地 HEAD 与 origin/main 相同。39 个版本文件通过实际密钥与凭据模式检查，未跟踪 .env 或 data/，原有 60 个数据文件哈希及第一阶段任务历史未变。
- [x] 获得三条真实通知外发授权并完成复验，保留首轮两个输出失败；完善修正反馈、报名/公示期限区分和连续原文校验。第二轮三条各一次请求通过预期状态，54 项离线测试通过，证据见报告第 17 节。
- [x] 引入兼容 Python 3.10 的 Pydantic AI 2.54.0：ToolOutput 仅编码最终分析，ModelRetry/UsageLimits 限两次请求，SDK 重试为零；无业务工具注册。开发 61 项（2.939 秒）、独立 wheel 61 项（3.106 秒）、独立 pip check 与 CLI 帮助通过；框架真实通知证据与失败见报告第 18 节。
- [x] Pydantic AI 功能提交 6c67bcb 与执行规则提交 89651ea 已普通推送到 origin/main，推送后本地与远端跟踪引用一致；40 个版本文件通过密钥检查，原有 65 个证据文件及 Notice v1、第一阶段归档保持不变。

执行环境：用户配置的 network_access 已为 true，但当前会话仍注入联网限制。最小线程探测在沙箱内超时、获准沙箱外通过，框架离线测试因此获准在沙箱外执行，未将其当成真实 API 验证。已向用户提供 WSL 内 Codex CLI 的显式联网/自动复核启动命令；恢复会话后的沙箱内生效检查尚待进行，未擅改全局安全配置。

## 任务 2.2：最小 Tool Calling

状态：未完成，在任务 2.1 基础上推进。

- [ ] 按确认的契约实现只读 get_notice_detail，不隐式触发采集或绕过访问控制。
- [ ] 按确认的偏好配置与契约实现只读 get_user_preferences，不推测用户背景。
- [ ] 验证真正的工具调用与执行循环：判断信息是否足够、按需选择工具、实际执行、结果回传、继续分析及终止。
- [ ] 验证不需要工具、工具失败、参数校验及循环边界等场景，记录真实调用证据。

## 任务 2.3：结果持久化与评估

状态：未完成，具体存储契约和实现方案待设计确认。

- [ ] 按审查确认的 Schema 建立独立 NoticeAnalysis 数据对象，与原通知及输入内容关联。
- [ ] 实现校验后的 SQLite 分析结果持久化，记录通知 ID、结果、UTC 分析时间及实际模型信息，保留第一阶段兼容性。
- [ ] 准备 10～15 条代表性真实通知和人工参考，核对原始链接、正文可用性及类别覆盖，标明样本缺口。
- [ ] 完成简单规则基线对比与逐样本评估，覆盖分类、时间、未知值编造、重要性、工具使用和偏好遵守。
- [ ] 更新第二阶段报告的实际技术决策、修改文件、测试命令、结果、失败案例及阶段验收结论。

## 文档准备记录

2026-11-01：已对指定文档、现有模型/服务/存储/CLI、构建配置、来源配置、相关测试及既有证据做只读核查。未发现项目内已实现的模型 API、Agent 框架或 Pydantic AI；第二阶段技术方案仍待设计审查。第一阶段 28 条通知、12 条文本正文、第二轮新增 0/未变 28、36 项历史测试通过的证据一致。本次不重新采集、运行模型、执行业务测试、修改数据库或安装依赖。

文档检查通过：7 个项目 Markdown 文件的 33 个相对链接及其中 9 个锚点有效；第一阶段 tasks.md 原文、require.md 原需求、Notice v1 契约及 README 原使用说明完整保留，AGENTS.md 与第一阶段报告逐字节未变。代码、配置、测试、被核查的数据库与原始证据文件均未修改。第二阶段 3 个任务和 15 个子任务均未完成。因当前无有效 Git 工作树，使用修改前快照生成文档 diff 供复核，不改动 Git 元数据。

# 第一阶段历史归档

以下保留本次修改前 tasks.md 的完整原文、完成状态和记录顺序。早期失败与探索性误收记录均保留其原始结论；第一阶段正式验收以“获准联网后的最终结果”为准。历史段落中的“当前”“本轮”等措辞指当时记录，不代表第二阶段现状。第一阶段遗留项继续保留，不自动视为第二阶段已解决。

# 实施清单

以当前 require.md 为准；复用前轮已实现能力，网页直采与原 RSSHub 并用。仅勾选已有验证依据的项目。

- [x] 检查仓库、项目约定及环境，确定复用项与依赖。复用原模型、SQLite、服务、CLI、HTTP 客户端与 HTMLParser 等效实现；Python 3.10.12，无须新增 HTTPX/BeautifulSoup；.git 仍为空。
- [x] 检查两个重点栏目的列表页与正文样本，形成来源验证表并确定采集方式。获准沙箱外联网后，两站各核对一个原始列表及两篇可读正文；每站列表 14 条，标题、链接和日期均在原始 HTML。其他来源按当前需求暂缓。
- [x] 按 `agent.md` 实现通知模型、身份识别和 SQLite 存储。保留已有实现和表结构，无须迁移、清空数据。
- [x] 实现来源配置和直接网页采集适配器，跑通采集入库闭环。两站真实入库共 28 条，12 条取得文本正文；第二轮新增 0、未变 28。旧 RSSHub 与 html 保留，数据及接口兼容。
- [x] 补足已确认的访问限制和正文失败处理，并记录采集方案依据。原始 HTML 已核对正文容器；教务处列表限定 wp_news_w8，吴院限定 col_news_list，修复页头轮播误收。受限、微信及 PDF 条目保留列表与原因，不绕过访问限制；无需浏览器。
- [x] 实现 Python 服务层、CLI 与 JSON 导出。原接口不变，支持同轮网页与 RSSHub 混合采集；纯网页配置无需 RSSHub 地址，旧配置兼容。
- [x] 完成离线测试并记录结果。最终 36 项通过，含双模式去重、失败隔离、正文恢复及列表容器范围回归；独立虚拟环境测试、pip check 和 compileall 通过。
- [x] 执行真实来源联网验证；受阻时记录原因和复验方法。最终两轮均成功 2 来源、失败 0，query_verified、direct_content_verified、repeat_identity_verified 均为 true；此前网络失败记录仍保留。
- [x] 补齐 README，按 `require.md` 核对实现与验收缺口。已同步新架构、来源、运行和服务器验证命令；Git diff 不具备执行条件，单列待办。
- [x] 更新第一阶段项目报告。保留旧架构验证结果，补充新架构、兼容性、样本证据与遗留验收项。

## 架构调整时的历史验证记录

- 离线命令：`.venv/bin/python -m unittest discover -v`，35 项通过；最终日志见 `data/combined-offline-tests.log`。
- 独立虚拟环境重装新 wheel 后，同一测试集 35 项通过，pip check 无依赖缺失；日志见 `data/combined-isolated-tests.log`。compileall、文档链接、空白与冲突标记检查通过，wheel 与当前 9 个项目模块一致。
- 混合闭环使用真实适配器与 SQLite，仅 HTTP 响应使用 fixture：网页 3 条、RSSHub 3 条，同轮入库 6 条；重复采集新增 0；一个采集器失败时另一个继续。
- `scripts/inspect_sources.py` 实测退出码 1，两个列表均连接失败，未获取原始 HTML 或正文样本。证据见 `data/source-inspection/report.json`。
- `scripts/verify_live.py --source jwc-international --source wjx-notices --database data/direct-live-verification.db --output data/direct-live-verification.json` 实测退出码 1，两轮各失败 2 来源、成功 0，入库 0，query_verified=false，direct_content_verified=false，repeat_identity_verified=null。
- 新证据时间为 UTC 2026-10-19 18:44，对应北京时间 2026-10-20 02:44。旧四来源证据仍在 `data/live-verification.json`，未重试其他来源阻塞重点来源。
- 原始样本和复验命令集中见 README。当前正文容器配置基于已有 WebPlus 支持，不代表两个重点网站的原始结构已验证。

## 实采验收与遗留

- [x] 原始 HTML 采样通过：每站列表 14 条；教务处两篇正文 4518/1723 字符，吴院两篇正文 145/169 字符。采样保留受限或 PDF 条目的失败记录，在最多六篇中取得两篇可读正文。
- [x] 真实采集、入库、正文、按 ID 查询及重复去重通过。正式 CLI 数据库同样入库 28 条，12 条有文本正文，list/get --content-only/export 实际验证通过。
- [x] 两个重点来源均完成获准执行环境中的实采复验。外站转载及微信跳转只保留本站列表记录；纯 PDF、图片和受限正文不扩展抓取范围，保留原因。
- [ ] 在有效 Git 工作树中核对 diff；当前 .git 无元数据，不初始化或修改它。

## 获准联网后的最终结果

- 2026-10-20 北京时间 04:10 至 04:11（UTC 2026-10-19 20:10 至 20:11）：沙箱外只读联网检查获准，代理 TCP 及两站 HTTP 200 均通过，确认此前阻塞来自沙箱内网络限制。
- 原始采样证据：`data/final-source-inspection/report.json` 及同目录 HTML，脚本退出码 0。
- 最终两轮验证：`data/final-live-verification.json`、`data/final-live-verification.db`，脚本退出码 0。第一轮读取/新增 28，第二轮读取 28/新增 0/更新 0/未变 28，每轮成功 2 来源/失败 0。
- 分来源：jwc-international 14 条、文本正文 8 条；wjx-notices 14 条、文本正文 4 条。无正文条目的访问限制、微信跳转或无可提取文本原因保存在 metadata。
- 正式 CLI 实测结果：`data/final-cli-fetch.json`、`data/final-cli-list.json`、`data/final-cli-content.json`、`data/final-notices.json`。数据库为配置指定的 `data/seu-pulse.db`，未清空旧数据库。
- 36 项离线测试日志：`data/network-approved-offline-tests.log`、`data/final-isolated-tests.log`；重新构建 wheel 并完成独立环境安装和依赖检查。代码与配置按真实 HTML 修正，需求及接口契约未改变。
- 首次连通的探索性运行曾误收页头轮播，保留于 `data/network-approved-live.json`，不作为最终验收；最终证据使用独立干净数据库和修正后的栏目范围。

## 网络重新配置后复验

- 2026-10-20 北京时间 03:32（UTC 2026-10-19 19:32）：按用户要求重新执行原始 HTML 采样及两个重点来源的两轮真实采集，仍均失败。每轮成功 0、失败 2、读取与入库 0，正文及查询未通过，重复身份验证为 null；不勾选待验收项。
- 精确诊断：当前进程的 HTTP(S) 代理指向 127.0.0.1:7892；连接该本机端口和 urllib 请求均抛出 PermissionError，errno=1，Operation not permitted。当前执行环境的网络连接被拒绝，不能归因于用户服务器或网站不可访问。
- 不经代理的两站 DNS 解析均返回 gaierror(-3)，curl 经代理退出码 7，直连退出码 6，均未收到 HTTP 状态码。不绕过执行环境权限或网站访问控制。
- 原始结果：`data/network-retry-inspection.stdout.json`、`data/network-retry-live.json`、`data/network-retry-live.db`；诊断摘要：`data/network-retry-diagnostics.json`。旧的独立采集证据保留；本轮未改动采集代码，无需重跑离线功能测试。

### 再次重新配置后的复验

- 2026-10-20 北京时间 03:37（UTC 2026-10-19 19:37）：再次实际运行两个重点来源的原始 HTML 采样及两轮真实采集，仍为每轮成功 0、失败 2、入库 0；query_verified=false、direct_content_verified=false、repeat_identity_verified=null。
- 重新探测当前环境：127.0.0.1:7892 的 TCP 连接仍抛出 PermissionError(errno=1, Operation not permitted)，两个站点的 DNS 解析仍为 gaierror(-3, Temporary failure in name resolution)。故当前执行环境仍无法建立所需网络连接，不判定用户服务器配置或网站不可用。
- 证据独立保存在 `data/network-retry-2-inspection/report.json`、`data/network-retry-2-live.json`、`data/network-retry-2-live.db`、`data/network-retry-2-diagnostics.json`，未覆盖前次记录。采集代码和验收勾选状态未变。

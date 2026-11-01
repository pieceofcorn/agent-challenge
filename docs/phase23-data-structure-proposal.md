# 事项层级与分层评估数据建议（第二轮草稿）

**待最终审查，未冻结、未编码、未评分。** 本稿只定义参考层级及评估表示，不修改运行Schema或程序。产品原则见 [require.md](../require.md#产品逻辑修正2026-11-02)，逐条事项见 [15条参考](phase23-evaluation-review.md)，数量和旧条目去向见 [第二轮变更表](phase23-round2-changes.md)。旧设计与旧参考均保存在Git和本地历史副本中。

## 一、先决定信息的层级

“值得保留”不等于“是一个独立事项”。判断依据是它在通知业务链中是否有可识别的独立目的、责任、时间节点或结果；不能只因为出现一个动词、主体名、日期或名词就另计一项。

| 层级 | 判断与表示 | 独立事项计数 |
| --- | --- | --- |
| 独立事项 | 具有可区分的办理/活动/审核/发布目标、责任或独立节点/结果；主体和目的仍要有来源依据 | 计数 |
| 子步骤 | 父事项的执行、查询、提交材料或受理过程，没有另一个独立业务目标；保留步骤主体和相对时限 | 不另计 |
| 属性 | 资格、条件、费用、要求、认定权限、预期成果、条件式机会；不因提及证书或审核权限就建新事项 | 不另计 |
| 备选方案 | 同一事项中的课程模块、住宿方式等；保留各选项的目的、时间、费用与选择规则 | 不另计，父项目计一次 |
| 背景事实 | 项目成立、历史合作、引用政策等对当前业务的说明 | 不另计，保留原文与历史时间 |

独立性不是“当前是否需要学生做什么”。真实独立的学院审核、学校公示、外方结果发布、学生缴费和奖学金申请均保留；历史业务事项也不因已过期降为背景。相反，历史成立/合作和泛泛的“此前经过考核”属于来由说明，不能随意扩为更多安排。

共同活动的参加者/组织者不必各造一场活动。出国申报与学院、国际合作处两方审核有不同责任，本轮分别保留三个事项；原文没有说明先后次序和各自截止，不补程序阶段。课程学习计划和学分认定表述在第9/11/12/13/14/15条只是申请要求及学院认定权限说明，未单列办理入口或时间，先归申请属性。若之后原文确有独立学分申请/审批安排，再据证据设独立事项。

证书、成绩单、报告和可能获得推荐信通常是项目成果属性。第15条另有明确的“考核结束后4周内发布”结果发布事项，应独立保留；不能为减少数量把它并入笼统的证书预期。

## 二、通知层和事项层分开分类

以下均为人工参考建议，不是可执行类型定义：

```text
NoticeReferenceDraft
  proposal_version: "matter-reference.round2.draft.1"
  notice_id, notice_content_hash, as_of
  notice_category:
    primary: NoticeCategory|null
    secondary: NoticeCategory[]
    topic_tags: string[]
    reason, evidence[]
  display_eligibility: Judgment<push|do_not_push>
  personalized_importance: Judgment<important|ordinary>
  matters: MatterReference[]
  notice_context_facts: ContextFact[]
  background_facts: BackgroundFact[]
  source_availability: {body, attachments}
  conflicts[]
```

- `notice_category.primary`描述整条通知主要用途，至多一个；无法确定时保留未知，不把“academic_affairs/exchange”当成一个新类别。
- `secondary`是其他确有证据支持的通知主题类别，不取代主分类，不影响独立事项数量；`topic_tags`保存更细主题。建议沿用competition/lecture/research/activity/academic_affairs/exchange/scholarship/other的通知类别词表，不把application、review、payment放进该词表。
- 例：第11条主exchange、辅scholarship，具体事项中仍有申请、审核、缴费等类型；第15条主exchange、辅research。第2条暂以academic_affairs为主、exchange为辅，并标标题证据有限。第8条“专项资助结果”是主题标签，不强行等同奖学金类别。这些均待人工确认。

```text
MatterReference
  matter_id                  # 独立事项ID，不是个人待办ID
  name
  matter_type                # 如activity/application/review/publication/payment/
                             # scholarship_application/result_release/enrollment/policy
  matter_subject[]           # 责任主体/参与角色、职责、未知说明、证据
  matter_purpose             # 业务目的和适用目标，不是“当前用户必须做”
  time_nodes[]               # 事项本身的开始/结束/截止/发布/相对约束
  substeps[]                 # 步骤自带主体、目的、证据、相对时限，且指向父事项
  attributes:
    audience[], conditions[], requirements[], fees[], locations[]
    expected_outcomes[], conditional_opportunities[]
  option_groups[]            # group与option各有ID、选择关系、时间/费用等
  conflict_refs[]
  evidence[]

TimeNode
  node_id, owner_ref          # matter/substep/option的明确归属
  time_type                  # start/end/deadline/occurrence/relative_constraint等
  purpose, responsible_subject_refs[]
  raw_text, raw_evidence[]
  date?, time?, utc_offset?, precision
  source_status              # known/partial/not_stated/unavailable/conflicting
  alternatives[], conflict_ref?
```

同日的外方网申和奖学金申请是不同事项与不同节点，不能用排序后的日期集合合并。子步骤有时间限制也须保留，例如外方收齐资料后1—2工作日回执；它不因此必然成为另一个独立事项。选项中的时间仍归该选项，例如OPP模块的不同上课区间，不直接变成五个已参加的活动。

费用未提不等于免费；主体未明确不推定执行机构。原文“约合人民币”只是原文估算。住宿是备选费用，不能加总成学生必付；共同项目条件不自动施加给学院等审核者。预期成果和“有机会”保留条件性，不表示学生已取得。

## 三、时间、优先级及信息可用性各自归层

| 输出 | 所属层级 | 责任与限制 |
| --- | --- | --- |
| 推送资格 | 通知层 | Agent依据明确政策判断是否进入应用内所有通知流；政策未定，本15条不可评 |
| 个性化重要性 | 通知层 | Agent依据显式用户偏好判断重要/普通；本组没有真实偏好，不设参考答案 |
| 时间节点、Deadline状态和紧急程度 | 事项层；节点保留其事项/选项/步骤归属 | 程序按时间证据与as_of计算，不由LLM编造 |
| 多事项通知的整体紧急程度 | 通知层聚合政策 | 待确认，不默认取最大/最小/最近截止 |
| 哪些主体Deadline触发软件消息 | 独立提醒政策 | 待确认，不默认所有学院/学校/外方Deadline都提醒学生；不发送消息 |
| 是否加入待办 | 学生个人决定 | 后续交互，Agent不决定；本轮不实现 |

建议未来的程序结果只描述各节点/事项：`deadline_state`、`remaining_seconds`或可靠范围、`urgency`、依据及`as_of`。过期、无截止、截止未知和冲突分开，不能全部标为不紧急。后台运算与前端页面/消息接口不是同一能力。

已确定：**非常紧急为未过期且剩余时间不超过24小时，24小时端点包含。** 较紧急上界待定，不能沿用72小时；超过24小时但未定政策时保留pending_policy。精确截止等于as_of的处理仍待确认，不擅自定为过期或到期中。

原文时间必须保留。完整开始日期独立提取；另一端缺少年份/时刻/偏移仍未知，不从标题、落款或URL补全。`13.00`原样保留，不改成`13:00`；第10条独立文字中的`13:00`有自己的证据，只用于同一首场记录，不把首场重复计为第10场。

固定评估时刻仍是2026-11-01T00:00:00Z。第13条校内2025-04-21/2025-04-14两候选均早于评估时刻，日期冲突保留、统一值未知，但过期关系可给保守日历参考；2025-04-15审核、04-18公示、05-05网申也保留并标过期。2025秋季项目作为历史项目保留，不能因为结束端年份未重述而删除开始日期，也不能假称学生实际参加或完成。

只有所有可行候选/时区偏移/日内时间都在as_of前，才能给保守日历过期关系；不据此填时区、23:59或精确负秒数。相对手续或未给绝对截止的项目要求保留历史关联，不伪造已超期。此处是参考建议，程序尚未实现新计算规则。

`source_availability.body`与`source_availability.attachments`分别表示内容可用性：第4条正文169字、第5条145字均可读，附件内容均未读取/未验证。补充属性列表为空不等于正文不可用，未读取附件也不等于已验证附件不可访问。新参考中的原文和旧模型记录分别留存，不互相覆盖。

## 四、保留和版本边界

旧146条候选的每个编号都保留到第二轮去向映射：独立事项、子步骤、属性、选项或背景。原条目的证据、时间、主体、目的及其他字段存于新本地提纲的source_outline_records，便于检查信息没有因层级调整丢失。旧01/02/03参考文件、原始模型输出、数据库和失败记录不变。

旧action_required、内容重要性和urgency.v1不能转换成新决定；旧score命令不适用于本稿。没有真实偏好或推送规则时分别标不可评，空值不是普通或不推送。15条继续是探索性样本，不称完整Benchmark；当前不冻结参考，不计算任何最终指标。

待最终确认：94个独立事项及非独立层级划分、主辅通知分类、等价匹配与指标分母；以及通知紧急程度聚合、提醒主体、展示资格政策、较紧急上界和截止恰等于as_of的规则。后几项可以继续待定，不能为了完成本轮填入默认值。

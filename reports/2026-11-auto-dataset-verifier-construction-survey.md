# LLM Agent 系统"测试数据集/验证器自动构造"调研报告

目标：摆脱人工构造数据集，用系统自身产生的轨迹（trajectories）与问题自动生成可回归的验证资产。按五个方向分节，每节写机制、依赖、优缺点与链接。

---

## 1. Property-based / Metamorphic Testing 与 LLM 结合（自动导出不变量作断言）

**机制**
- 经典 metamorphic testing 不需要 oracle：给定输入变换 `T`（改写、改选项顺序、加干扰句、否定），正确系统应满足关系 `f(x) ≈ f(T(x))`。对 LLM 系统而言，"不变量"就是断言：paraphrase 后答案语义不变、选项重排后选择分布不变、加入无关上下文结论不变。开源项目 [parag-labs/metamorph](https://github.com/parag-labs/metamorph) 即此模式：自动生成四类变换（paraphrase / option reorder / distraction / negation），断言不变量，并对违规样本做 shrink（最小化失败 prompt），类似 Hypothesis 的 shrinking。
- 自动导出不变量两条路线：(a) **LLM 读代码/文档/历史轨迹归纳 likely invariants**，作为断言放进 property 测试（arXiv 上 LLM-based invariant inference 一系工作，如 [LLM-based Invariant Inference](https://browse-export.arxiv.org/pdf/2603.26270)、[用 LLM 生成反例改进动态规格推断](https://export.arxiv.org/pdf/2604.10761)）；(b) **LLM 生成 metamorphic relations**：由 LLM 从任务描述提出"输入应满足 X 关系"，再程序化执行。
- 语义层不变量检验通常需要一个"语义等价 judge"（第二个 LLM 或 embedding 相似度），所以本方向常与 LLM-as-judge 组合。
- NLP 侧的祖先是 [CheckList (Ribeiro et al., ACL 2020)](http://xxx.itp.ac.cn/abs/2005.04118v1)：从任务 spec 自动展开成 capability × test-type 矩阵（invariance、directional、MINIMUM_FUNCTIONALITY），本质就是大规模自动生成的 metamorphic 断言，这套模板可直接搬到 agent 输出上。
- 更近的 [LGTM/Logic-Grounded Metamorphic Testing](https://browse-export.arxiv.org/pdf/2605.23965) 用逻辑化 metamorphic 关系评估 LLM 推理可靠性：不是随机扰动，而是从推理结构导出必然成立的变换。

**依赖**：一个变换生成器（LLM 或模板）、不变量库（可 LLM 归纳但需人抽检）、语义等价判定器、failure minimizer。

**优点**：断言不依赖标注答案，天然免人工；不变量一旦确定是确定性的、可回归、零 token 成本；shrink 后的失败样本可直接沉淀为回归 case。

**缺点**：LLM 归纳的不变量有假阳性（把本可容忍的行为当违规），需人审一遍建立"不变量白名单"；只覆盖不变性类缺陷，无法验证"答得对"；语义等价判定本身引入 judge 噪声。

---

## 2. LLM-as-judge 的工程化回归实践（rubric 生成、自一致性、多 judge）

**机制**
- **Rubric 自动生成**：从任务描述+历史轨迹让 LLM 产出 checklist 式评分标准。代表工作 [CheckEval](https://aclanthology.org/2025.emnlp-main.796/)：把评分维度拆成 yes/no 子项 checklist，显著提升 judge 与人的一致性——比 1–5 打分稳定得多，是回归场景首选格式。工程上（[promptfoo 的 LLM-as-judge 指南](https://www.promptfoo.dev/docs/guides/llm-as-a-judge/)）rubric 以 YAML 断言（`llm-rubric`、`assert`）固化进配置，随 PR 回归。
- **G-Eval 模式**（[G-Eval](https://www.comet.com/site/blog/g-eval-for-llm-evaluation/)）：用 LLM 以 CoT + form-filling 生成评估步骤再打分；[DeepEval 内置 G-Eval](https://deepeval.com/docs/synthetic-data-generation-introduction) 可直接对自定义 rubric 建 metric。
- **可靠性手段**（工程上已收敛为组合拳）：
  - 多 judge 投票/ ensemble：不同模型家族做 judge，取多数或取最低分（保守），[cost-effective LLM-judge 改进技术](https://ar5iv.labs.arxiv.org/html/2604.13717)系统比较了各种手段的性价比；
  - 交换位置/对称化：对 pairwise judge 跑 A-B 与 B-A 两次，消除 position bias（[Judging the Judges: position bias 系统研究](https://aclanthology.org/2025.ijcnlp-long.18/)）；
  - 自一致性：同一 judge 采样 k 次（不同温度）取多数；
  - 首先用小规模人工标注集**校准 judge**（算与人类的相关性/Kappa），校准不过关的 rubric 不进回归门禁；
  - 用 CheckEval 式分解把模糊维度变成可判定的原子断言。
- **回归集成**：promptfoo / DeepEval 都有 CI 模式，断言失败即红（参考 [Agent evals in CI/CD: Promptfoo + DeepEval + Langfuse + GitHub Actions](https://numoru.com/en/contributions/evals-agentes-ci-cd-promptfoo)）。关键工程规则：judge verdict 有随机性，回归要保留"基线 vs 当前"的**对照比较模式**（同 case 同 judge 跑新旧两版），而不是绝对阈值，以吸收 judge 噪声。

**依赖**：强模型作 judge、人工标注的小校准集（一次性）、rubric 版本管理。

**优点**：覆盖无法程序断言的"质量"维度；rubric 可从轨迹自动生成，人工只审不改写。

**缺点**：judge 有偏好（position/verbosity/self-preference bias）、非确定性导致回归 flaky；每次回归消耗 token；judge 与被测系统同源时会漏报同源错误（要用不同模型族做 judge）。

---

## 3. 从生产流量/轨迹挖掘典型场景再泛化出测试集

**机制**
- **OpenAI 官方闭环**（[Agent Improvement Loop cookbook](https://developers.openai.com/cookbook/examples/agents_sdk/agent_improvement_loop)，[笔记版](https://github.com/tonydzi/awesome-evals/blob/main/notes/articles/openai-cookbook-agent-improvement-loop.md)）：trace 存储给每条轨迹打 `trace_label`（good/bad）→ LLM 从 bad 聚类中归纳 failure taxonomy（每类含典型 query）→ 为每类自动生成 eval case + grader prompt → 跑 evals API → 修 prompt/代码 → 重跑。这就是"轨迹→场景→回归资产"的完整参考实现。
- **LangSmith**：trace 可按 filter 动态转成 dataset（[manage datasets in application](https://langchain-5e9cc07a.mintlify.cn/langsmith/manage-datasets-in-application) 的 "add to dataset" / 动态 dataset 即一条持久化查询），annotation queue 支持人工批量标注后入集；所谓 "shot routing"/clustering 场景化做法是：对 trace 做 embedding → 聚类成 scenario taxonomy → 每簇采样代表轨迹做 few-shot 或回归 case（LangSmith Engine / [smithtune datasets 文档](https://github.com/langchain-ai/smithtune/blob/dd6b3b9a1ce1edbdab107f9170cae7cd7751922e/docs/datasets.md) 亦围绕 trace→dataset 组织）。
- **DeepEval Synthesizer**（[合成数据生成](https://deepeval.com/docs/synthetic-data-generation-introduction)、[指南](https://deepeval.com/guides/guides-using-synthesizer)）：从**文档/上下文源**（也可从日志文本）自动生成 single/multi-turn goldens，包括 query 与 gold answer，用进化式生成+去重+质量过滤；rubric/assert 可同步生成。
- **promptfoo**：断言与 metric 从配置自动展开（[assertions](https://www.promptfoo.dev/docs/configuration/expected-outputs/)），支持 `llm-rubric` 自动判定；从日志生成 case 需要自己写导入脚本（node/python API 或把 eval 历史导出为测试集），没有内置 trace 聚类。
- 共同管道：**轨迹采集 → 打标（人工少量 + judge 自动大量）→ 聚类成场景 taxonomy → 每场景选代表样本 + LLM 泛化出变体 → 固化为 eval dataset + rubric → CI 回归**。

**依赖**：完整 trace 存储（含工具调用、中间结果）、embedding/聚类、少量人工标注用于冷启动打标与 taxonomy 校准。

**优点**：测试分布=真实流量分布，覆盖人工想不到的边缘场景；bad case 聚类天然给出回归重点；变体泛化把 1 个真实 case 扩成 N 个。

**缺点**：冷启动无流量时不可用；聚类质量决定 taxonomy 质量；隐私/PII 需脱敏；代表性样本会过时，需要滚动更新机制（定期重挖）。

---

## 4. SE 自进化闭环案例（经验库 + 检索复用 + 修 patch 自动回归）

**机制**
- **MetaGPT 经验库**（[Experience Retrieval and Learning](https://deepwiki.com/FoundationAgents/MetaGPT/4.6-experience-retrieval-and-learning)）：成功任务的轨迹被压缩为结构化 "experience"（任务特征→策略/教训），新任务先 embedding 检索相似经验注入 prompt。配套论文 [Experiential Co-Learning (ACL 2024)](https://aclanthology.org/2024.acl-long.305/)：ChatDev/MetaGPT 式多 agent 软件公司从历史完成项目中提取 shortcut insights 与教训，按 task domain 分桶存储、检索复用，同一任务组队成功率与代码质量提升。
- **ExpeL**（[AAAI 2024](https://ojs.aaai.org/index.php/AAAI/article/download/29936/31635)）：跨任务收集成功+失败轨迹 → LLM 对比归纳自然语言 **insights**（显式规则）+ 从成功轨迹维护 few-shot exemplar 池（检索 top-k 注入）。是"经验库+检索复用"最常被引用的模板。
- **Agent Hospital / MedAgent-Zero**（[arXiv 2405.02957](https://export.arxiv.org/abs/2405.02957v2)）：医生 agent 在模拟医院看病，无需人工标注——病人由 LLM 生成、诊断对错由**模拟 Ground-Truth（生成病例自带答案）+ 治疗结果反馈**判定；成功/失败经验转化为可检索的 practice/knowledge，随病例量自进化。
- **经验资产化+消融验证**：阿里 [AgentLoop 的经验库实践](https://www.alibabacloud.com/help/en/agentloop/use-cases/v-experience-base-automatic-mining-of-experience-assets-ablation-experiments-to-verify-real-returns)把经验挖掘做成流水线：自动挖掘经验资产 → **用消融实验（带/不带该经验跑回归）验证真实收益**，收益为正才入库。这是防止"经验污染"的关键机制。
- **修 patch 后自动跑回归**：SE agent（SWE-agent 类）的通用闭环是：issue → patch → 自动运行仓库测试套件/生成的回归测试 → 失败轨迹入经验库。近期工作如 [Trajectory-Aware Benchmark Subset Selection for SWE Agent Regression Testing](https://export.arxiv.org/pdf/2609.24928) 用历史轨迹挑选最小回归子集（每次 patch 后不必全量跑），以及 [Harness-R1](https://export.arxiv.org/pdf/2608.02276) 从失败轨迹学习改运行时 harness。社区还有 [evolveguard](https://pypi.org/project/evolveguard-cli/0.1.4/) 这类"进化守护"工具思路：约束自进化不回退。

**依赖**：轨迹存储与压缩器、经验 schema（结构化教训 vs 裸轨迹）、检索器、判定成败的 oracle（环境反馈/测试套件/生成器自带 ground truth）、消融回归算力。

**优点**：成败 oracle 用环境信号（测试通过、任务完成）而非人工标注；经验以自然语言/示例复用，成本低；消融验证形成"经验也过回归门禁"的闭环。

**缺点**：经验库会累积错误/过时教训（必须配消融+淘汰）；检索注入可能造成 prompt 漂移导致旧 case 回退；需要能自动判定成败的环境，开放域任务难以取得。

---

## 5. 轨迹反向提炼 spec（trajectory → spec → test）

**机制**
- 经典根基是**specification mining**（如 [Javert](https://people.inf.ethz.ch/suz/theses/MG-dissertation.pdf)、QUARTZ 等）：从执行 trace 归纳程序应满足的规约（FSM、时序约束、前后置条件）。LLM 时代的升级是把 trace 喂给 LLM 归纳**自然语言/可执行混合 spec**：
  - [Project Prometheus](https://ar5iv.labs.arxiv.org/html/2604.17464)：对 agent 修复任务**逆向工程出可执行规格（executable specification）**再驱动修复——即从轨迹/代码行为反推 spec，把 spec 变成测试 oracle；
  - [SpecFirst](https://ar5iv.labs.arxiv.org/html/2607.27167)：把"行为规约获取"作为 agent 程序合成的一等步骤，先从交互轨迹诱导行为 spec，再生成测试约束实现，防止 agent 走捷径刷指标；
  - [TrajSpec (Bug Report Specification Refinement with Trajectory Guidance)](https://arxiv-org.ezproxy.obspm.fr/html/2607.07882v1)：先无验证地跑一轮收集轨迹，从轨迹中提炼原始报告缺失的 spec，再用于自动修复——trajectory 直接作为 spec 细化的证据源。
- **通用管道**：`轨迹(成功/失败) → LLM 归纳场景级 spec（输入前置条件 + 期望行为 + 禁止行为）→ spec 编译成可执行断言（代码断言 / llm-rubric / metamorphic 不变量）→ 作为回归测试`。第 1 节的 likely invariants、第 2 节的 rubric 生成、第 3 节的 failure taxonomy 本质都是这个管道的局部实例。
- 也有跨任务策略归纳一系（trace→policy 规则，如 [trace-driven ALNS policy induction](https://dl.acm.org/doi/pdf/10.1145/3795095.3805061?download=true&__cf_chl_tk=x-1769228893-1.0.1.1-utbEhtJno_Vl.nPrq9cUG8yauM-1785168951-1.0.1.1-tCrnZ.QYGbGzMVNZMKVohsib2uqvpepSAprX5bFtzQk)），把轨迹归纳出的启发式规则作为可执行检查。

**依赖**：高质量轨迹（含上下文与结果）、归纳用强模型、spec→断言的编译器（人工审核 spec 是否正确这一步最难省）。

**优点**：spec 从"实际发生过什么"出发，比人工凭空写更贴现实；成功轨迹给出正例 spec、失败轨迹给出负例（禁止行为）spec，天然构成正负测试对。

**缺点**：归纳出的 spec 是"过去行为的描述"，可能把 bug 固化成规范（survivorship bias），需要区分"已验证正确"与"仅观察到"的轨迹；spec 表达能力有限，深层语义仍需人审；归纳→断言编译环节错误会静默削弱测试。

---

## 综合建议（组合成可回归的验证资产体系）

1. **确定性层**：不变量/metamorphic 断言（方向 1）做回归门禁主力——零噪声、可最小化。
2. **判断层**：CheckEval 式 checklist rubric + 多 judge（异构模型族）+ 基线对照模式（方向 2）处理语义质量。
3. **数据层**：OpenAI agent improvement loop 式的 trace 打标→聚类→泛化管道（方向 3）持续产出 case，人工只审 taxonomy 与新增不变量。
4. **进化层**：经验库 + 消融验证入库（方向 4），每个 patch 自动跑"不变量层+核心数据集"回归，失败轨迹回流到数据层。
5. **spec 层**：对反复出现的场景做 trajectory→spec 提炼（方向 5），把临时 rubric 升级为持久 spec，注意防 survivorship bias。

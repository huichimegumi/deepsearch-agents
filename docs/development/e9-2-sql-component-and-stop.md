# E9-2：SQL 意图组件与停止结果

新增共享 SQLIntent：记录指标/聚合、实体、期间、行粒度和关系，使用扁平字段供 Qwen 生成 SQL；命名值由后端绑定。SQLite EXPLAIN 与只读执行检查实际表/字段、拒绝写入；编译成功不等于业务语义正确。公开 schema 描述补充字段类型、主键位置、可空性、外键和唯一键。修复字符串/注释里的冒号被当作参数、重复输出列覆盖数据的问题。

## 一次冻结的 SQL 辅助输入控制

六道已暴露 Hybrid 题。生成端仅获得原问题、实际公开 schema/定义，以及参考 SQL 的单引号字符串常量列表；没有参考 SQL、目标行或评分反馈。这里提供的常量包括业务值和格式常量，属于 reference-literal assisted 上界诊断，不是实际 Web 上游执行，也不是端到端 benchmark。控制输入留在私有 evals/results，未写回 public.json，禁止复用于正式生成。

每题最多两请求、50k 预留 token；仅按实际 SQL 错误/空结果做有限检查，不用参考匹配结果决定重试。独立比较在生成结束后进行。九次实际请求模型全部 qwen-flash；没有 DeepSeek 或 GPU。

结果为 **0/6 匹配**，门槛为 4/6：

- 三题执行得到实际结果，但均未匹配；其中两题最终为空结果。
- 一题两次 SQL 工具执行错误。
- 一题模型工具参数 JSON 无效；一题 API 超时。这两题没有可评 SQL 输出，不能宣称六题全是 SQL 推理错误。
- 评分侧独立执行参考 SQL 可重现已发布参考行 6/6；这是数据/裁判 sanity control，不能算生成器通过。

摘要为 evals/reports/e9-2-assisted-sql.json；完整 SQL、输入、候选、原始/非法工具消息和账本保存在忽略目录。

这次控制也发现源描述没有显式标出 SQLite 方言。最终代码已经补充 sql_dialect=sqlite，并在 SQLIntent 指令明确 SQLite；单元测试已覆盖。这个补充发生在冻结控制之后，控制快照仍是 e9-sql-component-1；CLI 版本升为 2，禁止覆盖或恢复原目录。没有据此再次调用模型，也不宣称补充方言后成绩已改善。

## 门槛与后续范围

实际组件门槛见 evals/reports/e9-2-component-gate.json：报告协议 5/8（需 8/8），SQL 辅助控制 0/6（需 4/6）。两层均未通过。E9-3 的整组端到端研究和 E9-4 新验证均 **NOT RUN**，不继续整组修改 Prompt、提高预算或换题。该门槛按逐题结果重算，不能用顶层声称的通过数放行。

因此，当前证据能确认 Agent 接口和语义组织存在问题，也实际观察到 Qwen 的输出协议/判断限制；尚无同输入公平模型对照，不能把原因归为全是 Agent 或全是 LLM。用户指定的 Qwen 优先策略继续有效，本轮 DeepSeek 零调用。

本阶段全量离线测试 775 passed、6 skipped；相关 SQL/执行器测试 15 项通过，统一 CPU 入口 64 项通过，另新增门槛防伪/样本集校验回归单独通过。最终 CI 将包含全部门槛测试。默认产品路径未切换，新的组件没有冒充已达标的默认研究流程。

## 可复现入口

- 旧记录归因：`python -m scripts.evaluate e9-diagnose`
- 固定证据报告控制：`python -m evals.diagnostics.replay_report_e9 --live --output NEW_DIR`（仅 Qwen；组件诊断）
- 辅助 SQL 控制：`python -m evals.diagnostics.sql_component_e9 --output NEW_DIR`（仅 Qwen；明确含 evaluator-derived hints）
- 检查门槛：`python -m evals.diagnostics.gate_e9 --writer WRITER_DIR --sql SQL_DIR --output GATE.json`
- 无模型/GPU检查：`python -m scripts.evaluate check`

这些命令说明复现方式，不授权自动重跑已完成控制。原有 E7/E8 成绩和所有 E9 原型均保留，不从不同版本抽选最好案例拼成成绩。

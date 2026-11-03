# E8-2：观察实际结果后选择下一步

新增显式 adaptive 路径，保留 bounded/simple。每步实际执行后，把结果、错误与剩余额度交回模型；最多五次工具动作，重复动作拒绝，最终 Writer 预留不被研究吃光，模型总请求上限仍 8/180k token。API 可用 RESEARCH_WORKFLOW=adaptive 显式启用，兼容默认仍 legacy。

typed Action 支持只读 SQL query、sample_table、match_column_value、search_semantics、实际 Evidence ID 读取以及 Web 查询。SQLite 数据值使用命名参数，由数据库授权器/只读 URI/进度截止保护；包含引号或 update 的实体作为数据传递，不再要求实体字面值出现在 SQL 字符串里。支持多参数 IN，SQL 标量路径后端读取，Web 值必须在实际取证中出现；依赖由绑定记录的真实步骤推导。空查询结果返回带查询定位的空表证据，不能混同执行失败。

压缩 schema 并使用数据库目录中同名公开 column-meaning 侧车元数据，给出字段含义；同一公开资产集内的数据适配改善是本轮改动的一部分，不把效果单独归因于模型/调度。语义定义来自公开 KB，不是任务 gold。SQL 参数随 Evidence/实际操作保留，视图共享查询时也包含参数，避免相同模板的不同实体被混淆。

15 项相关离线测试通过，覆盖真实 Web→SQL 值绑定、引号实体、空结果、写操作拒绝、未取证 ID 拒绝和已有流程。两个真实公开开发 smoke 均有终态：一 completed、一 delivery_invalid；观察到按实际结果继续取证，尚不能认为完整任务已通过。原始 trace 和被拒报告留存，摘要见 evals/reports/e8-2-smoke.json。最终 8 题门槛留 E8-3 的合约/评分完成后测量，不启动新验证。

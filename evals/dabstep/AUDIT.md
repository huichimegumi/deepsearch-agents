# DABStep-Research 数据审计

数据版本：`62ae9e0de555a8fb1fd5ab334e0546dbf27aa10c`。审计脚本首先验证 8 个源文件的字节数和 SHA-256，当前全部通过。

## 结论

- 任务共 100 个，五类各 20 个；Open 类的 20 个任务全部缺少 checklist，不进入第一阶段子集。
- 第一阶段固定 8 个任务：dev 2 个、holdout 6 个，覆盖 Data Preparation、Data Analysis、Data Insight、Report Generation。
- `payments.csv` 有 138,236 行、21 列，`psp_reference` 全部唯一，无重复整行，日期范围为 2023-01-01 至 2023-12-31。
- 交易表只有 5 个活跃商户；商户元数据有 30 行，其中 25 行未出现在交易中。活跃交易均能关联商户元数据，活跃商户 MCC 均在参考表中。
- `fees.json` 有 1000 条唯一规则。手册只明确说明 `null` 是通配符，但规则中还存在空列表；手续费精确总额必须等独立规则引擎核验后才作为硬指标。
- 费率规则引用了 7 个 MCC 参考表中不存在的代码（3003, 5412, 5736, 5911, 7231, 8000, 8742）；当前 5 个活跃商户不受此问题影响，但规则库并非完全自洽。
- `acquirer_countries.csv` 是“收单机构名称 → 国家”的映射，而交易表只有国家代码；无法从当前快照还原每笔交易实际使用了哪个收单机构。
- 上游仓库未声明许可证。锁文件只用于可复现下载，原始数据保持 Git 忽略，在许可证澄清前不随项目再分发。

## 固定任务子集

| Source ID | Split | 类型 | 可回答性 |
| ---: | --- | --- | --- |
| 2 | dev | Data Preparation | directly_grounded |
| 84 | dev | Report Generation | partially_conditional |
| 0 | holdout | Data Preparation | directly_grounded |
| 3 | holdout | Data Preparation | partially_conditional |
| 20 | holdout | Data Analysis | partially_conditional |
| 41 | holdout | Data Insight | partially_conditional |
| 47 | holdout | Data Insight | partially_conditional |
| 85 | holdout | Report Generation | partially_conditional |

## 数据质量快照

| 检查 | 结果 |
| --- | ---: |
| 交易行数 | 138,236 |
| 唯一交易 ID | 138,236 |
| 重复整行 | 0 |
| 缺失 IP 哈希 | 27,647 |
| 缺失邮箱哈希 | 13,824 |
| 非法 ACI | 0 |
| 交易商户无法关联元数据 | 0 |
| 活跃商户 MCC 不在参考表 | 0 |
| 收单国家不在机构映射中的交易 | 0 |

观察到的交易收单国家：FR, GB, IT, NL, US。
机构映射覆盖的国家：FR, GB, IT, NL, US。

## 可回答性边界

- No realized fee column or authoritative worked example exists in this snapshot.
- The manual documents null as wildcard, while fees.json also uses empty lists as apparent wildcards.
- Transactions contain acquirer country codes but not acquirer names, so merchant-to-acquirer usage cannot be reconstructed.
- No processing latency or system-performance telemetry exists.
- Refusal is available as an authorization proxy; a full conversion funnel is not.
- Counterfactual savings and fraud-prevention ROI require assumptions not present in the data.

## 子集使用规则

- 只用 dev 任务调 prompt、工具和工作流；holdout 只用于里程碑验收。
- 原始问题、checklist、文件列表和 source ID 原样保留；新增字段只描述 split、可回答性和已知限制。
- SQL 参考结果只覆盖可确定事实。涉及手续费匹配、因果判断和反事实节省额时，报告必须标注假设及证据边界。
- Agent 运行时只能读取源数据和任务；`reference_results.json` 只供离线 evaluator 使用。

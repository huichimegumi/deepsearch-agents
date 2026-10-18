# RAG suite v2 review worksheet

All checkboxes are initially unchecked. Source anchors were verified against the indexed text by the agent; human approval is pending. Changes after test exposure require a new suite version, not silent editing of v2.

Confirm each required keypoint, the acceptability of alternative passages, and no-answer scope. Page hints are parser-derived PDF positions, not visually verified page numbers.

Corpus originals remain local and are not redistributed. Retrieve the referenced document locally by its SHA-256; short excerpts below identify the evidence.

## rag_local_zh_001 (dev, single_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

《2026数字人电商直播白皮书》主要讨论了哪些数字人直播应用场景？

- [ ] scenarios: 数字人直播的具体应用场景或场景分类
  - 61803158d2af; indexed pages [9]; 品牌自播间：7×24小时品牌店播
  - 61803158d2af; indexed pages [20]; 真人主播数字分身降本增效、AI总裁背书建立信任

## rag_local_zh_002 (dev, single_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

《2026数字人电商直播白皮书》中提到数字人直播相比真人直播有哪些优势？

- [ ] benefits: 标准化和全天候运营带来的成本、效率优势
  - 61803158d2af; indexed pages [9]; 高边际成本低边际成本
  - 61803158d2af; indexed pages [5]; 有效解决主播培养成本高、直播间搭建复杂、多场景适配难等痛点

## rag_local_zh_003 (dev, single_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

在《2026数字人电商直播白皮书》中，数字人电商直播的产业链或生态参与方有哪些？

- [ ] participants: 服务商、品牌商家、MCN和消费者构成生态
  - 61803158d2af; indexed pages [9]; 服务方：SaaS技术服务商、IP定制商、代运营机构

## rag_local_zh_004 (dev, single_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

《2026数字人电商直播白皮书》对数字人直播未来趋势有哪些判断？

- [ ] agent_future: 由标准工具向自主经营智能体与个性化服务演进
  - 61803158d2af; indexed pages [49]; 从标准化工具升级为全链路经营主体
  - 61803158d2af; indexed pages [51]; 从被动执行指令升级为主动理解生意、自主制定经营策略

## rag_local_zh_005 (dev, single_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

《全球电商行业AI应用研究报告2025》总结了哪些 AI 在电商行业的应用场景？

- [ ] applications: AI用于推荐、客服、营销、库存或物流等电商环节
  - 28aab03c3f2d; indexed pages [43]; 包括仓库机器人、智能客服、智能上架和营销工具
  - 28aab03c3f2d; indexed pages [30]; 人工智能解决方案还可以准确分析需求模式、检测波动
  - 28aab03c3f2d; indexed pages [42]; 他们的人工智能客户服务聊天机器人处理了高达95%的书面和口头客户咨询

## rag_local_zh_006 (dev, single_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

《全球电商行业AI应用研究报告2025》中，AI 如何影响电商营销和用户运营？

- [ ] marketing: 用户洞察支持个性化沟通、再营销与转化
  - 28aab03c3f2d; indexed pages [28]; 人工智能可以分析数据并提供有价值的用户洞察
  - 28aab03c3f2d; indexed pages [29]; 品牌越来越多地与专门为电商开发定制解决方案的人工智能咨询公司合作

## rag_local_zh_007 (dev, single_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

《全球电商行业AI应用研究报告2025》对 AI 客服或智能客服有什么描述？

- [ ] service: AI助手支持咨询答复、导购与客户关系维护
  - 28aab03c3f2d; indexed pages [42]; 他们的人工智能客户服务聊天机器人处理了高达95%的书面和口头客户咨询
  - 28aab03c3f2d; indexed pages [47]; 人工智能助手可以即时回复咨询、引导产品搜索、促进无缝交易
  - 28aab03c3f2d; indexed pages [29]; 他们还使用聊天机器人与用户互动并以有益的方式为他们提供帮助

## rag_local_zh_008 (dev, single_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

《全球电商行业AI应用研究报告2025》中提到电商企业采用 AI 面临哪些挑战？

- [ ] challenges: 部署挑战涉及数据质量、成本、隐私和系统错误
  - 28aab03c3f2d; indexed pages [51]; 这些挑战包括数据质量、成本、隐私和系统错误等问题

- [ ] integration: 部署还需保护客户数据并持续集成维护
  - 28aab03c3f2d; indexed pages [53]; 企业可能需要调整现有的工具、数据库或工作流程
  - 28aab03c3f2d; indexed pages [53]; 这引发了隐私方面的担忧，尤其是在保护敏感数据方面

## rag_local_zh_009 (dev, single_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

《贝莱德BlackRock2026年全球投资展望报告》对 2026 年全球宏观或市场环境的核心判断是什么？

- [ ] macro: AI资本支出支撑增长，同时存在通胀与结构调整不确定性
  - 96c7e95c3c6d; indexed pages [5]; 我们认为2026年人工智能资本支出仍将推动经济增长
  - 96c7e95c3c6d; indexed pages [3]; 颠覆性趋势（尤其是人工智能发展）正在重塑全球经济与金融市场

## rag_local_zh_010 (dev, single_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

《贝莱德BlackRock2026年全球投资展望报告》中如何看待人工智能或 AI 投资主题？

- [ ] macro: AI资本支出支撑增长，同时存在通胀与结构调整不确定性
  - 96c7e95c3c6d; indexed pages [5]; 我们认为2026年人工智能资本支出仍将推动经济增长
  - 96c7e95c3c6d; indexed pages [3]; 颠覆性趋势（尤其是人工智能发展）正在重塑全球经济与金融市场

- [ ] ai_investment: AI建设面临资本支出、收入兑现与融资期限错配
  - 96c7e95c3c6d; indexed pages [4]; 投资者面临的主要挑战在于如何调和庞大的资本支出计划与人工智能潜在收入
  - 96c7e95c3c6d; indexed pages [4]; 人工智能建设需要前期大规模投资，包括布局算力、数据中心及能源基础设施

## rag_local_zh_011 (dev, single_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

《贝莱德BlackRock2026年全球投资展望报告》对股票、债券或资产配置有什么建议？

- [ ] stocks: 报告的战术观点包括超配美国及日本股票
  - 96c7e95c3c6d; indexed pages [15]; 我们继续超配美国股票
  - 96c7e95c3c6d; indexed pages [15]; 日本股票是我们战术和战略配置的优选之一

- [ ] bonds: 报告低配发达市场长期债券并偏好新兴市场硬通货债券
  - 96c7e95c3c6d; indexed pages [15]; 我们低配日本政府债券以及整体发达市场长期债券
  - 96c7e95c3c6d; indexed pages [15]; 我们偏好新兴市场硬通货债券

## rag_local_zh_012 (dev, single_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

《中国人民银行2025年第四季度中国货币政策执行报告》如何描述货币政策取向？

- [ ] retrospective: 2025年实施适度宽松货币政策
  - 4cad3f2ced2a; indexed pages [2]; 实施适度宽松的货币政策，在执行好存量货币政策的基础上
  - 4cad3f2ced2a; indexed pages [16]; 实施好适度宽松的货币政策，在执行好存量货币政策基础上

- [ ] outlook: 后续继续适度宽松，重视增长及物价合理回升
  - 4cad3f2ced2a; indexed pages [4, 60]; 继续实施好适度宽松的货币政策
  - 4cad3f2ced2a; indexed pages [4, 60]; 促进经济稳定增长、物价合理回升作为货币政策的重要考量

## rag_local_zh_013 (dev, single_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

《中国人民银行2025年第四季度中国货币政策执行报告》中如何分析信贷、社融或融资环境？

- [ ] credit: 社融和M2保持较快增长，贷款还原化债影响后约增7%
  - 4cad3f2ced2a; indexed pages [3]; 年末社会融资规模存量、广义货币供应量（M2）同比分别增长8.3%和8.5%

- [ ] funding: 企业和个人住房新发贷款利率均在3.1%左右
  - 4cad3f2ced2a; indexed pages [3]; 12月新发放企业贷款利率、个人住房贷款利率均在3.1%左右

## rag_local_zh_014 (dev, single_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

《中国人民银行2025年第四季度中国货币政策执行报告》中对物价、通胀或价格形势有什么判断？

- [ ] prices: CPI总体持平，核心CPI温和上涨，PPI仍下降
  - 4cad3f2ced2a; indexed pages [53]; 全年，扣除食品和能源的核心CPI同比上涨0.7%

- [ ] ppi: 工业生产者出厂价格同比下降2.6%，降幅收窄
  - 4cad3f2ced2a; indexed pages [53]; 工业生产者出厂价格指数（PPI）同比下降2.6%

## rag_local_zh_015 (dev, single_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

《长江商学院2025年投资者情绪问卷调查CKISS四季度报告》主要调查了哪些投资者情绪指标？

- [ ] stock_expectations: 调查包括股票涨跌和预期回报
  - 51f243a95edf; indexed pages [5]; 受访者整体对A股的预期回报率约0.9%

- [ ] property_expectations: 调查覆盖房地产价格预期和投资意愿
  - 51f243a95edf; indexed pages [6]; 对房地产价格的预期回报率降至-0.6%

- [ ] macro_expectations: 调查还覆盖通胀、GDP和净利润预期
  - 51f243a95edf; indexed pages [14]; 您认为在将来的5年，中国CPI通胀率平均每年是多少？

## rag_local_zh_016 (dev, single_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

《长江商学院2025年投资者情绪问卷调查CKISS四季度报告》对投资者收益预期有什么发现？

- [ ] stock_expectations: 调查包括股票涨跌和预期回报
  - 51f243a95edf; indexed pages [5]; 受访者整体对A股的预期回报率约0.9%

- [ ] returns: 本期整体A股预期回报约0.9%，港股约1.6%
  - 51f243a95edf; indexed pages [5]; 本期约61.1%的受访者认为港股会上涨，较9月下降2.2个百分点，对港股的预期回报率约1.6%

## rag_local_zh_017 (dev, single_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

《长江商学院2025年投资者情绪问卷调查CKISS四季度报告》如何描述投资者风险偏好或市场信心？

- [ ] sentiment: 散户与金融从业者对股市的信心呈分化
  - 51f243a95edf; indexed pages [2, 5]; 散户认为A股会上涨的比例进一步提升至64.2%
  - 51f243a95edf; indexed pages [5]; 散户情绪依然保持韧性甚至略显乐观，而金融业则可能基于风控考量

## rag_local_zh_018 (dev, multi_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

只根据本地金融行业知识库，概括 2026 年全球投资展望和中国货币政策报告在宏观判断上的异同。

- [ ] macro: AI资本支出支撑增长，同时存在通胀与结构调整不确定性
  - 96c7e95c3c6d; indexed pages [5]; 我们认为2026年人工智能资本支出仍将推动经济增长
  - 96c7e95c3c6d; indexed pages [3]; 颠覆性趋势（尤其是人工智能发展）正在重塑全球经济与金融市场

- [ ] outlook: 后续继续适度宽松，重视增长及物价合理回升
  - 4cad3f2ced2a; indexed pages [4, 60]; 继续实施好适度宽松的货币政策
  - 4cad3f2ced2a; indexed pages [4, 60]; 促进经济稳定增长、物价合理回升作为货币政策的重要考量

## rag_local_zh_019 (dev, multi_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

只根据本地电商行业知识库，对比数字人直播白皮书和全球电商AI应用报告对 AI 落地场景的描述。

- [ ] scenarios: 数字人直播的具体应用场景或场景分类
  - 61803158d2af; indexed pages [9]; 品牌自播间：7×24小时品牌店播
  - 61803158d2af; indexed pages [20]; 真人主播数字分身降本增效、AI总裁背书建立信任

- [ ] applications: AI用于推荐、客服、营销、库存或物流等电商环节
  - 28aab03c3f2d; indexed pages [43]; 包括仓库机器人、智能客服、智能上架和营销工具
  - 28aab03c3f2d; indexed pages [30]; 人工智能解决方案还可以准确分析需求模式、检测波动
  - 28aab03c3f2d; indexed pages [42]; 他们的人工智能客户服务聊天机器人处理了高达95%的书面和口头客户咨询

## rag_local_zh_020 (dev, unanswerable)

- [ ] Human reviewed question, answerability, and evidence alternatives.

只用本地知识库回答：这些资料中是否包含关于火星移民电商直播的专门章节？如果没有依据，请说明。

- [ ] Confirm the requested topic/granularity is absent; literal absence alone does not prove semantic unanswerability.

## rag_test_zh_001 (test, natural_query)

- [ ] Human reviewed question, answerability, and evidence alternatives.

中小商家入门级数字人产品价格降到了什么水平，可以利用哪些非高峰时段的流量？

- [ ] entry_cost: 入门产品数百元甚至免费，可利用夜间长尾流量
  - 61803158d2af; indexed pages [19]; 入门级数字人产品价格从百万级降至数百元，甚至免费

## rag_test_zh_002 (test, natural_query)

- [ ] Human reviewed question, answerability, and evidence alternatives.

只看观看量和GMV够不够？本地资料提出从哪五个维度评估数字人直播能力？

- [ ] dimensions: 视觉表现、智能交互、智能决策、运营易用和商业价值
  - 61803158d2af; indexed pages [25]; 从视觉表现力、智能交互力、智能决策力、运营易用性、商业价值力五大维度

## rag_test_zh_003 (test, natural_query)

- [ ] Human reviewed question, answerability, and evidence alternatives.

购物者拍下一双鞋想找到相似商品，人工智能怎样改善这种查找体验？

- [ ] visual_search: 识别图片中的产品并推荐相似商品
  - 28aab03c3f2d; indexed pages [27]; 人工智能可以通过从图像中识别产品并向购物者提供相关结果

## rag_test_zh_004 (test, natural_query)

- [ ] Human reviewed question, answerability, and evidence alternatives.

潜在顾客离开购物网站却没有购买，商家可以怎样用AI重新触达他们？

- [ ] retargeting: 分析用户行为，预测购买意愿，再投放个性化广告
  - 28aab03c3f2d; indexed pages [28]; 然后，他们会制作个性化广告来吸引他们的注意力，并提高转化率

## rag_test_zh_005 (test, natural_query)

- [ ] Human reviewed question, answerability, and evidence alternatives.

2025年末社融存量和M2的同比增速分别是多少，与名义GDP增速相比如何？

- [ ] monetary_growth: 社融8.3%、M2为8.5%，明显高于名义GDP增速
  - 4cad3f2ced2a; indexed pages [3]; 年末社会融资规模存量、广义货币供应量（M2）同比分别增长8.3%和8.5%，明显高于名义GDP增速

## rag_test_zh_006 (test, natural_query)

- [ ] Human reviewed question, answerability, and evidence alternatives.

投资者问卷从何时起把基金拆成股票型基金和收益偏稳定型基金？

- [ ] survey_definition: 从2019年11月的调查开始拆分
  - 51f243a95edf; indexed pages [17]; 从2019年11月的调查开始，我们将基金拆分成股票型基金和收益偏稳定型基金

## rag_test_zh_007 (test, multi_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

数字人直播的个性化交互和电商AI对话营销有哪些共同点？分别引用两份材料说明。

- [ ] live_personalization: 直播走向一对一专属服务
  - 61803158d2af; indexed pages [50]; 下一代直播将从“一对多广播”进化为“一对一专属服务”

- [ ] marketing_personalization: AI对话营销建立个性化联系并改善用户关系
  - 28aab03c3f2d; indexed pages [29]; 广告商已转向人工智能对话式营销。这种创新方法有助于与客户建立个性化联系

## rag_test_zh_008 (test, multi_document)

- [ ] Human reviewed question, answerability, and evidence alternatives.

从电商企业和AI基础设施投资者两个视角，分别说明一项采用AI的成本压力，并各引一份本地材料。

- [ ] business_cost: 电商部署存在成本与集成维护挑战
  - 28aab03c3f2d; indexed pages [51]; 这些挑战包括数据质量、成本、隐私和系统错误等问题

- [ ] capital_cost: AI建设需要前期算力、数据中心及能源投入
  - 96c7e95c3c6d; indexed pages [4]; 人工智能建设需要前期大规模投资，包括布局算力、数据中心及能源基础设施

## rag_test_zh_009 (test, unanswerable)

- [ ] Human reviewed question, answerability, and evidence alternatives.

哪份本地资料介绍了量子芯片在月球仓库中的订单纠错算法？

- [ ] Confirm the requested topic/granularity is absent; literal absence alone does not prove semantic unanswerability.

## rag_test_zh_010 (test, unanswerable)

- [ ] Human reviewed question, answerability, and evidence alternatives.

请只用这些报告给出2027年每家商户数字人直播的逐日交易明细。

- [ ] Confirm the requested topic/granularity is absent; literal absence alone does not prove semantic unanswerability.

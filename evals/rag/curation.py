"""Source-reviewed authoring specification for suite v2; never used to tune retrieval.

Anchors are short excerpts from already indexed local documents. The frozen JSONL files, rather
than this authoring module, are the experiment inputs. Human review is still outstanding.
"""

from copy import deepcopy

from evals.rag.scoring import passage_sha256
from evals.runners.common import DATASET_DIR, load_jsonl

DOCUMENTS = {
    "live": "61803158d2af3f9913fffe612463789dc6fa46a97fe28dae199be216120a2d2c",
    "commerce": "28aab03c3f2d3a30c3b5b6ee6ed6b8adec9e9459d7e3588727920bf135742f2a",
    "outlook": "96c7e95c3c6da57bacff1ae409635029ff315f844a68363b1e41cf6cc5d4b651",
    "policy": "4cad3f2ced2a9a5b8813f81c6d293b90c77fd7f9e142df11d14fd3900e8633c6",
    "survey": "51f243a95edf3325f589ff226231f607367a64466a6bd079d19aa14c261c6257",
}


def unit(name, document, keypoint, *anchors):
    return {
        "id": name,
        "keypoint": keypoint,
        "locations": [
            {
                "document_sha256": DOCUMENTS[document],
                "anchor": anchor,
                "anchor_sha256": passage_sha256(anchor),
            }
            for anchor in anchors
        ],
    }


def development_units():
    scenarios = unit(
        "scenarios",
        "live",
        "数字人直播的具体应用场景或场景分类",
        "品牌自播间：7×24小时品牌店播",
        "真人主播数字分身降本增效、AI总裁背书建立信任",
    )
    benefits = unit(
        "benefits",
        "live",
        "标准化和全天候运营带来的成本、效率优势",
        "高边际成本低边际成本",
        "有效解决主播培养成本高、直播间搭建复杂、多场景适配难等痛点",
    )
    participants = unit(
        "participants",
        "live",
        "服务商、品牌商家、MCN和消费者构成生态",
        "服务方：SaaS技术服务商、IP定制商、代运营机构",
    )
    future = unit(
        "agent_future",
        "live",
        "由标准工具向自主经营智能体与个性化服务演进",
        "从标准化工具升级为全链路经营主体",
        "从被动执行指令升级为主动理解生意、自主制定经营策略",
    )
    applications = unit(
        "applications",
        "commerce",
        "AI用于推荐、客服、营销、库存或物流等电商环节",
        "包括仓库机器人、智能客服、智能上架和营销工具",
        "人工智能解决方案还可以准确分析需求模式、检测波动",
        "他们的人工智能客户服务聊天机器人处理了高达95%的书面和口头客户咨询",
    )
    marketing = unit(
        "marketing",
        "commerce",
        "用户洞察支持个性化沟通、再营销与转化",
        "人工智能可以分析数据并提供有价值的用户洞察",
        "品牌越来越多地与专门为电商开发定制解决方案的人工智能咨询公司合作",
    )
    service = unit(
        "service",
        "commerce",
        "AI助手支持咨询答复、导购与客户关系维护",
        "他们的人工智能客户服务聊天机器人处理了高达95%的书面和口头客户咨询",
        "人工智能助手可以即时回复咨询、引导产品搜索、促进无缝交易",
        "他们还使用聊天机器人与用户互动并以有益的方式为他们提供帮助",
    )
    challenges = unit(
        "challenges",
        "commerce",
        "部署挑战涉及数据质量、成本、隐私和系统错误",
        "这些挑战包括数据质量、成本、隐私和系统错误等问题",
    )
    integration = unit(
        "integration",
        "commerce",
        "部署还需保护客户数据并持续集成维护",
        "企业可能需要调整现有的工具、数据库或工作流程",
        "这引发了隐私方面的担忧，尤其是在保护敏感数据方面",
    )
    macro = unit(
        "macro",
        "outlook",
        "AI资本支出支撑增长，同时存在通胀与结构调整不确定性",
        "我们认为2026年人工智能资本支出仍将推动经济增长",
        "颠覆性趋势（尤其是人工智能发展）正在重塑全球经济与金融市场",
    )
    investment = unit(
        "ai_investment",
        "outlook",
        "AI建设面临资本支出、收入兑现与融资期限错配",
        "投资者面临的主要挑战在于如何调和庞大的资本支出计划与人工智能潜在收入",
        "人工智能建设需要前期大规模投资，包括布局算力、数据中心及能源基础设施",
    )
    stocks = unit(
        "stocks",
        "outlook",
        "报告的战术观点包括超配美国及日本股票",
        "我们继续超配美国股票",
        "日本股票是我们战术和战略配置的优选之一",
    )
    bonds = unit(
        "bonds",
        "outlook",
        "报告低配发达市场长期债券并偏好新兴市场硬通货债券",
        "我们低配日本政府债券以及整体发达市场长期债券",
        "我们偏好新兴市场硬通货债券",
    )
    retrospective = unit(
        "retrospective",
        "policy",
        "2025年实施适度宽松货币政策",
        "实施适度宽松的货币政策，在执行好存量货币政策的基础上",
        "实施好适度宽松的货币政策，在执行好存量货币政策基础上",
    )
    stance = unit(
        "outlook",
        "policy",
        "后续继续适度宽松，重视增长及物价合理回升",
        "继续实施好适度宽松的货币政策",
        "促进经济稳定增长、物价合理回升作为货币政策的重要考量",
    )
    credit = unit(
        "credit",
        "policy",
        "社融和M2保持较快增长，贷款还原化债影响后约增7%",
        "年末社会融资规模存量、广义货币供应量（M2）同比分别增长8.3%和8.5%",
    )
    funding = unit(
        "funding",
        "policy",
        "企业和个人住房新发贷款利率均在3.1%左右",
        "12月新发放企业贷款利率、个人住房贷款利率均在3.1%左右",
    )
    prices = unit(
        "prices",
        "policy",
        "CPI总体持平，核心CPI温和上涨，PPI仍下降",
        "全年，扣除食品和能源的核心CPI同比上涨0.7%",
    )
    ppi = unit(
        "ppi",
        "policy",
        "工业生产者出厂价格同比下降2.6%，降幅收窄",
        "工业生产者出厂价格指数（PPI）同比下降2.6%",
    )
    survey_stocks = unit(
        "stock_expectations",
        "survey",
        "调查包括股票涨跌和预期回报",
        "受访者整体对A股的预期回报率约0.9%",
    )
    survey_property = unit(
        "property_expectations",
        "survey",
        "调查覆盖房地产价格预期和投资意愿",
        "对房地产价格的预期回报率降至-0.6%",
    )
    survey_macro = unit(
        "macro_expectations",
        "survey",
        "调查还覆盖通胀、GDP和净利润预期",
        "您认为在将来的5年，中国CPI通胀率平均每年是多少？",
    )
    returns = unit(
        "returns",
        "survey",
        "本期整体A股预期回报约0.9%，港股约1.6%",
        "本期约61.1%的受访者认为港股会上涨，较9月下降2.2个百分点，对港股的预期回报率约1.6%",
    )
    sentiment = unit(
        "sentiment",
        "survey",
        "散户与金融从业者对股市的信心呈分化",
        "散户认为A股会上涨的比例进一步提升至64.2%",
        "散户情绪依然保持韧性甚至略显乐观，而金融业则可能基于风控考量",
    )
    return {
        1: [scenarios],
        2: [benefits],
        3: [participants],
        4: [future],
        5: [applications],
        6: [marketing],
        7: [service],
        8: [challenges, integration],
        9: [macro],
        10: [macro, investment],
        11: [stocks, bonds],
        12: [retrospective, stance],
        13: [credit, funding],
        14: [prices, ppi],
        15: [survey_stocks, survey_property, survey_macro],
        16: [survey_stocks, returns],
        17: [sentiment],
        18: [macro, stance],
        19: [scenarios, applications],
        20: [],
    }


def make_case(case_id, split, question, units, *, kind="single_document", absent_terms=None):
    return {
        "id": case_id,
        "split": split,
        "question": question,
        "answerable": bool(units),
        "kind": kind,
        "annotation_version": "v2",
        "annotation_review": "source_verified_by_agent_pending_human_review",
        "coverage_policy": "required_keypoints_not_exhaustive_document_summary",
        "answer_keypoints": [item["keypoint"] for item in units],
        "evidence_units": deepcopy(units),
        **({"absent_terms": absent_terms} if absent_terms else {}),
    }


def development_cases():
    units = development_units()
    cases = []
    for row in load_jsonl(DATASET_DIR / "rag_local_zh.jsonl"):
        number = int(row["id"].rsplit("_", 1)[1])
        cases.append(
            make_case(
                row["id"],
                "dev",
                row["task"],
                units[number],
                kind="unanswerable"
                if number == 20
                else "multi_document"
                if number in (18, 19)
                else "single_document",
                absent_terms=["火星移民"] if number == 20 else None,
            )
        )
    return cases


def test_cases():
    specs = [
        (
            "中小商家入门级数字人产品价格降到了什么水平，可以利用哪些非高峰时段的流量？",
            [
                unit(
                    "entry_cost",
                    "live",
                    "入门产品数百元甚至免费，可利用夜间长尾流量",
                    "入门级数字人产品价格从百万级降至数百元，甚至免费",
                )
            ],
        ),
        (
            "只看观看量和GMV够不够？本地资料提出从哪五个维度评估数字人直播能力？",
            [
                unit(
                    "dimensions",
                    "live",
                    "视觉表现、智能交互、智能决策、运营易用和商业价值",
                    "从视觉表现力、智能交互力、智能决策力、运营易用性、商业价值力五大维度",
                )
            ],
        ),
        (
            "购物者拍下一双鞋想找到相似商品，人工智能怎样改善这种查找体验？",
            [
                unit(
                    "visual_search",
                    "commerce",
                    "识别图片中的产品并推荐相似商品",
                    "人工智能可以通过从图像中识别产品并向购物者提供相关结果",
                )
            ],
        ),
        (
            "潜在顾客离开购物网站却没有购买，商家可以怎样用AI重新触达他们？",
            [
                unit(
                    "retargeting",
                    "commerce",
                    "分析用户行为，预测购买意愿，再投放个性化广告",
                    "然后，他们会制作个性化广告来吸引他们的注意力，并提高转化率",
                )
            ],
        ),
        (
            "2025年末社融存量和M2的同比增速分别是多少，与名义GDP增速相比如何？",
            [
                unit(
                    "monetary_growth",
                    "policy",
                    "社融8.3%、M2为8.5%，明显高于名义GDP增速",
                    "年末社会融资规模存量、广义货币供应量（M2）同比分别增长8.3%和8.5%，明显高于名义GDP增速",
                )
            ],
        ),
        (
            "投资者问卷从何时起把基金拆成股票型基金和收益偏稳定型基金？",
            [
                unit(
                    "survey_definition",
                    "survey",
                    "从2019年11月的调查开始拆分",
                    "从2019年11月的调查开始，我们将基金拆分成股票型基金和收益偏稳定型基金",
                )
            ],
        ),
        (
            "数字人直播的个性化交互和电商AI对话营销有哪些共同点？分别引用两份材料说明。",
            [
                unit(
                    "live_personalization",
                    "live",
                    "直播走向一对一专属服务",
                    "下一代直播将从“一对多广播”进化为“一对一专属服务”",
                ),
                unit(
                    "marketing_personalization",
                    "commerce",
                    "AI对话营销建立个性化联系并改善用户关系",
                    "广告商已转向人工智能对话式营销。这种创新方法有助于与客户建立个性化联系",
                ),
            ],
        ),
        (
            "从电商企业和AI基础设施投资者两个视角，分别说明一项采用AI的成本压力，并各引一份本地材料。",
            [
                unit(
                    "business_cost",
                    "commerce",
                    "电商部署存在成本与集成维护挑战",
                    "这些挑战包括数据质量、成本、隐私和系统错误等问题",
                ),
                unit(
                    "capital_cost",
                    "outlook",
                    "AI建设需要前期算力、数据中心及能源投入",
                    "人工智能建设需要前期大规模投资，包括布局算力、数据中心及能源基础设施",
                ),
            ],
        ),
        ("哪份本地资料介绍了量子芯片在月球仓库中的订单纠错算法？", []),
        ("请只用这些报告给出2027年每家商户数字人直播的逐日交易明细。", []),
    ]
    return [
        make_case(
            f"rag_test_zh_{index:03}",
            "test",
            question,
            units,
            kind="unanswerable"
            if not units
            else "multi_document"
            if index in (7, 8)
            else "natural_query",
            absent_terms=["月球仓库"] if index == 9 else ["逐日交易明细"] if index == 10 else None,
        )
        for index, (question, units) in enumerate(specs, 1)
    ]

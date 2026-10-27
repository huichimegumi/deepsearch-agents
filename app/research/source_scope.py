"""Bounded lexical source intent, not a natural-language parser or an access-control policy."""

import re

SOURCES = re.compile(
    r"(?P<local>本地知识库(?:助手)?|知识库助手|(?<![a-z0-9_])rag(?![a-z0-9_]))"
    r"|(?P<network>(?:网络|网页|联网)(?:搜索)?|\b(?:web|internet)(?:\s+search)?\b)"
    r"|(?P<other>数据库|费用引擎|(?<![a-z0-9_])(?:sql|fee)(?![a-z0-9_]))",
    re.I,
)
VERBS = r"使用|查询|查阅|检索|访问|调用|参考|读取|采用|搜索|用|根据|依据|通过|基于|结合|依赖|从|use\b|query\b|access\b|search\b"
DIRECTIVES = re.compile(
    rf"(?P<negative>不允许|不需要|不要|禁止|不得|不能|无法|无需|不必|不许|避免|别|不|do\s+not|don't|never)"
    rf"\s*(?:仅|只)?(?:{VERBS}|联网|网络搜索|网络|网页)"
    rf"|(?P<exclusive>只能|仅|只|\bonly\b)\s*(?:{VERBS})?"
    rf"|(?P<positive>{VERBS})",
    re.I,
)
QUALIFIERS = (
    r"(?:(?:公开|公共|本地|官方|内部|外部|现有|已有|指定|public\b|local\b|official\b|the\b)\s*)*"
)
SOURCE_PREFIX = re.compile(rf"\s*{QUALIFIERS}", re.I)
SOURCE_JOIN = re.compile(rf"\s*(?:和|与|及|以及|、|\+|或|and\b|or\b|/|&)\s*{QUALIFIERS}", re.I)


def requires_local_only(task_query: str) -> bool:
    """Bind source polarity to its preceding directive within a clause.

    A negative source list retains its polarity until another directive or clause.
    An exclusivity phrase elsewhere cannot turn a prohibited local source into a
    requested one. Any affirmed additional source keeps the general research route.
    """
    local_requested = local_exclusive = network_denied = other_requested = False
    for clause in re.split(r"[，,。；;！？!?\n]", task_query):
        sources = list(SOURCES.finditer(clause))
        directives = [
            event
            for event in DIRECTIVES.finditer(clause)
            if not event.group("positive")
            or not any(source.start() <= event.start() < source.end() for source in sources)
        ]
        previous_source = None
        for source in sources:
            preceding = [event for event in directives if event.start() < source.start()]
            directive = preceding[-1] if preceding else None
            negative = directive is not None and directive.group("negative") is not None
            direct = directive is not None and (
                directive.end() > source.start()
                or SOURCE_PREFIX.fullmatch(clause[directive.end() : source.start()]) is not None
            )
            gap = clause[previous_source.end() : source.start()] if previous_source else ""
            # An optional KB-name parenthesis can precede an actual source-list join.
            gap = re.sub(r"^\s*[（(][^()（）]*[）)]", "", gap)
            joined = previous_source is not None and SOURCE_JOIN.fullmatch(gap) is not None
            associated = direct or joined or (source.lastgroup == "local" and directive is None)
            if not associated:
                continue  # e.g. 网络安全 later in the question is a topic, not a source request.
            previous_source = source
            if source.lastgroup == "local":
                local_requested |= not negative
                local_exclusive |= (
                    not negative
                    and directive is not None
                    and directive.group("exclusive") is not None
                )
            else:
                other_requested |= not negative
                network_denied |= negative and source.lastgroup == "network"
    return local_requested and not other_requested and (local_exclusive or network_denied)

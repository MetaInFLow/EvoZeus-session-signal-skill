from __future__ import annotations

from collections import Counter, defaultdict
from difflib import SequenceMatcher
import logging
import re
from typing import Any, Mapping, NamedTuple

from evozeus_session_signal_skill import OfficialFactor, OfficialFactorResult
from evozeus_session_signal_skill.nlp import authored_request_text, canonical_text, event_chat_role, is_direct_user_input, semantic_phrase_candidates

try:  # Optional lightweight Chinese segmentation/POS dependency.
    import jieba
    import jieba.posseg as jieba_posseg
except ImportError:  # pragma: no cover - exercised when the optional dependency is absent.
    jieba = None
    jieba_posseg = None
else:
    jieba.setLogLevel(logging.ERROR)

try:  # Optional fast fuzzy matcher for candidate clustering.
    from rapidfuzz import fuzz as rapidfuzz_fuzz
except ImportError:  # pragma: no cover - exercised when the optional dependency is absent.
    rapidfuzz_fuzz = None


OFFICIAL_KEY_SENTENCE_TRENDS_SPEC = {
    "schema_version": "official.factor.v0",
    "stability": "official",
    "factor_id": "official.key-sentence-trends",
    "version": "v0.1.0",
    "title": "Key sentence trends",
    "summary": "按时间统计关键句出现趋势，帮助看出用户关注点如何变化。",
    "title_i18n": {
        "zh-CN": "关键句趋势",
        "en-US": "Key sentence trends",
    },
    "summary_i18n": {
        "zh-CN": "按时间统计关键句出现趋势，帮助看出用户关注点如何变化。",
        "en-US": "Aggregates key sentence trends over time to show how user attention changes.",
    },
    "compatibility": {"evozeus_protocol": ">=0.1.0"},
    "governance": {"owner": "evozeus-factor-maintainers"},
    "input_contract": {
        "event_model": "SessionEvent[]",
        "required_fields": ["events[].id", "events[].role", "events[].text"],
        "accepted_input_kinds": ["session", "project", "scan_record_set"],
        "target_types": ["session", "project", "scan_record_set"],
        "record_types": ["session_envelope"],
        "prior_result_policy": "not_required",
    },
    "evidence_contract": {
        "ref_format": "event:<event-id>",
        "privacy": "Official factors must use redacted events and stable evidence refs.",
    },
    "output_contract": {
        "statuses": ["matched", "not_matched", "skipped", "error"],
        "fields": ["scores", "datasets", "presentations", "evidence_refs"],
        "dataset_semantic_types": ["key_sentence_trend"],
        "presentation_components": ["builtin.line_chart.v1", "builtin.heatmap.v1", "builtin.table.v1", "builtin.json.v1"],
    },
    "test_vectors": [
        {
            "name": "key sentence trends by date bucket",
            "input": "factors/key-sentence-trends/session.json",
            "expected_status": "matched",
        }
    ],
}


class KeySentenceTrendsFactor(OfficialFactor):
    def __init__(self) -> None:
        super().__init__(OFFICIAL_KEY_SENTENCE_TRENDS_SPEC)

    def evaluate(self, context: Mapping[str, Any]) -> OfficialFactorResult:
        session_id = str(context.get("session_id", ""))
        trend_counts: Counter[tuple[str, str, str]] = Counter()
        evidence_by_cluster: dict[tuple[str, str], list[str]] = defaultdict(list)
        relation_by_cluster: dict[tuple[str, str], str] = {}
        clusters_by_role: dict[str, dict[str, KeySentenceCandidate]] = defaultdict(dict)

        for event in context.get("events", []):
            chat_role = event_chat_role(event)
            if chat_role != "user":
                continue
            if not is_direct_user_input(event):
                continue
            bucket = _date_bucket(str(event.get("timestamp", "")))
            event_clusters: set[str] = set()
            text = authored_request_text(event)
            if not text:
                canonical = canonical_text(event)
                if "http://" in canonical or "https://" in canonical:
                    text = URL_RE.sub(" ", canonical)
            if not text:
                continue
            for candidate in _key_sentence_candidates(text[:2000]):
                cluster_label = _cluster_label_for(candidate, clusters_by_role[chat_role])
                if cluster_label in event_clusters:
                    continue
                event_clusters.add(cluster_label)
                trend_counts[(chat_role, bucket, cluster_label)] += 1
                cluster_key = (chat_role, cluster_label)
                evidence_by_cluster[cluster_key].append(str(event.get("id", "")))
                relation_by_cluster.setdefault(cluster_key, candidate.relation_type)

        if not trend_counts:
            return self.build_result(status="not_matched", target_type="session", target_id=session_id)

        records = [
            {
                "date_bucket": bucket,
                "chat_role": chat_role,
                "cluster_label": cluster_label,
                "count": int(count),
                "session_count": 1,
                "score": float(count),
                "relation_type": relation_by_cluster.get((chat_role, cluster_label), "key_sentence"),
            }
            for (chat_role, bucket, cluster_label), count in sorted(trend_counts.items())
        ]
        evidence_refs = [
            {"ref_id": event_id, "kind": f"{cluster_key[0]}_turn"}
            for cluster_key, event_ids in evidence_by_cluster.items()
            for event_id in event_ids
            if event_id
        ]

        return self.build_result(
            status="matched",
            target_type="session",
            target_id=session_id,
            confidence=0.73,
            tags=[{"type": "key_sentence", "value": "trend"}],
            scores={"key_sentence_cluster_count": float(len(evidence_by_cluster))},
            datasets=[
                {
                    "id": "key_sentence_trends",
                    "semantic_type": "key_sentence_trend",
                    "shape": "time_series",
                    "primary_key": "date_bucket,cluster_label",
                    "records": records,
                    "schema": {
                        "date_bucket": "string",
                        "chat_role": "string",
                        "cluster_label": "string",
                        "count": "number",
                        "relation_type": "string",
                    },
                }
            ],
            presentations=[
                {
                    "id": "key_sentence_line",
                    "title": "关键句趋势",
                    "component_ref": "builtin.line_chart.v1",
                    "data_ref": "key_sentence_trends",
                    "bindings": {"x": "date_bucket", "y": "count", "series": "cluster_label", "group": "chat_role"},
                    "routes": ["dashboard"],
                    "fallback": ["builtin.table.v1", "builtin.json.v1"],
                    "priority": 70,
                },
                {
                    "id": "key_sentence_heatmap",
                    "title": "关键句热力",
                    "component_ref": "builtin.heatmap.v1",
                    "data_ref": "key_sentence_trends",
                    "bindings": {"x": "date_bucket", "y": "cluster_label", "color": "count"},
                    "routes": ["dashboard"],
                    "fallback": ["builtin.table.v1", "builtin.json.v1"],
                    "priority": 71,
                },
            ],
            evidence_refs=evidence_refs,
        )


class PosToken(NamedTuple):
    text: str
    pos: str


class KeySentenceCandidate(NamedTuple):
    label: str
    relation_type: str
    tokens: tuple[str, ...]


class ExplicitKeyPhraseRule(NamedTuple):
    pattern: re.Pattern[str]
    relation_type: str


DROP_BLOCK_PATTERNS = [
    re.compile(r"```.*?```", re.S),
    re.compile(r"<image\b.*?</image>", re.S | re.I),
    re.compile(r"<environment_context>.*?</environment_context>", re.S | re.I),
    re.compile(r"<INSTRUCTIONS>.*?</INSTRUCTIONS>", re.S | re.I),
    re.compile(r"<subagent_notification>.*?</subagent_notification>", re.S | re.I),
]
REQUEST_MARKER_RE = re.compile(r"##\s*My request for Codex:\s*", re.I)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\([^)]+\)")
SENTENCE_SPLIT_RE = re.compile(r"[\n\r\t。！？!?；;，,：:]+")
LEADING_MARKDOWN_RE = re.compile(r"^\s*(?:[-*+>]\s+|#{1,6}\s+|\d+[.)]\s+)")
PATH_OR_URL_RE = re.compile(r"(?:https?://|^//|/Users/|/var/folders|\.jsonl\b)", re.I)
URL_RE = re.compile(r"https?://\S+", re.I)
TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{1,4}|[A-Za-z][A-Za-z0-9_-]*")
HAS_TEXT_RE = re.compile(r"[\u4e00-\u9fffA-Za-z]")
POLITE_PREFIXES = ("麻烦", "请帮忙", "请帮我", "帮忙", "帮我", "请")
NEGATION_PREFIXES = ("不要", "别", "禁止", "不能", "不许", "不准")
OUTPUT_PREFIXES = ("输出", "给出", "列出", "生成", "返回", "展示", "告诉我", "总结下")
SEQUENCE_PREFIXES = ("先", "再", "然后", "最后")
ACTION_PREFIXES = (
    "部署",
    "使用",
    "调用",
    "启动",
    "看",
    "安装",
    "检查",
    "review",
    "修改",
    "改",
    "修复",
    "实现",
    "运行",
    "统计",
    "跑",
    "整理",
    "分析",
    "写一个",
    "看看",
    "有没有",
    "结合",
    "针对",
    "分开区域讲",
    "能不能",
    "要用",
)
NOISE_EXACT = {
    "好的",
    "继续",
    "收到",
    "可以",
    "ok",
    "yes",
    "no",
    "project",
    "index",
    "text",
}
OBJECT_POS_PREFIXES = ("n", "eng")
ACTION_POS_PREFIXES = ("v",)


def _key_rule(pattern: str, relation_type: str) -> ExplicitKeyPhraseRule:
    return ExplicitKeyPhraseRule(re.compile(pattern, re.I), relation_type)


EXPLICIT_KEY_PHRASE_RULES = (
    _key_rule(r"(?P<phrase>总结下[，,]包括网站叙事和视频呈现脚本)", "output_request"),
    _key_rule(r"(?P<phrase>需要图片/视频/动画\s*可能用GSAP要用到的地方留出空位)", "output_request"),
    _key_rule(r"(?:还要)?(?P<phrase>再详细一点[，,]甚至要带一些例子)", "output_request"),
    _key_rule(r"(?P<phrase>资料都要有[“\"]真实[”\"]案例作证)", "output_request"),
    _key_rule(r"(?P<phrase>真实案例要从github上找到)", "output_request"),
    _key_rule(r"(?P<phrase>告诉我什么情况下会激活什么hook会做什么)", "output_request"),
    _key_rule(r"(?P<phrase>这些hook的原始意图讲一下)", "output_request"),
    _key_rule(r"(?:我希望我们这个harness会)?(?P<phrase>给目标skill正确的hooks机制)", "action_request"),
    _key_rule(r"(?P<phrase>注册hooks自动)", "action_request"),
    _key_rule(r"(?:这个\s*skill\s*不能)?(?P<phrase>引导用户主动[^。！？!?，,]{0,60}推进下一步)", "action_request"),
    _key_rule(r"(?:我希望)?(?P<phrase>细节都在SKILL里)", "output_request"),
    _key_rule(r"(?P<phrase>说明能做什么的时候要借鉴template来输出)", "output_request"),
    _key_rule(r"(?P<phrase>把当前的提交上去并发release)", "action_request"),
    _key_rule(r"(?P<phrase>把pdf（直接可解析版和需要ocr版的）的解析功能包含了)", "action_request"),
    _key_rule(r"(?P<phrase>有没有地方存中间结果)", "action_request"),
    _key_rule(r"(?P<phrase>针对skill的开发范式[，,]蒸馏一份关于skill开发的重构书)", "action_request"),
    _key_rule(r"(?:然后)?(?P<phrase>无法应用到skill开发的就剔除)", "negative_constraint"),
    _key_rule(r"(?P<phrase>写一个skill[，,]用来以我想要的维度蒸馏一本书)", "action_request"),
    _key_rule(r"(?P<phrase>视频的主题要展现我们被进化的东西、我们evozeus提供了什么、进化过程)", "action_request"),
    _key_rule(r"(?P<phrase>结合我的项目定位重新设计一个符合我项目定位的页面)", "action_request"),
)


def _key_sentence_candidates(value: str) -> list[KeySentenceCandidate]:
    text = authored_request_text(value) or value.strip()
    if not text:
        return []

    candidates: list[KeySentenceCandidate] = []
    seen_labels: set[str] = set()
    consumed_spans: list[tuple[int, int]] = []
    for rule in EXPLICIT_KEY_PHRASE_RULES:
        for match in rule.pattern.finditer(text):
            phrase = _normalize_clause(match.groupdict().get("phrase") or match.group(0))
            candidate = _candidate_with_relation(phrase, rule.relation_type)
            if candidate is None or candidate.label in seen_labels:
                continue
            seen_labels.add(candidate.label)
            candidates.append(candidate)
            consumed_spans.append(match.span())

    remaining = list(text)
    for start, end in consumed_spans:
        remaining[start:end] = " " * (end - start)
    for raw_clause in SENTENCE_SPLIT_RE.split("".join(remaining)):
        candidate = _candidate_from_clause(raw_clause)
        if candidate is None or candidate.label in seen_labels:
            continue
        seen_labels.add(candidate.label)
        candidates.append(candidate)
    return candidates


def _candidate_with_relation(value: str, relation_type: str) -> KeySentenceCandidate | None:
    label = _canonical_label(value, relation_type)
    if not _is_valid_clause(label):
        return None
    tokens = _tokens_for_label(label)
    if not tokens:
        return None
    return KeySentenceCandidate(label=label, relation_type=relation_type, tokens=tokens)


def _candidate_from_clause(value: str) -> KeySentenceCandidate | None:
    if len(value) > 240:
        return None
    clause = _normalize_clause(value)
    if not _is_valid_clause(clause):
        return None
    if _is_feedback_only(clause):
        return None

    relation_type = _relation_type(clause)
    if not relation_type:
        return None

    label = _canonical_label(clause, relation_type)
    if not _is_valid_clause(label):
        return None

    tokens = _tokens_for_label(label)
    if not tokens:
        return None
    return KeySentenceCandidate(label=label, relation_type=relation_type, tokens=tokens)


def _canonical_user_text(value: str) -> str:
    value = value.strip()
    if not value:
        return ""

    marker = REQUEST_MARKER_RE.search(value)
    if marker is not None:
        value = value[marker.end() :]
    elif value.lower().lstrip().startswith("# agents.md instructions"):
        return ""

    for pattern in DROP_BLOCK_PATTERNS:
        value = pattern.sub(" ", value)
    value = MARKDOWN_LINK_RE.sub(" ", value)

    lines = []
    for line in value.splitlines():
        line = line.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith("# files mentioned by the user"):
            continue
        if lowered.startswith("## codex-clipboard-"):
            continue
        if line.startswith("<") and line.endswith(">"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _normalize_clause(value: str) -> str:
    value = value.replace("\\n", " ")
    value = LEADING_MARKDOWN_RE.sub("", value).strip()
    value = value.strip("` \"'“”‘’()[]{}<>《》")
    value = " ".join(value.split())
    if not value:
        return ""

    value = value.replace("合理利用subagent", "合理利用 subagent")
    for prefix in POLITE_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix) :].strip()
            break

    if value.startswith("并") and any(value[1:].startswith(prefix) for prefix in ACTION_PREFIXES):
        value = value[1:].strip()

    value = re.sub(r"^我希望我们这个harness会", "", value, flags=re.I).strip()
    value = re.sub(r"^我希望(?=(?:细节|结果|输出|页面|文档))", "", value).strip()
    value = re.sub(r"^是否具有\s*\d+[）)]?", "", value).strip()
    value = re.sub(r"^这个\s*skill\s*不能(?=引导)", "", value, flags=re.I).strip()

    value = re.sub(r"(?:别删|不要删)(?!除)", "不要删除", value)
    replacements = (
        ("别删除", "不要删除"),
        ("禁止删除", "不要删除"),
        ("不能删除", "不要删除"),
        ("不要修改", "不要改"),
        ("别修改", "不要改"),
        ("别改", "不要改"),
        ("禁止修改", "不要改"),
        ("不能修改", "不要改"),
        ("只读不改", "不要改"),
        ("只读不要改", "不要改"),
    )
    for old, new in replacements:
        value = value.replace(old, new)
    return value.strip()


def _relation_type(clause: str) -> str:
    if "只读" in clause and any(term in clause.lower() for term in ("审查", "复核", "review")):
        return "read_only_constraint"
    without_connector = re.sub(r"^(?:然后|另外|接着)", "", clause).strip()
    if without_connector.startswith("无法") and any(term in without_connector for term in ("剔除", "删除", "排除")):
        return "negative_constraint"
    if "不要" in without_connector and not without_connector.startswith("能不能"):
        return "negative_constraint"
    if any(without_connector.startswith(prefix) for prefix in NEGATION_PREFIXES):
        return "negative_constraint"
    if clause.startswith("写一个TLDR") or clause.startswith("我只要结果"):
        return "output_request"
    if any(without_connector.startswith(prefix) for prefix in OUTPUT_PREFIXES):
        return "output_request"
    if without_connector.startswith("细节都在") or "要借鉴template来输出" in without_connector:
        return "output_request"
    if without_connector.startswith("资料都要") or without_connector.startswith("真实案例要从"):
        return "output_request"
    if without_connector.startswith("需要") and any(term in without_connector for term in ("留出", "输出", "写好", "展示")):
        return "output_request"
    if clause.startswith("然后") and without_connector.startswith("不确定"):
        return "sequence_step"
    if any(without_connector.startswith(prefix) for prefix in SEQUENCE_PREFIXES):
        return "sequence_step"
    if without_connector.startswith("分开区域讲") or without_connector.startswith("视频的主题要"):
        return "action_request"
    if without_connector.startswith("引导用户") or without_connector.startswith("给目标skill"):
        return "action_request"
    if any(
        candidate.cluster_id in {"intent.run_project", "intent.review_factors"}
        for candidate in semantic_phrase_candidates(without_connector)
    ):
        return "action_request"
    if _has_dependency_like_action_object(without_connector):
        return "action_request"
    return ""


def _canonical_label(clause: str, relation_type: str) -> str:
    clause = re.sub(r"^(?:然后|另外|接着)", "", clause).strip()
    if relation_type == "read_only_constraint":
        return "只读审查"
    if relation_type == "negative_constraint":
        return _negative_constraint_label(clause)
    return clause


def _negative_constraint_label(clause: str) -> str:
    if clause.startswith("不要"):
        return clause
    for prefix in ("别", "禁止", "不能", "不许", "不准"):
        if clause.startswith(prefix):
            return "不要" + clause[len(prefix) :]
    return clause


def _has_dependency_like_action_object(clause: str) -> bool:
    if clause.startswith("运行时"):
        return False
    if clause.startswith("改动") and not any(term in clause for term in ("改成", "修改为", "改为")):
        return False
    if clause.startswith("把") and any(term in clause for term in ("改成", "改为", "拉起来", "跑起来", "打开", "看下")):
        return True
    if not any(clause.startswith(prefix) for prefix in ACTION_PREFIXES):
        return False
    tokens = _pos_tokens(clause)
    if not tokens:
        return True

    seen_action = False
    for token in tokens:
        if _is_action_token(token):
            seen_action = True
            continue
        if seen_action and _is_object_token(token):
            return True
    return seen_action and len("".join(token.text for token in tokens)) <= 24


def _pos_tokens(value: str) -> list[PosToken]:
    if jieba_posseg is not None:
        return [
            PosToken(text=word.strip(), pos=flag)
            for word, flag in jieba_posseg.cut(value)
            if word.strip() and HAS_TEXT_RE.search(word)
        ]
    return [PosToken(text=token, pos="") for token in _fallback_tokens(value)]


def _is_action_token(token: PosToken) -> bool:
    if token.pos.startswith(ACTION_POS_PREFIXES):
        return True
    return token.text in ACTION_PREFIXES or token.text in OUTPUT_PREFIXES


def _is_object_token(token: PosToken) -> bool:
    if token.pos.startswith(OBJECT_POS_PREFIXES):
        return True
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", token.text)) and token.text not in NEGATION_PREFIXES


def _is_valid_clause(value: str) -> bool:
    lowered = value.lower()
    if not value or lowered in NOISE_EXACT:
        return False
    if len(value) > 120:
        return False
    if PATH_OR_URL_RE.search(value):
        return False
    if not HAS_TEXT_RE.search(value):
        return False
    compact = "".join(value.split())
    return 2 <= len(compact) <= 80


def _is_feedback_only(value: str) -> bool:
    normalized = value.lower()
    if re.match(r"^(?:感觉)?(?:还是|还|依旧|仍然|方向|\d+好一点|不好|看不懂)", normalized):
        return not any(
            marker in normalized
            for marker in ("先", "要用", "需要", "告诉我", "总结", "重新设计", "能不能", "分开区域讲")
        )
    if normalized.startswith("看到") and "好处" in normalized:
        return True
    return False


def _tokens_for_label(label: str) -> tuple[str, ...]:
    if jieba is not None:
        tokens = [token.strip().lower() for token in jieba.cut(label) if token.strip()]
        return tuple(token for token in tokens if HAS_TEXT_RE.search(token))
    return tuple(_fallback_tokens(label))


def _fallback_tokens(value: str) -> list[str]:
    tokens = [token.lower() for token in TOKEN_RE.findall(value)]
    if len(tokens) > 1:
        return tokens
    compact = "".join(value.split()).lower()
    if re.search(r"[\u4e00-\u9fff]", compact):
        return [compact[index : index + 2] for index in range(max(1, len(compact) - 1))]
    return tokens


def _cluster_label_for(candidate: KeySentenceCandidate, clusters: dict[str, KeySentenceCandidate]) -> str:
    if candidate.label in clusters:
        return candidate.label
    for label, existing in clusters.items():
        if _same_cluster(candidate, existing):
            return label
    clusters[candidate.label] = candidate
    return candidate.label


def _same_cluster(current: KeySentenceCandidate, previous: KeySentenceCandidate) -> bool:
    if current.relation_type != previous.relation_type:
        return False
    if current.label == previous.label:
        return True
    score = _similarity_score(current, previous)
    return score >= 0.86


def _similarity_score(current: KeySentenceCandidate, previous: KeySentenceCandidate) -> float:
    current_text = " ".join(current.tokens)
    previous_text = " ".join(previous.tokens)
    if rapidfuzz_fuzz is not None:
        return float(rapidfuzz_fuzz.token_set_ratio(current_text, previous_text)) / 100.0

    current_tokens = set(current.tokens)
    previous_tokens = set(previous.tokens)
    overlap = len(current_tokens & previous_tokens)
    union = max(1, len(current_tokens | previous_tokens))
    jaccard = overlap / union
    sequence = SequenceMatcher(None, current.label, previous.label).ratio()
    return max(jaccard, sequence)


def _cluster_labels(value: str) -> list[str]:
    return [candidate.label for candidate in _key_sentence_candidates(value)]


def _date_bucket(value: str) -> str:
    if len(value) >= 10:
        return value[:10]
    return "unknown-date"

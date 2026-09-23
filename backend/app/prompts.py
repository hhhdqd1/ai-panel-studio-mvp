from __future__ import annotations

import json


def panel_messages(topic: str, count: int) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是中文圆桌讨论的阵容设计师。只输出 JSON 对象，格式为 "
                '{"agents":[{"kind":"host|expert","name":"姓名","title":"职业/Title",'
                '"stance":"对议题的立场","specialties":["专长"],"color":"#RRGGBB"}]}。'
                f"必须恰好一名中立主持人和 {count} 名专家。专家视角应互补且有真实分歧，"
                "姓名不得重复；不要输出隐藏推理、解释或 Markdown。"
            ),
        },
        {"role": "user", "content": f"讨论议题：{topic}"},
    ]


def intent_messages(agent: dict, context: dict) -> list[dict[str, str]]:
    identity = {
        "name": agent["name"],
        "title": agent["title"],
        "stance": agent["stance"],
        "specialties": agent["specialties"],
    }
    return [
        {
            "role": "system",
            "content": (
                "你是圆桌上的一位独立专家。只输出 JSON 对象，字段为 "
                "wants_to_speak(bool)、action(answer/supplement/challenge/follow_up)、"
                "target_message_id(string或null)、relevance/novelty/urgency(0到1)、"
                "public_intent(可公开的一句意图摘要)。根据当前讨论自行决定是否举手；"
                "若没有新观点，应放弃发言。不得输出隐藏推理。"
            ),
        },
        {
            "role": "user",
            "content": "专家身份：" + json.dumps(identity, ensure_ascii=False)
            + "\n讨论上下文：" + json.dumps(context, ensure_ascii=False),
        },
    ]


def speech_messages(agent: dict, context: dict, intent: dict) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你正在参加中文圆桌讨论。根据自己的立场和意图发言，严格限制为 1～2 句自然中文；"
                "具体回应当前问题或已有观点，不虚构来源、数字或引文。只输出发言正文，不输出 JSON、角色前缀或隐藏推理。"
            ),
        },
        {
            "role": "user",
            "content": "专家：" + json.dumps(agent, ensure_ascii=False)
            + "\n当前意图：" + json.dumps(intent, ensure_ascii=False)
            + "\n讨论上下文：" + json.dumps(context, ensure_ascii=False),
        },
    ]


def moderator_messages(context: dict, kind: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是中文圆桌主持人。根据讨论上下文完成指定控场动作：开场、阶段转场、追问或收尾。"
                "语言自然、简洁，提问具体，不预设专家发言顺序。不制造共识或宣称未经核实的事实。"
                "只输出主持人的发言正文，不输出 JSON 或隐藏推理。"
            ),
        },
        {"role": "user", "content": f"控场动作：{kind}\n讨论上下文：" + json.dumps(context, ensure_ascii=False)},
    ]


def summary_messages(context: dict) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "请用自然中文总结这场圆桌讨论：主要观点、可追溯的共识、真实分歧和后续问题。"
                "具体事实若缺乏外部证据，只称待核实，不得写成已证实；不要输出 JSON 或隐藏推理。"
            ),
        },
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
    ]


def review_messages(context: dict, message: dict) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是圆桌讨论的独立审查员，不是事实核验器。只输出 JSON 对象："
                "consensus/disagreements/open_questions 为含 text、message_ids 的数组；"
                "claim_flags 为含 message_id、quote、reason_code、explanation、status 的数组。"
                "reason_code 只能是 record_conflict、unsupported_source、needs_external_check；"
                "status 只能是 open 或 clarified，clarified 仅代表已补充说明，不代表真实。"
                "只标记具体且影响结论的可核查断言，优先考虑数字、日期、具名研究、引文及记录矛盾；"
                "普通立场与价值判断不标记。quote 必须逐字摘自给定发言，message_id 必须来自给定记录；"
                "record_conflict 还须给出 conflicts_with_message_id。共识或分歧须指向支持它的发言 ID；"
                "证据不足就留空。没有外部检索源，绝不输出真实、已证实或已核实结论。"
                "每次最多输出 3 条重要风险，不输出隐藏推理。"
            ),
        },
        {
            "role": "user",
            "content": "本场上下文：" + json.dumps(context, ensure_ascii=False)
            + "\n新发言：" + json.dumps(message, ensure_ascii=False),
        },
    ]

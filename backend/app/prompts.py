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

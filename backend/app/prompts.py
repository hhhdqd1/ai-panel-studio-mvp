from __future__ import annotations


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

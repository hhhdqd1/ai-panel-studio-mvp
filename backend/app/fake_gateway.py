from __future__ import annotations


class FakeGateway:
    model = "fake-model"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.panel = self._default_panel(4)

    @staticmethod
    def _default_panel(count: int) -> list[dict]:
        panel = [
            {
                "kind": "host", "name": "林知衡", "title": "圆桌主持人", "stance": "中立引导",
                "specialties": ["议题梳理", "追问"], "color": "#5865f2",
            }
        ]
        colors = ["#f97316", "#0d9488", "#a855f7", "#e11d48", "#2563eb", "#65a30d"]
        for index in range(count):
            panel.append(
                {
                    "kind": "expert", "name": f"专家{index + 1}", "title": f"领域研究员{index + 1}",
                    "stance": f"视角{index + 1}", "specialties": ["案例研究"],
                    "color": colors[index],
                }
            )
        return panel

    async def generate_panel(self, topic: str, count: int) -> list[dict]:
        self.calls.append({"purpose": "panel", "topic": topic, "count": count})
        return self.panel if count == 4 else self._default_panel(count)

    async def propose_intent(self, agent: dict, context: dict) -> dict:
        self.calls.append(
            {"purpose": "intent", "discussion_id": context["discussion_id"], "topic": context["topic"]}
        )
        index = int(agent["name"][-1]) if agent["name"][-1].isdigit() else 1
        return {
            "agent_id": agent["id"],
            "wants_to_speak": True,
            "action": "challenge" if context["stage"] == "challenge" else "answer",
            "target_message_id": context["messages"][-1]["id"] if context["messages"] else None,
            "relevance": 0.65 + (index % 3) * 0.05,
            "novelty": 0.7,
            "urgency": 0.5,
            "public_intent": "准备提出一个不同视角",
        }

    async def generate_speech(self, agent: dict, context: dict, intent: dict) -> str:
        self.calls.append(
            {"purpose": "speech", "discussion_id": context["discussion_id"], "topic": context["topic"]}
        )
        if context["expert_turns"] == 2:
            return "有统计声称83%的参与者获益，但来源尚未提供。这个数字不能直接当作结论。"
        topic = context["topic"].rstrip("？?。！! ")
        cautious_stance = any(
            word in agent.get("stance", "")
            for word in ("担忧", "风险", "反对", "审慎", "不主张", "警惕", "优先关注")
        )
        if cautious_stance or agent["name"].endswith(("2", "4")):
            return f"关于“{topic}”，{agent['name']}担心贸然推广会放大成本与风险，不宜过早推广。我们应先核对长期影响。"
        return f"关于“{topic}”，{agent['name']}支持先做小范围试点。我们再根据证据评估效果。"

    async def moderate(self, context: dict, kind: str) -> str:
        self.calls.append(
            {"purpose": "moderate", "discussion_id": context["discussion_id"], "topic": context["topic"], "kind": kind}
        )
        if kind == "opening":
            return f"欢迎来到圆桌，今天讨论{context['topic']}。请大家先提出各自最重要的判断依据。"
        if kind == "closing":
            return "感谢各位的讨论，我们已经看到不同立场与仍需核实的问题。下面作一个简要总结。"
        return "我们先停下来比较已有论据，再从另一个角度追问这个问题。"

    async def summarize(self, context: dict) -> str:
        self.calls.append(
            {"purpose": "summary", "discussion_id": context["discussion_id"], "topic": context["topic"]}
        )
        return f"本场围绕{context['topic']}展开了多角度讨论。专家提出试点与长期评估两条路径；具体效果和数字待核实。"

    async def review(self, context: dict, message: dict) -> dict:
        self.calls.append(
            {
                "purpose": "review", "discussion_id": context["discussion_id"],
                "topic": context["topic"], "message_id": message["id"],
            }
        )
        messages = context["messages"]
        flags = []
        questions = []
        if "83%的参与者获益" in message["content"]:
            flags.append(
                {
                    "message_id": message["id"],
                    "quote": "83%的参与者获益",
                    "reason_code": "needs_external_check",
                    "explanation": "具体数字未附可追溯来源",
                    "status": "open",
                }
            )
            questions.append(
                {"text": "这项统计的来源和适用范围是什么？", "message_ids": [message["id"]]}
            )
        cautious = next((item for item in messages if "不宜过早推广" in item["content"]), None)
        proactive = next((item for item in messages if "先做小范围试点" in item["content"]), None)
        disagreements = []
        if cautious is not None and proactive is not None:
            disagreements.append(
                {
                    "text": "对试点之后的推进速度存在不同看法",
                    "message_ids": [proactive["id"], cautious["id"]],
                }
            )
        return {
            "consensus": [], "disagreements": disagreements,
            "open_questions": questions, "claim_flags": flags,
        }

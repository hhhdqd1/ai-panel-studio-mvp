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

"""封装 LangGraph interrupt 与恢复数据。"""

from typing import Any


def extract_interrupt_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return None
    first = interrupts[0]
    value = getattr(first, "value", first)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value if isinstance(value, dict) else {"question": str(value)}

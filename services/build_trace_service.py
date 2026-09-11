"""从LangGraph检查点构造可视化执行轨迹。"""

from typing import Any


def build_execution_trace(graph: Any, config: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        snapshots = list(reversed(list(graph.get_state_history(config))))
    except Exception:
        return events
    for index in range(1, len(snapshots)):
        previous = snapshots[index - 1]
        snapshot = snapshots[index]
        metadata = dict(snapshot.metadata or {})
        nodes = [node for node in previous.next if node != "__start__"]
        for node in nodes:
            events.append({
                "sequence": len(events) + 1,
                "node": node,
                "step": metadata.get("step"),
                "source": metadata.get("source"),
                "created_at": snapshot.created_at,
                "next": list(snapshot.next),
            })
    return events

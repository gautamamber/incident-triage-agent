from langgraph.graph import END, StateGraph

from app.agents.nodes.classify import classify
from app.agents.nodes.code_investigation import code_investigation
from app.agents.nodes.collect import collect_git, collect_logs, collect_metrics, collect_traces
from app.agents.nodes.evidence import fuse_evidence
from app.agents.nodes.load_context import load_context
from app.agents.nodes.notify import notify
from app.agents.nodes.rca import rca_node
from app.agents.state import InvestigationState


def build_graph():
    """load_context -> classify -> [4 parallel collectors] -> fuse_evidence
    -> code_investigation -> rca -> notify (doc section 6.1; retrieve_knowledge
    and confidence-routing/fix still not built — Phase 9 and Phase 8/10)."""
    graph = StateGraph(InvestigationState)

    graph.add_node("load_context", load_context)
    graph.add_node("classify", classify)
    graph.add_node("collect_logs", collect_logs)
    graph.add_node("collect_traces", collect_traces)
    graph.add_node("collect_metrics", collect_metrics)
    graph.add_node("collect_git", collect_git)
    graph.add_node("fuse_evidence", fuse_evidence)
    graph.add_node("code_investigation", code_investigation)
    graph.add_node("rca", rca_node)
    graph.add_node("notify", notify)

    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "classify")

    collectors = ("collect_logs", "collect_traces", "collect_metrics", "collect_git")
    for collector in collectors:
        graph.add_edge("classify", collector)  # fan-out: 4 in parallel
        graph.add_edge(collector, "fuse_evidence")  # fan-in: waits for all 4

    graph.add_edge("fuse_evidence", "code_investigation")
    graph.add_edge("code_investigation", "rca")
    graph.add_edge("rca", "notify")
    graph.add_edge("notify", END)

    return graph.compile()

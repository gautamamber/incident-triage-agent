from langgraph.graph import END, StateGraph

from app.agents.nodes.classify import classify
from app.agents.nodes.code_investigation import code_investigation
from app.agents.nodes.collect import collect_git, collect_logs, collect_metrics, collect_traces
from app.agents.nodes.confidence import score_confidence
from app.agents.nodes.evidence import fuse_evidence
from app.agents.nodes.fix import run_fix
from app.agents.nodes.knowledge import retrieve_knowledge
from app.agents.nodes.load_context import load_context
from app.agents.nodes.notify import notify
from app.agents.nodes.rca import rca_node
from app.agents.nodes.route import mark_needs_human, route_decision
from app.agents.state import InvestigationState


def build_graph(checkpointer=None):
    """load_context -> classify -> [4 parallel collectors] -> fuse_evidence
    -> code_investigation -> retrieve_knowledge -> rca -> score_confidence ->
    route -> {mark_needs_human | run_fix | notify} -> notify (doc section
    6.1/9.2). `run_fix` is only ever reachable when route_decision's
    fix_eligibility() check passes, which itself reads AGENT_MODE directly
    from settings — 'observe'/'rca' modes never route here.

    `checkpointer`, when given, makes every node's output durable in Postgres
    (doc section 6.2) — a killed worker resumes an in-progress investigation
    from its last completed node instead of starting over."""
    graph = StateGraph(InvestigationState)

    graph.add_node("load_context", load_context)
    graph.add_node("classify", classify)
    graph.add_node("collect_logs", collect_logs)
    graph.add_node("collect_traces", collect_traces)
    graph.add_node("collect_metrics", collect_metrics)
    graph.add_node("collect_git", collect_git)
    graph.add_node("fuse_evidence", fuse_evidence)
    graph.add_node("code_investigation", code_investigation)
    graph.add_node("retrieve_knowledge", retrieve_knowledge)
    graph.add_node("rca", rca_node)
    graph.add_node("score_confidence", score_confidence)
    graph.add_node("mark_needs_human", mark_needs_human)
    graph.add_node("run_fix", run_fix)
    graph.add_node("notify", notify)

    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "classify")

    collectors = ("collect_logs", "collect_traces", "collect_metrics", "collect_git")
    for collector in collectors:
        graph.add_edge("classify", collector)  # fan-out: 4 in parallel
        graph.add_edge(collector, "fuse_evidence")  # fan-in: waits for all 4

    graph.add_edge("fuse_evidence", "code_investigation")
    graph.add_edge("code_investigation", "retrieve_knowledge")
    graph.add_edge("retrieve_knowledge", "rca")
    graph.add_edge("rca", "score_confidence")
    graph.add_conditional_edges(
        "score_confidence",
        route_decision,
        {"needs_human": "mark_needs_human", "fix": "run_fix", "notify": "notify"},
    )
    graph.add_edge("mark_needs_human", "notify")
    graph.add_edge("run_fix", "notify")
    graph.add_edge("notify", END)

    return graph.compile(checkpointer=checkpointer)

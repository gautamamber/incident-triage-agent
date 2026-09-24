from app.agents.state import InvestigationState
from app.notify.slack import post_slack
from app.security.redaction import redact


def build_message(state: InvestigationState) -> str:
    incident = state["incident"]
    rca = state.get("rca")
    classification = state.get("classification") or {}

    if rca is None:
        lines = [
            f"⚠️ {incident.severity} Incident {incident.key} — {incident.service}",
            "",
            f"Error:        {incident.normalized_message} ({incident.exception_type})",
            f"Occurrences:  {incident.error_count}   First seen: {incident.first_seen}",
            "",
            "RCA:          investigation failed — see agent logs. NEEDS_HUMAN.",
        ]
        return redact("\n".join(lines))

    evidence_ids = ", ".join(rca.evidence_ids)
    lines = [
        f"🔎 {incident.severity} Incident {incident.key} — {incident.service}",
        "",
        f"Error:        {incident.normalized_message} ({incident.exception_type})",
        f"Occurrences:  {incident.error_count}   First seen: {incident.first_seen}",
        f"Category:     {classification.get('category', 'UNKNOWN')}",
        "",
        f"RCA:          {rca.root_cause}",
        f"Action:       {rca.recommended_action}",
        f"Evidence:     {evidence_ids}",
    ]
    if rca.suspect_commit:
        lines.append(f"Suspect commit: {rca.suspect_commit}")
    lines.append("")
    lines.append("🤖 RCA-only — no fix attempted. Review required.")

    return redact("\n".join(lines))


def notify(state: InvestigationState) -> dict:
    message = build_message(state)
    print(message)  # always visible locally, regardless of Slack config
    sent = post_slack(message)
    if not sent:
        return {"errors": ["notify: SLACK_WEBHOOK_URL not configured, message not sent"]}
    return {}

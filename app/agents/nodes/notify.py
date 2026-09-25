from app.agents.nodes.route import fix_eligibility
from app.agents.state import InvestigationState
from app.notify.slack import post_slack
from app.security.redaction import redact


def build_message(state: InvestigationState) -> str:
    incident = state["incident"]
    rca = state.get("rca")
    classification = state.get("classification") or {}
    confidence = state.get("confidence")

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

    is_needs_human = confidence is not None and confidence.band == "low"
    icon = "🚑" if is_needs_human else "🔎"

    lines = [
        f"{icon} {incident.severity} Incident {incident.key} — {incident.service}",
        "",
        f"Error:        {incident.normalized_message} ({incident.exception_type})",
        f"Occurrences:  {incident.error_count}   First seen: {incident.first_seen}",
        f"Category:     {classification.get('category', 'UNKNOWN')}",
    ]
    if confidence is not None:
        fired = ", ".join(f"{k}={v:+.2f}" for k, v in confidence.signals.items() if v != 0)
        lines.append(
            f"Confidence:   {confidence.score} ({confidence.band}) — {fired or 'no signals fired'}"
        )
    lines += [
        "",
        f"RCA:          {rca.root_cause}",
        f"Action:       {rca.recommended_action}",
        f"Evidence:     {', '.join(rca.evidence_ids)}",
    ]
    if rca.suspect_commit:
        lines.append(f"Suspect commit: {rca.suspect_commit}")
    if rca.unknowns:
        lines.append(f"Unknowns:     {'; '.join(rca.unknowns)}")
    lines.append("")

    fix = state.get("fix")
    if is_needs_human:
        lines.append(
            "🚑 NEEDS_HUMAN — confidence too low for an automated call. Please investigate."
        )
    elif fix is not None:
        if fix.outcome.value == "draft_pr_opened":
            lines.append(f"🤖 Draft PR opened ({fix.strategy}): {fix.pr_url}")
        else:
            lines.append(
                f"🤖 Fix attempt failed ({fix.strategy}): {fix.give_up_reason}. Review required."
            )
    else:
        eligible, reason = fix_eligibility(state)
        if eligible:
            lines.append(f"🤖 High confidence — {reason}")
        else:
            lines.append(f"🤖 RCA-only — no fix attempted ({reason}). Review required.")

    return redact("\n".join(lines))


def notify(state: InvestigationState) -> dict:
    message = build_message(state)
    print(message)  # always visible locally, regardless of Slack config
    sent = post_slack(message)
    if not sent:
        return {"errors": ["notify: SLACK_WEBHOOK_URL not configured, message not sent"]}
    return {}

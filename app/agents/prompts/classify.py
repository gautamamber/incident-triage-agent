from app.security.untrusted import UNTRUSTED_DATA_RULE, wrap_text

CLASSIFY_SYSTEM = (
    "You classify a software incident into exactly one category, based only on "
    "the exception type and error message given. Categories: DATABASE, API, "
    "NETWORK, MEMORY, CPU, DEPENDENCY, APPLICATION, UNKNOWN. Respond with only "
    f"the category name, nothing else.\n\n{UNTRUSTED_DATA_RULE}"
)


def build_classify_prompt(exception_type: str | None, message: str) -> str:
    return (
        f"exception_type: {exception_type or 'none'}\n"
        f"{wrap_text('logs', message)}\n\n"
        "Which category best fits? Answer with exactly one of: DATABASE, API, "
        "NETWORK, MEMORY, CPU, DEPENDENCY, APPLICATION, UNKNOWN."
    )

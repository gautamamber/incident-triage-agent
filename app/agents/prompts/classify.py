CLASSIFY_SYSTEM = (
    "You classify a software incident into exactly one category, based only on "
    "the exception type and error message given. Categories: DATABASE, API, "
    "NETWORK, MEMORY, CPU, DEPENDENCY, APPLICATION, UNKNOWN. Respond with only "
    "the category name, nothing else."
)


def build_classify_prompt(exception_type: str | None, message: str) -> str:
    return (
        f"exception_type: {exception_type or 'none'}\n"
        f"message: {message}\n\n"
        "Which category best fits? Answer with exactly one of: DATABASE, API, "
        "NETWORK, MEMORY, CPU, DEPENDENCY, APPLICATION, UNKNOWN."
    )

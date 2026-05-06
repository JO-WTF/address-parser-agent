
def merge_text(name_text: str, addr_text: str, phone_text: str) -> str:
    """Merge selected fields into one extraction input text."""
    return " ".join([x for x in [name_text, phone_text, addr_text] if x]).strip()

"""Small helpers shared by both render targets."""

ESCAPES = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
)


def escape(text):
    """Escape text for inclusion in HTML or minihtml."""
    for char, entity in ESCAPES:
        text = text.replace(char, entity)
    return text


def escape_attr(text):
    """Escape text for use inside a double-quoted attribute value."""
    return escape(text).replace("'", "&#39;")


def slugify(text):
    """Turn heading text into a GitHub-style anchor id."""
    out = []
    for char in text.lower().strip():
        if char.isalnum() or char in "-_":
            out.append(char)
        elif char in " \t":
            out.append("-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "section"

"""Small dependency-free Markdown renderer for the bundled help pages."""
import html
import re
from urllib.parse import urlsplit


def _slug(value):
    value = re.sub(r"<[^>]+>", "", value).strip().lower()
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    return re.sub(r"[\s-]+", "-", value).strip("-") or "section"


def _safe_href(value, allowed_docs):
    value = html.unescape(value).strip()
    if value.startswith("#") or value.startswith("/"):
        return value
    if value.endswith(".md") and "://" not in value:
        name = value.rsplit("/", 1)[-1][:-3]
        return f"/docs/{name}" if name in allowed_docs else None
    parsed = urlsplit(value)
    if parsed.scheme in {"https", "http", "mailto"} and (parsed.netloc or parsed.scheme == "mailto"):
        return value
    return None


def _inline(value, allowed_docs):
    codes = []

    def save_code(match):
        codes.append(f"<code>{html.escape(match.group(1))}</code>")
        return f"\x00CODE{len(codes) - 1}\x00"

    value = re.sub(r"`([^`]+)`", save_code, value)
    value = html.escape(value, quote=False)

    def link(match):
        label, raw_href = match.groups()
        href = _safe_href(raw_href, allowed_docs)
        if href is None:
            return label
        external = urlsplit(href).scheme in {"https", "http"}
        attrs = ' target="_blank" rel="noopener noreferrer"' if external else ""
        return f'<a href="{html.escape(href, quote=True)}"{attrs}>{label}</a>'

    value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, value)
    value = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", value)
    value = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", value)
    for index, code in enumerate(codes):
        value = value.replace(f"\x00CODE{index}\x00", code)
    return value


def _table_cells(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def render_markdown(source, allowed_docs=()):
    """Render common Markdown blocks while escaping raw HTML and unsafe links."""
    lines = str(source or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = []
    paragraph = []
    list_type = None
    in_code = False
    code_lines = []

    def flush_paragraph():
        if paragraph:
            output.append("<p>" + _inline(" ".join(line.strip() for line in paragraph), allowed_docs) + "</p>")
            paragraph.clear()

    def close_list():
        nonlocal list_type
        if list_type:
            output.append(f"</{list_type}>")
            list_type = None

    index = 0
    while index < len(lines):
        line = lines[index]
        if line.lstrip().startswith("```"):
            if in_code:
                output.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
                code_lines.clear()
                in_code = False
            else:
                flush_paragraph()
                close_list()
                in_code = True
            index += 1
            continue
        if in_code:
            code_lines.append(line)
            index += 1
            continue

        if not line.strip():
            flush_paragraph()
            close_list()
            index += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            body = _inline(heading.group(2), allowed_docs)
            output.append(f'<h{level} id="{_slug(heading.group(2))}">{body}</h{level}>')
            index += 1
            continue

        if index + 1 < len(lines) and "|" in line and re.match(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$", lines[index + 1]):
            flush_paragraph()
            close_list()
            headers = _table_cells(line)
            output.append("<div class=\"table-wrap\"><table><thead><tr>" + "".join(f"<th>{_inline(cell, allowed_docs)}</th>" for cell in headers) + "</tr></thead><tbody>")
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                cells = _table_cells(lines[index])
                cells += [""] * max(0, len(headers) - len(cells))
                output.append("<tr>" + "".join(f"<td>{_inline(cell, allowed_docs)}</td>" for cell in cells[:len(headers)]) + "</tr>")
                index += 1
            output.append("</tbody></table></div>")
            continue

        if re.match(r"^\s*(---+|\*\*\*+|___+)\s*$", line):
            flush_paragraph()
            close_list()
            output.append("<hr>")
            index += 1
            continue

        if line.startswith("> "):
            flush_paragraph()
            close_list()
            quoted = []
            while index < len(lines) and lines[index].startswith("> "):
                quoted.append(_inline(lines[index][2:], allowed_docs))
                index += 1
            output.append("<blockquote><p>" + " ".join(quoted) + "</p></blockquote>")
            continue

        unordered = re.match(r"^\s*[-*+]\s+(.+)$", line)
        ordered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        match = unordered or ordered
        if match:
            flush_paragraph()
            wanted = "ul" if unordered else "ol"
            if list_type != wanted:
                close_list()
                output.append(f"<{wanted}>")
                list_type = wanted
            output.append("<li>" + _inline(match.group(1), allowed_docs) + "</li>")
            index += 1
            continue

        close_list()
        paragraph.append(line)
        index += 1

    if in_code:
        output.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
    flush_paragraph()
    close_list()
    return "\n".join(output)

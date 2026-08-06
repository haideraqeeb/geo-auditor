from bs4 import BeautifulSoup


def extract_document_structure(html: str) -> dict:
    """
    Extracts a simplified semantic representation of an HTML document.

    Returns:
    {
        "headings": [...],
        "paragraphs": [...],
        "lists": [...],
        "tables": [...],
        "quotes": [...]
    }
    """

    soup = BeautifulSoup(html, "html.parser")

    # Remove irrelevant elements
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    structure = {
        "headings": [],
        "paragraphs": [],
        "lists": [],
        "tables": [],
        "quotes": [],
    }

    # -----------------------------
    # Headings
    # -----------------------------
    for heading in soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6"]
    ):
        text = heading.get_text(" ", strip=True)

        if text:
            structure["headings"].append(
                {
                    "level": int(heading.name[1]),
                    "text": text,
                }
            )

    # -----------------------------
    # Paragraphs
    # -----------------------------
    for paragraph in soup.find_all("p"):
        text = paragraph.get_text(" ", strip=True)

        if text:
            structure["paragraphs"].append(text)

    # -----------------------------
    # Lists
    # -----------------------------
    for lst in soup.find_all(["ul", "ol"]):

        items = []

        for li in lst.find_all("li", recursive=False):

            text = li.get_text(" ", strip=True)

            if text:
                items.append(text)

        if items:
            structure["lists"].append(items)

    # -----------------------------
    # Tables
    # -----------------------------
    for table in soup.find_all("table"):

        headers = []

        header_row = table.find("tr")

        if header_row:
            headers = [
                cell.get_text(" ", strip=True)
                for cell in header_row.find_all(["th", "td"])
            ]

        rows = []

        for row in table.find_all("tr")[1:]:

            values = [
                cell.get_text(" ", strip=True)
                for cell in row.find_all(["th", "td"])
            ]

            if values:
                rows.append(values)

        structure["tables"].append(
            {
                "headers": headers,
                "rows": rows,
            }
        )

    # -----------------------------
    # Block Quotes
    # -----------------------------
    for quote in soup.find_all("blockquote"):

        text = quote.get_text(" ", strip=True)

        if text:
            structure["quotes"].append(text)

    return structure
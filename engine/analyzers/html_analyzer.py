"""
Deterministic DOM & HTML signal extractor using Python standard library html.parser.
Extracts canonical, metadata, headings, images, links, and structured data blocks.
"""

from html.parser import HTMLParser
from typing import Any
import re


class DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.in_script = False
        self.in_style = False
        self.current_script_type = ""
        self.current_heading_tag = None
        self.current_heading_text = []

        self.title = ""
        self.meta_description = None
        self.canonical = None
        self.viewport = None
        self.meta_robots = None
        self.open_graph = {}
        self.twitter_card = {}

        self.headings = []  # List of {"level": int, "text": str}
        self.images = []    # List of {"src": str, "alt": str | None, "has_dims": bool}
        self.links = []     # List of {"href": str, "rel": str}
        self.json_ld_blocks = []
        self.visible_text_parts = []
        self._current_script_text = []

        # CSR / SPA Shell detection
        self.csr_mount_elements = []
        self.has_client_bundle = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        tag = tag.lower()
        attr_dict = {k.lower(): (v if v is not None else "") for k, v in attrs}

        tag_id = attr_dict.get("id", "").lower()
        if tag_id in ("root", "app", "__next", "__nuxt"):
            self.csr_mount_elements.append(f"{tag}#{tag_id}")

        if tag == "title":
            self.in_title = True
        elif tag == "style":
            self.in_style = True
        elif tag == "script":
            self.in_script = True
            self.current_script_type = attr_dict.get("type", "").lower()
            self._current_script_text = []
            script_src = attr_dict.get("src", "").lower()
            if script_src and any(pattern in script_src for pattern in ("chunk", "bundle", "main.", "app.", "/static/js/", "_next/static/")):
                self.has_client_bundle = True
        elif tag == "meta":
            name = attr_dict.get("name", "").lower()
            prop = attr_dict.get("property", "").lower()
            content = attr_dict.get("content", "")

            if name == "description":
                self.meta_description = content
            elif name == "viewport":
                self.viewport = content
            elif name == "robots":
                self.meta_robots = content
            elif prop.startswith("og:"):
                self.open_graph[prop] = content
            elif name.startswith("twitter:"):
                self.twitter_card[name] = content

        elif tag == "link":
            rel = attr_dict.get("rel", "").lower()
            href = attr_dict.get("href", "")
            if rel == "canonical":
                self.canonical = href
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.current_heading_tag = tag
            self.current_heading_text = []
        elif tag == "img":
            src = attr_dict.get("src", "")
            alt = attr_dict.get("alt")
            has_w = "width" in attr_dict
            has_h = "height" in attr_dict
            self.images.append({
                "src": src,
                "alt": alt,
                "has_dimensions": (has_w and has_h)
            })
        elif tag == "a":
            href = attr_dict.get("href", "")
            rel = attr_dict.get("rel", "")
            self.links.append({
                "href": href,
                "rel": rel
            })

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        elif tag == "style":
            self.in_style = False
        elif tag == "script":
            self.in_script = False
            if "application/ld+json" in self.current_script_type:
                block_content = "".join(self._current_script_text).strip()
                if block_content:
                    self.json_ld_blocks.append(block_content)
            self._current_script_text = []
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self.current_heading_tag == tag:
            heading_str = " ".join("".join(self.current_heading_text).split())
            if heading_str:
                self.headings.append({
                    "level": int(tag[1]),
                    "text": heading_str
                })
            self.current_heading_tag = None
            self.current_heading_text = []

    def handle_data(self, data: str):
        if self.in_title:
            self.title += data
        elif self.in_script:
            self._current_script_text.append(data)
        elif not self.in_style:
            if self.current_heading_tag:
                self.current_heading_text.append(data)
            cleaned = data.strip()
            if cleaned:
                self.visible_text_parts.append(cleaned)


def analyze_target_html(html_content: str, base_url: str = "") -> dict[str, Any]:
    """
    Parses HTML content into a structured semantic signal dictionary.
    """
    parser = DocumentParser()
    try:
        parser.feed(html_content)
    except Exception as e:
        # html.parser is generally forgiving, but handle unexpected parse errors gracefully
        pass

    title_clean = " ".join(parser.title.split())
    h1_headings = [h["text"] for h in parser.headings if h["level"] == 1]
    
    # Analyze links internal vs external
    internal_links = 0
    external_links = 0
    base_domain = base_url.split("://")[-1].split("/")[0].lower() if "://" in base_url else ""

    for l in parser.links:
        href = l["href"].strip().lower()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        if href.startswith("/") or (base_domain and base_domain in href):
            internal_links += 1
        elif href.startswith("http://") or href.startswith("https://"):
            external_links += 1
        else:
            internal_links += 1

    missing_alt_count = sum(1 for img in parser.images if img["alt"] is None or img["alt"].strip() == "")
    missing_dims_count = sum(1 for img in parser.images if not img["has_dimensions"])

    full_text = " ".join(parser.visible_text_parts)

    return {
        "title": {
            "value": title_clean,
            "length": len(title_clean),
            "present": bool(title_clean)
        },
        "meta_description": {
            "value": parser.meta_description,
            "length": len(parser.meta_description) if parser.meta_description else 0,
            "present": parser.meta_description is not None
        },
        "canonical": {
            "value": parser.canonical,
            "present": parser.canonical is not None
        },
        "viewport": {
            "value": parser.viewport,
            "present": parser.viewport is not None
        },
        "meta_robots": {
            "value": parser.meta_robots,
            "present": parser.meta_robots is not None
        },
        "open_graph": parser.open_graph,
        "twitter_card": parser.twitter_card,
        "headings": {
            "h1_count": len(h1_headings),
            "h1_values": h1_headings,
            "outline": parser.headings
        },
        "images": {
            "total_count": len(parser.images),
            "missing_alt": missing_alt_count,
            "missing_dimensions": missing_dims_count
        },
        "links": {
            "total_count": len(parser.links),
            "internal_count": internal_links,
            "external_count": external_links
        },
        "json_ld_raw_blocks": parser.json_ld_blocks,
        "visible_text": full_text,
        "visible_text_preview": full_text[:1000] if full_text else "",
        "word_count": len(full_text.split()),
        "csr_detection": {
            "is_csr_shell": (bool(parser.csr_mount_elements) and len(full_text.split()) < 35) or (parser.has_client_bundle and len(full_text.split()) < 25),
            "mount_elements": parser.csr_mount_elements,
            "has_client_bundle": parser.has_client_bundle,
            "visible_word_count": len(full_text.split())
        }
    }

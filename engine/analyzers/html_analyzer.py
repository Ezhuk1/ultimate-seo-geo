"""
Deterministic DOM & HTML signal extractor using Python standard library html.parser.
Extracts canonical, metadata, headings, images, links, and structured data blocks.
"""

from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit
import re


VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def estimate_title_pixel_width(title: str, font_size: int = 18) -> int:
    """
    Estimates desktop Google SERP title width in pixels based on Arial 18px proportional character metrics.
    Google desktop SERP truncates titles at approximately 580-600px.
    """
    if not title:
        return 0
    width = 0.0
    for ch in title:
        if ch in "ijl|'!,.:; ":
            width += 4.5
        elif ch in "fkt-`\"":
            width += 6.5
        elif ch in "abcdeghnopqrsuvxyz0123456789":
            width += 10.0
        elif ch in "mwMW_~":
            width += 16.0
        elif ch in "ABCDEFGHJKLMNOPQRSTUVXYZ":
            width += 12.0
        elif "\u0400" <= ch <= "\u04FF":  # Cyrillic
            if ch in "шщюжфШЩЮЖФ":
                width += 16.0
            elif ch in "іії!":
                width += 4.5
            elif ch.isupper():
                width += 13.0
            else:
                width += 10.0
        elif ord(ch) > 127:
            width += 16.0
        else:
            width += 10.0
    return int(round(width))


class DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_head = False
        self.in_title = False
        self.in_script = False
        self.in_style = False
        self.in_svg = False
        self.in_main = False
        self.has_main = False
        self.has_header = False
        self.has_nav = False
        self.has_footer = False
        self.boilerplate_depth = 0

        # DOM & Performance metrics
        self.dom_nodes_count = 0
        self.current_dom_depth = 0
        self.max_dom_depth = 0
        self.script_tags_count = 0
        self.render_blocking_css = []
        self.render_blocking_js = []
        self.resource_hints = []
        self.hero_image = None

        # Content structure & extractable elements
        self.tables_count = 0
        self.has_comparison_table = False
        self.lists_count = 0
        self.definition_lists_count = 0
        self.tldr_blocks_count = 0
        self.image_formats = {"modern": 0, "legacy": 0}

        self.form_inputs = []
        self.label_for_ids = set()
        self.insecure_resources = []
        self.in_a = False
        self.current_a_href = ""
        self.current_a_rel = ""
        self.current_a_text = []
        self.current_a_aria_label = ""
        self.current_a_has_img_alt = False

        # Agentic readiness & accessibility for AI agents
        self.markdown_alternate_url = None
        self.has_pricing_link = False
        self.buttons = []
        self.in_button = False
        self.current_button_text = []
        self.current_button_aria = ""
        self.fake_buttons = []

        self.current_script_type = ""
        self.current_heading_tag = None
        self.current_heading_text = []
        self._current_script_text = []
        self._current_title_text = []

        self.lang = None
        self.meta_charset = None
        self.title = ""
        self.title_tags = []
        self.meta_description = None
        self.meta_descriptions = []
        self.canonical = None
        self.canonical_tags = []
        self.canonical_in_body = False
        self.viewport = None
        self.viewport_parsed = {}
        self.meta_robots = None
        self.meta_googlebot = None
        self.robots_directives = set()
        self.open_graph = {}
        self.twitter_card = {}
        self.hreflang_tags = []

        self.headings = []  # List of {"level": int, "text": str}
        self.images = []    # List of {"src": str, "alt": str | None, "has_dims": bool, "loading": str, "fetchpriority": str}
        self.links = []     # List of {"href": str, "rel": str, "text": str, "aria_label": str, "has_text": bool}
        self.json_ld_blocks = []
        self.visible_text_parts = []
        self.main_text_parts = []
        self.boilerplate_text_parts = []

        # CSR / SPA Shell detection
        self.csr_mount_elements = []
        self.has_client_bundle = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        tag = tag.lower()
        attr_dict = {k.lower(): (v if v is not None else "") for k, v in attrs}

        self.dom_nodes_count += 1
        if tag not in VOID_TAGS:
            self.current_dom_depth += 1
            if self.current_dom_depth > self.max_dom_depth:
                self.max_dom_depth = self.current_dom_depth

        # Check for mixed content
        if tag in ("img", "script", "link", "iframe", "video", "audio"):
            for attr_k in ("src", "href"):
                attr_v = attr_dict.get(attr_k, "").strip()
                if attr_v.lower().startswith("http://"):
                    self.insecure_resources.append({"tag": tag, "url": attr_v})

        if tag == "head":
            self.in_head = True
        elif tag == "body":
            self.in_head = False
        elif tag == "html":
            html_lang = attr_dict.get("lang", "").strip()
            if html_lang:
                self.lang = html_lang
        elif tag == "header":
            self.has_header = True
            self.boilerplate_depth += 1
        elif tag == "nav":
            self.has_nav = True
            self.boilerplate_depth += 1
        elif tag == "main":
            self.in_main = True
            self.has_main = True
        elif tag == "footer":
            self.has_footer = True
            self.boilerplate_depth += 1
        elif tag == "aside":
            self.boilerplate_depth += 1
        elif tag == "svg":
            self.in_svg = True

        tag_id = attr_dict.get("id", "").lower()
        tag_cls = attr_dict.get("class", "").lower()
        tag_lower = tag.lower()
        if (
            tag_id in ("root", "app", "__next", "__nuxt", "svelte-announcer")
            or tag_lower in ("app-root", "astro-island")
            or tag_lower.startswith(("svelte-", "astro-"))
            or (tag == "div" and ("app" in tag_cls.split() or "root" in tag_cls.split()))
        ):
            self.csr_mount_elements.append(f"{tag}#{tag_id or tag_cls or tag_lower}")

        if any(marker in tag_id or marker in tag_cls for marker in ("tldr", "key-takeaway", "summary-box", "takeaways", "quick-answer")):
            self.tldr_blocks_count += 1

        if tag == "title" and not self.in_svg:
            self.in_title = True
            self._current_title_text = []
        elif tag == "style":
            self.in_style = True
        elif tag == "table":
            self.tables_count += 1
        elif tag == "th":
            self.has_comparison_table = True
        elif tag in ("ul", "ol"):
            self.lists_count += 1
        elif tag == "dl":
            self.definition_lists_count += 1
        elif tag == "script":
            self.in_script = True
            self.script_tags_count += 1
            self.current_script_type = attr_dict.get("type", "").lower()
            self._current_script_text = []
            script_src = attr_dict.get("src", "").lower()
            if script_src and any(pattern in script_src for pattern in ("chunk", "bundle", "main.", "app.", "/static/js/", "_next/static/")):
                self.has_client_bundle = True
            if self.in_head and script_src:
                is_async = "async" in attr_dict
                is_defer = "defer" in attr_dict
                if not is_async and not is_defer and self.current_script_type not in ("module", "application/ld+json"):
                    self.render_blocking_js.append(script_src)
        elif tag == "meta":
            name = attr_dict.get("name", "").lower()
            prop = attr_dict.get("property", "").lower()
            content = attr_dict.get("content", "")
            charset = attr_dict.get("charset", "").strip()
            http_equiv = attr_dict.get("http-equiv", "").lower()

            if charset:
                self.meta_charset = charset.lower()
            elif http_equiv == "content-type" and "charset=" in content.lower():
                m = re.search(r'charset=["\']?([a-zA-Z0-9_\-]+)', content, re.IGNORECASE)
                if m:
                    self.meta_charset = m.group(1).strip().lower()

            if name == "description":
                if content:
                    self.meta_descriptions.append(content)
                if self.meta_description is None:
                    self.meta_description = content
            elif name == "viewport":
                self.viewport = content
                for part in content.split(","):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        self.viewport_parsed[k.strip().lower()] = v.strip().lower()
            elif name in ("robots", "googlebot"):
                if name == "robots":
                    self.meta_robots = content
                elif name == "googlebot":
                    self.meta_googlebot = content
                for directive in content.split(","):
                    d_clean = directive.strip().lower()
                    if d_clean:
                        self.robots_directives.add(d_clean)
            elif prop.startswith("og:") or name.startswith("og:"):
                key = prop if prop.startswith("og:") else name
                self.open_graph[key] = content
            elif name.startswith("twitter:") or prop.startswith("twitter:"):
                key = name if name.startswith("twitter:") else prop
                self.twitter_card[key] = content

        elif tag == "link":
            rel = attr_dict.get("rel", "").lower()
            rel_tokens = rel.split()
            href = attr_dict.get("href", "")
            if "canonical" in rel_tokens:
                if not self.in_head:
                    self.canonical_in_body = True
                if self.canonical is None and self.in_head:
                    self.canonical = href
                elif self.canonical is None:
                    self.canonical = href
                self.canonical_tags.append(href)
            elif "alternate" in rel_tokens and "hreflang" in attr_dict:
                self.hreflang_tags.append({
                    "hreflang": attr_dict.get("hreflang", "").lower(),
                    "href": href
                })
            elif "stylesheet" in rel_tokens and self.in_head:
                media = attr_dict.get("media", "").strip().lower()
                if media != "print" and "preload" not in rel_tokens:
                    self.render_blocking_css.append(href)
            if any(r in rel_tokens for r in ("preconnect", "dns-prefetch", "preload")):
                self.resource_hints.append({
                    "rel": rel,
                    "href": href,
                    "as": attr_dict.get("as", "").lower()
                })
            if "alternate" in rel_tokens and attr_dict.get("type", "").lower() in ("text/markdown", "text/x-markdown"):
                self.markdown_alternate_url = href
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.current_heading_tag = tag
            self.current_heading_text = []
        elif tag == "button":
            self.in_button = True
            self.current_button_text = []
            self.current_button_aria = attr_dict.get("aria-label", "").strip() or attr_dict.get("title", "").strip()
        elif tag in ("div", "span"):
            if "onclick" in attr_dict:
                role = attr_dict.get("role", "").lower()
                tabindex = attr_dict.get("tabindex", "").strip()
                if role != "button" or not tabindex:
                    self.fake_buttons.append({"tag": tag, "id": attr_dict.get("id", "")})
        elif tag in ("input", "textarea", "select"):
            inp_type = attr_dict.get("type", "").lower()
            if inp_type != "hidden":
                self.form_inputs.append({
                    "tag": tag,
                    "type": inp_type,
                    "id": attr_dict.get("id", "").strip(),
                    "name": attr_dict.get("name", "").strip(),
                    "aria_label": attr_dict.get("aria-label", "").strip(),
                    "aria_labelledby": attr_dict.get("aria-labelledby", "").strip()
                })
        elif tag == "label":
            for_id = attr_dict.get("for", "").strip()
            if for_id:
                self.label_for_ids.add(for_id)
        elif tag == "img":
            src = attr_dict.get("src", "")
            alt = attr_dict.get("alt")
            has_w = "width" in attr_dict
            has_h = "height" in attr_dict
            loading_attr = attr_dict.get("loading", "").lower()
            fetch_attr = attr_dict.get("fetchpriority", "").lower()
            self.images.append({
                "src": src,
                "alt": alt,
                "has_dimensions": (has_w and has_h),
                "loading": loading_attr,
                "fetchpriority": fetch_attr
            })
            if not self.in_head and self.hero_image is None and src:
                self.hero_image = {
                    "src": src,
                    "loading": loading_attr,
                    "fetchpriority": fetch_attr
                }
            clean_src = src.split("?")[0].lower()
            ext = clean_src.rsplit(".", 1)[-1] if "." in clean_src else ""
            if ext in ("webp", "avif", "svg"):
                self.image_formats["modern"] += 1
            elif ext in ("jpg", "jpeg", "png", "gif", "bmp", "ico"):
                self.image_formats["legacy"] += 1

            if self.in_a and alt is not None and alt.strip():
                self.current_a_has_img_alt = True
        elif tag == "a":
            self.in_a = True
            self.current_a_href = attr_dict.get("href", "")
            self.current_a_rel = attr_dict.get("rel", "")
            self.current_a_text = []
            self.current_a_aria_label = attr_dict.get("aria-label", "").strip() or attr_dict.get("title", "").strip()
            self.current_a_has_img_alt = False
            if "pricing.md" in self.current_a_href.lower() or "/pricing" in self.current_a_href.lower() or self.current_a_href.strip().lower().endswith("/pricing") or self.current_a_href.strip().lower() == "pricing":
                self.has_pricing_link = True

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag not in VOID_TAGS and self.current_dom_depth > 0:
            self.current_dom_depth -= 1
        if tag in ("header", "footer", "nav", "aside") and self.boilerplate_depth > 0:
            self.boilerplate_depth -= 1

        if tag == "head":
            self.in_head = False
        elif tag == "main":
            self.in_main = False
        elif tag == "svg":
            self.in_svg = False
        elif tag == "button":
            self.in_button = False
            b_text = " ".join("".join(self.current_button_text).split())
            has_name = bool(b_text or self.current_button_aria)
            self.buttons.append({
                "text": b_text,
                "aria_label": self.current_button_aria,
                "has_accessible_name": has_name
            })
            self.current_button_text = []
        elif tag == "a":
            self.in_a = False
            anchor_text = " ".join("".join(self.current_a_text).split())
            has_text = bool(anchor_text or self.current_a_aria_label or self.current_a_has_img_alt)
            self.links.append({
                "href": self.current_a_href,
                "rel": self.current_a_rel,
                "text": anchor_text,
                "aria_label": self.current_a_aria_label,
                "has_text": has_text
            })
            self.current_a_text = []
        elif tag == "title":
            self.in_title = False
            title_text = " ".join("".join(self._current_title_text).split())
            if title_text:
                self.title_tags.append(title_text)
                if not self.title:
                    self.title = title_text
            self._current_title_text = []
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
            self.headings.append({
                "level": int(tag[1]),
                "text": heading_str
            })
            self.current_heading_tag = None
            self.current_heading_text = []
        elif tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "section", "article", "header", "footer", "main", "aside"):
            if self.visible_text_parts and self.visible_text_parts[-1] != "\n\n":
                self.visible_text_parts.append("\n\n")
            if self.in_main and self.main_text_parts and self.main_text_parts[-1] != "\n\n":
                self.main_text_parts.append("\n\n")

    def handle_data(self, data: str):
        if self.in_title:
            self._current_title_text.append(data)
        elif self.in_script:
            self._current_script_text.append(data)
        elif not self.in_style:
            if self.in_a:
                self.current_a_text.append(data)
            if self.in_button:
                self.current_button_text.append(data)
            if self.current_heading_tag:
                self.current_heading_text.append(data)
            cleaned = data.strip()
            if cleaned:
                self.visible_text_parts.append(cleaned)
                if self.in_main:
                    self.main_text_parts.append(cleaned)
                if self.boilerplate_depth > 0:
                    self.boilerplate_text_parts.append(cleaned)


def analyze_target_html(html_content: str, base_url: str = "") -> dict[str, Any]:
    """
    Parses HTML content into a structured semantic signal dictionary.
    """
    parser = DocumentParser()
    try:
        parser.feed(html_content)
    except Exception:
        pass

    title_clean = parser.title
    h1_headings = [h["text"] for h in parser.headings if h["level"] == 1 and h["text"]]
    empty_headings_count = sum(1 for h in parser.headings if not h["text"])

    hierarchy_jumps = []
    prev_level = 0
    for h in parser.headings:
        curr_level = h["level"]
        if prev_level > 0 and (curr_level - prev_level) > 1:
            hierarchy_jumps.append({
                "from_level": prev_level,
                "to_level": curr_level,
                "text": h["text"]
            })
        prev_level = curr_level

    # Analyze links internal vs external
    internal_links = 0
    external_links = 0
    empty_anchors_count = 0
    base_host = ""
    if base_url:
        parsed_base = urlsplit(base_url)
        base_host = parsed_base.netloc.lower().split(":")[0]

    ignored_schemes = ("mailto:", "tel:", "sms:", "javascript:", "#", "data:")

    for l in parser.links:
        href = l["href"].strip()
        href_lower = href.lower()
        if not href or any(href_lower.startswith(sch) for sch in ignored_schemes):
            continue

        if not l.get("has_text"):
            empty_anchors_count += 1

        target_host = urlsplit(href).netloc.lower().split(":")[0]
        if not target_host or target_host == base_host or (base_host and target_host.endswith("." + base_host)):
            internal_links += 1
        elif href_lower.startswith("http://") or href_lower.startswith("https://"):
            external_links += 1
        else:
            internal_links += 1

    missing_alt_count = sum(1 for img in parser.images if img["alt"] is None)
    decorative_alt_count = sum(1 for img in parser.images if img["alt"] is not None and img["alt"].strip() == "")
    missing_dims_count = sum(1 for img in parser.images if not img["has_dimensions"])

    unlabelled_inputs_count = 0
    for inp in parser.form_inputs:
        has_aria = bool(inp["aria_label"] or inp["aria_labelledby"])
        has_for = bool(inp["id"] and inp["id"] in parser.label_for_ids)
        if not (has_aria or has_for):
            unlabelled_inputs_count += 1

    unnamed_buttons_count = sum(1 for b in parser.buttons if not b["has_accessible_name"])
    fake_buttons_count = len(parser.fake_buttons)
    agentic_a11y_score = max(0, 100 - (unnamed_buttons_count * 15 + unlabelled_inputs_count * 10 + fake_buttons_count * 15))

    full_text_chunks = []
    for part in parser.visible_text_parts:
        if part == "\n\n":
            full_text_chunks.append("\n\n")
        else:
            if full_text_chunks and full_text_chunks[-1] != "\n\n":
                full_text_chunks.append(" ")
            full_text_chunks.append(part)
    full_text = "".join(full_text_chunks)

    main_text_chunks = []
    for part in parser.main_text_parts:
        if part == "\n\n":
            main_text_chunks.append("\n\n")
        else:
            if main_text_chunks and main_text_chunks[-1] != "\n\n":
                main_text_chunks.append(" ")
            main_text_chunks.append(part)
    main_text = "".join(main_text_chunks)
    boilerplate_text_chunks = []
    for part in parser.boilerplate_text_parts:
        if part == "\n\n":
            boilerplate_text_chunks.append("\n\n")
        else:
            if boilerplate_text_chunks and boilerplate_text_chunks[-1] != "\n\n":
                boilerplate_text_chunks.append(" ")
            boilerplate_text_chunks.append(part)
    boilerplate_text = "".join(boilerplate_text_chunks)
    boilerplate_words = len(boilerplate_text.split())
    total_words = len(full_text.split())
    substantive_words = len(main_text.split()) if parser.has_main else max(0, total_words - boilerplate_words)
    content_ratio = round((substantive_words / max(1, total_words)), 3)
    title_pixel_width = estimate_title_pixel_width(title_clean)

    return {
        "lang": parser.lang,
        "meta_charset": parser.meta_charset,
        "title": {
            "value": title_clean,
            "length": len(title_clean),
            "pixel_width": title_pixel_width,
            "present": bool(title_clean),
            "count": len(parser.title_tags),
            "all_titles": parser.title_tags
        },
        "meta_description": {
            "value": parser.meta_description,
            "length": len(parser.meta_description) if parser.meta_description else 0,
            "present": parser.meta_description is not None,
            "count": len(parser.meta_descriptions),
            "all_descriptions": parser.meta_descriptions
        },
        "canonical": {
            "value": parser.canonical,
            "present": parser.canonical is not None,
            "all_tags": parser.canonical_tags,
            "count": len(parser.canonical_tags),
            "in_body": parser.canonical_in_body
        },
        "viewport": {
            "value": parser.viewport,
            "present": parser.viewport is not None,
            "parsed": parser.viewport_parsed,
            "has_width_device": parser.viewport_parsed.get("width") == "device-width",
            "has_initial_scale": "initial-scale" in parser.viewport_parsed
        },
        "meta_robots": {
            "value": parser.meta_robots,
            "googlebot": parser.meta_googlebot,
            "present": (parser.meta_robots is not None or parser.meta_googlebot is not None),
            "directives": sorted(list(parser.robots_directives)),
            "is_noindex": ("noindex" in parser.robots_directives or "none" in parser.robots_directives),
            "is_nofollow": ("nofollow" in parser.robots_directives or "none" in parser.robots_directives)
        },
        "hreflang": {
            "tags": parser.hreflang_tags,
            "count": len(parser.hreflang_tags),
            "has_x_default": any(t["hreflang"].lower() == "x-default" for t in parser.hreflang_tags)
        },
        "open_graph": parser.open_graph,
        "twitter_card": parser.twitter_card,
        "headings": {
            "h1_count": len(h1_headings),
            "h1_values": h1_headings,
            "outline": parser.headings,
            "empty_count": empty_headings_count,
            "hierarchy_jumps": hierarchy_jumps,
            "hierarchy_jumps_count": len(hierarchy_jumps)
        },
        "images": {
            "total_count": len(parser.images),
            "missing_alt": missing_alt_count,
            "decorative_alt": decorative_alt_count,
            "missing_dimensions": missing_dims_count,
            "hero_image": parser.hero_image,
            "formats": parser.image_formats
        },
        "links": {
            "total_count": len(parser.links),
            "internal_count": internal_links,
            "external_count": external_links,
            "empty_anchors_count": empty_anchors_count,
            "all": parser.links
        },
        "landmarks": {
            "has_header": parser.has_header,
            "has_nav": parser.has_nav,
            "has_main": parser.has_main,
            "has_footer": parser.has_footer
        },
        "dom_stats": {
            "nodes_count": parser.dom_nodes_count,
            "max_depth": parser.max_dom_depth,
            "script_tags_count": parser.script_tags_count
        },
        "performance_assets": {
            "render_blocking_css": parser.render_blocking_css,
            "render_blocking_js": parser.render_blocking_js,
            "resource_hints": parser.resource_hints,
            "hero_image": parser.hero_image,
            "image_formats": parser.image_formats
        },
        "extractable_elements": {
            "tables_count": parser.tables_count,
            "has_comparison_table": parser.has_comparison_table,
            "lists_count": parser.lists_count,
            "definition_lists_count": parser.definition_lists_count,
            "tldr_blocks_count": parser.tldr_blocks_count
        },
        "content_ratio": {
            "substantive_words": substantive_words,
            "boilerplate_words": boilerplate_words,
            "total_words": total_words,
            "ratio": content_ratio
        },
        "forms": {
            "total_inputs": len(parser.form_inputs),
            "unlabelled_count": unlabelled_inputs_count
        },
        "mixed_content": {
            "insecure_resources": parser.insecure_resources,
            "insecure_count": len(parser.insecure_resources)
        },
        "json_ld_raw_blocks": parser.json_ld_blocks,
        "visible_text": full_text,
        "visible_text_preview": full_text[:1000] if full_text else "",
        "word_count": total_words,
        "main_text": main_text,
        "has_main": parser.has_main,
        "csr_detection": {
            "is_csr_shell": (
                (bool(parser.csr_mount_elements) and len(full_text.split()) < 8)
                or (bool(parser.csr_mount_elements) and parser.has_client_bundle and len(full_text.split()) < 25 and not (h1_headings and any(len(h.strip()) > 0 for h in h1_headings)))
            ),
            "mount_elements": parser.csr_mount_elements,
            "has_client_bundle": parser.has_client_bundle,
            "visible_word_count": len(full_text.split())
        },
        "agentic_readiness": {
            "markdown_alternate_url": parser.markdown_alternate_url,
            "has_pricing_link": parser.has_pricing_link,
            "buttons_count": len(parser.buttons),
            "unnamed_buttons_count": unnamed_buttons_count,
            "unlabelled_inputs_count": unlabelled_inputs_count,
            "fake_buttons_count": fake_buttons_count,
            "interactive_accessibility_score": agentic_a11y_score
        }
    }

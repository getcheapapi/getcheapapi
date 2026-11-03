"""Render site/src/index.html once per language in site/i18n/ into site/public/, plus sitemap.xml.

English is served at /, every other language at /<code>/. Run after editing the template or any string:

    python site/build.py
"""

import json
import re
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent
ORIGIN = "https://getcheapapi.com"
HOLE = re.compile(r"\{\{(\w+)\}\}")


def load_langs():
    langs = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((SITE / "i18n").glob("*.json"))}
    order = ["en"] + [c for c in langs if c != "en"]
    return [(c, langs[c]) for c in order]


def path_of(code):
    return "/" if code == "en" else f"/{code}/"


def check(langs, template):
    en = langs[0][1]
    wanted = set(HOLE.findall(template))
    problems = []
    for code, strings in langs:
        for key in en:
            if key not in strings:
                problems.append(f"{code}: missing {key}")
        for key, value in strings.items():
            if '"' in value:
                problems.append(f'{code}.{key}: use typographic quotes, not "')
    generated = {"html_lang", "url", "og_locale", "hreflang", "lang_menu", "lang_links"}
    for key in wanted - generated - set(en):
        problems.append(f"template uses {{{{{key}}}}}, which en.json does not define")
    return problems


def render(template, langs, code, strings):
    links = [(c, s, path_of(c)) for c, s in langs]
    hreflang = [f'    <link rel="alternate" hreflang="{s["_hreflang"]}" href="{ORIGIN}{p}" />' for c, s, p in links]
    hreflang.append(f'    <link rel="alternate" hreflang="x-default" href="{ORIGIN}/" />')

    def anchors(indent):
        return "\n".join(
            f'{indent}<a href="{p}" lang="{s["_hreflang"]}" hreflang="{s["_hreflang"]}"'
            + (' aria-current="page"' if c == code else "")
            + f'>{s["_name"]}</a>'
            for c, s, p in links
        )

    values = dict(
        strings,
        html_lang=strings["_hreflang"],
        url=ORIGIN + path_of(code),
        og_locale=strings["_og_locale"],
        hreflang="\n".join(hreflang),
        lang_menu=anchors("              "),
        lang_links=anchors("            "),
    )
    return HOLE.sub(lambda m: values[m.group(1)], template)


def sitemap(langs):
    alternates = "\n".join(
        f'    <xhtml:link rel="alternate" hreflang="{s["_hreflang"]}" href="{ORIGIN}{path_of(c)}" />' for c, s in langs
    )
    urls = "\n".join(f"  <url>\n    <loc>{ORIGIN}{path_of(c)}</loc>\n{alternates}\n  </url>" for c, _ in langs)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        f"{urls}\n</urlset>\n"
    )


def main():
    template = (SITE / "src" / "index.html").read_text(encoding="utf-8")
    langs = load_langs()
    problems = check(langs, template)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    public = SITE / "public"
    for code, strings in langs:
        out = public / "index.html" if code == "en" else public / code / "index.html"
        out.parent.mkdir(exist_ok=True)
        out.write_text(render(template, langs, code, strings), encoding="utf-8", newline="\n")
    (public / "sitemap.xml").write_text(sitemap(langs), encoding="utf-8", newline="\n")
    print(f"built {len(langs)} languages: {', '.join(c for c, _ in langs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

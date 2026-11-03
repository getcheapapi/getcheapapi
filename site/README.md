# getcheapapi.com

The project's one-page website. Static files in `public/`, served by Workers static assets; no Worker code, no secrets.

- `src/index.html`: the page template, with `{{key}}` holes for every translatable string.
- `i18n/<code>.json`: one file per language (en, es, ja, ko, pt, zh). English is served at `/`, the rest at `/<code>/`.
- `build.py`: renders the template into `public/index.html` and `public/<code>/index.html`, with hreflang links, the language menu and `sitemap.xml`. It refuses to build if a language is missing a key. The generated pages are committed, so deploy needs no build step.
- `public/site.css`, `public/site.js`: shared by every language. The ASCII figures are drawn on `<canvas>` from the product's own words.
- `public/robots.txt`, `llms.txt`, `404.html`, `og.png`: SEO and sharing (English only).

```bash
python site/build.py      # after editing src/index.html or any i18n file
cd site && npm install
npm run dev               # http://localhost:6191
npm run deploy            # production, needs confirmation
```

To add a language, copy `i18n/en.json` to `i18n/<code>.json`, translate it (titles with the local search terms, not a literal translation), and run the build. Every number on the page comes from the README; keep them in sync when prices or capabilities change.

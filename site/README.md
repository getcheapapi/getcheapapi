# getcheapapi.com

The project's one-page website: a Vite multi-page build in `dist/`, served by Workers static assets. No Worker code, no secrets.

- `src/page.html`: the page template, with `{{key}}` holes for every translatable string.
- `i18n/<code>.json`: one file per language (en, es, ja, ko, pt, zh). English is served at `/`, the rest at `/<code>/`.
- `vite.config.js`: renders the template once per language (hreflang links, language menu), hands the pages to Vite, and emits `sitemap.xml`. It refuses to build if a language is missing a key. The rendered `index.html` and `<code>/index.html` are build output, not committed.
- `src/site.css`, `src/site.js`: shared by every language; Vite hashes and minifies them. The ASCII figures are drawn on `<canvas>` from the product's own words.
- `public/`: copied as is (favicon, `og.png`, `robots.txt`, `llms.txt`). `404.html` is English only.

```bash
cd site && npm install
npm run dev       # http://localhost:6191, reloads on template and i18n edits
npm run build     # dist/
npm run deploy    # build + wrangler deploy, production, needs confirmation
```

To add a language, copy `i18n/en.json` to `i18n/<code>.json` and translate it (titles with the local search terms, not a literal translation). Every number on the page comes from the README; keep them in sync when prices or capabilities change.

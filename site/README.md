# getcheapapi.com

The project's one-page website. Static files in `public/`, served by Workers static assets; no Worker code, no secrets.

- `index.html`, `site.css`, `site.js`: the page. The ASCII figures are drawn on `<canvas>` by `site.js` from the product's own words.
- `robots.txt`, `sitemap.xml`, `llms.txt`, `404.html`, `og.png`: SEO and sharing.

```bash
cd site && npm install
npm run dev       # http://localhost:6191
npm run deploy    # production, needs confirmation
```

Every number on the page comes from the README; keep them in sync when prices or capabilities change.

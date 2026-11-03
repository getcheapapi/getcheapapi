// Renders src/page.html once per language in i18n/ (English at /, the rest at /<code>/), then lets Vite
// build them like any multi-page site. The rendered HTML files are build output and are not committed.
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

const SITE = dirname(fileURLToPath(import.meta.url));
const TEMPLATE = join(SITE, 'src', 'page.html');
const I18N = join(SITE, 'i18n');
const ORIGIN = 'https://getcheapapi.com';
const HOLE = /\{\{(\w+)\}\}/g;

const pathOf = (code) => (code === 'en' ? '/' : `/${code}/`);
const fileOf = (code) => (code === 'en' ? join(SITE, 'index.html') : join(SITE, code, 'index.html'));

function loadLangs() {
  const langs = readdirSync(I18N)
    .filter((f) => f.endsWith('.json'))
    .map((f) => [f.slice(0, -5), JSON.parse(readFileSync(join(I18N, f), 'utf8'))]);
  return [...langs.filter(([c]) => c === 'en'), ...langs.filter(([c]) => c !== 'en')];
}

function check(langs, template) {
  const en = langs[0][1];
  const generated = new Set(['html_lang', 'url', 'og_locale', 'hreflang', 'lang_menu', 'lang_links']);
  const problems = [];
  for (const [code, strings] of langs) {
    for (const key of Object.keys(en)) if (!(key in strings)) problems.push(`${code}: missing ${key}`);
    for (const [key, value] of Object.entries(strings)) {
      if (value.includes('"')) problems.push(`${code}.${key}: use typographic quotes, not "`);
    }
  }
  for (const [, key] of template.matchAll(HOLE)) {
    if (!generated.has(key) && !(key in en)) problems.push(`template uses {{${key}}}, which en.json does not define`);
  }
  if (problems.length) throw new Error(`i18n:\n${problems.join('\n')}`);
}

function render(template, langs, code, strings) {
  const hreflang = langs.map(([c, s]) => `    <link rel="alternate" hreflang="${s._hreflang}" href="${ORIGIN}${pathOf(c)}" />`);
  hreflang.push(`    <link rel="alternate" hreflang="x-default" href="${ORIGIN}/" />`);
  const anchors = (indent) =>
    langs
      .map(([c, s]) => `${indent}<a href="${pathOf(c)}" lang="${s._hreflang}" hreflang="${s._hreflang}"${c === code ? ' aria-current="page"' : ''}>${s._name}</a>`)
      .join('\n');
  const values = {
    ...strings,
    html_lang: strings._hreflang,
    url: ORIGIN + pathOf(code),
    og_locale: strings._og_locale,
    hreflang: hreflang.join('\n'),
    lang_menu: anchors('              '),
    lang_links: anchors('            '),
  };
  return template.replace(HOLE, (_, key) => values[key]);
}

function writePages() {
  const template = readFileSync(TEMPLATE, 'utf8');
  const langs = loadLangs();
  check(langs, template);
  for (const [code, strings] of langs) {
    const file = fileOf(code);
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, render(template, langs, code, strings));
  }
  return langs;
}

// Pages kept as plain HTML in their own folder: /<slug>/ in English, /<code>/<slug>/ once translated.
const PAGES = ['serp-api-pricing', 'twitter-api-pricing', 'reddit-api-pricing'];
const pageFile = (code, slug) => join(SITE, code === 'en' ? '' : code, slug, 'index.html');
const pageFiles = (langs) => langs.flatMap(([c]) => PAGES.map((p) => pageFile(c, p))).filter(existsSync);

// Internal links are always written as the English path (/serp-api-pricing/). On a page in another
// language each one points at that language's copy, or is marked hreflang="en" while there is none.
// Anchors that already declare hreflang (the language menu) target a language on purpose and stay as is.
function localize(html, code) {
  if (code === 'en') return html;
  return html.replace(/<a\b[^>]*>/g, (tag) => {
    if (/\shreflang=/.test(tag)) return tag;
    return tag.replace(/\shref="(\/[^"#?]*\/|\/)([#?][^"]*)?"/, (attr, path, rest = '') =>
      existsSync(pageFile(code, path.slice(1, -1))) ? ` href="/${code}${path}${rest}"` : `${attr} hreflang="en"`,
    );
  });
}

function sitemap(langs) {
  const alternates = langs
    .map(([c, s]) => `    <xhtml:link rel="alternate" hreflang="${s._hreflang}" href="${ORIGIN}${pathOf(c)}" />`)
    .join('\n');
  const urls = [
    ...langs.map(([c]) => `  <url>\n    <loc>${ORIGIN}${pathOf(c)}</loc>\n${alternates}\n  </url>`),
    ...pageFiles(langs).map((f) => `  <url>\n    <loc>${ORIGIN}/${relative(SITE, dirname(f)).split(sep).join('/')}/</loc>\n  </url>`),
  ].join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n${urls}\n</urlset>\n`;
}

export default defineConfig(() => {
  const langs = writePages();
  return {
    root: SITE,
    appType: 'mpa',
    server: { host: '127.0.0.1', port: 6191, strictPort: true },
    preview: { host: '127.0.0.1', port: 6191 },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      rollupOptions: { input: [...langs.map(([c]) => fileOf(c)), ...pageFiles(langs), join(SITE, '404.html')] },
    },
    plugins: [
      {
        name: 'i18n-pages',
        transformIndexHtml(html, ctx) {
          const first = relative(SITE, ctx.filename).split(sep)[0];
          return localize(html, langs.some(([c]) => c === first) ? first : 'en');
        },
        configureServer(server) {
          server.watcher.add([TEMPLATE, I18N]);
          server.watcher.on('change', (file) => {
            if (file !== TEMPLATE && !file.startsWith(I18N)) return;
            try {
              writePages();
              server.ws.send({ type: 'full-reload' });
            } catch (err) {
              server.config.logger.error(err.message);
            }
          });
        },
        generateBundle() {
          this.emitFile({ type: 'asset', fileName: 'sitemap.xml', source: sitemap(langs) });
        },
      },
    ],
  };
});

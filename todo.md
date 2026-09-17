# SEO/GEO Skill Improvement Roadmap

Repository: `Ezhuk1/ultimate-seo-geo`

## Цель

Превратить текущий сильный page-level SEO/GEO-аудитор в полноценную production-систему для аудита сайтов, индексации, контента, Schema.org и AI visibility.

## Приоритеты

- **P0:** корректность аудита и scoring; устранение ложных PASS/FAIL и завышенных оценок.
- **P0:** полноценная indexability-модель.
- **P1:** site-level crawling, internal linking и архитектура сайта.
- **P1:** content quality, E-E-A-T и topical authority.
- **P1:** воспроизводимая GEO-оценка.
- **P2:** производительность, CLI, CI/CD и документация.

---

# Неделя 1 — Исправление фундамента

## 1. Унифицировать scoring

Перенести параметры правил из hardcoded-логики `engine/scoring.py` в `rules/*.json`:

```json
{
  "id": "TECH-TITLE-003",
  "category": "technical",
  "severity": "WARNING",
  "impact": "P1",
  "score_weight": 5,
  "confidence_type": "heuristic",
  "unknown_policy": "exclude"
}
```

Единый pipeline:

```text
rule result -> status -> confidence -> severity -> weight -> score contribution
```

**Критерий готовности:** изменение веса правила выполняется в JSON, а не через специальные условия по `rule_id` в Python.

## 2. Переделать observation coverage

Вместо зависимости от числа зарегистрированных signals ввести отдельные показатели:

- `criteria_total`
- `criteria_observed`
- `criteria_passed`
- `criteria_failed`
- `criteria_unknown`

Формула:

```text
coverage = observed_criteria / total_criteria * 100
```

Считать coverage отдельно для technical SEO, indexability, performance, schema, GEO, content и site architecture.

## 3. Разделить статусы

Добавить:

```python
STATUS_UNKNOWN = "UNKNOWN"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
```

Примеры:

- CrUX API не подключён — `UNKNOWN`.
- На странице нет изображений — `NOT_APPLICABLE`.
- Sitemap не найдена — `UNKNOWN` или `WARNING` в зависимости от типа сайта.
- Намеренный `noindex` — `NOT_APPLICABLE` для непубличной страницы.

## 4. Расширить тесты

Добавить positive, negative, edge-case и `UNKNOWN` fixtures для:

- нескольких canonical;
- canonical в `<body>`;
- относительного canonical;
- canonical с query string и fragment;
- scoped `noindex` в meta и `X-Robots-Tag`;
- сложных robots.txt-групп;
- `Allow`/`Disallow` одинаковой длины;
- пустого CSR shell;
- WAF challenge;
- HTML без `<main>`;
- страницы без текста, но с валидной схемой.

---

# Неделя 2 — Полноценный технический SEO-аудит

## 5. Добавить indexability matrix

Для каждой страницы показывать:

| Сигнал | Значение |
|---|---|
| HTTP status | 200 |
| Canonical | self / other / missing |
| Meta robots | index / noindex |
| X-Robots-Tag | index / noindex |
| Robots.txt | allowed / blocked |
| Sitemap | included / missing |
| Internal links | linked / orphan candidate |
| Rendered content | present / missing |
| Indexability verdict | indexable / blocked / ambiguous |

Итоговый verdict должен учитывать все сигналы, а не только один флаг.

## 6. Расширить canonical consistency

Проверять:

- canonical совпадает с final URL;
- canonical не ведёт на redirect;
- canonical возвращает 200;
- canonical не имеет `noindex`;
- canonical разрешён robots.txt;
- canonical входит в sitemap;
- hostname входит в допустимый список доменов;
- trailing slash policy;
- query parameter normalization;
- HTTP/HTTPS и www/non-www consistency.

## 7. Добавить HTTP и security signals

Проверять:

- `Content-Type` и charset;
- compression;
- cache headers;
- HSTS;
- mixed content;
- redirect loop;
- soft 404;
- suspicious 200 error pages;
- `X-Robots-Tag`;
- `Content-Language`;
- `Last-Modified` и `ETag`.

Security hygiene выводить отдельным score, не смешивая автоматически с SEO score.

## 8. Расширить sitemap audit

Добавить:

- sitemap index и все дочерние sitemap;
- лимит 50 000 URL;
- duplicate и normalized duplicate URLs;
- URL с redirect, 4xx/5xx и noindex;
- URL, заблокированные robots.txt;
- stale и invalid `lastmod`;
- cross-domain URLs;
- расхождения sitemap и canonical.

Для больших sitemap использовать streaming-парсинг.

## 9. Расширить HTML и semantic structure

Проверять:

- `<main>`, `<nav>`, `<header>`, `<footer>`;
- heading hierarchy и empty headings;
- hidden text;
- duplicate visible content;
- формы без labels;
- ссылки без anchor text;
- hreflang и `rel=alternate`;
- pagination signals;
- print/mobile/AMP alternates.

---

# Неделя 3 — Site-level SEO и контент

## 10. Добавить crawler mode

Пример CLI:

```bash
python -m engine.inspector https://example.com \\
  --crawl \\
  --max-pages 100 \\
  --depth 3 \\
  --format json
```

Минимальный pipeline:

```text
seed URL -> normalize -> check robots -> fetch -> parse links -> enqueue -> aggregate
```

Обязательные ограничения:

- rate limit;
- max pages/depth;
- domain restriction;
- robots enforcement;
- canonical deduplication;
- timeout и retry policy;
- SSRF protection;
- maximum response size;
- content-type validation.

## 11. Добавить internal linking и crawl depth

Показывать:

- crawl depth;
- orphan page candidates;
- страницы без внутренних ссылок;
- важные страницы глубже 3–4 кликов;
- ссылки на redirects, 404 и noindex;
- navigation consistency;
- contextual links;
- anchor text diversity.

## 12. Добавить duplicate content и URL normalization

Проверять:

- duplicate title, H1 и meta description;
- near-duplicate body text;
- canonical clusters;
- URL parameter clusters;
- pagination duplicates;
- language duplicates;
- thin pages;
- soft duplicates.

Можно начать с stdlib-реализации shingling, Jaccard similarity и SimHash.

## 13. Расширить content quality layer

Проверять:

- search intent match;
- topical completeness;
- entity coverage;
- unique value;
- evidence presence;
- source attribution;
- freshness;
- author/reviewer;
- editorial date;
- commercial intent;
- unsupported claims;
- generic language;
- answer completeness.

Каждую эвристику сопровождать наблюдаемым доказательством.

---

# Неделя 4 — GEO, E-E-A-T, интеграции и production

## 14. Улучшить GEO scoring

Рекомендуемые компоненты:

| Компонент | Вес |
|---|---:|
| Answerability | 20 |
| Evidence density | 20 |
| Entity clarity | 15 |
| Passage extractability | 15 |
| Source attribution | 10 |
| Schema/entity graph | 10 |
| Freshness | 5 |
| AI crawler access | 5 |

Показывать score вместе с confidence и покрытием:

```text
GEO Readiness: 68/100
Confidence: MEDIUM
Measured: 4/8 dimensions
Unknown: freshness, external citations, brand footprint
```

## 15. Добавить E-E-A-T и trust layer

Проверять:

- author и author bio;
- author `sameAs`;
- organization;
- editorial policy;
- contact information;
- sources и references;
- review date;
- fact-checking signals;
- disclaimers для YMYL;
- markers of first-hand experience;
- product/service transparency.

Не считать страницу E-E-A-T compliant только из-за наличия `Person` в Schema.org.

## 16. Добавить freshness и change detection

Проверять:

- `datePublished` и `dateModified`;
- sitemap `lastmod`;
- HTTP `Last-Modified`;
- content hash;
- historical comparison;
- stale content;
- mismatch между visible date, schema date и sitemap date.

Сохранять предыдущие аудиты и score delta.

## 17. Усилить Schema validator

Добавить:

- JSON-LD MIME и script type;
- invalid context;
- duplicate `@id`;
- orphan entities;
- invalid `sameAs`;
- missing `url`;
- mismatch с visible content;
- unsupported claims в Product/Review/FAQ;
- aggregate rating abuse;
- price/availability consistency;
- suitability schema type;
- required/recommended properties.

Разделять:

```text
Syntax valid: YES
Schema.org structure: PARTIAL
Google rich result eligibility: UNKNOWN
Visible-content consistency: FAIL
```

## 18. Разделить AI crawler governance

Выделить три политики:

```text
SEARCH RETRIEVAL
MODEL TRAINING
USER-INITIATED FETCH
```

Всегда уточнять: разрешение crawler access не гарантирует индексацию, retrieval или цитирование.

## 19. Улучшить CLI, JSON и CI

Добавить опции:

```bash
--strict
--fail-on P0
--fail-on-score 70
--crawl
--user-agent Googlebot
--user-agent OAI-SearchBot
--rendered-html path.html
--previous-audit audit.json
--sarif
```

Поддержать Markdown, JSON, SARIF и CSV, а также GitHub Actions annotations.

## 20. Обновить документацию и claims

Маркировать утверждения как:

```text
[STANDARD]
[DOCUMENTED]
[RESEARCH]
[HEURISTIC]
[EXPERIMENTAL]
[UNKNOWN]
```

Избегать категоричных утверждений о гарантированной AI-видимости. Использовать формулировки “может повысить вероятность”, “создаёт риск” и “в benchmark наблюдалась корреляция”.

---

# Рекомендуемые релизы

## Версия 2.2 — Reliability

- scoring и coverage;
- indexability matrix;
- canonical consistency;
- schema consistency;
- расширенные тесты.

## Версия 2.3 — Site Audit

- crawler mode;
- internal linking;
- crawl depth;
- orphan pages;
- duplicate content;
- sitemap-scale analysis.

## Версия 3.0 — SEO/GEO Intelligence Platform

- E-E-A-T;
- topical authority;
- freshness;
- historical comparisons;
- GEO measurement;
- SARIF/CI;
- configurable rule packs;
- external data providers.

---

# Топ-10 задач при ограниченных ресурсах

1. Убрать hardcoded rule exceptions из scoring.
2. Переделать coverage на coverage критериев.
3. Добавить indexability matrix.
4. Проверять canonical против final URL и HTTP-статуса.
5. Добавить hreflang и language clusters.
6. Реализовать безопасный crawl mode.
7. Добавить internal links, orphan pages и crawl depth.
8. Добавить duplicate/thin content detection.
9. Расширить schema validator до visible-content consistency.
10. Разделить standards, research и heuristics в `SKILL.md` и README.

## Целевая архитектура

```text
Page Audit
   +
Indexability Audit
   +
Site Crawl
   +
Content Quality
   +
Entity & Schema Graph
   +
AI Crawler Governance
   +
GEO Readiness
   +
Historical Monitoring
   +
CI/CD Enforcement
```

## Release gate

### Функциональность

- [ ] URL audit
- [ ] local HTML audit
- [ ] schema validation
- [ ] robots simulator
- [ ] sitemap parsing
- [ ] crawl mode
- [ ] JSON, Markdown и SARIF output
- [ ] CI exit codes

### Корректность

- [ ] Unknown не уменьшает score
- [ ] Not applicable не считается ошибкой
- [ ] Score не завышается при неполном coverage
- [ ] canonical проверяется против final URL
- [ ] sitemap сверяется с HTTP/indexability
- [ ] noindex проверяется в meta и headers
- [ ] robots policy разделяет search/training/fetch

### SEO-покрытие

- [ ] indexability matrix
- [ ] redirects
- [ ] sitemap
- [ ] canonical
- [ ] hreflang
- [ ] internal links
- [ ] orphan pages
- [ ] duplicate content
- [ ] thin content
- [ ] structured data
- [ ] author/trust signals
- [ ] freshness
- [ ] Core Web Vitals integration

### Безопасность

- [ ] SSRF protection
- [ ] response size limit
- [ ] domain restriction
- [ ] crawl rate limit
- [ ] robots enforcement
- [ ] redirect limit
- [ ] безопасный local file access
- [ ] безопасный parsing malformed HTML/XML/JSON

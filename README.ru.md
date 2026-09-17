# 🚀 Ultimate SEO & GEO All-In-One (`ultimate-seo-geo`)

[![Версия: 2.1.0](https://img.shields.io/badge/Версия-2.1.0-blue.svg)](evals/CHANGELOG.md)
[![Лицензия: MIT](https://img.shields.io/badge/Лицензия-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B%20%7C%20Zero--Dep-success.svg)](engine/)
[![Стандарт: AgentSkills](https://img.shields.io/badge/AgentSkills-1.0-emerald.svg)](SKILL.md)
[![Язык](https://img.shields.io/badge/Язык-Русский%20%7C%20English-purple.svg)](#язык--language)

> **Эталонная production-grade система поисковой оптимизации (SEO) и оптимизации под генеративный ИИ (GEO/AEO) для ИИ-агентов и CLI.**  
> Объединяет **автономный детерминированный движок инспекции** (чистый Python stdlib, <50 мс) и **доказательного ИИ-агента**. Проводит технический аудит SEO, выявляет невидимость Client-Side Rendering (CSR) для роботов, максимизирует вероятность цитирования в генеративных ответах (ChatGPT Search, Perplexity AI, Claude, Gemini, Google AI Overviews), валидирует AST связного Schema.org `@graph`, настраивает защищенные протоколы обхода (`robots.txt` и `llms.txt`) и строит контент-планы на основе реальных фактов.

---

### Язык / Language
* 🇷🇺 **Русский** (Вы здесь)
* 🇬🇧 **[English Version](README.md)**

---

## 💡 Архитектура: Двухэтапная модель поиска и генерации

Современный AI-поиск функционирует в **два взаимосвязанных этапа**:

```
                       ┌─────────────────────────────────────────────────────────┐
                       │                       ЦЕЛЕВОЙ URL                       │
                       └────────────────────────────┬────────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ЭТАП 1: ОТБОР КАНДИДАТОВ (Классическое техническое SEO / Retrieval)                                             │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ • Доступность и индексируемость (RFC 9309 robots.txt, HTTP 200, чистые редиректы)                                │
│ • Каноникализация (RFC 6596) и иерархия документа (единственный H1, семантические H2-H6)                        │
│ • Server-Side Rendering (SSR/SSG): Детекция пустых CSR-оболочек (div#root), ослепляющих быстрые AI-краулеры     │
│ • Авторитет домена, PageRank и фиксация сущности бренда (Wikipedia, Wikidata, YouTube, Reddit)                  │
│ ──► Результат: Попадание в пул кандидатов (Google Top-5 или контекстное окно Perplexity)                        │
└───────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ЭТАП 2: ГЕНЕРАТИВНЫЙ СИНТЕЗ (Оптимизация под генеративные движки / GEO)                                         │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ • Экспоненциальное затухание веса цитат (Метрика PAWC): Прямой ответ вынесен в первые 60 слов                   │
│ • Эмпирический прирост цитирования (Princeton KDD 2024): Прямые цитаты экспертов (+41%), статистика (+30%)     │
│ • Извлекаемость для RAG: Адаптивный чанкинг (~100-200 слов) и независимость местоимений (явные сущности)       │
│ • Knowledge Graph: Связный Schema.org @graph с датами ISO 8601 и взаимными ссылками @id                         │
│ ──► Результат: ИИ предпочитает цитировать, упоминать и рекомендовать именно ваш контент в финальном ответе      │
└───────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                                    │
                                                    ▼
                       ┌─────────────────────────────────────────────────────────┐
                       │             ОТЧЕТ EVIDENCE LEDGER И СКОРИНГ             │
                       │     (Observable Score 0-100, Coverage %, GEO Index)     │
                       └─────────────────────────────────────────────────────────┘
```

### Научный фундамент:
1. **Эффект демократизации (Princeton KDD 2024, Table 2):** В пуле кандидатов (Google Top-5) сайты на 5-й позиции с оптимизацией доказательной плотности (*Cite Sources*) получили **+115.1% видимости в ответах ИИ**, в то время как 1-я позиция просела на **-30.3%**. Качественные доказательства побеждают позиции традиционной выдачи.
2. **Экспоненциальное затухание веса цитат (Метрика PAWC):**  
   $$\text{PAWC}(c, q) = \sum_{s \in S_c} \frac{|s|}{L_r} \cdot e^{-\alpha \cdot \frac{\text{pos}(s)}{N_r}}$$  
   Вес цитирования предложений падает экспоненциально ($\sim 2.7\times$ при $\alpha = 1.0$) по мере удаления от начала *синтезированного ответа модели*. Размещение определений в первых предложениях абзаца гарантирует попадание на первые позиции ответа ($\text{pos}(s)=0$).
3. **Инвариант «Unknown $\ne$ Failure»:** Неизмеренные сигналы (полевые данные CrUX без API-ключа, логи сервера) помечаются как `UNKNOWN` с **0 штрафом** и изолируются от подтвержденных дефектов.

---

## 🖥️ Автономный консольный движок CLI (`engine/`)

Встроенный детерминированный движок не требует **никаких сторонних pip-зависимостей** (написан исключительно на стандартной библиотеке Python 3.10+). Скорость выполнения составляет **<15 мс для локальных файлов и in-memory AST-парсинга** (без сетевых задержек) и **<500 мс для полного аудита живого сайта** (включая HTTP-запросы, TLS-рукопожатие и анализ robots/sitemap):

```bash
# 1. Аудит живого сайта с симуляцией AI-краулеров и детекцией CSR-пустышек
python -m engine.inspector https://example.com

# 2. Аудит локального HTML-файла или артефакта сборки
python -m engine.inspector path/to/page.html

# 3. Валидация сгенерированной разметки Schema.org JSON-LD перед деплоем
python -m engine.inspector --validate-schema path/to/schema.json

# 4. Валидация Schema.org через конвейер (stdin) в CI/CD
cat schema.json | python -m engine.inspector --validate-schema

# 5. Экспорт в машиночитаемый JSON с полным Evidence Ledger и SHA-256
python -m engine.inspector https://example.com --format json --output audit.json

# 6. Проверка правил краулинга с кастомным файлом robots.txt
python -m engine.inspector https://example.com --robots path/to/custom-robots.txt
```

### Возможности движка
- **Детекция пустых CSR-оболочек (`TECH-CSR-SHELL-008`):** Распознает пустые контейнеры (`div#root`, `div#app`, `div#__next`) без серверного HTML. Поисковые AI-боты (`GPTBot`, `ClaudeBot`, `PerplexityBot`, `CCBot`) не выполняют JS; пустые CSR-страницы полностью выпадают из AI-поиска.
- **Автономный валидатор Schema.org AST (`--validate-schema`):** Pre-flight проверка сниппетов на битые ссылки `@id` (`SCHEMA-BROKEN-REF-005`), стандарты дат ISO 8601 (`SCHEMA-DATE-FORMAT-006`) и форматы цен (`SCHEMA-PRICE-FORMAT-003`).
- **Симулятор доступа по RFC 9309:** Полный AST-парсер с поддержкой группировок User-agent, подстановок `*` и `$`, правила максимального совпадения (longest-match) и приоритета Allow для `GPTBot`, `ClaudeBot`, `PerplexityBot`, `Google-Extended`.
- **4-уровневый протокол Evidence Ledger:** Конвейер `RAW` $\to$ `SIGNAL` $\to$ `EVIDENCE` $\to$ `FINDING` с фиксацией хэша прослеживаемости SHA-256.
- **Анализатор контента и готовности к GEO:** Детекция прямого ответа в первом блоке, выявление «воды», анализ длины чанков и независимости местоимений (coreference).

---

## ⚡ 5 режимов работы ИИ-агента

При использовании в качестве AI Agent Skill (в Antigravity, Claude Code, Cursor, Codex) система маршрутизирует запросы по 5 специализированным режимам:

| Режим | Триггеры | Результат работы |
|---|---|---|
| **1. `audit`** | `аудит сайта`, `проверь SEO`, `посчитай GEO score`, `почему упал трафик` | Детерминированный CLI-аудит, таблица Evidence Ledger, Observable Technical Score (0–100), Observation Coverage % и GEO Readiness Index (0–100) с планом P0/P1/P2. |
| **2. `optimize`** | `перепиши для ИИ`, `сделай цитируемым в ChatGPT`, `PAWC`, `вынеси ответ вперед` | Превращение рекламной «воды» в высокоцитируемые пассажи по шаблонам Princeton KDD 2024. |
| **3. `schema`** | `создай JSON-LD`, `добавь микроразметку`, `rich snippets`, `FAQ схема`, `HowTo` | Генерация валидного связного `@graph` JSON-LD (WebSite, WebPage, Service, Product, FAQ, HowTo) с предварительной проверкой через `--validate-schema`. |
| **4. `ai-files`** | `настрой llms.txt`, `исправь robots.txt для AI`, `разреши GPTBot` | Безопасный `robots.txt` с разрешением для AI-поисковиков и защитой приватных маршрутов + структурированный манифест `llms.txt`. |
| **5. `strategy`** | `контент-план для AI`, `карта тематического авторитета`, `запросы для Perplexity` | Тематические кластеры для захвата поисковых запросов в Perplexity и ChatGPT. |

*(Внутренний режим `safety_check` обеспечивает безусловный отказ от генерации вымышленных фактов, метрик и фейковых отзывов).*

---

## 📚 Строгий JIT-режим чтения справочников

Для предотвращения раздувания контекстного окна (40 000+ токенов) и защиты от эффекта **«Lost in the middle»**, `SKILL.md` предписывает строгое селективное чтение справочников:

| Активный режим | Какой документ читает агент | Содержание документа |
|---|---|---|
| **`audit`** | `references/technical-seo-checklist.md` + `references/geo-framework.md` | *Примечание:* При вызове CLI-инспектора справочники в контекст не загружаются вовсе! |
| **`optimize`** | `references/geo-framework.md` | Таблица прироста KDD 2024, формула PAWC, эвристики чанкинга |
| **`schema`** | `references/schema-templates.md` | Мастер-шаблоны графа `@graph` (WebSite, WebPage, Service, FAQ, HowTo) |
| **`ai-files`** | `references/ai-crawler-spec.md` | Спецификации роботов RFC 9309, защита от утечек данных, стандарт `llms.txt` |
| **`strategy`** | `references/content-strategy-ai.md` | Принцип Information Gain, карта интентов, правила цитирования источников |

> **Правило изоляции:** Одновременная загрузка нерелевантных справочников строго запрещена.

---

## 🛡️ Безопасный шаблон `robots.txt` (RFC 9309)

По стандарту **RFC 9309** специализированные группы User-Agent переопределяют общую группу `*`. Если открыть доступ AI-ботам через `Allow: /` без дублирования запретов, приватные разделы окажутся в открытом доступе для индексации:

```txt
# Стандартные поисковые краулеры
User-agent: *
Allow: /
Disallow: /api/
Disallow: /admin/
Disallow: /private/
Disallow: /checkout/
Disallow: /auth/

# AI-краулеры с дублированием запретов по RFC 9309
User-agent: GPTBot
User-agent: ChatGPT-User
User-agent: OAI-SearchBot
User-agent: ClaudeBot
User-agent: Claude-SearchBot
User-agent: Claude-User
User-agent: PerplexityBot
User-agent: Perplexity-User
User-agent: meta-externalagent
User-agent: meta-externalfetcher
User-agent: cohere-ai
# Примечание: Google-Extended и Applebot-Extended управляют обучением моделей, а не поиском.
# Запрещайте их ("Disallow: /") только если хотите запретить обучение моделей на вашем контенте.
Allow: /
Disallow: /api/
Disallow: /admin/
Disallow: /private/
Disallow: /checkout/
Disallow: /auth/

Sitemap: https://[YOUR_DOMAIN]/sitemap.xml
```

---

## 📊 Научные основы и иерархия доказательств

Эмпирический рейтинг техник по приросту цитируемости ([Princeton / Georgia Tech KDD 2024, arXiv:2311.09735](https://arxiv.org/abs/2311.09735)):

```
┌──────────────────────────────────────────────────────────────┐
│  ТЕХНИКА ОПТИМИЗАЦИИ                ПРИРОСТ ЦИТАТ (PAWC)     │
├──────────────────────────────────────────────────────────────┤
│  1. Прямые цитаты экспертов (≥2)    +41%  ██████████████████ │
│  2. Добавление точной статистики    +30%  █████████████      │
│  3. Ссылки на первоисточники        +28%  ████████████       │
│  4. Прямые ответы и ясность языка   +28%  ████████████       │
│  5. Точные технические сущности     +18%  ████████           │
│  6. Структурированность подачи      +14%  ██████             │
│  7. Авторитетный тон                +10%  ████               │
│  8. Уникальный словарный запас       +6%  ██                 │
│  9. Переспам ключевыми словами      -8%   ▼ ШТРАФУЕТСЯ       │
└──────────────────────────────────────────────────────────────┘
```

### 6 уровней эпистемической иерархии
- **Tier A:** Официальные протоколы и стандарты (RFC 9309, RFC 6596, Schema.org W3C).
- **Tier B:** Рецензируемые академические исследования (Princeton KDD 2024).
- **Tier C:** Крупномасштабные отраслевые датасеты (Ahrefs 75k доменов, CrUX).
- **Tier D:** Воспроизводимые контролируемые эксперименты (A/B тесты, абляции).
- **Tier E:** Инженерные эвристики практиков (чанки ~100-200 слов, прямой ответ, независимость местоимений).
- **Tier F:** Рабочие гипотезы и наблюдения за отдельными апдейтами.

---

## 🛠️ Установка и подключение

### Вариант А: Глобальная установка в Google Antigravity
```bash
# Windows PowerShell (Antigravity 2.0 / текущий AGY)
git clone https://github.com/Ezhuk1/ultimate-seo-geo.git "$env:USERPROFILE\.gemini\antigravity\skills\ultimate-seo-geo"

# macOS / Linux
git clone https://github.com/Ezhuk1/ultimate-seo-geo.git ~/.gemini/antigravity/skills/ultimate-seo-geo
```

### Вариант Б: Локально для проекта (.agents/skills)
```bash
mkdir -p .agents/skills
git clone https://github.com/Ezhuk1/ultimate-seo-geo.git .agents/skills/ultimate-seo-geo
```

---

## 🧪 Верификация и автотесты

Запуск полного набора тестов и проверок безопасности:
```bash
python evals/run_evals.py
```

Результат:
```text
==================================================
 ultimate-seo-geo Test Runner & Assertion Harness
==================================================
Suite: ultimate-seo-geo-evals (v2.1.0) - 10 test cases

[OK] Schema & reference file integrity: PASS
--- 1. Canonical Fixture Evaluation ---
  [PASS] 10/10 canonical evals passed
--- 2. Negative Mutation & Anti-Regression Suite ---
  [PASS] 9/9 negative mutation guards passed
--- 3. Autonomous Inspection Engine (v2.1.0) Integration Suite ---
  [PASS] test_clean_page_inspection             -> Deterministic assertion passed
  [PASS] test_defective_page_detection          -> Deterministic assertion passed
  [PASS] test_robots_simulator_rfc9309          -> Deterministic assertion passed
  [PASS] test_unknown_signal_invariant          -> Deterministic assertion passed
  [PASS] test_csr_shell_detection               -> Deterministic assertion passed
  [PASS] test_schema_standalone_validator       -> Deterministic assertion passed

[SUCCESS] All evaluation fixtures, assertions, mutation guards, and Engine v2.1.0 tests are healthy.
```

---

## 📁 Структура репозитория

```
ultimate-seo-geo/
├── SKILL.md                          # Главная спецификация скилла, маршрутизация 5 режимов и JIT-правила
├── README.md                         # Документация на английском языке
├── README.ru.md                      # Полная русскоязычная документация (этот файл)
├── LICENSE                           # Открытая лицензия MIT
├── .gitignore                        # Исключения Git (с фильтрами кэша Python)
├── engine/                           # Автономный детерминированный движок (Python stdlib)
│   ├── inspector.py                  # CLI раннер, --validate-schema и генератор Markdown/JSON
│   ├── ledger.py                     # Протокол 4-уровневого Evidence Ledger и хэш SHA-256
│   ├── scoring.py                    # Движок многомерного скоринга и защита инварианта
│   └── analyzers/
│       ├── http_analyzer.py          # Наблюдатель HTTP/HTTPS и локальных файлов
│       ├── html_analyzer.py          # DOM-парсер: canonical, CSR shell, метатеги, H1-H6, ссылки
│       ├── robots_simulator.py       # AST парсер RFC 9309 и симулятор краулеров
│       ├── schema_analyzer.py        # Валидатор Schema.org AST, @graph, дат ISO и битых @id
│       └── content_analyzer.py       # Анализатор прямого ответа, чанков и местоимений
├── rules/                            # Декларативные контракты правил
│   ├── technical_rules.json          # Контракты canonical, robots, CSR shell, title, meta, H1
│   ├── schema_rules.json             # Контракты синтаксиса, графа, битых ссылок, цен и дат
│   └── geo_rules.json                # Контракты прямых ответов, чанкинга, местоимений
├── references/                       # Справочники с динамической подгрузкой Just-In-Time
│   ├── geo-framework.md              # Математика PAWC, KDD 2024, матрица движков
│   ├── technical-seo-checklist.md    # Индексация, Core Web Vitals, метатеги, canonicals
│   ├── schema-templates.md           # Готовые мастер-шаблоны единого @graph JSON-LD
│   ├── ai-crawler-spec.md            # Защита RFC 9309 от утечек и пропозал llms.txt
│   └── content-strategy-ai.md        # Принцип Information Gain, front-loading, сбор доказательств
└── evals/
    ├── evals.json                    # Эвристические и структурные тесты + негативные проверки
    ├── run_evals.py                  # Тестовый харнесс и раннер ассершенов
    ├── test_engine.py                # Интеграционный тестовый набор движка
    └── CHANGELOG.md                  # Полный журнал изменений бенчмарка и движка
```

---

## 🛡️ Лицензия

Проект распространяется под открытой лицензией [MIT License](LICENSE). Разрешено свободное использование в личных, коммерческих и корпоративных проектах.

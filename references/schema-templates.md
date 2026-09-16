# Schema.org JSON-LD Architecture & Templates

This reference provides production-ready, interconnected `@graph` schema templates optimized for AI knowledge extraction (GEO/AEO) and search entity resolution.

## 1. Architectural Rules (The Unified Graph)

> [!IMPORTANT]
> **Never output multiple disconnected `<script type="application/ld+json">` tags.**
> Outputting separate scripts for Organization, Breadcrumbs, and FAQ creates duplicate context overhead and prevents search engines from resolving entity relationships.
> All page entities MUST be unified under a single `@graph` array inside one script tag.

### Entity Relationship Hierarchy:
```
Organization (#organization)
     ▲ publisher
     │
  WebSite (#website)
     ▲ isPartOf
     │
  WebPage (#webpage) ──┬── about ────────────► Service / Product (#service)
                       ├── mainEntity / hasPart ► FAQPage (#faq)
                       ├── hasPart ──────────► HowTo (#howto)
                       └── breadcrumb ────────► BreadcrumbList (#breadcrumbs)
```

> [!NOTE]
> **Google Search Policy on FAQ & HowTo (2023 Deprecations):**
> Google Search deprecated HowTo rich results entirely (September 2023) and restricted FAQ rich snippets to authoritative government and healthcare websites (August 2023).
> Consequently, `HowTo` and `FAQPage` are no longer reliable drivers for Google SERP rich snippets. However, for **GEO (Generative Engine Optimization)** across ChatGPT, Perplexity, Claude, and Gemini, they remain critical: generative models directly parse procedural steps (`HowTo`) and question-answer pairs (`FAQPage`) to assemble cited answers.

---

## 2. Complete Enterprise Unified `@graph` Master Template

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": "https://example.com/#organization",
      "name": "Brand Name",
      "url": "https://example.com",
      "logo": "https://example.com/logo.png",
      "sameAs": [
        "https://github.com/organization",
        "https://x.com/organization",
        "https://linkedin.com/company/organization"
      ],
      "contactPoint": {
        "@type": "ContactPoint",
        "contactType": "customer support",
        "email": "support@example.com",
        "availableLanguage": ["en", "ru"]
      }
    },
    {
      "@type": "Person",
      "@id": "https://example.com/#author",
      "name": "Jane Doe",
      "jobTitle": "Chief Technology Officer & Lead Security Researcher",
      "description": "Network security architect with over 15 years experience in DNS protocols, privacy engineering, and network infrastructure.",
      "sameAs": [
        "https://linkedin.com/in/janedoe",
        "https://github.com/janedoe",
        "https://orcid.org/0000-0002-1825-0097"
      ],
      "worksFor": { "@id": "https://example.com/#organization" }
    },
    {
      "@type": "WebSite",
      "@id": "https://example.com/#website",
      "name": "Brand Name",
      "url": "https://example.com",
      "publisher": { "@id": "https://example.com/#organization" },
      "inLanguage": "en"
    },
    {
      "@type": "WebPage",
      "@id": "https://example.com/#webpage",
      "url": "https://example.com",
      "name": "Brand Homepage Title",
      "isPartOf": { "@id": "https://example.com/#website" },
      "about": { "@id": "https://example.com/#service" },
      "hasPart": [
        { "@id": "https://example.com/#faq" },
        { "@id": "https://example.com/#howto-setup" }
      ],
      "breadcrumb": { "@id": "https://example.com/#breadcrumbs" },
      "author": { "@id": "https://example.com/#author" },
      "datePublished": "[YYYY-MM-DDThh:mm:ssZ]",
      "dateModified": "[YYYY-MM-DDThh:mm:ssZ]",
      "inLanguage": "en"
    },
    {
      "@type": "BreadcrumbList",
      "@id": "https://example.com/#breadcrumbs",
      "itemListElement": [
        {
          "@type": "ListItem",
          "position": 1,
          "name": "Home",
          "item": "https://example.com"
        },
        {
          "@type": "ListItem",
          "position": 2,
          "name": "Setup Guides",
          "item": "https://example.com/setup"
        }
      ]
    },
    {
      "@type": "Service",
      "@id": "https://example.com/#service",
      "name": "Primary Service Name",
      "serviceType": "DNS resolver, Cloud Security",
      "provider": { "@id": "https://example.com/#organization" },
      "url": "https://example.com",
      "isBasedOn": [
        "https://datatracker.ietf.org/doc/html/rfc7858",
        "https://datatracker.ietf.org/doc/html/rfc8484"
      ],
      "offers": {
        "@type": "Offer",
        "price": "0.00",
        "priceCurrency": "USD",
        "priceValidUntil": "[YYYY-12-31]",
        "availability": "https://schema.org/InStock"
      }
    },
    {
      "@type": "FAQPage",
      "@id": "https://example.com/#faq",
      "inLanguage": "en",
      "mainEntity": [
        {
          "@type": "Question",
          "name": "How does this solution prevent speed loss?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "The engine operates at DNS resolution layer without encapsulating packets in a continuous tunnel, maintaining native connection throughput [VERIFY_BEFORE_PUBLISHING: REAL_BENCHMARK_MS]."
          }
        }
      ]
    },
    {
      "@type": "HowTo",
      "@id": "https://example.com/#howto-setup",
      "name": "How to Configure Encrypted DNS on Android",
      "description": "Step-by-step setup guide for DoT configuration.",
      "totalTime": "PT1M",
      "step": [
        {
          "@type": "HowToStep",
          "name": "Open Settings",
          "text": "Navigate to Settings → Network & Internet → Private DNS."
        },
        {
          "@type": "HowToStep",
          "name": "Enter Hostname",
          "text": "Select Private DNS provider hostname and input dns.example.com."
        }
      ]
    }
  ]
}
```

---

## 3. Blog & Thought Leadership Graph (`TechArticle`)

When generating markup for a blog post or technical guide, attach the article to the master graph as follows:

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": "https://example.com/#organization",
      "name": "Brand Name",
      "url": "https://example.com"
    },
    {
      "@type": "WebSite",
      "@id": "https://example.com/#website",
      "url": "https://example.com",
      "publisher": { "@id": "https://example.com/#organization" }
    },
    {
      "@type": "TechArticle",
      "@id": "https://example.com/blog/benchmark-results#article",
      "isPartOf": { "@id": "https://example.com/#website" },
      "headline": "Empirical Benchmark: DNS Resolution Latency in 2026",
      "description": "Comprehensive comparative study of DoT vs DoH across regional ISPs.",
      "datePublished": "[YYYY-MM-DDThh:mm:ssZ]",
      "dateModified": "[YYYY-MM-DDThh:mm:ssZ]",
      "author": {
        "@type": "Person",
        "name": "Alex Mercer",
        "jobTitle": "Lead Network Architect",
        "sameAs": [
          "https://linkedin.com/in/alex-mercer",
          "https://github.com/alex-mercer",
          "https://orcid.org/0000-0002-1825-0097"
        ]
      },
      "publisher": { "@id": "https://example.com/#organization" },
      "mainEntityOfPage": "https://example.com/blog/benchmark-results"
    }
  ]
}
```

---

## 4. SaaS & Developer Tool Graph (`SoftwareApplication`)

When marking up web tools, APIs, CLI utilities, or SaaS apps, nest `SoftwareApplication` directly into the unified graph:

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": "https://example.com/#organization",
      "name": "SaaS Brand",
      "url": "https://example.com",
      "sameAs": [
        "https://github.com/saasbrand",
        "https://linkedin.com/company/saasbrand"
      ]
    },
    {
      "@type": "WebSite",
      "@id": "https://example.com/#website",
      "url": "https://example.com",
      "publisher": { "@id": "https://example.com/#organization" }
    },
    {
      "@type": "WebPage",
      "@id": "https://example.com/#webpage",
      "url": "https://example.com",
      "isPartOf": { "@id": "https://example.com/#website" },
      "about": { "@id": "https://example.com/#software" }
    },
    {
      "@type": "SoftwareApplication",
      "@id": "https://example.com/#software",
      "name": "Network Shield SaaS",
      "operatingSystem": "Linux, macOS, Windows, Android, iOS",
      "applicationCategory": "SecurityApplication, NetworkingApplication",
      "softwareVersion": "2.4.0",
      "author": { "@id": "https://example.com/#organization" },
      "offers": {
        "@type": "Offer",
        "price": "0.00",
        "priceCurrency": "USD",
        "priceValidUntil": "[YYYY-12-31]",
        "availability": "https://schema.org/InStock"
      },
      "featureList": [
        "Encrypted DNS-over-TLS (RFC 7858)",
        "Zero-log policy",
        "Sub-2ms average query latency",
        "Automated failover routing"
      ]
    }
  ]
}
```

# Schema.org JSON-LD Architecture & Templates

This reference provides production-ready, interconnected `@graph` schema templates adhering to Google Search Rich Results guidelines.

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
                       ├── step ──────────────► HowTo (#howto)
                       └── breadcrumb ────────► BreadcrumbList (#breadcrumbs)
```

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
      "datePublished": "2024-01-01T00:00:00Z",
      "dateModified": "2026-09-15T00:00:00Z",
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
        "price": 0,
        "priceCurrency": "USD",
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
            "text": "The engine operates at DNS resolution layer without encapsulating packets in a continuous tunnel, maintaining 100% native throughput."
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
          "position": 1,
          "name": "Open Settings",
          "text": "Navigate to Settings → Network & Internet → Private DNS."
        },
        {
          "@type": "HowToStep",
          "position": 2,
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
      "datePublished": "2026-09-01T10:00:00Z",
      "dateModified": "2026-09-15T12:00:00Z",
      "author": {
        "@type": "Person",
        "name": "Alex Mercer",
        "jobTitle": "Lead Network Architect",
        "sameAs": "https://linkedin.com/in/alex-mercer"
      },
      "publisher": { "@id": "https://example.com/#organization" },
      "mainEntityOfPage": "https://example.com/blog/benchmark-results"
    }
  ]
}
```

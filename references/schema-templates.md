# Schema.org JSON-LD Architecture & Templates

This reference provides production-ready, interconnected `@graph` schema templates adhering to Google Search Rich Results guidelines.

## 1. Architectural Principles
1. **Unified Graph:** Combine all page entities into a single `<script type="application/ld+json">` block using `@graph: [...]`. Avoid multiple disconnected script tags.
2. **Entity Interconnection:** Connect entities via `@id` references (`provider: { "@id": "https://domain.com/#organization" }`).
3. **Freshness Tracking:** Always supply ISO 8601 timestamps for `datePublished` and `dateModified`.
4. **Technical Grounding:** Use `isBasedOn` to link RFCs, ISO standards, or authoritative specifications.

---

## 2. Complete Enterprise Homepage Graph

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
        "https://twitter.com/organization",
        "https://linkedin.com/company/organization"
      ],
      "contactPoint": {
        "@type": "ContactPoint",
        "contactType": "technical support",
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
      "datePublished": "2024-01-01T00:00:00Z",
      "dateModified": "2026-09-15T00:00:00Z",
      "inLanguage": "en"
    },
    {
      "@type": "Service",
      "@id": "https://example.com/#service",
      "name": "Primary Service or Software Name",
      "serviceType": "Cloud Infrastructure, Networking",
      "provider": { "@id": "https://example.com/#organization" },
      "url": "https://example.com",
      "isBasedOn": [
        "https://datatracker.ietf.org/doc/html/rfc7858",
        "https://datatracker.ietf.org/doc/html/rfc8484"
      ],
      "offers": {
        "@type": "Offer",
        "price": "0",
        "priceCurrency": "USD",
        "availability": "https://schema.org/InStock"
      }
    },
    {
      "@type": "FAQPage",
      "@id": "https://example.com/#faq",
      "mainEntity": [
        {
          "@type": "Question",
          "name": "What is the primary technical distinction of this service?",
          "acceptedAnswer": {
            "@type": "Answer",
            "text": "The service operates at DNS resolution layer, removing tunnel overhead and preserving 100% native network bandwidth."
          }
        }
      ]
    }
  ]
}
```

---

## 3. HowTo Schema Template (For Step-by-Step Guides)

```json
{
  "@type": "HowTo",
  "@id": "https://example.com/setup#howto-platform",
  "name": "How to Configure Encrypted DNS on Android 9+",
  "description": "Step-by-step configuration for DNS-over-TLS (DoT) on mobile devices.",
  "totalTime": "PT1M",
  "step": [
    {
      "@type": "HowToStep",
      "position": 1,
      "name": "Open Network Settings",
      "text": "Navigate to Settings → Network & Internet → Private DNS."
    },
    {
      "@type": "HowToStep",
      "position": 2,
      "name": "Specify Hostname",
      "text": "Select 'Private DNS provider hostname' and enter dns.example.com."
    },
    {
      "@type": "HowToStep",
      "position": 3,
      "name": "Save and Verify",
      "text": "Tap Save. The connection status will indicate active encryption."
    }
  ]
}
```

---

## 4. Article Schema Template (For Thought Leadership / Blog)

```json
{
  "@type": "TechArticle",
  "@id": "https://example.com/blog/benchmark-results#article",
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
```

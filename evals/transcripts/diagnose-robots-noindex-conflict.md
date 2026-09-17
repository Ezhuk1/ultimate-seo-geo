Root Cause Analysis: Per RFC 9309, search engine crawlers obey robots.txt Disallow directives before fetching HTML content. Because /private/ is disallowed, Googlebot cannot fetch the page HTML and therefore cannot see the <meta name='robots' content='noindex'> tag. If external or internal links point to this URL, Google indexes the bare URL with the message 'No information is available for this page'.

Remediation & Solution:
1. Remove the Disallow directive in robots.txt to allow Googlebot to fetch the page and parse the noindex tag.
2. Alternatively, protect the route with HTTP 401 Authentication so unauthorized crawlers receive an HTTP challenge.
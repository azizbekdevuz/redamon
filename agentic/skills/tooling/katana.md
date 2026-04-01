---
name: katana
description: Katana crawler syntax, depth/js/known-files behavior, and stable concurrency controls.
---

# Katana CLI Playbook

Official docs:
- https://docs.projectdiscovery.io/opensource/katana/usage
- https://github.com/projectdiscovery/katana

Canonical syntax:
`katana [flags]`

High-signal flags:
- `-u, -list <url|file>` target URL(s)
- `-d, -depth <n>` crawl depth
- `-jc, -js-crawl` parse JavaScript-discovered endpoints
- `-jsl, -jsluice` deeper JS parsing (memory intensive)
- `-kf, -known-files <all|robotstxt|sitemapxml>` known-file crawling mode
- `-proxy <http|socks5 proxy>` explicit proxy setting
- `-c, -concurrency <n>` concurrent fetchers
- `-p, -parallelism <n>` concurrent input targets
- `-rl, -rate-limit <n>` request rate limit
- `-timeout <seconds>` request timeout
- `-retry <n>` retry count
- `-ef, -extension-filter <list>` extension exclusions
- `-hl, -headless` enable hybrid headless crawling
- `-sc, -system-chrome` use local Chrome for headless mode
- `-silent`, `-j, -jsonl`, `-o <file>` output controls

Agent-safe baseline for automation:
`mkdir -p crawl && katana -u https://target.tld -d 3 -jc -kf robotstxt -c 10 -p 10 -rl 50 -timeout 10 -retry 1 -ef png,jpg,jpeg,gif,svg,css,woff,woff2,ttf,eot,map -silent -j -o crawl/katana.jsonl`

Common patterns:
- Fast crawl baseline:
  `katana -u https://target.tld -d 3 -jc -silent`
- Deeper JS-aware crawl:
  `katana -u https://target.tld -d 5 -jc -jsl -kf all -c 10 -p 10 -rl 50 -o katana_urls.txt`
- Headless crawl with local Chrome:
  `katana -u https://target.tld -hl -sc -nos -xhr -j -o crawl/katana_headless.jsonl`
- Headless crawl through proxy:
  `katana -u https://target.tld -hl -sc -ho proxy-server=http://127.0.0.1:48080 -j -o crawl/katana_proxy.jsonl`

Critical correctness rules:
- `-kf` must be followed by one of `all`, `robotstxt`, or `sitemapxml`.
- Use documented `-hl` for headless mode.
- `-proxy` expects a single proxy URL string.
- For `-kf`, keep depth at least `-d 3` so known files are fully covered.

Failure recovery:
- If crawl runs too long, lower `-d`.
- If memory spikes, disable `-jsl` and lower `-c/-p`.
- If headless fails with Chrome errors, drop `-sc` or install system Chrome.

If uncertain, query web_search with:
`site:docs.projectdiscovery.io katana <flag> usage`

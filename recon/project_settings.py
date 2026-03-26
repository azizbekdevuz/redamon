"""
Project Settings - Fetch project configuration from webapp API

When PROJECT_ID and WEBAPP_API_URL are set as environment variables,
settings are fetched from the PostgreSQL database via webapp API.
Otherwise, falls back to DEFAULT_SETTINGS for CLI usage.
"""
import os
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# =============================================================================
# DEFAULT SETTINGS - Used as fallback for CLI usage and missing API fields
# =============================================================================
# These defaults are used when:
# 1. Running from CLI without PROJECT_ID/WEBAPP_API_URL env vars
# 2. As default values for any fields missing from the API response

DEFAULT_SETTINGS: dict[str, Any] = {
    # Core identifiers (empty for CLI usage)
    'PROJECT_ID': '',
    'USER_ID': '',

    # Target Configuration
    'TARGET_DOMAIN': '',
    'SUBDOMAIN_LIST': [],
    'IP_MODE': False,
    'TARGET_IPS': [],
    'VERIFY_DOMAIN_OWNERSHIP': False,
    'OWNERSHIP_TOKEN': 'your-secret-token-here',
    'OWNERSHIP_TXT_PREFIX': '_redamon-verify',

    # Scan Modules
    'SCAN_MODULES': ['domain_discovery', 'port_scan', 'http_probe', 'resource_enum', 'vuln_scan'],
    'UPDATE_GRAPH_DB': True,
    'USE_TOR_FOR_RECON': False,
    'USE_BRUTEFORCE_FOR_SUBDOMAINS': False,
    'STEALTH_MODE': False,

    # WHOIS/DNS
    'WHOIS_ENABLED': True,
    'WHOIS_MAX_RETRIES': 6,
    'DNS_ENABLED': True,
    'DNS_MAX_RETRIES': 3,

    # Naabu Port Scanner
    'NAABU_DOCKER_IMAGE': 'projectdiscovery/naabu:latest',
    'NAABU_TOP_PORTS': '1000',
    'NAABU_CUSTOM_PORTS': '',
    'NAABU_RATE_LIMIT': 1000,
    'NAABU_THREADS': 25,
    'NAABU_TIMEOUT': 10000,
    'NAABU_RETRIES': 1,
    'NAABU_SCAN_TYPE': 's',
    'NAABU_EXCLUDE_CDN': False,
    'NAABU_DISPLAY_CDN': True,
    'NAABU_SKIP_HOST_DISCOVERY': True,
    'NAABU_VERIFY_PORTS': True,
    'NAABU_PASSIVE_MODE': False,

    # Masscan Port Scanner (off by default)
    'MASSCAN_ENABLED': False,
    'MASSCAN_TOP_PORTS': '1000',
    'MASSCAN_CUSTOM_PORTS': '',
    'MASSCAN_RATE': 1000,
    'MASSCAN_BANNERS': False,
    'MASSCAN_WAIT': 10,
    'MASSCAN_RETRIES': 1,
    'MASSCAN_EXCLUDE_TARGETS': '',

    # httpx HTTP Probing
    'HTTPX_DOCKER_IMAGE': 'projectdiscovery/httpx:latest',
    'HTTPX_THREADS': 50,
    'HTTPX_TIMEOUT': 10,
    'HTTPX_RETRIES': 2,
    'HTTPX_RATE_LIMIT': 50,
    'HTTPX_FOLLOW_REDIRECTS': True,
    'HTTPX_MAX_REDIRECTS': 10,
    'HTTPX_PROBE_STATUS_CODE': True,
    'HTTPX_PROBE_CONTENT_LENGTH': True,
    'HTTPX_PROBE_CONTENT_TYPE': True,
    'HTTPX_PROBE_TITLE': True,
    'HTTPX_PROBE_SERVER': True,
    'HTTPX_PROBE_RESPONSE_TIME': True,
    'HTTPX_PROBE_WORD_COUNT': True,
    'HTTPX_PROBE_LINE_COUNT': True,
    'HTTPX_PROBE_TECH_DETECT': True,
    'HTTPX_PROBE_IP': True,
    'HTTPX_PROBE_CNAME': True,
    'HTTPX_PROBE_TLS_INFO': True,
    'HTTPX_PROBE_TLS_GRAB': True,
    'HTTPX_PROBE_FAVICON': True,
    'HTTPX_PROBE_JARM': True,
    'HTTPX_PROBE_HASH': 'sha256',
    'HTTPX_INCLUDE_RESPONSE': True,
    'HTTPX_INCLUDE_RESPONSE_HEADERS': True,
    'HTTPX_PROBE_ASN': True,
    'HTTPX_PROBE_CDN': True,
    'HTTPX_PATHS': [],
    'HTTPX_CUSTOM_HEADERS': [
        'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language: en-US,en;q=0.9',
        'Accept-Encoding: gzip, deflate',
        'Connection: keep-alive',
        'Upgrade-Insecure-Requests: 1',
        'Sec-Fetch-Dest: document',
        'Sec-Fetch-Mode: navigate',
        'Sec-Fetch-Site: none',
        'Sec-Fetch-User: ?1',
        'Cache-Control: max-age=0',
    ],
    'HTTPX_MATCH_CODES': [],
    'HTTPX_FILTER_CODES': [],

    # Wappalyzer
    'WAPPALYZER_ENABLED': True,
    'WAPPALYZER_MIN_CONFIDENCE': 50,
    'WAPPALYZER_REQUIRE_HTML': True,
    'WAPPALYZER_AUTO_UPDATE': True,
    'WAPPALYZER_NPM_VERSION': '6.10.56',
    'WAPPALYZER_CACHE_TTL_HOURS': 24,

    # Banner Grabbing
    'BANNER_GRAB_ENABLED': True,
    'BANNER_GRAB_TIMEOUT': 5,
    'BANNER_GRAB_THREADS': 20,
    'BANNER_GRAB_MAX_LENGTH': 500,

    # Nuclei Vulnerability Scanner
    'NUCLEI_SEVERITY': ['critical', 'high', 'medium', 'low'],
    'NUCLEI_TEMPLATES': [],
    'NUCLEI_EXCLUDE_TEMPLATES': [],
    'NUCLEI_CUSTOM_TEMPLATES': [],
    'NUCLEI_SELECTED_CUSTOM_TEMPLATES': [],
    'NUCLEI_RATE_LIMIT': 100,
    'NUCLEI_BULK_SIZE': 25,
    'NUCLEI_CONCURRENCY': 25,
    'NUCLEI_TIMEOUT': 10,
    'NUCLEI_RETRIES': 1,
    'NUCLEI_TAGS': [],
    'NUCLEI_EXCLUDE_TAGS': [],
    'NUCLEI_DAST_MODE': True,
    'NUCLEI_AUTO_UPDATE_TEMPLATES': True,
    'NUCLEI_NEW_TEMPLATES_ONLY': False,
    'NUCLEI_HEADLESS': False,
    'NUCLEI_SYSTEM_RESOLVERS': True,
    'NUCLEI_FOLLOW_REDIRECTS': True,
    'NUCLEI_MAX_REDIRECTS': 10,
    'NUCLEI_SCAN_ALL_IPS': False,
    'NUCLEI_INTERACTSH': True,
    'NUCLEI_DOCKER_IMAGE': 'projectdiscovery/nuclei:latest',

    # Katana Web Crawler
    'KATANA_ENABLED': True,
    'KATANA_DOCKER_IMAGE': 'projectdiscovery/katana:latest',
    'KATANA_DEPTH': 2,
    'KATANA_MAX_URLS': 300,
    'KATANA_RATE_LIMIT': 50,
    'KATANA_TIMEOUT': 3600,
    'KATANA_JS_CRAWL': True,
    'KATANA_PARAMS_ONLY': False,
    'KATANA_EXCLUDE_PATTERNS': [
        '/_next/image', '/_next/static', '/_next/data', '/__nextjs',
        '/_nuxt/', '/__nuxt',
        '/runtime.', '/polyfills.', '/vendor.',
        '/webpack', '/chunk.', '.chunk.js', '.bundle.js', 'hot-update',
        '/static/', '/public/', '/dist/', '/build/', '/lib/', '/vendor/', '/node_modules/',
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp', '.avif',
        '.bmp', '.tiff', '.tif', '.heic', '.heif', '.raw',
        '/images/', '/img/', '/image/', '/pics/', '/pictures/',
        '/thumbnails/', '/thumb/', '/thumbs/',
        '.css', '.scss', '.sass', '.less', '.styl', '.css.map',
        '/css/', '/styles/', '/style/', '/stylesheet/',
        '.js.map', '.min.js', '/js/lib/', '/js/vendor/', '/js/plugins/',
        'jquery', 'bootstrap.js', 'popper.js',
        '.woff', '.woff2', '.ttf', '.eot', '.otf', '/fonts/', '/font/', '/webfonts/',
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.txt', '.rtf', '.odt', '.ods', '.odp',
        '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2',
        '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv',
        '.wav', '.ogg', '.aac', '.m4a', '.flac',
        '/video/', '/videos/', '/audio/', '/music/', '/sounds/',
        '/wp-content/uploads/', '/wp-content/themes/', '/wp-includes/',
        '/sites/default/files/', '/core/assets/',
        '/pub/static/', '/pub/media/',
        '/storage/', '/staticfiles/', '/packs/',
        'cdn.', 'cdnjs.', 'cloudflare.', 'akamai.', 'fastly.',
        'googleapis.com', 'gstatic.com', 'cloudfront.net',
        'unpkg.com', 'jsdelivr.net', 'bootstrapcdn.com',
        'google-analytics', 'googletagmanager', 'gtag/',
        'facebook.com/tr', 'facebook.net',
        'analytics.', 'tracking.', 'pixel.',
        'hotjar.', 'mouseflow.', 'clarity.',
        'googlesyndication', 'doubleclick', 'adservice',
        'platform.twitter', 'connect.facebook', 'platform.linkedin',
        'maps.google', 'maps.googleapis', 'openstreetmap', 'mapbox',
        'recaptcha', 'hcaptcha', 'captcha',
        'manifest.json', 'sw.js', 'service-worker',
        'browserconfig.xml', 'robots.txt', 'sitemap.xml', '.well-known/',
        'favicon', 'apple-touch-icon', 'android-chrome', '/icons/', '/icon/',
    ],
    'KATANA_CUSTOM_HEADERS': [
        'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language: en-US,en;q=0.9',
    ],

    # GAU Passive URL Discovery
    'GAU_ENABLED': False,
    'GAU_DOCKER_IMAGE': 'sxcurity/gau:latest',
    'GAU_PROVIDERS': ['wayback', 'commoncrawl', 'otx', 'urlscan'],
    'GAU_MAX_URLS': 1000,
    'GAU_TIMEOUT': 60,
    'GAU_THREADS': 5,
    'GAU_BLACKLIST_EXTENSIONS': [
        'png', 'jpg', 'jpeg', 'gif', 'svg', 'ico', 'webp', 'avif',
        'css', 'woff', 'woff2', 'ttf', 'eot', 'otf',
        'mp3', 'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm',
        'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
        'zip', 'rar', '7z', 'tar', 'gz',
    ],
    'GAU_YEAR_RANGE': [],
    'GAU_VERBOSE': False,
    'GAU_VERIFY_URLS': True,
    'GAU_VERIFY_DOCKER_IMAGE': 'projectdiscovery/httpx:latest',
    'GAU_VERIFY_TIMEOUT': 5,
    'GAU_VERIFY_RATE_LIMIT': 100,
    'GAU_VERIFY_THREADS': 50,
    'GAU_VERIFY_ACCEPT_STATUS': [200, 201, 301, 302, 307, 308, 401, 403],
    'GAU_DETECT_METHODS': True,
    'GAU_METHOD_DETECT_TIMEOUT': 5,
    'GAU_METHOD_DETECT_RATE_LIMIT': 50,
    'GAU_METHOD_DETECT_THREADS': 25,
    'GAU_FILTER_DEAD_ENDPOINTS': True,

    # ParamSpider Passive Parameter Discovery
    'PARAMSPIDER_ENABLED': False,
    'PARAMSPIDER_PLACEHOLDER': 'FUZZ',
    'PARAMSPIDER_TIMEOUT': 120,

    # Hakrawler Web Crawler
    'HAKRAWLER_ENABLED': True,
    'HAKRAWLER_DOCKER_IMAGE': 'jauderho/hakrawler:latest',
    'HAKRAWLER_DEPTH': 2,
    'HAKRAWLER_THREADS': 5,
    'HAKRAWLER_TIMEOUT': 30,
    'HAKRAWLER_MAX_URLS': 500,
    'HAKRAWLER_INCLUDE_SUBS': True,
    'HAKRAWLER_INSECURE': True,
    'HAKRAWLER_CUSTOM_HEADERS': [],

    # jsluice JavaScript Analyzer
    'JSLUICE_ENABLED': True,
    'JSLUICE_MAX_FILES': 100,
    'JSLUICE_TIMEOUT': 300,
    'JSLUICE_EXTRACT_URLS': True,
    'JSLUICE_EXTRACT_SECRETS': True,
    'JSLUICE_CONCURRENCY': 5,

    # FFuf Directory Fuzzer
    'FFUF_ENABLED': False,
    'FFUF_WORDLIST': '/usr/share/seclists/Discovery/Web-Content/common.txt',
    'FFUF_THREADS': 40,
    'FFUF_RATE': 0,
    'FFUF_TIMEOUT': 10,
    'FFUF_MAX_TIME': 600,
    'FFUF_MATCH_CODES': [200, 201, 204, 301, 302, 307, 308, 401, 403, 405],
    'FFUF_FILTER_CODES': [],
    'FFUF_FILTER_SIZE': '',
    'FFUF_EXTENSIONS': [],
    'FFUF_RECURSION': False,
    'FFUF_RECURSION_DEPTH': 2,
    'FFUF_AUTO_CALIBRATE': True,
    'FFUF_FOLLOW_REDIRECTS': False,
    'FFUF_CUSTOM_HEADERS': [],
    'FFUF_SMART_FUZZ': True,

    # Arjun Parameter Discovery
    'ARJUN_ENABLED': True,
    'ARJUN_THREADS': 2,
    'ARJUN_TIMEOUT': 15,
    'ARJUN_SCAN_TIMEOUT': 600,
    'ARJUN_METHODS': ['GET', 'POST'],
    'ARJUN_MAX_ENDPOINTS': 50,
    'ARJUN_CHUNK_SIZE': 500,
    'ARJUN_RATE_LIMIT': 0,
    'ARJUN_STABLE': False,
    'ARJUN_PASSIVE': False,
    'ARJUN_DISABLE_REDIRECTS': False,
    'ARJUN_CUSTOM_HEADERS': [],

    # Kiterunner API Discovery
    'KITERUNNER_ENABLED': False,
    'KITERUNNER_WORDLISTS': ['routes-large'],
    'KITERUNNER_RATE_LIMIT': 100,
    'KITERUNNER_CONNECTIONS': 100,
    'KITERUNNER_TIMEOUT': 10,
    'KITERUNNER_SCAN_TIMEOUT': 1000,
    'KITERUNNER_THREADS': 50,
    'KITERUNNER_IGNORE_STATUS': [],
    'KITERUNNER_MIN_CONTENT_LENGTH': 0,
    'KITERUNNER_MATCH_STATUS': [200, 201, 204, 301, 302, 401, 403, 405],
    'KITERUNNER_HEADERS': [],
    'KITERUNNER_DETECT_METHODS': True,
    'KITERUNNER_METHOD_DETECTION_MODE': 'bruteforce',
    'KITERUNNER_BRUTEFORCE_METHODS': ['POST', 'PUT', 'DELETE', 'PATCH'],
    'KITERUNNER_METHOD_DETECT_TIMEOUT': 5,
    'KITERUNNER_METHOD_DETECT_RATE_LIMIT': 50,
    'KITERUNNER_METHOD_DETECT_THREADS': 25,

    # CVE Lookup
    'CVE_LOOKUP_ENABLED': True,
    'CVE_LOOKUP_SOURCE': 'nvd',
    'CVE_LOOKUP_MAX_CVES': 20,
    'CVE_LOOKUP_MIN_CVSS': 0.0,
    'VULNERS_API_KEY': '',
    'NVD_API_KEY': '',  # Configured in Global Settings → Tool API Keys

    # MITRE CWE/CAPEC Enrichment
    'MITRE_AUTO_UPDATE_DB': True,
    'MITRE_INCLUDE_CWE': True,
    'MITRE_INCLUDE_CAPEC': True,
    'MITRE_ENRICH_RECON': True,
    'MITRE_ENRICH_GVM': True,
    'MITRE_CACHE_TTL_HOURS': 24,

    # Security Checks
    'SECURITY_CHECK_ENABLED': True,
    'SECURITY_CHECK_DIRECT_IP_HTTP': True,
    'SECURITY_CHECK_DIRECT_IP_HTTPS': True,
    'SECURITY_CHECK_IP_API_EXPOSED': True,
    'SECURITY_CHECK_WAF_BYPASS': True,
    'SECURITY_CHECK_TLS_EXPIRING_SOON': True,
    'SECURITY_CHECK_TLS_EXPIRY_DAYS': 30,
    'SECURITY_CHECK_MISSING_REFERRER_POLICY': True,
    'SECURITY_CHECK_MISSING_PERMISSIONS_POLICY': True,
    'SECURITY_CHECK_MISSING_COOP': True,
    'SECURITY_CHECK_MISSING_CORP': True,
    'SECURITY_CHECK_MISSING_COEP': True,
    'SECURITY_CHECK_CACHE_CONTROL_MISSING': True,
    'SECURITY_CHECK_LOGIN_NO_HTTPS': True,
    'SECURITY_CHECK_SESSION_NO_SECURE': True,
    'SECURITY_CHECK_SESSION_NO_HTTPONLY': True,
    'SECURITY_CHECK_BASIC_AUTH_NO_TLS': True,
    'SECURITY_CHECK_SPF_MISSING': True,
    'SECURITY_CHECK_DMARC_MISSING': True,
    'SECURITY_CHECK_DNSSEC_MISSING': True,
    'SECURITY_CHECK_ZONE_TRANSFER': True,
    'SECURITY_CHECK_ADMIN_PORT_EXPOSED': True,
    'SECURITY_CHECK_DATABASE_EXPOSED': True,
    'SECURITY_CHECK_REDIS_NO_AUTH': True,
    'SECURITY_CHECK_KUBERNETES_API_EXPOSED': True,
    'SECURITY_CHECK_SMTP_OPEN_RELAY': True,
    'SECURITY_CHECK_CSP_UNSAFE_INLINE': True,
    'SECURITY_CHECK_INSECURE_FORM_ACTION': True,
    'SECURITY_CHECK_NO_RATE_LIMITING': True,
    'SECURITY_CHECK_TIMEOUT': 10,
    'SECURITY_CHECK_MAX_WORKERS': 10,

    # Shodan Pipeline Enrichment
    'SHODAN_HOST_LOOKUP': True,
    'SHODAN_REVERSE_DNS': True,
    'SHODAN_DOMAIN_DNS': False,
    'SHODAN_PASSIVE_CVES': True,
    'SHODAN_API_KEY': '',
    'URLSCAN_API_KEY': '',

    # URLScan.io Passive Enrichment
    'URLSCAN_ENABLED': True,
    'URLSCAN_MAX_RESULTS': 5000,

    # Subdomain Discovery Tool Toggles
    'CRTSH_ENABLED': True,
    'CRTSH_MAX_RESULTS': 5000,
    'HACKERTARGET_ENABLED': True,
    'HACKERTARGET_MAX_RESULTS': 5000,
    'KNOCKPY_RECON_ENABLED': True,
    'KNOCKPY_RECON_MAX_RESULTS': 5000,
    'SUBFINDER_ENABLED': True,
    'SUBFINDER_MAX_RESULTS': 5000,
    'SUBFINDER_DOCKER_IMAGE': 'projectdiscovery/subfinder:latest',

    # Amass (OWASP subdomain enumeration)
    'AMASS_ENABLED': True,
    'AMASS_MAX_RESULTS': 5000,
    'AMASS_TIMEOUT': 10,
    'AMASS_ACTIVE': True,
    'AMASS_BRUTE': False,
    'AMASS_DOCKER_IMAGE': 'caffix/amass:latest',

    # Puredns (wildcard filtering — runs after discovery, before DNS resolution)
    'PUREDNS_ENABLED': True,
    'PUREDNS_DOCKER_IMAGE': 'frost19k/puredns:latest',
    'PUREDNS_THREADS': 0,          # 0 = auto-detect
    'PUREDNS_RATE_LIMIT': 0,       # 0 = unlimited
    'PUREDNS_WILDCARD_BATCH': 0,   # 0 = default batch size
    'PUREDNS_SKIP_VALIDATION': False,

    # Rules of Engagement (recon-relevant fields only)
    'ROE_ENABLED': False,
    'ROE_EXCLUDED_HOSTS': [],
    'ROE_TIME_WINDOW_ENABLED': False,
    'ROE_TIME_WINDOW_TIMEZONE': 'UTC',
    'ROE_TIME_WINDOW_DAYS': ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
    'ROE_TIME_WINDOW_START_TIME': '09:00',
    'ROE_TIME_WINDOW_END_TIME': '18:00',
    'ROE_GLOBAL_MAX_RPS': 0,
}


def _fetch_user_api_key(user_id: str, webapp_url: str, key_name: str) -> str:
    """Fetch an unmasked API key from user's global settings."""
    import requests as _req
    try:
        url = f"{webapp_url.rstrip('/')}/api/users/{user_id}/settings?internal=true"
        resp = _req.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json().get(key_name, '')
    except Exception as e:
        logger.warning(f"Could not fetch {key_name}: {e}")
        return ''


def _fetch_user_settings_full(user_id: str, webapp_url: str) -> dict:
    """Fetch all unmasked user settings including rotation configs."""
    import requests as _req
    try:
        url = f"{webapp_url.rstrip('/')}/api/users/{user_id}/settings?internal=true"
        resp = _req.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"Could not fetch user settings: {e}")
        return {}


def _fetch_shodan_api_key(user_id: str, webapp_url: str) -> str:
    """Fetch the unmasked Shodan API key from user's global settings."""
    return _fetch_user_api_key(user_id, webapp_url, 'shodanApiKey')


def _fetch_urlscan_api_key(user_id: str, webapp_url: str) -> str:
    """Fetch the unmasked URLScan API key from user's global settings."""
    return _fetch_user_api_key(user_id, webapp_url, 'urlscanApiKey')


def fetch_project_settings(project_id: str, webapp_url: str) -> dict[str, Any]:
    """
    Fetch project settings from webapp API.

    Args:
        project_id: The project ID to fetch settings for
        webapp_url: Base URL of the webapp API (e.g., http://localhost:3000)

    Returns:
        Dictionary of settings in SCREAMING_SNAKE_CASE format
    """
    import requests

    url = f"{webapp_url.rstrip('/')}/api/projects/{project_id}"
    logger.info(f"Fetching project settings from {url}")

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    project = response.json()

    # Start with defaults, then override with API values
    settings = DEFAULT_SETTINGS.copy()

    # Core identifiers
    settings['PROJECT_ID'] = project_id
    settings['USER_ID'] = project.get('userId', DEFAULT_SETTINGS['USER_ID'])

    # Target Configuration
    settings['TARGET_DOMAIN'] = project.get('targetDomain', DEFAULT_SETTINGS['TARGET_DOMAIN']).strip()
    raw_subs = project.get('subdomainList', DEFAULT_SETTINGS['SUBDOMAIN_LIST'])
    settings['SUBDOMAIN_LIST'] = [s.strip() for s in raw_subs if s.strip()]
    settings['IP_MODE'] = project.get('ipMode', DEFAULT_SETTINGS['IP_MODE'])
    raw_ips = project.get('targetIps', DEFAULT_SETTINGS['TARGET_IPS'])
    settings['TARGET_IPS'] = [ip.strip() for ip in raw_ips if ip.strip()]
    settings['VERIFY_DOMAIN_OWNERSHIP'] = project.get('verifyDomainOwnership', DEFAULT_SETTINGS['VERIFY_DOMAIN_OWNERSHIP'])
    settings['OWNERSHIP_TOKEN'] = project.get('ownershipToken', DEFAULT_SETTINGS['OWNERSHIP_TOKEN'])
    settings['OWNERSHIP_TXT_PREFIX'] = project.get('ownershipTxtPrefix', DEFAULT_SETTINGS['OWNERSHIP_TXT_PREFIX'])

    # Scan Modules
    settings['SCAN_MODULES'] = project.get('scanModules', DEFAULT_SETTINGS['SCAN_MODULES'])
    settings['UPDATE_GRAPH_DB'] = project.get('updateGraphDb', DEFAULT_SETTINGS['UPDATE_GRAPH_DB'])
    settings['USE_TOR_FOR_RECON'] = project.get('useTorForRecon', DEFAULT_SETTINGS['USE_TOR_FOR_RECON'])
    settings['USE_BRUTEFORCE_FOR_SUBDOMAINS'] = project.get('useBruteforceForSubdomains', DEFAULT_SETTINGS['USE_BRUTEFORCE_FOR_SUBDOMAINS'])
    settings['STEALTH_MODE'] = project.get('stealthMode', DEFAULT_SETTINGS['STEALTH_MODE'])

    # WHOIS/DNS
    settings['WHOIS_ENABLED'] = project.get('whoisEnabled', DEFAULT_SETTINGS['WHOIS_ENABLED'])
    settings['WHOIS_MAX_RETRIES'] = project.get('whoisMaxRetries', DEFAULT_SETTINGS['WHOIS_MAX_RETRIES'])
    settings['DNS_ENABLED'] = project.get('dnsEnabled', DEFAULT_SETTINGS['DNS_ENABLED'])
    settings['DNS_MAX_RETRIES'] = project.get('dnsMaxRetries', DEFAULT_SETTINGS['DNS_MAX_RETRIES'])

    # Naabu Port Scanner
    settings['NAABU_DOCKER_IMAGE'] = project.get('naabuDockerImage', DEFAULT_SETTINGS['NAABU_DOCKER_IMAGE'])
    settings['NAABU_TOP_PORTS'] = project.get('naabuTopPorts', DEFAULT_SETTINGS['NAABU_TOP_PORTS'])
    settings['NAABU_CUSTOM_PORTS'] = project.get('naabuCustomPorts', DEFAULT_SETTINGS['NAABU_CUSTOM_PORTS'])
    settings['NAABU_RATE_LIMIT'] = project.get('naabuRateLimit', DEFAULT_SETTINGS['NAABU_RATE_LIMIT'])
    settings['NAABU_THREADS'] = project.get('naabuThreads', DEFAULT_SETTINGS['NAABU_THREADS'])
    settings['NAABU_TIMEOUT'] = project.get('naabuTimeout', DEFAULT_SETTINGS['NAABU_TIMEOUT'])
    settings['NAABU_RETRIES'] = project.get('naabuRetries', DEFAULT_SETTINGS['NAABU_RETRIES'])
    settings['NAABU_SCAN_TYPE'] = project.get('naabuScanType', DEFAULT_SETTINGS['NAABU_SCAN_TYPE'])
    settings['NAABU_EXCLUDE_CDN'] = project.get('naabuExcludeCdn', DEFAULT_SETTINGS['NAABU_EXCLUDE_CDN'])
    settings['NAABU_DISPLAY_CDN'] = project.get('naabuDisplayCdn', DEFAULT_SETTINGS['NAABU_DISPLAY_CDN'])
    settings['NAABU_SKIP_HOST_DISCOVERY'] = project.get('naabuSkipHostDiscovery', DEFAULT_SETTINGS['NAABU_SKIP_HOST_DISCOVERY'])
    settings['NAABU_VERIFY_PORTS'] = project.get('naabuVerifyPorts', DEFAULT_SETTINGS['NAABU_VERIFY_PORTS'])
    settings['NAABU_PASSIVE_MODE'] = project.get('naabuPassiveMode', DEFAULT_SETTINGS['NAABU_PASSIVE_MODE'])

    # Masscan Port Scanner
    settings['MASSCAN_ENABLED'] = project.get('masscanEnabled', DEFAULT_SETTINGS['MASSCAN_ENABLED'])
    settings['MASSCAN_TOP_PORTS'] = project.get('masscanTopPorts', DEFAULT_SETTINGS['MASSCAN_TOP_PORTS'])
    settings['MASSCAN_CUSTOM_PORTS'] = project.get('masscanCustomPorts', DEFAULT_SETTINGS['MASSCAN_CUSTOM_PORTS'])
    settings['MASSCAN_RATE'] = project.get('masscanRate', DEFAULT_SETTINGS['MASSCAN_RATE'])
    settings['MASSCAN_BANNERS'] = project.get('masscanBanners', DEFAULT_SETTINGS['MASSCAN_BANNERS'])
    settings['MASSCAN_WAIT'] = project.get('masscanWait', DEFAULT_SETTINGS['MASSCAN_WAIT'])
    settings['MASSCAN_RETRIES'] = project.get('masscanRetries', DEFAULT_SETTINGS['MASSCAN_RETRIES'])
    settings['MASSCAN_EXCLUDE_TARGETS'] = project.get('masscanExcludeTargets', DEFAULT_SETTINGS['MASSCAN_EXCLUDE_TARGETS'])

    # httpx HTTP Probing
    settings['HTTPX_DOCKER_IMAGE'] = project.get('httpxDockerImage', DEFAULT_SETTINGS['HTTPX_DOCKER_IMAGE'])
    settings['HTTPX_THREADS'] = project.get('httpxThreads', DEFAULT_SETTINGS['HTTPX_THREADS'])
    settings['HTTPX_TIMEOUT'] = project.get('httpxTimeout', DEFAULT_SETTINGS['HTTPX_TIMEOUT'])
    settings['HTTPX_RETRIES'] = project.get('httpxRetries', DEFAULT_SETTINGS['HTTPX_RETRIES'])
    settings['HTTPX_RATE_LIMIT'] = project.get('httpxRateLimit', DEFAULT_SETTINGS['HTTPX_RATE_LIMIT'])
    settings['HTTPX_FOLLOW_REDIRECTS'] = project.get('httpxFollowRedirects', DEFAULT_SETTINGS['HTTPX_FOLLOW_REDIRECTS'])
    settings['HTTPX_MAX_REDIRECTS'] = project.get('httpxMaxRedirects', DEFAULT_SETTINGS['HTTPX_MAX_REDIRECTS'])
    settings['HTTPX_PROBE_STATUS_CODE'] = project.get('httpxProbeStatusCode', DEFAULT_SETTINGS['HTTPX_PROBE_STATUS_CODE'])
    settings['HTTPX_PROBE_CONTENT_LENGTH'] = project.get('httpxProbeContentLength', DEFAULT_SETTINGS['HTTPX_PROBE_CONTENT_LENGTH'])
    settings['HTTPX_PROBE_CONTENT_TYPE'] = project.get('httpxProbeContentType', DEFAULT_SETTINGS['HTTPX_PROBE_CONTENT_TYPE'])
    settings['HTTPX_PROBE_TITLE'] = project.get('httpxProbeTitle', DEFAULT_SETTINGS['HTTPX_PROBE_TITLE'])
    settings['HTTPX_PROBE_SERVER'] = project.get('httpxProbeServer', DEFAULT_SETTINGS['HTTPX_PROBE_SERVER'])
    settings['HTTPX_PROBE_RESPONSE_TIME'] = project.get('httpxProbeResponseTime', DEFAULT_SETTINGS['HTTPX_PROBE_RESPONSE_TIME'])
    settings['HTTPX_PROBE_WORD_COUNT'] = project.get('httpxProbeWordCount', DEFAULT_SETTINGS['HTTPX_PROBE_WORD_COUNT'])
    settings['HTTPX_PROBE_LINE_COUNT'] = project.get('httpxProbeLineCount', DEFAULT_SETTINGS['HTTPX_PROBE_LINE_COUNT'])
    settings['HTTPX_PROBE_TECH_DETECT'] = project.get('httpxProbeTechDetect', DEFAULT_SETTINGS['HTTPX_PROBE_TECH_DETECT'])
    settings['HTTPX_PROBE_IP'] = project.get('httpxProbeIp', DEFAULT_SETTINGS['HTTPX_PROBE_IP'])
    settings['HTTPX_PROBE_CNAME'] = project.get('httpxProbeCname', DEFAULT_SETTINGS['HTTPX_PROBE_CNAME'])
    settings['HTTPX_PROBE_TLS_INFO'] = project.get('httpxProbeTlsInfo', DEFAULT_SETTINGS['HTTPX_PROBE_TLS_INFO'])
    settings['HTTPX_PROBE_TLS_GRAB'] = project.get('httpxProbeTlsGrab', DEFAULT_SETTINGS['HTTPX_PROBE_TLS_GRAB'])
    settings['HTTPX_PROBE_FAVICON'] = project.get('httpxProbeFavicon', DEFAULT_SETTINGS['HTTPX_PROBE_FAVICON'])
    settings['HTTPX_PROBE_JARM'] = project.get('httpxProbeJarm', DEFAULT_SETTINGS['HTTPX_PROBE_JARM'])
    settings['HTTPX_PROBE_HASH'] = project.get('httpxProbeHash', DEFAULT_SETTINGS['HTTPX_PROBE_HASH'])
    settings['HTTPX_INCLUDE_RESPONSE'] = project.get('httpxIncludeResponse', DEFAULT_SETTINGS['HTTPX_INCLUDE_RESPONSE'])
    settings['HTTPX_INCLUDE_RESPONSE_HEADERS'] = project.get('httpxIncludeResponseHeaders', DEFAULT_SETTINGS['HTTPX_INCLUDE_RESPONSE_HEADERS'])
    settings['HTTPX_PROBE_ASN'] = project.get('httpxProbeAsn', DEFAULT_SETTINGS['HTTPX_PROBE_ASN'])
    settings['HTTPX_PROBE_CDN'] = project.get('httpxProbeCdn', DEFAULT_SETTINGS['HTTPX_PROBE_CDN'])
    settings['HTTPX_PATHS'] = project.get('httpxPaths', DEFAULT_SETTINGS['HTTPX_PATHS'])
    settings['HTTPX_CUSTOM_HEADERS'] = project.get('httpxCustomHeaders', DEFAULT_SETTINGS['HTTPX_CUSTOM_HEADERS'])
    settings['HTTPX_MATCH_CODES'] = project.get('httpxMatchCodes', DEFAULT_SETTINGS['HTTPX_MATCH_CODES'])
    settings['HTTPX_FILTER_CODES'] = project.get('httpxFilterCodes', DEFAULT_SETTINGS['HTTPX_FILTER_CODES'])

    # Wappalyzer
    settings['WAPPALYZER_ENABLED'] = project.get('wappalyzerEnabled', DEFAULT_SETTINGS['WAPPALYZER_ENABLED'])
    settings['WAPPALYZER_MIN_CONFIDENCE'] = project.get('wappalyzerMinConfidence', DEFAULT_SETTINGS['WAPPALYZER_MIN_CONFIDENCE'])
    settings['WAPPALYZER_REQUIRE_HTML'] = project.get('wappalyzerRequireHtml', DEFAULT_SETTINGS['WAPPALYZER_REQUIRE_HTML'])
    settings['WAPPALYZER_AUTO_UPDATE'] = project.get('wappalyzerAutoUpdate', DEFAULT_SETTINGS['WAPPALYZER_AUTO_UPDATE'])
    settings['WAPPALYZER_NPM_VERSION'] = project.get('wappalyzerNpmVersion', DEFAULT_SETTINGS['WAPPALYZER_NPM_VERSION'])
    settings['WAPPALYZER_CACHE_TTL_HOURS'] = project.get('wappalyzerCacheTtlHours', DEFAULT_SETTINGS['WAPPALYZER_CACHE_TTL_HOURS'])

    # Banner Grabbing
    settings['BANNER_GRAB_ENABLED'] = project.get('bannerGrabEnabled', DEFAULT_SETTINGS['BANNER_GRAB_ENABLED'])
    settings['BANNER_GRAB_TIMEOUT'] = project.get('bannerGrabTimeout', DEFAULT_SETTINGS['BANNER_GRAB_TIMEOUT'])
    settings['BANNER_GRAB_THREADS'] = project.get('bannerGrabThreads', DEFAULT_SETTINGS['BANNER_GRAB_THREADS'])
    settings['BANNER_GRAB_MAX_LENGTH'] = project.get('bannerGrabMaxLength', DEFAULT_SETTINGS['BANNER_GRAB_MAX_LENGTH'])

    # Nuclei Vulnerability Scanner
    settings['NUCLEI_SEVERITY'] = project.get('nucleiSeverity', DEFAULT_SETTINGS['NUCLEI_SEVERITY'])
    settings['NUCLEI_TEMPLATES'] = project.get('nucleiTemplates', DEFAULT_SETTINGS['NUCLEI_TEMPLATES'])
    settings['NUCLEI_EXCLUDE_TEMPLATES'] = project.get('nucleiExcludeTemplates', DEFAULT_SETTINGS['NUCLEI_EXCLUDE_TEMPLATES'])
    settings['NUCLEI_CUSTOM_TEMPLATES'] = project.get('nucleiCustomTemplates', DEFAULT_SETTINGS['NUCLEI_CUSTOM_TEMPLATES'])
    settings['NUCLEI_SELECTED_CUSTOM_TEMPLATES'] = project.get('nucleiSelectedCustomTemplates', DEFAULT_SETTINGS['NUCLEI_SELECTED_CUSTOM_TEMPLATES'])
    settings['NUCLEI_RATE_LIMIT'] = project.get('nucleiRateLimit', DEFAULT_SETTINGS['NUCLEI_RATE_LIMIT'])
    settings['NUCLEI_BULK_SIZE'] = project.get('nucleiBulkSize', DEFAULT_SETTINGS['NUCLEI_BULK_SIZE'])
    settings['NUCLEI_CONCURRENCY'] = project.get('nucleiConcurrency', DEFAULT_SETTINGS['NUCLEI_CONCURRENCY'])
    settings['NUCLEI_TIMEOUT'] = project.get('nucleiTimeout', DEFAULT_SETTINGS['NUCLEI_TIMEOUT'])
    settings['NUCLEI_RETRIES'] = project.get('nucleiRetries', DEFAULT_SETTINGS['NUCLEI_RETRIES'])
    settings['NUCLEI_TAGS'] = project.get('nucleiTags', DEFAULT_SETTINGS['NUCLEI_TAGS'])
    settings['NUCLEI_EXCLUDE_TAGS'] = project.get('nucleiExcludeTags', DEFAULT_SETTINGS['NUCLEI_EXCLUDE_TAGS'])
    settings['NUCLEI_DAST_MODE'] = project.get('nucleiDastMode', DEFAULT_SETTINGS['NUCLEI_DAST_MODE'])
    settings['NUCLEI_AUTO_UPDATE_TEMPLATES'] = project.get('nucleiAutoUpdateTemplates', DEFAULT_SETTINGS['NUCLEI_AUTO_UPDATE_TEMPLATES'])
    settings['NUCLEI_NEW_TEMPLATES_ONLY'] = project.get('nucleiNewTemplatesOnly', DEFAULT_SETTINGS['NUCLEI_NEW_TEMPLATES_ONLY'])
    settings['NUCLEI_HEADLESS'] = project.get('nucleiHeadless', DEFAULT_SETTINGS['NUCLEI_HEADLESS'])
    settings['NUCLEI_SYSTEM_RESOLVERS'] = project.get('nucleiSystemResolvers', DEFAULT_SETTINGS['NUCLEI_SYSTEM_RESOLVERS'])
    settings['NUCLEI_FOLLOW_REDIRECTS'] = project.get('nucleiFollowRedirects', DEFAULT_SETTINGS['NUCLEI_FOLLOW_REDIRECTS'])
    settings['NUCLEI_MAX_REDIRECTS'] = project.get('nucleiMaxRedirects', DEFAULT_SETTINGS['NUCLEI_MAX_REDIRECTS'])
    settings['NUCLEI_SCAN_ALL_IPS'] = project.get('nucleiScanAllIps', DEFAULT_SETTINGS['NUCLEI_SCAN_ALL_IPS'])
    settings['NUCLEI_INTERACTSH'] = project.get('nucleiInteractsh', DEFAULT_SETTINGS['NUCLEI_INTERACTSH'])
    settings['NUCLEI_DOCKER_IMAGE'] = project.get('nucleiDockerImage', DEFAULT_SETTINGS['NUCLEI_DOCKER_IMAGE'])

    # Katana Web Crawler
    settings['KATANA_ENABLED'] = project.get('katanaEnabled', DEFAULT_SETTINGS['KATANA_ENABLED'])
    settings['KATANA_DOCKER_IMAGE'] = project.get('katanaDockerImage', DEFAULT_SETTINGS['KATANA_DOCKER_IMAGE'])
    settings['KATANA_DEPTH'] = project.get('katanaDepth', DEFAULT_SETTINGS['KATANA_DEPTH'])
    settings['KATANA_MAX_URLS'] = project.get('katanaMaxUrls', DEFAULT_SETTINGS['KATANA_MAX_URLS'])
    settings['KATANA_RATE_LIMIT'] = project.get('katanaRateLimit', DEFAULT_SETTINGS['KATANA_RATE_LIMIT'])
    settings['KATANA_TIMEOUT'] = project.get('katanaTimeout', DEFAULT_SETTINGS['KATANA_TIMEOUT'])
    settings['KATANA_JS_CRAWL'] = project.get('katanaJsCrawl', DEFAULT_SETTINGS['KATANA_JS_CRAWL'])
    settings['KATANA_PARAMS_ONLY'] = project.get('katanaParamsOnly', DEFAULT_SETTINGS['KATANA_PARAMS_ONLY'])
    settings['KATANA_EXCLUDE_PATTERNS'] = project.get('katanaExcludePatterns', DEFAULT_SETTINGS['KATANA_EXCLUDE_PATTERNS'])
    settings['KATANA_CUSTOM_HEADERS'] = project.get('katanaCustomHeaders', DEFAULT_SETTINGS['KATANA_CUSTOM_HEADERS'])

    # Hakrawler Web Crawler
    settings['HAKRAWLER_ENABLED'] = project.get('hakrawlerEnabled', DEFAULT_SETTINGS['HAKRAWLER_ENABLED'])
    settings['HAKRAWLER_DOCKER_IMAGE'] = project.get('hakrawlerDockerImage', DEFAULT_SETTINGS['HAKRAWLER_DOCKER_IMAGE'])
    settings['HAKRAWLER_DEPTH'] = project.get('hakrawlerDepth', DEFAULT_SETTINGS['HAKRAWLER_DEPTH'])
    settings['HAKRAWLER_THREADS'] = project.get('hakrawlerThreads', DEFAULT_SETTINGS['HAKRAWLER_THREADS'])
    settings['HAKRAWLER_TIMEOUT'] = project.get('hakrawlerTimeout', DEFAULT_SETTINGS['HAKRAWLER_TIMEOUT'])
    settings['HAKRAWLER_MAX_URLS'] = project.get('hakrawlerMaxUrls', DEFAULT_SETTINGS['HAKRAWLER_MAX_URLS'])
    settings['HAKRAWLER_INCLUDE_SUBS'] = project.get('hakrawlerIncludeSubs', DEFAULT_SETTINGS['HAKRAWLER_INCLUDE_SUBS'])
    settings['HAKRAWLER_INSECURE'] = project.get('hakrawlerInsecure', DEFAULT_SETTINGS['HAKRAWLER_INSECURE'])
    settings['HAKRAWLER_CUSTOM_HEADERS'] = project.get('hakrawlerCustomHeaders', DEFAULT_SETTINGS['HAKRAWLER_CUSTOM_HEADERS'])

    # jsluice JavaScript Analyzer
    settings['JSLUICE_ENABLED'] = project.get('jsluiceEnabled', DEFAULT_SETTINGS['JSLUICE_ENABLED'])
    settings['JSLUICE_MAX_FILES'] = project.get('jsluiceMaxFiles', DEFAULT_SETTINGS['JSLUICE_MAX_FILES'])
    settings['JSLUICE_TIMEOUT'] = project.get('jsluiceTimeout', DEFAULT_SETTINGS['JSLUICE_TIMEOUT'])
    settings['JSLUICE_EXTRACT_URLS'] = project.get('jsluiceExtractUrls', DEFAULT_SETTINGS['JSLUICE_EXTRACT_URLS'])
    settings['JSLUICE_EXTRACT_SECRETS'] = project.get('jsluiceExtractSecrets', DEFAULT_SETTINGS['JSLUICE_EXTRACT_SECRETS'])
    settings['JSLUICE_CONCURRENCY'] = project.get('jsluiceConcurrency', DEFAULT_SETTINGS['JSLUICE_CONCURRENCY'])

    # FFuf Directory Fuzzer
    settings['FFUF_ENABLED'] = project.get('ffufEnabled', DEFAULT_SETTINGS['FFUF_ENABLED'])
    settings['FFUF_WORDLIST'] = project.get('ffufWordlist', DEFAULT_SETTINGS['FFUF_WORDLIST'])
    settings['FFUF_THREADS'] = project.get('ffufThreads', DEFAULT_SETTINGS['FFUF_THREADS'])
    settings['FFUF_RATE'] = project.get('ffufRate', DEFAULT_SETTINGS['FFUF_RATE'])
    settings['FFUF_TIMEOUT'] = project.get('ffufTimeout', DEFAULT_SETTINGS['FFUF_TIMEOUT'])
    settings['FFUF_MAX_TIME'] = project.get('ffufMaxTime', DEFAULT_SETTINGS['FFUF_MAX_TIME'])
    settings['FFUF_MATCH_CODES'] = project.get('ffufMatchCodes', DEFAULT_SETTINGS['FFUF_MATCH_CODES'])
    settings['FFUF_FILTER_CODES'] = project.get('ffufFilterCodes', DEFAULT_SETTINGS['FFUF_FILTER_CODES'])
    settings['FFUF_FILTER_SIZE'] = project.get('ffufFilterSize', DEFAULT_SETTINGS['FFUF_FILTER_SIZE'])
    settings['FFUF_EXTENSIONS'] = project.get('ffufExtensions', DEFAULT_SETTINGS['FFUF_EXTENSIONS'])
    settings['FFUF_RECURSION'] = project.get('ffufRecursion', DEFAULT_SETTINGS['FFUF_RECURSION'])
    settings['FFUF_RECURSION_DEPTH'] = project.get('ffufRecursionDepth', DEFAULT_SETTINGS['FFUF_RECURSION_DEPTH'])
    settings['FFUF_AUTO_CALIBRATE'] = project.get('ffufAutoCalibrate', DEFAULT_SETTINGS['FFUF_AUTO_CALIBRATE'])
    settings['FFUF_FOLLOW_REDIRECTS'] = project.get('ffufFollowRedirects', DEFAULT_SETTINGS['FFUF_FOLLOW_REDIRECTS'])
    settings['FFUF_CUSTOM_HEADERS'] = project.get('ffufCustomHeaders', DEFAULT_SETTINGS['FFUF_CUSTOM_HEADERS'])
    settings['FFUF_SMART_FUZZ'] = project.get('ffufSmartFuzz', DEFAULT_SETTINGS['FFUF_SMART_FUZZ'])

    # Arjun Parameter Discovery
    settings['ARJUN_ENABLED'] = project.get('arjunEnabled', DEFAULT_SETTINGS['ARJUN_ENABLED'])
    settings['ARJUN_THREADS'] = project.get('arjunThreads', DEFAULT_SETTINGS['ARJUN_THREADS'])
    settings['ARJUN_TIMEOUT'] = project.get('arjunTimeout', DEFAULT_SETTINGS['ARJUN_TIMEOUT'])
    settings['ARJUN_SCAN_TIMEOUT'] = project.get('arjunScanTimeout', DEFAULT_SETTINGS['ARJUN_SCAN_TIMEOUT'])
    settings['ARJUN_METHODS'] = project.get('arjunMethods', DEFAULT_SETTINGS['ARJUN_METHODS'])
    settings['ARJUN_MAX_ENDPOINTS'] = project.get('arjunMaxEndpoints', DEFAULT_SETTINGS['ARJUN_MAX_ENDPOINTS'])
    settings['ARJUN_CHUNK_SIZE'] = project.get('arjunChunkSize', DEFAULT_SETTINGS['ARJUN_CHUNK_SIZE'])
    settings['ARJUN_RATE_LIMIT'] = project.get('arjunRateLimit', DEFAULT_SETTINGS['ARJUN_RATE_LIMIT'])
    settings['ARJUN_STABLE'] = project.get('arjunStable', DEFAULT_SETTINGS['ARJUN_STABLE'])
    settings['ARJUN_PASSIVE'] = project.get('arjunPassive', DEFAULT_SETTINGS['ARJUN_PASSIVE'])
    settings['ARJUN_DISABLE_REDIRECTS'] = project.get('arjunDisableRedirects', DEFAULT_SETTINGS['ARJUN_DISABLE_REDIRECTS'])
    settings['ARJUN_CUSTOM_HEADERS'] = project.get('arjunCustomHeaders', DEFAULT_SETTINGS['ARJUN_CUSTOM_HEADERS'])

    # GAU Passive URL Discovery
    settings['GAU_ENABLED'] = project.get('gauEnabled', DEFAULT_SETTINGS['GAU_ENABLED'])
    settings['GAU_DOCKER_IMAGE'] = project.get('gauDockerImage', DEFAULT_SETTINGS['GAU_DOCKER_IMAGE'])
    settings['GAU_PROVIDERS'] = project.get('gauProviders', DEFAULT_SETTINGS['GAU_PROVIDERS'])
    settings['GAU_MAX_URLS'] = project.get('gauMaxUrls', DEFAULT_SETTINGS['GAU_MAX_URLS'])
    settings['GAU_TIMEOUT'] = project.get('gauTimeout', DEFAULT_SETTINGS['GAU_TIMEOUT'])
    settings['GAU_THREADS'] = project.get('gauThreads', DEFAULT_SETTINGS['GAU_THREADS'])
    settings['GAU_BLACKLIST_EXTENSIONS'] = project.get('gauBlacklistExtensions', DEFAULT_SETTINGS['GAU_BLACKLIST_EXTENSIONS'])
    settings['GAU_YEAR_RANGE'] = project.get('gauYearRange', DEFAULT_SETTINGS['GAU_YEAR_RANGE'])
    settings['GAU_VERBOSE'] = project.get('gauVerbose', DEFAULT_SETTINGS['GAU_VERBOSE'])
    settings['GAU_VERIFY_URLS'] = project.get('gauVerifyUrls', DEFAULT_SETTINGS['GAU_VERIFY_URLS'])
    settings['GAU_VERIFY_DOCKER_IMAGE'] = project.get('gauVerifyDockerImage', DEFAULT_SETTINGS['GAU_VERIFY_DOCKER_IMAGE'])
    settings['GAU_VERIFY_TIMEOUT'] = project.get('gauVerifyTimeout', DEFAULT_SETTINGS['GAU_VERIFY_TIMEOUT'])
    settings['GAU_VERIFY_RATE_LIMIT'] = project.get('gauVerifyRateLimit', DEFAULT_SETTINGS['GAU_VERIFY_RATE_LIMIT'])
    settings['GAU_VERIFY_THREADS'] = project.get('gauVerifyThreads', DEFAULT_SETTINGS['GAU_VERIFY_THREADS'])
    settings['GAU_VERIFY_ACCEPT_STATUS'] = project.get('gauVerifyAcceptStatus', DEFAULT_SETTINGS['GAU_VERIFY_ACCEPT_STATUS'])
    settings['GAU_DETECT_METHODS'] = project.get('gauDetectMethods', DEFAULT_SETTINGS['GAU_DETECT_METHODS'])
    settings['GAU_METHOD_DETECT_TIMEOUT'] = project.get('gauMethodDetectTimeout', DEFAULT_SETTINGS['GAU_METHOD_DETECT_TIMEOUT'])
    settings['GAU_METHOD_DETECT_RATE_LIMIT'] = project.get('gauMethodDetectRateLimit', DEFAULT_SETTINGS['GAU_METHOD_DETECT_RATE_LIMIT'])
    settings['GAU_METHOD_DETECT_THREADS'] = project.get('gauMethodDetectThreads', DEFAULT_SETTINGS['GAU_METHOD_DETECT_THREADS'])
    settings['GAU_FILTER_DEAD_ENDPOINTS'] = project.get('gauFilterDeadEndpoints', DEFAULT_SETTINGS['GAU_FILTER_DEAD_ENDPOINTS'])

    # ParamSpider Passive Parameter Discovery
    settings['PARAMSPIDER_ENABLED'] = project.get('paramspiderEnabled', DEFAULT_SETTINGS['PARAMSPIDER_ENABLED'])
    settings['PARAMSPIDER_PLACEHOLDER'] = project.get('paramspiderPlaceholder', DEFAULT_SETTINGS['PARAMSPIDER_PLACEHOLDER'])
    settings['PARAMSPIDER_TIMEOUT'] = project.get('paramspiderTimeout', DEFAULT_SETTINGS['PARAMSPIDER_TIMEOUT'])

    # Kiterunner API Discovery
    settings['KITERUNNER_ENABLED'] = project.get('kiterunnerEnabled', DEFAULT_SETTINGS['KITERUNNER_ENABLED'])
    settings['KITERUNNER_WORDLISTS'] = project.get('kiterunnerWordlists', DEFAULT_SETTINGS['KITERUNNER_WORDLISTS'])
    settings['KITERUNNER_RATE_LIMIT'] = project.get('kiterunnerRateLimit', DEFAULT_SETTINGS['KITERUNNER_RATE_LIMIT'])
    settings['KITERUNNER_CONNECTIONS'] = project.get('kiterunnerConnections', DEFAULT_SETTINGS['KITERUNNER_CONNECTIONS'])
    settings['KITERUNNER_TIMEOUT'] = project.get('kiterunnerTimeout', DEFAULT_SETTINGS['KITERUNNER_TIMEOUT'])
    settings['KITERUNNER_SCAN_TIMEOUT'] = project.get('kiterunnerScanTimeout', DEFAULT_SETTINGS['KITERUNNER_SCAN_TIMEOUT'])
    settings['KITERUNNER_THREADS'] = project.get('kiterunnerThreads', DEFAULT_SETTINGS['KITERUNNER_THREADS'])
    settings['KITERUNNER_IGNORE_STATUS'] = project.get('kiterunnerIgnoreStatus', DEFAULT_SETTINGS['KITERUNNER_IGNORE_STATUS'])
    settings['KITERUNNER_MIN_CONTENT_LENGTH'] = project.get('kiterunnerMinContentLength', DEFAULT_SETTINGS['KITERUNNER_MIN_CONTENT_LENGTH'])
    settings['KITERUNNER_MATCH_STATUS'] = project.get('kiterunnerMatchStatus', DEFAULT_SETTINGS['KITERUNNER_MATCH_STATUS'])
    settings['KITERUNNER_HEADERS'] = project.get('kiterunnerHeaders', DEFAULT_SETTINGS['KITERUNNER_HEADERS'])
    settings['KITERUNNER_DETECT_METHODS'] = project.get('kiterunnerDetectMethods', DEFAULT_SETTINGS['KITERUNNER_DETECT_METHODS'])
    settings['KITERUNNER_METHOD_DETECTION_MODE'] = project.get('kiterunnerMethodDetectionMode', DEFAULT_SETTINGS['KITERUNNER_METHOD_DETECTION_MODE'])
    settings['KITERUNNER_BRUTEFORCE_METHODS'] = project.get('kiterunnerBruteforceMethods', DEFAULT_SETTINGS['KITERUNNER_BRUTEFORCE_METHODS'])
    settings['KITERUNNER_METHOD_DETECT_TIMEOUT'] = project.get('kiterunnerMethodDetectTimeout', DEFAULT_SETTINGS['KITERUNNER_METHOD_DETECT_TIMEOUT'])
    settings['KITERUNNER_METHOD_DETECT_RATE_LIMIT'] = project.get('kiterunnerMethodDetectRateLimit', DEFAULT_SETTINGS['KITERUNNER_METHOD_DETECT_RATE_LIMIT'])
    settings['KITERUNNER_METHOD_DETECT_THREADS'] = project.get('kiterunnerMethodDetectThreads', DEFAULT_SETTINGS['KITERUNNER_METHOD_DETECT_THREADS'])

    # CVE Lookup
    settings['CVE_LOOKUP_ENABLED'] = project.get('cveLookupEnabled', DEFAULT_SETTINGS['CVE_LOOKUP_ENABLED'])
    settings['CVE_LOOKUP_SOURCE'] = project.get('cveLookupSource', DEFAULT_SETTINGS['CVE_LOOKUP_SOURCE'])
    settings['CVE_LOOKUP_MAX_CVES'] = project.get('cveLookupMaxCves', DEFAULT_SETTINGS['CVE_LOOKUP_MAX_CVES'])
    settings['CVE_LOOKUP_MIN_CVSS'] = project.get('cveLookupMinCvss', DEFAULT_SETTINGS['CVE_LOOKUP_MIN_CVSS'])

    # MITRE CWE/CAPEC Enrichment
    settings['MITRE_AUTO_UPDATE_DB'] = project.get('mitreAutoUpdateDb', DEFAULT_SETTINGS['MITRE_AUTO_UPDATE_DB'])
    settings['MITRE_INCLUDE_CWE'] = project.get('mitreIncludeCwe', DEFAULT_SETTINGS['MITRE_INCLUDE_CWE'])
    settings['MITRE_INCLUDE_CAPEC'] = project.get('mitreIncludeCapec', DEFAULT_SETTINGS['MITRE_INCLUDE_CAPEC'])
    settings['MITRE_ENRICH_RECON'] = project.get('mitreEnrichRecon', DEFAULT_SETTINGS['MITRE_ENRICH_RECON'])
    settings['MITRE_ENRICH_GVM'] = project.get('mitreEnrichGvm', DEFAULT_SETTINGS['MITRE_ENRICH_GVM'])
    settings['MITRE_CACHE_TTL_HOURS'] = project.get('mitreCacheTtlHours', DEFAULT_SETTINGS['MITRE_CACHE_TTL_HOURS'])

    # Security Checks
    settings['SECURITY_CHECK_ENABLED'] = project.get('securityCheckEnabled', DEFAULT_SETTINGS['SECURITY_CHECK_ENABLED'])
    settings['SECURITY_CHECK_DIRECT_IP_HTTP'] = project.get('securityCheckDirectIpHttp', DEFAULT_SETTINGS['SECURITY_CHECK_DIRECT_IP_HTTP'])
    settings['SECURITY_CHECK_DIRECT_IP_HTTPS'] = project.get('securityCheckDirectIpHttps', DEFAULT_SETTINGS['SECURITY_CHECK_DIRECT_IP_HTTPS'])
    settings['SECURITY_CHECK_IP_API_EXPOSED'] = project.get('securityCheckIpApiExposed', DEFAULT_SETTINGS['SECURITY_CHECK_IP_API_EXPOSED'])
    settings['SECURITY_CHECK_WAF_BYPASS'] = project.get('securityCheckWafBypass', DEFAULT_SETTINGS['SECURITY_CHECK_WAF_BYPASS'])
    settings['SECURITY_CHECK_TLS_EXPIRING_SOON'] = project.get('securityCheckTlsExpiringSoon', DEFAULT_SETTINGS['SECURITY_CHECK_TLS_EXPIRING_SOON'])
    settings['SECURITY_CHECK_TLS_EXPIRY_DAYS'] = project.get('securityCheckTlsExpiryDays', DEFAULT_SETTINGS['SECURITY_CHECK_TLS_EXPIRY_DAYS'])
    settings['SECURITY_CHECK_MISSING_REFERRER_POLICY'] = project.get('securityCheckMissingReferrerPolicy', DEFAULT_SETTINGS['SECURITY_CHECK_MISSING_REFERRER_POLICY'])
    settings['SECURITY_CHECK_MISSING_PERMISSIONS_POLICY'] = project.get('securityCheckMissingPermissionsPolicy', DEFAULT_SETTINGS['SECURITY_CHECK_MISSING_PERMISSIONS_POLICY'])
    settings['SECURITY_CHECK_MISSING_COOP'] = project.get('securityCheckMissingCoop', DEFAULT_SETTINGS['SECURITY_CHECK_MISSING_COOP'])
    settings['SECURITY_CHECK_MISSING_CORP'] = project.get('securityCheckMissingCorp', DEFAULT_SETTINGS['SECURITY_CHECK_MISSING_CORP'])
    settings['SECURITY_CHECK_MISSING_COEP'] = project.get('securityCheckMissingCoep', DEFAULT_SETTINGS['SECURITY_CHECK_MISSING_COEP'])
    settings['SECURITY_CHECK_CACHE_CONTROL_MISSING'] = project.get('securityCheckCacheControlMissing', DEFAULT_SETTINGS['SECURITY_CHECK_CACHE_CONTROL_MISSING'])
    settings['SECURITY_CHECK_LOGIN_NO_HTTPS'] = project.get('securityCheckLoginNoHttps', DEFAULT_SETTINGS['SECURITY_CHECK_LOGIN_NO_HTTPS'])
    settings['SECURITY_CHECK_SESSION_NO_SECURE'] = project.get('securityCheckSessionNoSecure', DEFAULT_SETTINGS['SECURITY_CHECK_SESSION_NO_SECURE'])
    settings['SECURITY_CHECK_SESSION_NO_HTTPONLY'] = project.get('securityCheckSessionNoHttponly', DEFAULT_SETTINGS['SECURITY_CHECK_SESSION_NO_HTTPONLY'])
    settings['SECURITY_CHECK_BASIC_AUTH_NO_TLS'] = project.get('securityCheckBasicAuthNoTls', DEFAULT_SETTINGS['SECURITY_CHECK_BASIC_AUTH_NO_TLS'])
    settings['SECURITY_CHECK_SPF_MISSING'] = project.get('securityCheckSpfMissing', DEFAULT_SETTINGS['SECURITY_CHECK_SPF_MISSING'])
    settings['SECURITY_CHECK_DMARC_MISSING'] = project.get('securityCheckDmarcMissing', DEFAULT_SETTINGS['SECURITY_CHECK_DMARC_MISSING'])
    settings['SECURITY_CHECK_DNSSEC_MISSING'] = project.get('securityCheckDnssecMissing', DEFAULT_SETTINGS['SECURITY_CHECK_DNSSEC_MISSING'])
    settings['SECURITY_CHECK_ZONE_TRANSFER'] = project.get('securityCheckZoneTransfer', DEFAULT_SETTINGS['SECURITY_CHECK_ZONE_TRANSFER'])
    settings['SECURITY_CHECK_ADMIN_PORT_EXPOSED'] = project.get('securityCheckAdminPortExposed', DEFAULT_SETTINGS['SECURITY_CHECK_ADMIN_PORT_EXPOSED'])
    settings['SECURITY_CHECK_DATABASE_EXPOSED'] = project.get('securityCheckDatabaseExposed', DEFAULT_SETTINGS['SECURITY_CHECK_DATABASE_EXPOSED'])
    settings['SECURITY_CHECK_REDIS_NO_AUTH'] = project.get('securityCheckRedisNoAuth', DEFAULT_SETTINGS['SECURITY_CHECK_REDIS_NO_AUTH'])
    settings['SECURITY_CHECK_KUBERNETES_API_EXPOSED'] = project.get('securityCheckKubernetesApiExposed', DEFAULT_SETTINGS['SECURITY_CHECK_KUBERNETES_API_EXPOSED'])
    settings['SECURITY_CHECK_SMTP_OPEN_RELAY'] = project.get('securityCheckSmtpOpenRelay', DEFAULT_SETTINGS['SECURITY_CHECK_SMTP_OPEN_RELAY'])
    settings['SECURITY_CHECK_CSP_UNSAFE_INLINE'] = project.get('securityCheckCspUnsafeInline', DEFAULT_SETTINGS['SECURITY_CHECK_CSP_UNSAFE_INLINE'])
    settings['SECURITY_CHECK_INSECURE_FORM_ACTION'] = project.get('securityCheckInsecureFormAction', DEFAULT_SETTINGS['SECURITY_CHECK_INSECURE_FORM_ACTION'])
    settings['SECURITY_CHECK_NO_RATE_LIMITING'] = project.get('securityCheckNoRateLimiting', DEFAULT_SETTINGS['SECURITY_CHECK_NO_RATE_LIMITING'])
    settings['SECURITY_CHECK_TIMEOUT'] = project.get('securityCheckTimeout', DEFAULT_SETTINGS['SECURITY_CHECK_TIMEOUT'])
    settings['SECURITY_CHECK_MAX_WORKERS'] = project.get('securityCheckMaxWorkers', DEFAULT_SETTINGS['SECURITY_CHECK_MAX_WORKERS'])

    # Shodan Pipeline Enrichment
    settings['SHODAN_HOST_LOOKUP'] = project.get('shodanHostLookup', DEFAULT_SETTINGS['SHODAN_HOST_LOOKUP'])
    settings['SHODAN_REVERSE_DNS'] = project.get('shodanReverseDns', DEFAULT_SETTINGS['SHODAN_REVERSE_DNS'])
    settings['SHODAN_DOMAIN_DNS'] = project.get('shodanDomainDns', DEFAULT_SETTINGS['SHODAN_DOMAIN_DNS'])
    settings['SHODAN_PASSIVE_CVES'] = project.get('shodanPassiveCves', DEFAULT_SETTINGS['SHODAN_PASSIVE_CVES'])

    # URLScan.io Passive Enrichment
    settings['URLSCAN_ENABLED'] = project.get('urlscanEnabled', DEFAULT_SETTINGS['URLSCAN_ENABLED'])
    settings['URLSCAN_MAX_RESULTS'] = project.get('urlscanMaxResults', DEFAULT_SETTINGS['URLSCAN_MAX_RESULTS'])

    # Subdomain Discovery Tool Toggles
    settings['CRTSH_ENABLED'] = project.get('crtshEnabled', DEFAULT_SETTINGS['CRTSH_ENABLED'])
    settings['CRTSH_MAX_RESULTS'] = project.get('crtshMaxResults', DEFAULT_SETTINGS['CRTSH_MAX_RESULTS'])
    settings['HACKERTARGET_ENABLED'] = project.get('hackerTargetEnabled', DEFAULT_SETTINGS['HACKERTARGET_ENABLED'])
    settings['HACKERTARGET_MAX_RESULTS'] = project.get('hackerTargetMaxResults', DEFAULT_SETTINGS['HACKERTARGET_MAX_RESULTS'])
    settings['KNOCKPY_RECON_ENABLED'] = project.get('knockpyReconEnabled', DEFAULT_SETTINGS['KNOCKPY_RECON_ENABLED'])
    settings['KNOCKPY_RECON_MAX_RESULTS'] = project.get('knockpyReconMaxResults', DEFAULT_SETTINGS['KNOCKPY_RECON_MAX_RESULTS'])
    settings['SUBFINDER_ENABLED'] = project.get('subfinderEnabled', DEFAULT_SETTINGS['SUBFINDER_ENABLED'])
    settings['SUBFINDER_MAX_RESULTS'] = project.get('subfinderMaxResults', DEFAULT_SETTINGS['SUBFINDER_MAX_RESULTS'])
    settings['SUBFINDER_DOCKER_IMAGE'] = project.get('subfinderDockerImage', DEFAULT_SETTINGS['SUBFINDER_DOCKER_IMAGE'])
    settings['AMASS_ENABLED'] = project.get('amassEnabled', DEFAULT_SETTINGS['AMASS_ENABLED'])
    settings['AMASS_MAX_RESULTS'] = project.get('amassMaxResults', DEFAULT_SETTINGS['AMASS_MAX_RESULTS'])
    settings['AMASS_TIMEOUT'] = project.get('amassTimeout', DEFAULT_SETTINGS['AMASS_TIMEOUT'])
    settings['AMASS_ACTIVE'] = project.get('amassActive', DEFAULT_SETTINGS['AMASS_ACTIVE'])
    settings['AMASS_BRUTE'] = project.get('amassBrute', DEFAULT_SETTINGS['AMASS_BRUTE'])
    settings['AMASS_DOCKER_IMAGE'] = project.get('amassDockerImage', DEFAULT_SETTINGS['AMASS_DOCKER_IMAGE'])

    # Puredns (wildcard filtering)
    settings['PUREDNS_ENABLED'] = project.get('purednsEnabled', DEFAULT_SETTINGS['PUREDNS_ENABLED'])
    settings['PUREDNS_DOCKER_IMAGE'] = project.get('purednsDockerImage', DEFAULT_SETTINGS['PUREDNS_DOCKER_IMAGE'])
    settings['PUREDNS_THREADS'] = project.get('purednsThreads', DEFAULT_SETTINGS['PUREDNS_THREADS'])
    settings['PUREDNS_RATE_LIMIT'] = project.get('purednsRateLimit', DEFAULT_SETTINGS['PUREDNS_RATE_LIMIT'])
    settings['PUREDNS_WILDCARD_BATCH'] = project.get('purednsWildcardBatch', DEFAULT_SETTINGS['PUREDNS_WILDCARD_BATCH'])
    settings['PUREDNS_SKIP_VALIDATION'] = project.get('purednsSkipValidation', DEFAULT_SETTINGS['PUREDNS_SKIP_VALIDATION'])

    # Fetch all API keys and rotation configs from user's global settings (single call)
    from helpers.key_rotation import KeyRotator

    user_global = {}
    if settings.get('USER_ID'):
        user_global = _fetch_user_settings_full(settings['USER_ID'], webapp_url)

    rotation_cfgs = user_global.get('rotationConfigs', {})

    def _build_rotator(main_key: str, tool_name: str) -> 'KeyRotator':
        cfg = rotation_cfgs.get(tool_name, {})
        extra = cfg.get('extraKeys', [])
        rotate_n = cfg.get('rotateEveryN', 10)
        return KeyRotator([main_key] + extra, rotate_n)

    # Shodan
    shodan_any = any([
        settings['SHODAN_HOST_LOOKUP'], settings['SHODAN_REVERSE_DNS'],
        settings['SHODAN_DOMAIN_DNS'], settings['SHODAN_PASSIVE_CVES'],
    ])
    if shodan_any:
        shodan_key = user_global.get('shodanApiKey', '')
        settings['SHODAN_API_KEY'] = shodan_key
        settings['SHODAN_KEY_ROTATOR'] = _build_rotator(shodan_key, 'shodan')

    # URLScan
    urlscan_enrichment = settings.get('URLSCAN_ENABLED', False)
    gau_uses_urlscan = (
        settings.get('GAU_ENABLED', False)
        and 'urlscan' in settings.get('GAU_PROVIDERS', [])
    )
    if urlscan_enrichment or gau_uses_urlscan:
        urlscan_key = user_global.get('urlscanApiKey', '')
        settings['URLSCAN_API_KEY'] = urlscan_key
        settings['URLSCAN_KEY_ROTATOR'] = _build_rotator(urlscan_key, 'urlscan')

    # NVD / Vulners
    if settings.get('CVE_LOOKUP_ENABLED'):
        nvd_key = user_global.get('nvdApiKey', '')
        vulners_key = user_global.get('vulnersApiKey', '')
        settings['NVD_API_KEY'] = nvd_key
        settings['VULNERS_API_KEY'] = vulners_key
        settings['NVD_KEY_ROTATOR'] = _build_rotator(nvd_key, 'nvd')
        settings['VULNERS_KEY_ROTATOR'] = _build_rotator(vulners_key, 'vulners')

    # Rules of Engagement
    settings['ROE_ENABLED'] = project.get('roeEnabled', DEFAULT_SETTINGS['ROE_ENABLED'])
    settings['ROE_EXCLUDED_HOSTS'] = project.get('roeExcludedHosts', DEFAULT_SETTINGS['ROE_EXCLUDED_HOSTS'])
    settings['ROE_TIME_WINDOW_ENABLED'] = project.get('roeTimeWindowEnabled', DEFAULT_SETTINGS['ROE_TIME_WINDOW_ENABLED'])
    settings['ROE_TIME_WINDOW_TIMEZONE'] = project.get('roeTimeWindowTimezone', DEFAULT_SETTINGS['ROE_TIME_WINDOW_TIMEZONE'])
    settings['ROE_TIME_WINDOW_DAYS'] = project.get('roeTimeWindowDays', DEFAULT_SETTINGS['ROE_TIME_WINDOW_DAYS'])
    settings['ROE_TIME_WINDOW_START_TIME'] = project.get('roeTimeWindowStartTime', DEFAULT_SETTINGS['ROE_TIME_WINDOW_START_TIME'])
    settings['ROE_TIME_WINDOW_END_TIME'] = project.get('roeTimeWindowEndTime', DEFAULT_SETTINGS['ROE_TIME_WINDOW_END_TIME'])
    settings['ROE_GLOBAL_MAX_RPS'] = project.get('roeGlobalMaxRps', DEFAULT_SETTINGS['ROE_GLOBAL_MAX_RPS'])

    # RoE: cap all rate limits to the global max if set
    roe_max_rps = settings['ROE_GLOBAL_MAX_RPS']
    if settings.get('ROE_ENABLED', False) and roe_max_rps > 0:
        RATE_LIMIT_KEYS = [
            'NAABU_RATE_LIMIT', 'MASSCAN_RATE', 'HTTPX_RATE_LIMIT', 'NUCLEI_RATE_LIMIT',
            'KATANA_RATE_LIMIT', 'GAU_VERIFY_RATE_LIMIT', 'GAU_METHOD_DETECT_RATE_LIMIT',
            'KITERUNNER_RATE_LIMIT', 'KITERUNNER_METHOD_DETECT_RATE_LIMIT',
            'FFUF_RATE', 'ARJUN_RATE_LIMIT',
            'PUREDNS_RATE_LIMIT',
            'HAKRAWLER_THREADS',
        ]
        for key in RATE_LIMIT_KEYS:
            if key not in settings:
                continue
            # FFUF_RATE and ARJUN_RATE_LIMIT use 0 to mean "unlimited" — must be capped under RoE
            if settings[key] == 0 and key in ('FFUF_RATE', 'ARJUN_RATE_LIMIT'):
                logger.info(f"RoE: capping {key} from unlimited (0) to {roe_max_rps} rps")
                settings[key] = roe_max_rps
            elif settings[key] > roe_max_rps:
                logger.info(f"RoE: capping {key} from {settings[key]} to {roe_max_rps} rps")
                settings[key] = roe_max_rps

    logger.info(f"Loaded {len(settings)} settings for project {project_id}")
    return settings


def get_settings() -> dict[str, Any]:
    """
    Get project settings from webapp API.

    REQUIRES PROJECT_ID and WEBAPP_API_URL environment variables to be set.
    When running in Docker container, these are always provided by the orchestrator.
    Falls back to DEFAULT_SETTINGS only for CLI usage without env vars.

    Returns:
        Dictionary of settings in SCREAMING_SNAKE_CASE format
    """
    project_id = os.environ.get('PROJECT_ID')
    webapp_url = os.environ.get('WEBAPP_API_URL')

    if project_id and webapp_url:
        try:
            settings = fetch_project_settings(project_id, webapp_url)
            logger.info(f"Loaded {len(settings)} settings from API for project {project_id}")
            return settings

        except Exception as e:
            logger.error(f"Failed to fetch project settings: {e}")
            raise  # Don't silently fall back - fail loudly if API is expected but unavailable

    # Fallback to DEFAULT_SETTINGS for CLI usage only
    logger.info("Using DEFAULT_SETTINGS (no PROJECT_ID/WEBAPP_API_URL set - CLI mode)")
    return DEFAULT_SETTINGS.copy()


# Singleton settings instance
_settings: Optional[dict[str, Any]] = None


def get_setting(key: str, default: Any = None) -> Any:
    """
    Get a single setting value.

    Args:
        key: Setting name in SCREAMING_SNAKE_CASE
        default: Default value if setting not found

    Returns:
        Setting value or default
    """
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings.get(key, default)


def reload_settings() -> dict[str, Any]:
    """Force reload of settings (useful for testing)"""
    global _settings
    _settings = get_settings()
    return _settings


# =============================================================================
# STEALTH MODE OVERRIDES
# =============================================================================

def apply_stealth_overrides(settings: dict[str, Any]) -> dict[str, Any]:
    """
    Apply stealth mode overrides to all recon tool settings.

    When STEALTH_MODE is True, forces all tools to use passive/low-noise
    techniques. Noisy tools (Kiterunner, banner grabbing) are disabled entirely.

    Args:
        settings: The full settings dictionary

    Returns:
        Modified settings dictionary with stealth overrides applied
    """
    if not settings.get('STEALTH_MODE', False):
        return settings

    logger.info("STEALTH MODE ENABLED — applying passive/low-noise overrides to all recon tools")

    # --- Naabu Port Scanner: passive mode only ---
    settings['NAABU_PASSIVE_MODE'] = True
    settings['NAABU_RATE_LIMIT'] = 10
    settings['NAABU_THREADS'] = 1
    settings['NAABU_SCAN_TYPE'] = 'c'  # CONNECT scan (no raw SYN)
    settings['NAABU_SKIP_HOST_DISCOVERY'] = True

    # --- httpx HTTP Probing: low-rate, disable fingerprinting ---
    settings['HTTPX_THREADS'] = 1
    settings['HTTPX_RATE_LIMIT'] = 2
    settings['HTTPX_PROBE_JARM'] = False      # JARM = 10 TLS connections per target
    settings['HTTPX_PROBE_FAVICON'] = False    # Extra HTTP requests for hashing

    # --- Katana Web Crawler: minimal crawl ---
    settings['KATANA_DEPTH'] = 1
    settings['KATANA_RATE_LIMIT'] = 2
    settings['KATANA_MAX_URLS'] = 50
    settings['KATANA_JS_CRAWL'] = False  # JS rendering = headless browser = noisy

    # --- GAU: enable it (passive source) but throttle verification ---
    settings['GAU_ENABLED'] = True
    settings['GAU_VERIFY_RATE_LIMIT'] = 2
    settings['GAU_VERIFY_THREADS'] = 1
    settings['GAU_METHOD_DETECT_RATE_LIMIT'] = 2
    settings['GAU_METHOD_DETECT_THREADS'] = 1

    # --- ParamSpider: enable it (passive source) ---
    settings['PARAMSPIDER_ENABLED'] = True

    # --- Nuclei: passive-only scanning ---
    settings['NUCLEI_DAST_MODE'] = False       # No active fuzzing
    settings['NUCLEI_INTERACTSH'] = False      # No OOB callbacks
    settings['NUCLEI_RATE_LIMIT'] = 5
    settings['NUCLEI_CONCURRENCY'] = 2
    settings['NUCLEI_BULK_SIZE'] = 5
    settings['NUCLEI_HEADLESS'] = False
    # Exclude intrusive template tags
    existing_exclude = settings.get('NUCLEI_EXCLUDE_TAGS', [])
    stealth_exclude = ['dos', 'fuzz', 'intrusive', 'sqli', 'rce']
    settings['NUCLEI_EXCLUDE_TAGS'] = list(set(existing_exclude + stealth_exclude))

    # --- Hakrawler: DISABLED (active crawler, no rate-limit control) ---
    settings['HAKRAWLER_ENABLED'] = False

    # --- jsluice: keep enabled (passive) but reduce file count ---
    settings['JSLUICE_MAX_FILES'] = 20

    # --- FFuf: DISABLED (active directory brute-force) ---
    settings['FFUF_ENABLED'] = False

    # --- Kiterunner: DISABLED (active brute-force API discovery) ---
    settings['KITERUNNER_ENABLED'] = False

    # --- Arjun: force PASSIVE ONLY (no active probing in stealth) ---
    settings['ARJUN_PASSIVE'] = True

    # --- Banner Grabbing: DISABLED (direct socket connections) ---
    settings['BANNER_GRAB_ENABLED'] = False

    # --- Subdomain Brute Force: DISABLED ---
    settings['USE_BRUTEFORCE_FOR_SUBDOMAINS'] = False

    # --- Passive sources: keep enabled but reduce results ---
    settings['URLSCAN_MAX_RESULTS'] = min(settings.get('URLSCAN_MAX_RESULTS', 5000), 100)
    settings['CRTSH_MAX_RESULTS'] = min(settings.get('CRTSH_MAX_RESULTS', 5000), 100)
    settings['HACKERTARGET_MAX_RESULTS'] = min(settings.get('HACKERTARGET_MAX_RESULTS', 5000), 100)
    settings['KNOCKPY_RECON_MAX_RESULTS'] = min(settings.get('KNOCKPY_RECON_MAX_RESULTS', 5000), 100)
    settings['SUBFINDER_MAX_RESULTS'] = min(settings.get('SUBFINDER_MAX_RESULTS', 5000), 100)
    settings['AMASS_ACTIVE'] = False
    settings['AMASS_BRUTE'] = False
    settings['AMASS_MAX_RESULTS'] = min(settings.get('AMASS_MAX_RESULTS', 5000), 100)

    # --- Puredns: DISABLED (active DNS queries) ---
    settings['PUREDNS_ENABLED'] = False

    # --- Security Checks: disable active checks, keep passive ones ---
    # Active checks (make network connections to target)
    settings['SECURITY_CHECK_DIRECT_IP_HTTP'] = False
    settings['SECURITY_CHECK_DIRECT_IP_HTTPS'] = False
    settings['SECURITY_CHECK_WAF_BYPASS'] = False
    settings['SECURITY_CHECK_ZONE_TRANSFER'] = False
    settings['SECURITY_CHECK_ADMIN_PORT_EXPOSED'] = False
    settings['SECURITY_CHECK_DATABASE_EXPOSED'] = False
    settings['SECURITY_CHECK_REDIS_NO_AUTH'] = False
    settings['SECURITY_CHECK_KUBERNETES_API_EXPOSED'] = False
    settings['SECURITY_CHECK_SMTP_OPEN_RELAY'] = False
    settings['SECURITY_CHECK_NO_RATE_LIMITING'] = False
    # Passive checks remain enabled (SPF, DMARC, DNSSEC, TLS expiry, headers)

    # --- Masscan: DISABLED (active SYN scanning) ---
    settings['MASSCAN_ENABLED'] = False

    logger.info("Stealth overrides applied: Naabu=passive, Masscan=OFF, httpx=low-rate, Katana=minimal, "
                "Nuclei=no-DAST, Kiterunner=OFF, BannerGrab=OFF, BruteForce=OFF, "
                "ActiveSecurityChecks=OFF")

    return settings

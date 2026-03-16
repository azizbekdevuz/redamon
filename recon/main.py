#!/usr/bin/env python3
"""
RedAmon - Main Reconnaissance Controller
=========================================
Orchestrates all OSINT reconnaissance modules:
1. WHOIS lookup (integrated into domain recon JSON)
2. Subdomain discovery & DNS resolution
3. Port scanning (fast, lightweight)
4. HTTP probing & technology detection
5. Resource enumeration (endpoint discovery & classification)
6. Vulnerability scanning + MITRE CWE/CAPEC enrichment

Pipeline: domain_discovery -> port_scan -> http_probe -> resource_enum -> vuln_scan

Note: vuln_scan automatically includes MITRE CWE/CAPEC enrichment for all CVEs.

Run this file to execute the full recon pipeline.
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add project root to path for imports (needed for graph_db, utils modules)
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import settings from project_settings (fetches from API or falls back to params.py)
from recon.project_settings import get_settings, apply_stealth_overrides

# Load settings from API (if PROJECT_ID/WEBAPP_API_URL set) or params.py (CLI mode)
_settings = get_settings()
_settings = apply_stealth_overrides(_settings)

# Extract commonly used settings as module-level variables for compatibility
TARGET_DOMAIN = _settings['TARGET_DOMAIN']
SUBDOMAIN_LIST = _settings['SUBDOMAIN_LIST']
USE_TOR_FOR_RECON = _settings['USE_TOR_FOR_RECON']
USE_BRUTEFORCE_FOR_SUBDOMAINS = _settings['USE_BRUTEFORCE_FOR_SUBDOMAINS']
SCAN_MODULES = _settings['SCAN_MODULES']
UPDATE_GRAPH_DB = _settings['UPDATE_GRAPH_DB']
USER_ID = _settings['USER_ID']
PROJECT_ID = _settings['PROJECT_ID']
VERIFY_DOMAIN_OWNERSHIP = _settings['VERIFY_DOMAIN_OWNERSHIP']
OWNERSHIP_TOKEN = _settings['OWNERSHIP_TOKEN']
OWNERSHIP_TXT_PREFIX = _settings['OWNERSHIP_TXT_PREFIX']
IP_MODE = _settings['IP_MODE']
TARGET_IPS = _settings['TARGET_IPS']

# Import recon modules
from recon.whois_recon import whois_lookup
from recon.domain_recon import discover_subdomains, verify_domain_ownership, reverse_dns_lookup
from recon.port_scan import run_port_scan
from recon.http_probe import run_http_probe
from recon.resource_enum import run_resource_enum
from recon.vuln_scan import run_vuln_scan
from recon.add_mitre import run_mitre_enrichment

# Output directory
OUTPUT_DIR = Path(__file__).parent / "output"


def _is_roe_excluded(host: str, excluded_list: list) -> bool:
    """Check if a host (IP or domain) matches any RoE exclusion entry.

    Supports:
    - Exact IP/domain match: "10.0.0.5" matches "10.0.0.5"
    - CIDR match: "10.0.0.5" matches "10.0.0.0/24"
    - Subdomain match: "payments.example.com" matches "payments.example.com"
    """
    import ipaddress as _ipaddress

    for entry in excluded_list:
        entry = entry.strip()
        if not entry:
            continue
        # Exact string match (works for both IPs and domains)
        if host == entry:
            return True
        # CIDR match: check if host IP falls within an excluded network
        if '/' in entry:
            try:
                network = _ipaddress.ip_network(entry, strict=False)
                try:
                    if _ipaddress.ip_address(host) in network:
                        return True
                except ValueError:
                    pass  # host is a domain, not an IP — skip CIDR check
            except ValueError:
                pass  # invalid CIDR in exclusion list
        # Domain suffix match: "payments.example.com" should be excluded
        # if the exclusion is a parent domain pattern
        elif host.endswith('.' + entry):
            return True
    return False


def _filter_roe_excluded(hosts: list, settings: dict, label: str = "host") -> list:
    """Filter a list of hosts/IPs against ROE_EXCLUDED_HOSTS. Returns the filtered list."""
    roe_excluded = settings.get('ROE_EXCLUDED_HOSTS', [])
    if not settings.get('ROE_ENABLED', False) or not roe_excluded:
        return hosts
    before_count = len(hosts)
    filtered = [h for h in hosts if not _is_roe_excluded(h, roe_excluded)]
    removed = before_count - len(filtered)
    if removed:
        print(f"[RoE] Excluded {removed} {label}(s) per Rules of Engagement")
    return filtered


def _merge_external_domain(aggregated: dict, entry: dict):
    """Merge a single external domain entry into the aggregated dict."""
    domain = entry.get("domain", "").strip().lower()
    if not domain:
        return
    if domain not in aggregated:
        aggregated[domain] = {
            "domain": domain, "sources": [], "redirect_from_urls": [],
            "redirect_to_urls": [], "status_codes_seen": [], "titles_seen": [],
            "servers_seen": [], "ips_seen": [], "countries_seen": [], "times_seen": 0,
        }
    rec = aggregated[domain]
    rec["times_seen"] += 1
    for val, key in [
        (entry.get("source"), "sources"),
        (entry.get("url"), "redirect_to_urls"),
        (entry.get("redirect_from_url"), "redirect_from_urls"),
        (entry.get("title"), "titles_seen"),
        (entry.get("server"), "servers_seen"),
        (entry.get("ip"), "ips_seen"),
        (entry.get("country"), "countries_seen"),
    ]:
        if val and val not in rec[key]:
            rec[key].append(val)
    sc = entry.get("status_code")
    if sc is not None:
        sc_str = str(sc)
        if sc_str not in rec["status_codes_seen"]:
            rec["status_codes_seen"].append(sc_str)


def _aggregate_external_domains(combined_result: dict) -> list:
    """Aggregate external domains from all pipeline sources."""
    aggregated = {}
    for e in combined_result.get("http_probe", {}).get("external_domains", []):
        _merge_external_domain(aggregated, e)
    for e in combined_result.get("urlscan", {}).get("external_domains", []):
        _merge_external_domain(aggregated, e)
    for e in combined_result.get("resource_enum", {}).get("external_domains", []):
        _merge_external_domain(aggregated, e)
    for e in combined_result.get("domain_discovery_external_domains", []):
        _merge_external_domain(aggregated, e)
    return list(aggregated.values())


def should_skip_active_scans(recon_data: dict) -> tuple:
    """
    Check if active scanning modules (resource_enum, vuln_scan) should be skipped.
    
    These modules require live targets to work with. If http_probe found no live URLs,
    there's nothing to crawl or scan.
    
    Args:
        recon_data: Current reconnaissance data
        
    Returns:
        Tuple of (should_skip: bool, reason: str)
    """
    http_probe_data = recon_data.get('http_probe', {})
    http_summary = http_probe_data.get('summary', {})
    
    live_urls = http_summary.get('live_urls', 0)
    total_hosts = http_summary.get('total_hosts', 0)
    
    # Check if http_probe ran but found nothing
    if 'http_probe' in recon_data:
        if live_urls == 0 and total_hosts == 0:
            # Also check by_url to be sure
            by_url = http_probe_data.get('by_url', {})
            if len(by_url) == 0:
                return True, "No live URLs found by http_probe - nothing to scan"
    
    return False, ""


def parse_target(target: str, subdomain_list: list = None) -> dict:
    """
    Parse target domain and determine scan mode based on SUBDOMAIN_LIST.

    Args:
        target: Root domain (e.g., "example.com", "vulnweb.com")
                TARGET_DOMAIN in params.py must always be a root domain.
        subdomain_list: List of subdomain prefixes to filter (e.g., ["testphp.", "www."])
                       Empty list = full discovery mode (scan all subdomains)
                       Special prefix "." = include root domain directly (no subdomain)

    Returns:
        Dictionary with:
        - target: original target (root domain)
        - root_domain: the root domain (same as target)
        - filtered_mode: True if SUBDOMAIN_LIST has entries (filtered scan)
        - subdomain_list: list of subdomain prefixes to scan
        - full_subdomains: list of full subdomain names (prefix + root domain)
        - include_root_domain: True if "." is in subdomain_list (scan root domain directly)
    """
    # TARGET_DOMAIN is always the root domain (e.g., "vulnweb.com")
    root_domain = target

    # Determine if we're in filtered mode (SUBDOMAIN_LIST has entries)
    subdomain_list = subdomain_list or []
    filtered_mode = len(subdomain_list) > 0

    # Check if root domain should be included (prefix "." means root domain)
    include_root_domain = False
    
    # Build full subdomain names from prefixes
    full_subdomains = []
    if filtered_mode:
        for prefix in subdomain_list:
            # Handle "." as special case meaning root domain itself
            clean_prefix = prefix.rstrip('.')
            if clean_prefix == "" or prefix == ".":
                # "." means include root domain directly (e.g., vulnweb.com)
                include_root_domain = True
                # Add root domain to the list
                if root_domain not in full_subdomains:
                    full_subdomains.append(root_domain)
            else:
                # Normal subdomain prefix (e.g., "testphp." -> testphp.vulnweb.com)
                full_subdomain = f"{clean_prefix}.{root_domain}"
                if full_subdomain not in full_subdomains:
                    full_subdomains.append(full_subdomain)

    return {
        "target": target,
        "root_domain": root_domain,
        "filtered_mode": filtered_mode,
        "subdomain_list": subdomain_list,
        "full_subdomains": full_subdomains,
        "include_root_domain": include_root_domain
    }


def build_scan_type() -> str:
    """Build dynamic scan type based on enabled modules."""
    modules = []
    if "domain_discovery" in SCAN_MODULES:
        modules.append("domain_discovery")
    if "port_scan" in SCAN_MODULES:
        modules.append("port_scan")
    if "http_probe" in SCAN_MODULES:
        modules.append("http_probe")
    if "resource_enum" in SCAN_MODULES:
        modules.append("resource_enum")
    if "vuln_scan" in SCAN_MODULES:
        modules.append("vuln_scan")
    return "_".join(modules) if modules else "custom"


def save_recon_file(data: dict, output_file: Path):
    """Save recon data to JSON file."""
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)


def run_ip_recon(target_ips: list, settings: dict) -> dict:
    """
    Run IP-based reconnaissance: expand CIDRs, reverse DNS, IP WHOIS.

    Produces a recon data structure compatible with the domain-based pipeline
    using mock Domain/Subdomain names derived from reverse DNS or IP addresses.

    Args:
        target_ips: List of IP addresses and/or CIDR ranges
        settings: Full settings dictionary

    Returns:
        Complete reconnaissance data dict (same shape as run_domain_recon output)
    """
    import ipaddress
    from recon.domain_recon import dns_lookup

    print("\n" + "=" * 70)
    print("               RedAmon - IP-Based Reconnaissance")
    print("=" * 70)
    print(f"  Target IPs/CIDRs: {', '.join(target_ips)}")
    print("=" * 70 + "\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"recon_{PROJECT_ID}.json"

    mock_domain = f"ip-targets.{PROJECT_ID}"

    # Step 1: Expand CIDRs into individual IPs
    expanded_ips = []
    original_cidrs = []
    for entry in target_ips:
        entry = entry.strip()
        if '/' in entry:
            try:
                network = ipaddress.ip_network(entry, strict=False)
                original_cidrs.append(entry)
                for host in network.hosts():
                    expanded_ips.append(str(host))
                # For /32 (IPv4) or /128 (IPv6) single-host networks, hosts() is empty
                if network.prefixlen in (32, 128):
                    expanded_ips.append(str(network.network_address))
            except ValueError as e:
                print(f"[!] Invalid CIDR {entry}: {e}")
        else:
            expanded_ips.append(entry)

    expanded_ips = list(dict.fromkeys(expanded_ips))  # deduplicate preserving order
    print(f"[*] Expanded {len(target_ips)} entries to {len(expanded_ips)} individual IPs")

    # RoE: filter out excluded hosts (supports exact match + CIDR)
    expanded_ips = _filter_roe_excluded(expanded_ips, settings, label="IP")

    # Step 2: Reverse DNS for each IP
    print(f"\n[PHASE 1] Reverse DNS Lookup")
    print("-" * 40)

    ip_to_hostname = {}
    all_hostnames = []
    subdomains_dns = {}

    for ip in expanded_ips:
        hostname = reverse_dns_lookup(ip, max_retries=settings.get('DNS_MAX_RETRIES', 3))
        if hostname:
            ip_to_hostname[ip] = hostname
            all_hostnames.append(hostname)
            print(f"[+] {ip} -> {hostname}")
        else:
            # Use IP with dashes as mock subdomain name
            mock_name = ip.replace('.', '-').replace(':', '-')
            ip_to_hostname[ip] = mock_name
            print(f"[-] {ip} -> no PTR (using {mock_name})")

    # Step 3: Build DNS data structure for each "subdomain"
    print(f"\n[PHASE 2] DNS Resolution for Discovered Hosts")
    print("-" * 40)

    subdomain_names = []
    for ip, hostname in ip_to_hostname.items():
        # Determine if this is a real hostname or mock
        is_real_hostname = hostname in all_hostnames and not hostname.replace('-', '').replace('.', '').isdigit()

        if is_real_hostname:
            # Resolve DNS for real hostnames
            print(f"[*] Resolving: {hostname}")
            host_dns = dns_lookup(hostname)
            subdomains_dns[hostname] = host_dns
            subdomain_names.append(hostname)
        else:
            # Mock entry - create minimal DNS data with the IP
            is_v6 = ':' in ip
            subdomains_dns[hostname] = {
                "has_records": True,
                "ips": {
                    "ipv4": [] if is_v6 else [ip],
                    "ipv6": [ip] if is_v6 else [],
                },
                "records": {},
                "is_mock": True,
                "actual_ip": ip,
            }
            subdomain_names.append(hostname)

    # Step 4: IP WHOIS (best-effort)
    print(f"\n[PHASE 3] IP WHOIS Lookup")
    print("-" * 40)
    ip_whois = {}
    try:
        from recon.whois_recon import whois_lookup as ip_whois_lookup
        # WHOIS a sample of IPs (first one per /24 block to avoid flooding)
        seen_blocks = set()
        for ip in expanded_ips:
            block = '.'.join(ip.split('.')[:3]) if '.' in ip else ip[:16]
            if block in seen_blocks:
                continue
            seen_blocks.add(block)
            try:
                result = ip_whois_lookup(ip, save_output=False, settings=settings)
                ip_whois[ip] = result.get("whois_data", {})
                org = ip_whois[ip].get("org", "unknown")
                print(f"[+] {ip}: org={org}")
            except Exception as e:
                print(f"[-] WHOIS for {ip} failed: {e}")
    except Exception as e:
        print(f"[!] IP WHOIS module error: {e}")

    # Build the subdomain_filter (all IPs + any PTR-resolved hostnames)
    # This becomes allowed_hosts for http_probe scope checking
    subdomain_filter = list(set(expanded_ips + all_hostnames + subdomain_names))

    # Build result structure compatible with domain-based pipeline
    combined_result = {
        "metadata": {
            "scan_type": build_scan_type(),
            "scan_timestamp": datetime.now().isoformat(),
            "target": mock_domain,
            "root_domain": mock_domain,
            "ip_mode": True,
            "target_ips": target_ips,
            "expanded_ips": expanded_ips,
            "original_cidrs": original_cidrs,
            "ip_to_hostname": ip_to_hostname,
            "filtered_mode": True,
            "subdomain_filter": subdomain_filter,
            "anonymous_mode": settings.get('USE_TOR_FOR_RECON', False),
            "bruteforce_mode": False,
            "modules_executed": ["ip_recon", "reverse_dns"],
        },
        "domain": mock_domain,
        "whois": {"ip_whois": ip_whois},
        "subdomains": subdomain_names,
        "subdomain_count": len(subdomain_names),
        "dns": {
            "domain": {},
            "subdomains": subdomains_dns,
        },
    }

    save_recon_file(combined_result, output_file)
    print(f"\n[+] Saved: {output_file}")

    # Update Graph DB
    if UPDATE_GRAPH_DB:
        print(f"\n[PHASE 4] Graph Database Update")
        print("-" * 40)
        try:
            from graph_db import Neo4jClient
            with Neo4jClient() as graph_client:
                if graph_client.verify_connection():
                    stats = graph_client.update_graph_from_ip_recon(combined_result, USER_ID, PROJECT_ID)
                    combined_result["metadata"]["graph_db_updated"] = True
                    combined_result["metadata"]["graph_db_stats"] = stats
                    print(f"[+] Graph database updated successfully")
                else:
                    print(f"[!] Could not connect to Neo4j - skipping graph update")
                    combined_result["metadata"]["graph_db_updated"] = False
        except ImportError:
            print(f"[!] Neo4j client not available - skipping graph update")
            combined_result["metadata"]["graph_db_updated"] = False
        except Exception as e:
            print(f"[!] Graph DB update failed: {e}")
            combined_result["metadata"]["graph_db_updated"] = False
            combined_result["metadata"]["graph_db_error"] = str(e)

        save_recon_file(combined_result, output_file)

    # Shodan OSINT Enrichment (passive — runs before port scan)
    shodan_enabled = any([
        settings.get('SHODAN_HOST_LOOKUP'),
        settings.get('SHODAN_REVERSE_DNS'),
        settings.get('SHODAN_DOMAIN_DNS'),
        settings.get('SHODAN_PASSIVE_CVES'),
    ])
    if shodan_enabled:
        from recon.shodan_enrich import run_shodan_enrichment
        combined_result = run_shodan_enrichment(combined_result, settings)
        combined_result["metadata"]["modules_executed"].append("shodan_enrich")
        save_recon_file(combined_result, output_file)

        if UPDATE_GRAPH_DB:
            try:
                from graph_db import Neo4jClient
                with Neo4jClient() as graph_client:
                    if graph_client.verify_connection():
                        graph_client.update_graph_from_shodan(combined_result, USER_ID, PROJECT_ID)
            except Exception as e:
                print(f"[!] Shodan graph update failed: {e}")

    # Continue pipeline: port_scan -> http_probe -> resource_enum -> vuln_scan
    if "port_scan" in SCAN_MODULES:
        combined_result = run_port_scan(combined_result, output_file=output_file, settings=settings)
        combined_result["metadata"]["modules_executed"].append("port_scan")
        save_recon_file(combined_result, output_file)

        if UPDATE_GRAPH_DB:
            try:
                from graph_db import Neo4jClient
                with Neo4jClient() as graph_client:
                    if graph_client.verify_connection():
                        graph_client.update_graph_from_port_scan(combined_result, USER_ID, PROJECT_ID)
            except Exception as e:
                print(f"[!] Port scan graph update failed: {e}")

    if "http_probe" in SCAN_MODULES:
        combined_result = run_http_probe(combined_result, output_file=output_file, settings=settings)
        combined_result["metadata"]["modules_executed"].append("http_probe")
        save_recon_file(combined_result, output_file)

        if UPDATE_GRAPH_DB:
            try:
                from graph_db import Neo4jClient
                with Neo4jClient() as graph_client:
                    if graph_client.verify_connection():
                        graph_client.update_graph_from_http_probe(combined_result, USER_ID, PROJECT_ID)
            except Exception as e:
                print(f"[!] HTTP probe graph update failed: {e}")

        # URLScan Phase B: Enrich BaseURLs + create Endpoints (only after http_probe)
        if 'urlscan' in combined_result and UPDATE_GRAPH_DB:
            try:
                from graph_db import Neo4jClient
                with Neo4jClient() as graph_client:
                    if graph_client.verify_connection():
                        graph_client.update_graph_from_urlscan_enrichment(combined_result, USER_ID, PROJECT_ID)
            except Exception as e:
                print(f"[!] URLScan enrichment graph update failed: {e}")

    # Check if active scans should be skipped
    skip_active_scans, skip_reason = should_skip_active_scans(combined_result)

    if skip_active_scans:
        print(f"\n[!] SKIPPING ACTIVE SCANS: {skip_reason}")
        combined_result["metadata"]["active_scans_skipped"] = True
        combined_result["metadata"]["active_scans_skip_reason"] = skip_reason
        save_recon_file(combined_result, output_file)
    else:
        if "resource_enum" in SCAN_MODULES:
            combined_result = run_resource_enum(combined_result, output_file=output_file, settings=settings)
            combined_result["metadata"]["modules_executed"].append("resource_enum")
            save_recon_file(combined_result, output_file)

            if UPDATE_GRAPH_DB:
                try:
                    from graph_db import Neo4jClient
                    with Neo4jClient() as graph_client:
                        if graph_client.verify_connection():
                            graph_client.update_graph_from_resource_enum(combined_result, USER_ID, PROJECT_ID)
                except Exception as e:
                    print(f"[!] Resource enum graph update failed: {e}")

        if "vuln_scan" in SCAN_MODULES:
            combined_result = run_vuln_scan(combined_result, output_file=output_file, settings=settings)
            combined_result["metadata"]["modules_executed"].append("vuln_scan")
            save_recon_file(combined_result, output_file)

            combined_result = run_mitre_enrichment(combined_result, output_file=output_file, settings=settings)
            save_recon_file(combined_result, output_file)

            if UPDATE_GRAPH_DB:
                try:
                    from graph_db import Neo4jClient
                    with Neo4jClient() as graph_client:
                        if graph_client.verify_connection():
                            graph_client.update_graph_from_vuln_scan(combined_result, USER_ID, PROJECT_ID)
                except Exception as e:
                    print(f"[!] Vuln scan graph update failed: {e}")

    # External Domains — aggregate from all sources and persist
    ext_domains = _aggregate_external_domains(combined_result)
    if ext_domains:
        combined_result["external_domains_aggregated"] = ext_domains
        save_recon_file(combined_result, output_file)

        if UPDATE_GRAPH_DB:
            print(f"\n[GRAPH UPDATE] External Domains")
            print("-" * 40)
            try:
                from graph_db import Neo4jClient
                with Neo4jClient() as graph_client:
                    if graph_client.verify_connection():
                        graph_client.update_graph_from_external_domains(
                            combined_result, USER_ID, PROJECT_ID
                        )
                        combined_result["metadata"]["graph_db_external_domains_updated"] = True
                        print(f"[+] Graph database updated with {len(ext_domains)} external domains")
                    else:
                        print(f"[!] Could not connect to Neo4j - skipping external domains graph update")
                        combined_result["metadata"]["graph_db_external_domains_updated"] = False
            except ImportError:
                print(f"[!] Neo4j client not available - skipping external domains graph update")
                combined_result["metadata"]["graph_db_external_domains_updated"] = False
            except Exception as e:
                print(f"[!] External domain graph update failed: {e}")
                combined_result["metadata"]["graph_db_external_domains_updated"] = False

            save_recon_file(combined_result, output_file)

    print(f"\n{'=' * 70}")
    print(f"[+] IP RECON COMPLETE")
    print(f"[+] IPs scanned: {len(expanded_ips)}")
    print(f"[+] Hostnames resolved: {len(all_hostnames)}")
    print(f"[+] Output saved: {output_file}")
    print(f"{'=' * 70}")

    return combined_result


def run_domain_recon(target: str, anonymous: bool = False, bruteforce: bool = False,
                     target_info: dict = None) -> dict:
    """
    Run combined WHOIS + subdomain discovery + DNS resolution.
    Produces a single unified JSON file with incremental saves.

    Scan modes based on SUBDOMAIN_LIST:
    - Empty list []: Full subdomain discovery (discover and scan all subdomains)
    - With entries ["testphp.", "www."]: Filtered mode (only scan specified subdomains)

    Args:
        target: Root domain (e.g., "vulnweb.com", "example.com")
        anonymous: Use Tor to hide real IP
        bruteforce: Enable Knockpy bruteforce mode (only for full discovery mode)
        target_info: Parsed target info from parse_target()

    Returns:
        Complete reconnaissance data including WHOIS and subdomains
    """
    # Parse target if not provided
    if target_info is None:
        target_info = parse_target(target, SUBDOMAIN_LIST)

    filtered_mode = target_info["filtered_mode"]
    root_domain = target_info["root_domain"]
    full_subdomains = target_info["full_subdomains"]

    print("\n" + "=" * 70)
    print("               RedAmon - Domain Reconnaissance")
    print("=" * 70)
    print(f"  Target: {root_domain}")
    if filtered_mode:
        print(f"  Mode: FILTERED SUBDOMAIN SCAN")
        print(f"  Subdomains: {', '.join(full_subdomains)}")
    else:
        print(f"  Mode: FULL DISCOVERY (all subdomains)")
    print(f"  Anonymous Mode: {anonymous}")
    if not filtered_mode:
        print(f"  Bruteforce Mode: {bruteforce}")
    print(f"  WHOIS Retries: {_settings.get('WHOIS_RETRIES', 2)}")
    print(f"  DNS Retries: {_settings.get('DNS_RETRIES', 2)}")
    print("=" * 70 + "\n")

    # Setup output file (use PROJECT_ID for filename)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"recon_{PROJECT_ID}.json"

    # Initialize result structure with dynamic scan_type and empty modules_executed
    combined_result = {
        "metadata": {
            "scan_type": build_scan_type(),
            "scan_timestamp": datetime.now().isoformat(),
            "target": root_domain,
            "root_domain": root_domain,
            "filtered_mode": filtered_mode,
            "subdomain_filter": full_subdomains if filtered_mode else [],
            "anonymous_mode": anonymous,
            "bruteforce_mode": bruteforce if not filtered_mode else False,
            "modules_executed": []
        },
        "domain": root_domain,
        "whois": {},
        "subdomains": [],
        "subdomain_count": 0,
        "dns": {}
    }

    # Step 1: WHOIS lookup (always on root domain)
    print("[PHASE 1] WHOIS Lookup")
    print("-" * 40)
    whois_target = root_domain
    print(f"[*] Performing WHOIS on root domain: {whois_target}")
    try:
        whois_result = whois_lookup(whois_target, save_output=False, settings=_settings)
        combined_result["whois"] = whois_result.get("whois_data", {})
        print(f"[+] WHOIS data retrieved successfully")
    except Exception as e:
        print(f"[!] WHOIS lookup failed: {e}")
        combined_result["whois"] = {"error": str(e)}

    combined_result["metadata"]["modules_executed"].append("whois")
    save_recon_file(combined_result, output_file)
    print(f"[+] Saved: {output_file}")

    # Step 2: Subdomain discovery & DNS resolution
    if filtered_mode:
        # FILTERED MODE: Only scan the specified subdomains from SUBDOMAIN_LIST
        print(f"\n[PHASE 2] Filtered Subdomain DNS Resolution")
        print("-" * 40)
        print(f"[*] Resolving DNS for {len(full_subdomains)} specified host(s)")

        # Import dns_lookup from domain_recon
        from recon.domain_recon import dns_lookup

        # Check if root domain should be included (via "." prefix)
        include_root = target_info.get("include_root_domain", False)
        
        # Resolve root domain DNS if included
        domain_dns = {}
        if include_root:
            print(f"[*] Resolving root domain: {root_domain}")
            domain_dns = dns_lookup(root_domain)
            if domain_dns["ips"]["ipv4"] or domain_dns["ips"]["ipv6"]:
                all_ips = domain_dns["ips"]["ipv4"] + domain_dns["ips"]["ipv6"]
                print(f"[+] {root_domain} -> {', '.join(all_ips)}")
            else:
                print(f"[-] {root_domain}: No DNS records found")

        # Resolve each specified subdomain (excluding root domain which is handled above)
        subdomains_dns = {}
        for subdomain in full_subdomains:
            # Skip root domain (already resolved above)
            if subdomain == root_domain:
                continue
                
            print(f"[*] Resolving: {subdomain}")
            subdomain_dns = dns_lookup(subdomain)
            subdomains_dns[subdomain] = subdomain_dns

            if subdomain_dns["ips"]["ipv4"] or subdomain_dns["ips"]["ipv6"]:
                all_ips = subdomain_dns["ips"]["ipv4"] + subdomain_dns["ips"]["ipv6"]
                print(f"[+] {subdomain} -> {', '.join(all_ips)}")
            else:
                print(f"[-] {subdomain}: No DNS records found")

        combined_result["subdomains"] = full_subdomains
        combined_result["subdomain_count"] = len(full_subdomains)
        combined_result["dns"] = {
            "domain": domain_dns,  # Include root domain DNS if "." was in SUBDOMAIN_LIST
            "subdomains": subdomains_dns
        }
        combined_result["metadata"]["include_root_domain"] = include_root

        combined_result["metadata"]["modules_executed"].append("dns_resolution")
    else:
        # FULL DISCOVERY MODE: Discover all subdomains
        print(f"\n[PHASE 2] Subdomain Discovery & DNS Resolution")
        print("-" * 40)
        recon_result = discover_subdomains(
            root_domain,
            anonymous=anonymous,
            bruteforce=bruteforce,
            resolve=True,
            save_output=False,
            settings=_settings
        )

        discovered_subs = recon_result.get("subdomains", [])
        # RoE: filter dynamically discovered subdomains against exclusion list
        discovered_subs = _filter_roe_excluded(discovered_subs, _settings, label="discovered subdomain")
        combined_result["subdomains"] = discovered_subs
        combined_result["subdomain_count"] = len(discovered_subs)
        combined_result["metadata"]["modules_executed"].append("subdomain_discovery")
        # Capture external domains from cert discovery
        if recon_result.get("external_domains"):
            combined_result["domain_discovery_external_domains"] = recon_result["external_domains"]
        save_recon_file(combined_result, output_file)
        print(f"[+] Saved: {output_file}")

        # Step 3: DNS resolution (already done in discover_subdomains)
        combined_result["dns"] = recon_result.get("dns", {})
        combined_result["metadata"]["modules_executed"].append("dns_resolution")

    save_recon_file(combined_result, output_file)
    print(f"[+] Saved: {output_file}")

    # Update Graph DB after domain_discovery completes
    if UPDATE_GRAPH_DB:
        print(f"\n[PHASE 3] Graph Database Update")
        print("-" * 40)
        try:
            from graph_db import Neo4jClient
            with Neo4jClient() as graph_client:
                if graph_client.verify_connection():
                    stats = graph_client.update_graph_from_domain_discovery(combined_result, USER_ID, PROJECT_ID)
                    combined_result["metadata"]["graph_db_updated"] = True
                    combined_result["metadata"]["graph_db_stats"] = stats
                    print(f"[+] Graph database updated successfully")
                else:
                    print(f"[!] Could not connect to Neo4j - skipping graph update")
                    combined_result["metadata"]["graph_db_updated"] = False
        except ImportError:
            print(f"[!] Neo4j client not available - skipping graph update")
            combined_result["metadata"]["graph_db_updated"] = False
        except Exception as e:
            print(f"[!] Graph DB update failed: {e}")
            combined_result["metadata"]["graph_db_updated"] = False
            combined_result["metadata"]["graph_db_error"] = str(e)

        save_recon_file(combined_result, output_file)

    # Step 2.5: Shodan OSINT Enrichment (passive — runs before port scan)
    shodan_enabled = any([
        _settings.get('SHODAN_HOST_LOOKUP'),
        _settings.get('SHODAN_REVERSE_DNS'),
        _settings.get('SHODAN_DOMAIN_DNS'),
        _settings.get('SHODAN_PASSIVE_CVES'),
    ])
    if shodan_enabled:
        from recon.shodan_enrich import run_shodan_enrichment
        combined_result = run_shodan_enrichment(combined_result, _settings)
        combined_result["metadata"]["modules_executed"].append("shodan_enrich")
        save_recon_file(combined_result, output_file)

        if UPDATE_GRAPH_DB:
            print(f"\n[GRAPH UPDATE] Shodan Enrichment Data")
            print("-" * 40)
            try:
                from graph_db import Neo4jClient
                with Neo4jClient() as graph_client:
                    if graph_client.verify_connection():
                        shodan_stats = graph_client.update_graph_from_shodan(combined_result, USER_ID, PROJECT_ID)
                        combined_result["metadata"]["graph_db_shodan_updated"] = True
                        combined_result["metadata"]["graph_db_shodan_stats"] = shodan_stats
                        print(f"[+] Graph database updated with Shodan data")
                    else:
                        print(f"[!] Could not connect to Neo4j - skipping Shodan graph update")
                        combined_result["metadata"]["graph_db_shodan_updated"] = False
            except ImportError:
                print(f"[!] Neo4j client not available - skipping Shodan graph update")
                combined_result["metadata"]["graph_db_shodan_updated"] = False
            except Exception as e:
                print(f"[!] Shodan graph update failed: {e}")
                combined_result["metadata"]["graph_db_shodan_updated"] = False
                combined_result["metadata"]["graph_db_shodan_error"] = str(e)

            save_recon_file(combined_result, output_file)

    # URLScan.io Passive Enrichment (after domain discovery, before port scan)
    if _settings.get('URLSCAN_ENABLED'):
        from recon.urlscan_enrich import run_urlscan_enrichment
        combined_result = run_urlscan_enrichment(combined_result, _settings)
        combined_result["metadata"]["modules_executed"].append("urlscan_enrich")
        save_recon_file(combined_result, output_file)

        # Phase A: Subdomain/IP discovery graph update
        if UPDATE_GRAPH_DB:
            print(f"\n[GRAPH UPDATE] URLScan Discovery Data")
            print("-" * 40)
            try:
                from graph_db import Neo4jClient
                with Neo4jClient() as graph_client:
                    if graph_client.verify_connection():
                        urlscan_disc_stats = graph_client.update_graph_from_urlscan_discovery(combined_result, USER_ID, PROJECT_ID)
                        combined_result["metadata"]["graph_db_urlscan_discovery_updated"] = True
                        combined_result["metadata"]["graph_db_urlscan_discovery_stats"] = urlscan_disc_stats
                        print(f"[+] Graph database updated with URLScan discovery data")
                    else:
                        print(f"[!] Could not connect to Neo4j - skipping URLScan discovery graph update")
                        combined_result["metadata"]["graph_db_urlscan_discovery_updated"] = False
            except ImportError:
                print(f"[!] Neo4j client not available - skipping URLScan discovery graph update")
                combined_result["metadata"]["graph_db_urlscan_discovery_updated"] = False
            except Exception as e:
                print(f"[!] URLScan discovery graph update failed: {e}")
                combined_result["metadata"]["graph_db_urlscan_discovery_updated"] = False
                combined_result["metadata"]["graph_db_urlscan_discovery_error"] = str(e)

            save_recon_file(combined_result, output_file)

    # Step 3: Port scanning (fast port discovery)
    if "port_scan" in SCAN_MODULES:
        combined_result = run_port_scan(combined_result, output_file=output_file, settings=_settings)
        combined_result["metadata"]["modules_executed"].append("port_scan")
        save_recon_file(combined_result, output_file)

        # Update Graph DB with port scan data
        if UPDATE_GRAPH_DB:
            print(f"\n[GRAPH UPDATE] Port Scan Data")
            print("-" * 40)
            try:
                from graph_db import Neo4jClient
                with Neo4jClient() as graph_client:
                    if graph_client.verify_connection():
                        port_stats = graph_client.update_graph_from_port_scan(combined_result, USER_ID, PROJECT_ID)
                        combined_result["metadata"]["graph_db_port_scan_updated"] = True
                        combined_result["metadata"]["graph_db_port_scan_stats"] = port_stats
                        print(f"[+] Graph database updated with port scan data")
                    else:
                        print(f"[!] Could not connect to Neo4j - skipping port scan graph update")
                        combined_result["metadata"]["graph_db_port_scan_updated"] = False
            except ImportError:
                print(f"[!] Neo4j client not available - skipping port scan graph update")
                combined_result["metadata"]["graph_db_port_scan_updated"] = False
            except Exception as e:
                print(f"[!] Port scan graph update failed: {e}")
                combined_result["metadata"]["graph_db_port_scan_updated"] = False
                combined_result["metadata"]["graph_db_port_scan_error"] = str(e)

            save_recon_file(combined_result, output_file)

    # Step 4: HTTP probing (technology detection, live URL discovery)
    if "http_probe" in SCAN_MODULES:
        combined_result = run_http_probe(combined_result, output_file=output_file, settings=_settings)
        combined_result["metadata"]["modules_executed"].append("http_probe")
        save_recon_file(combined_result, output_file)

        # Update Graph DB with http probe data
        if UPDATE_GRAPH_DB:
            print(f"\n[GRAPH UPDATE] HTTP Probe Data")
            print("-" * 40)
            try:
                from graph_db import Neo4jClient
                with Neo4jClient() as graph_client:
                    if graph_client.verify_connection():
                        http_stats = graph_client.update_graph_from_http_probe(combined_result, USER_ID, PROJECT_ID)
                        combined_result["metadata"]["graph_db_http_probe_updated"] = True
                        combined_result["metadata"]["graph_db_http_probe_stats"] = http_stats
                        print(f"[+] Graph database updated with http probe data")
                    else:
                        print(f"[!] Could not connect to Neo4j - skipping http probe graph update")
                        combined_result["metadata"]["graph_db_http_probe_updated"] = False
            except ImportError:
                print(f"[!] Neo4j client not available - skipping http probe graph update")
                combined_result["metadata"]["graph_db_http_probe_updated"] = False
            except Exception as e:
                print(f"[!] HTTP probe graph update failed: {e}")
                combined_result["metadata"]["graph_db_http_probe_updated"] = False
                combined_result["metadata"]["graph_db_http_probe_error"] = str(e)

            save_recon_file(combined_result, output_file)

        # URLScan Phase B: Enrich BaseURLs + create Endpoints (only after http_probe confirmed live URLs)
        if 'urlscan' in combined_result and UPDATE_GRAPH_DB:
            print(f"\n[GRAPH UPDATE] URLScan Enrichment Data (Phase B)")
            print("-" * 40)
            try:
                from graph_db import Neo4jClient
                with Neo4jClient() as graph_client:
                    if graph_client.verify_connection():
                        urlscan_enrich_stats = graph_client.update_graph_from_urlscan_enrichment(combined_result, USER_ID, PROJECT_ID)
                        combined_result["metadata"]["graph_db_urlscan_enrichment_updated"] = True
                        combined_result["metadata"]["graph_db_urlscan_enrichment_stats"] = urlscan_enrich_stats
                        print(f"[+] Graph database updated with URLScan enrichment data")
                    else:
                        print(f"[!] Could not connect to Neo4j - skipping URLScan enrichment graph update")
                        combined_result["metadata"]["graph_db_urlscan_enrichment_updated"] = False
            except ImportError:
                print(f"[!] Neo4j client not available - skipping URLScan enrichment graph update")
                combined_result["metadata"]["graph_db_urlscan_enrichment_updated"] = False
            except Exception as e:
                print(f"[!] URLScan enrichment graph update failed: {e}")
                combined_result["metadata"]["graph_db_urlscan_enrichment_updated"] = False
                combined_result["metadata"]["graph_db_urlscan_enrichment_error"] = str(e)

            save_recon_file(combined_result, output_file)

    # Check if we should skip active scanning modules (resource_enum, vuln_scan)
    # These require live targets from http_probe to work
    skip_active_scans, skip_reason = should_skip_active_scans(combined_result)
    
    if skip_active_scans:
        print(f"\n{'=' * 70}")
        print(f"[!] SKIPPING ACTIVE SCANS: {skip_reason}")
        print(f"[!] Modules skipped: resource_enum, vuln_scan")
        print(f"{'=' * 70}")
        combined_result["metadata"]["active_scans_skipped"] = True
        combined_result["metadata"]["active_scans_skip_reason"] = skip_reason
        save_recon_file(combined_result, output_file)
    else:
        # Step 5: Resource enumeration (endpoint discovery & classification)
        if "resource_enum" in SCAN_MODULES:
            combined_result = run_resource_enum(combined_result, output_file=output_file, settings=_settings)
            combined_result["metadata"]["modules_executed"].append("resource_enum")
            save_recon_file(combined_result, output_file)

            # Update Graph DB with resource enumeration data
            if UPDATE_GRAPH_DB:
                print(f"\n[GRAPH UPDATE] Resource Enumeration Data")
                print("-" * 40)
                try:
                    from graph_db import Neo4jClient
                    with Neo4jClient() as graph_client:
                        if graph_client.verify_connection():
                            resource_stats = graph_client.update_graph_from_resource_enum(combined_result, USER_ID, PROJECT_ID)
                            combined_result["metadata"]["graph_db_resource_enum_updated"] = True
                            combined_result["metadata"]["graph_db_resource_enum_stats"] = resource_stats
                            print(f"[+] Graph database updated with resource enumeration data")
                        else:
                            print(f"[!] Could not connect to Neo4j - skipping resource enum graph update")
                            combined_result["metadata"]["graph_db_resource_enum_updated"] = False
                except ImportError:
                    print(f"[!] Neo4j client not available - skipping resource enum graph update")
                    combined_result["metadata"]["graph_db_resource_enum_updated"] = False
                except Exception as e:
                    print(f"[!] Resource enum graph update failed: {e}")
                    combined_result["metadata"]["graph_db_resource_enum_updated"] = False
                    combined_result["metadata"]["graph_db_resource_enum_error"] = str(e)

                save_recon_file(combined_result, output_file)

        # Step 6: Vulnerability scanning (web application vulns) + MITRE enrichment
        if "vuln_scan" in SCAN_MODULES:
            combined_result = run_vuln_scan(combined_result, output_file=output_file, settings=_settings)
            combined_result["metadata"]["modules_executed"].append("vuln_scan")
            save_recon_file(combined_result, output_file)

            # Automatically run MITRE CWE/CAPEC enrichment after vuln_scan
            combined_result = run_mitre_enrichment(combined_result, output_file=output_file, settings=_settings)
            save_recon_file(combined_result, output_file)

            # Update Graph DB with vuln scan data
            if UPDATE_GRAPH_DB:
                print(f"\n[GRAPH UPDATE] Vuln Scan Data")
                print("-" * 40)
                try:
                    from graph_db import Neo4jClient
                    with Neo4jClient() as graph_client:
                        if graph_client.verify_connection():
                            vuln_stats = graph_client.update_graph_from_vuln_scan(combined_result, USER_ID, PROJECT_ID)
                            combined_result["metadata"]["graph_db_vuln_scan_updated"] = True
                            combined_result["metadata"]["graph_db_vuln_scan_stats"] = vuln_stats
                            print(f"[+] Graph database updated with vuln scan data")
                        else:
                            print(f"[!] Could not connect to Neo4j - skipping vuln scan graph update")
                            combined_result["metadata"]["graph_db_vuln_scan_updated"] = False
                except ImportError:
                    print(f"[!] Neo4j client not available - skipping vuln scan graph update")
                    combined_result["metadata"]["graph_db_vuln_scan_updated"] = False
                except Exception as e:
                    print(f"[!] Vuln scan graph update failed: {e}")
                    combined_result["metadata"]["graph_db_vuln_scan_updated"] = False
                    combined_result["metadata"]["graph_db_vuln_scan_error"] = str(e)

                save_recon_file(combined_result, output_file)

    # External Domains — aggregate from all sources and persist
    ext_domains = _aggregate_external_domains(combined_result)
    if ext_domains:
        combined_result["external_domains_aggregated"] = ext_domains
        save_recon_file(combined_result, output_file)

        if UPDATE_GRAPH_DB:
            print(f"\n[GRAPH UPDATE] External Domains")
            print("-" * 40)
            try:
                from graph_db import Neo4jClient
                with Neo4jClient() as graph_client:
                    if graph_client.verify_connection():
                        graph_client.update_graph_from_external_domains(
                            combined_result, USER_ID, PROJECT_ID
                        )
                        combined_result["metadata"]["graph_db_external_domains_updated"] = True
                        print(f"[+] Graph database updated with {len(ext_domains)} external domains")
                    else:
                        print(f"[!] Could not connect to Neo4j - skipping external domains graph update")
                        combined_result["metadata"]["graph_db_external_domains_updated"] = False
            except ImportError:
                print(f"[!] Neo4j client not available - skipping external domains graph update")
                combined_result["metadata"]["graph_db_external_domains_updated"] = False
            except Exception as e:
                print(f"[!] External domain graph update failed: {e}")
                combined_result["metadata"]["graph_db_external_domains_updated"] = False

            save_recon_file(combined_result, output_file)

    # Print summary
    print(f"\n{'=' * 70}")
    print(f"[+] DOMAIN RECON COMPLETE")
    if filtered_mode:
        print(f"[+] Mode: Filtered ({len(full_subdomains)} subdomain(s))")
    else:
        print(f"[+] Subdomains found: {combined_result['subdomain_count']}")
    
    # Port scan stats
    if "port_scan" in SCAN_MODULES and "port_scan" in combined_result:
        port_summary = combined_result["port_scan"].get("summary", {})
        print(f"[+] Open ports: {port_summary.get('total_open_ports', 0)}")
    
    # HTTP probe stats
    if "http_probe" in SCAN_MODULES and "http_probe" in combined_result:
        http_summary = combined_result["http_probe"].get("summary", {})
        print(f"[+] Live URLs: {http_summary.get('live_urls', 0)}")
        print(f"[+] Technologies: {http_summary.get('technology_count', 0)}")

    # Check if active scans were skipped
    active_scans_skipped = combined_result.get("metadata", {}).get("active_scans_skipped", False)

    # Resource enumeration stats
    if active_scans_skipped:
        print(f"[!] Resource enum: SKIPPED (no live targets)")
    elif "resource_enum" in SCAN_MODULES and "resource_enum" in combined_result:
        resource_summary = combined_result["resource_enum"].get("summary", {})
        print(f"[+] Endpoints: {resource_summary.get('total_endpoints', 0)}")
        print(f"[+] Parameters: {resource_summary.get('total_parameters', 0)}")
        print(f"[+] Forms (POST): {resource_summary.get('total_forms', 0)}")

    # Vuln scan stats (includes MITRE enrichment)
    if active_scans_skipped:
        print(f"[!] Vuln scan: SKIPPED (no live targets)")
    elif "vuln_scan" in SCAN_MODULES and "vuln_scan" in combined_result:
        vuln_summary = combined_result["vuln_scan"].get("summary", {})
        vuln_total = combined_result["vuln_scan"].get("vulnerabilities", {}).get("total", 0)
        print(f"[+] Vuln findings: {vuln_summary.get('total_findings', 0)} ({vuln_total} vulnerabilities)")

        # MITRE enrichment stats (part of vuln_scan)
        mitre_meta = combined_result.get("metadata", {}).get("mitre_enrichment", {})
        if mitre_meta:
            print(f"[+] MITRE enriched: {mitre_meta.get('total_cves_enriched', 0)}/{mitre_meta.get('total_cves_processed', 0)} CVEs")

    print(f"[+] Output saved: {output_file}")
    print(f"{'=' * 70}")

    return combined_result


def main():
    """
    Main entry point - runs the complete recon pipeline.

    Pipeline: domain_discovery -> port_scan -> http_probe -> resource_enum -> vuln_scan

    Scan modes based on SUBDOMAIN_LIST:
    - Empty list []: Full subdomain discovery (discover and scan all subdomains)
    - With entries ["testphp.", "www."]: Filtered mode (only scan specified subdomains)
    """
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 20 + "RedAmon OSINT Framework" + " " * 25 + "║")
    print("║" + " " * 15 + "Automated Reconnaissance Pipeline" + " " * 18 + "║")
    print("╚" + "═" * 68 + "╝")
    print()

    start_time = datetime.now()

    # IP Mode: skip domain verification and run IP-based recon instead
    if IP_MODE and TARGET_IPS:
        print(f"  MODE:              IP-BASED TARGETING")
        print(f"  TARGET_IPS:        {', '.join(TARGET_IPS)}")
        print(f"  SCAN_MODULES:      {','.join(SCAN_MODULES) if isinstance(SCAN_MODULES, list) else SCAN_MODULES}")
        print(f"  UPDATE_GRAPH_DB:   {UPDATE_GRAPH_DB}")
        print(f"  USER_ID:           {USER_ID}")
        print(f"  PROJECT_ID:        {PROJECT_ID}")
        print("═" * 63)

        # Clear previous graph data
        if UPDATE_GRAPH_DB:
            print("[*] Clearing previous graph data for this project...")
            try:
                from graph_db import Neo4jClient
                with Neo4jClient() as graph_client:
                    if graph_client.verify_connection():
                        clear_stats = graph_client.clear_project_data(USER_ID, PROJECT_ID)
                        print(f"[+] Previous data cleared: {clear_stats['nodes_deleted']} nodes removed\n")
                    else:
                        print("[!] Could not connect to Neo4j - skipping clear\n")
            except Exception as e:
                print(f"[!] Failed to clear previous graph data: {e}\n")

        run_ip_recon(TARGET_IPS, _settings)

        end_time = datetime.now()
        duration = end_time - start_time
        print(f"\n[+] Total time: {duration}")
        return 0

    # Domain Ownership Verification (if enabled)
    # This MUST be the first check before any scanning to ensure we only
    # scan domains the user controls.
    if VERIFY_DOMAIN_OWNERSHIP:
        ownership_result = verify_domain_ownership(
            TARGET_DOMAIN,
            OWNERSHIP_TOKEN,
            OWNERSHIP_TXT_PREFIX
        )

        if not ownership_result["verified"]:
            print(f"\n[!] SCAN ABORTED: Domain ownership verification failed!")
            print(f"[!] Add TXT record: {ownership_result['record_name']} → \"{ownership_result['expected_value']}\"")
            print(f"[!] Set VERIFY_DOMAIN_OWNERSHIP = False in params.py to disable\n")
            return 1

    # Parse target with SUBDOMAIN_LIST filter
    target_info = parse_target(TARGET_DOMAIN, SUBDOMAIN_LIST)
    filtered_mode = target_info["filtered_mode"]
    root_domain = target_info["root_domain"]
    full_subdomains = target_info["full_subdomains"]

    # RoE: filter out excluded hosts from subdomains
    full_subdomains = _filter_roe_excluded(full_subdomains, _settings, label="subdomain")
    target_info["full_subdomains"] = full_subdomains

    # Display full configuration (values loaded from DB/API)
    print("═" * 63)
    print("Configuration:")
    print(f"  TARGET_DOMAIN:     {TARGET_DOMAIN}")
    print(f"  SUBDOMAIN_LIST:    {SUBDOMAIN_LIST if SUBDOMAIN_LIST else '[] (full discovery)'}")
    print(f"  SCAN_MODULES:      {','.join(SCAN_MODULES) if isinstance(SCAN_MODULES, list) else SCAN_MODULES}")
    print(f"  USE_TOR_FOR_RECON: {USE_TOR_FOR_RECON}")
    print(f"  STEALTH_MODE:      {_settings.get('STEALTH_MODE', False)}")
    print(f"  UPDATE_GRAPH_DB:   {UPDATE_GRAPH_DB}")
    print(f"  USER_ID:           {USER_ID}")
    print(f"  PROJECT_ID:        {PROJECT_ID}")
    if filtered_mode:
        print(f"  MODE:              FILTERED SUBDOMAIN SCAN")
        print(f"  SUBDOMAINS:        {', '.join(full_subdomains)}")
    else:
        print(f"  MODE:              FULL DISCOVERY (all subdomains)")
    print("═" * 63)

    if _settings.get('STEALTH_MODE', False):
        print()
        print("  ╔══════════════════════════════════════════════════════════╗")
        print("  ║  STEALTH MODE ACTIVE — passive/low-noise only           ║")
        print("  ║  Kiterunner: OFF | Banner Grab: OFF | Brute Force: OFF  ║")
        print("  ║  Naabu: passive | httpx: 2 req/s | Nuclei: no DAST     ║")
        print("  ╚══════════════════════════════════════════════════════════╝")

    print()

    # Clear previous graph data for this project before starting new scan
    if UPDATE_GRAPH_DB:
        print("[*] Clearing previous graph data for this project...")
        try:
            from graph_db import Neo4jClient
            with Neo4jClient() as graph_client:
                if graph_client.verify_connection():
                    clear_stats = graph_client.clear_project_data(USER_ID, PROJECT_ID)
                    print(f"[+] Previous data cleared: {clear_stats['nodes_deleted']} nodes removed\n")
                else:
                    print("[!] Could not connect to Neo4j - skipping clear\n")
        except Exception as e:
            print(f"[!] Failed to clear previous graph data: {e}\n")

    # Check anonymity status if Tor is enabled
    if USE_TOR_FOR_RECON:
        try:
            from recon.helpers.anonymity import print_anonymity_status
            print_anonymity_status()
        except ImportError:
            print("[!] Anonymity module not found, proceeding without Tor status check")

    # Phase 1 & 2: Domain recon (WHOIS + Subdomains + DNS) - Combined JSON
    output_file = Path(__file__).parent / "output" / f"recon_{PROJECT_ID}.json"

    if "domain_discovery" in SCAN_MODULES:
        domain_result = run_domain_recon(
            TARGET_DOMAIN,
            anonymous=USE_TOR_FOR_RECON,
            bruteforce=USE_BRUTEFORCE_FOR_SUBDOMAINS,
            target_info=target_info
        )
    else:
        # Load existing recon file if domain_discovery not in modules
        if output_file.exists():
            with open(output_file, 'r') as f:
                domain_result = json.load(f)
            print(f"[*] Loaded existing recon file: {output_file}")
        else:
            print(f"[!] No existing recon file found: {output_file}")
            print(f"[!] Add 'domain_discovery' to SCAN_MODULES to create it first")
            return 1
        
        # Run port_scan if in SCAN_MODULES (when domain_discovery is skipped)
        if "port_scan" in SCAN_MODULES:
            domain_result = run_port_scan(domain_result, output_file=output_file, settings=_settings)
            if "metadata" in domain_result and "modules_executed" in domain_result["metadata"]:
                if "port_scan" not in domain_result["metadata"]["modules_executed"]:
                    domain_result["metadata"]["modules_executed"].append("port_scan")
            with open(output_file, 'w') as f:
                json.dump(domain_result, f, indent=2)

            # Update Graph DB with port scan data
            if UPDATE_GRAPH_DB:
                print(f"\n[GRAPH UPDATE] Port Scan Data")
                print("-" * 40)
                try:
                    from graph_db import Neo4jClient
                    with Neo4jClient() as graph_client:
                        if graph_client.verify_connection():
                            port_stats = graph_client.update_graph_from_port_scan(domain_result, USER_ID, PROJECT_ID)
                            domain_result["metadata"]["graph_db_port_scan_updated"] = True
                            domain_result["metadata"]["graph_db_port_scan_stats"] = port_stats
                            print(f"[+] Graph database updated with port scan data")
                        else:
                            print(f"[!] Could not connect to Neo4j - skipping port scan graph update")
                            domain_result["metadata"]["graph_db_port_scan_updated"] = False
                except ImportError:
                    print(f"[!] Neo4j client not available - skipping port scan graph update")
                    domain_result["metadata"]["graph_db_port_scan_updated"] = False
                except Exception as e:
                    print(f"[!] Port scan graph update failed: {e}")
                    domain_result["metadata"]["graph_db_port_scan_updated"] = False
                    domain_result["metadata"]["graph_db_port_scan_error"] = str(e)

                with open(output_file, 'w') as f:
                    json.dump(domain_result, f, indent=2)
        
        # Run http_probe if in SCAN_MODULES (when domain_discovery is skipped)
        if "http_probe" in SCAN_MODULES:
            domain_result = run_http_probe(domain_result, output_file=output_file, settings=_settings)
            if "metadata" in domain_result and "modules_executed" in domain_result["metadata"]:
                if "http_probe" not in domain_result["metadata"]["modules_executed"]:
                    domain_result["metadata"]["modules_executed"].append("http_probe")
            with open(output_file, 'w') as f:
                json.dump(domain_result, f, indent=2)

            # Update Graph DB with http probe data
            if UPDATE_GRAPH_DB:
                print(f"\n[GRAPH UPDATE] HTTP Probe Data")
                print("-" * 40)
                try:
                    from graph_db import Neo4jClient
                    with Neo4jClient() as graph_client:
                        if graph_client.verify_connection():
                            http_stats = graph_client.update_graph_from_http_probe(domain_result, USER_ID, PROJECT_ID)
                            domain_result["metadata"]["graph_db_http_probe_updated"] = True
                            domain_result["metadata"]["graph_db_http_probe_stats"] = http_stats
                            print(f"[+] Graph database updated with http probe data")
                        else:
                            print(f"[!] Could not connect to Neo4j - skipping http probe graph update")
                            domain_result["metadata"]["graph_db_http_probe_updated"] = False
                except ImportError:
                    print(f"[!] Neo4j client not available - skipping http probe graph update")
                    domain_result["metadata"]["graph_db_http_probe_updated"] = False
                except Exception as e:
                    print(f"[!] HTTP probe graph update failed: {e}")
                    domain_result["metadata"]["graph_db_http_probe_updated"] = False
                    domain_result["metadata"]["graph_db_http_probe_error"] = str(e)

                with open(output_file, 'w') as f:
                    json.dump(domain_result, f, indent=2)

        # Check if we should skip active scanning modules (resource_enum, vuln_scan)
        # These require live targets from http_probe to work
        skip_active_scans, skip_reason = should_skip_active_scans(domain_result)
        
        if skip_active_scans:
            print(f"\n{'=' * 70}")
            print(f"[!] SKIPPING ACTIVE SCANS: {skip_reason}")
            print(f"[!] Modules skipped: resource_enum, vuln_scan")
            print(f"{'=' * 70}")
            if "metadata" in domain_result:
                domain_result["metadata"]["active_scans_skipped"] = True
                domain_result["metadata"]["active_scans_skip_reason"] = skip_reason
            with open(output_file, 'w') as f:
                json.dump(domain_result, f, indent=2)
        else:
            # Run resource_enum if in SCAN_MODULES (when domain_discovery is skipped)
            if "resource_enum" in SCAN_MODULES:
                domain_result = run_resource_enum(domain_result, output_file=output_file, settings=_settings)
                if "metadata" in domain_result and "modules_executed" in domain_result["metadata"]:
                    if "resource_enum" not in domain_result["metadata"]["modules_executed"]:
                        domain_result["metadata"]["modules_executed"].append("resource_enum")
                with open(output_file, 'w') as f:
                    json.dump(domain_result, f, indent=2)

                # Update Graph DB with resource enumeration data
                if UPDATE_GRAPH_DB:
                    print(f"\n[GRAPH UPDATE] Resource Enumeration Data")
                    print("-" * 40)
                    try:
                        from graph_db import Neo4jClient
                        with Neo4jClient() as graph_client:
                            if graph_client.verify_connection():
                                resource_stats = graph_client.update_graph_from_resource_enum(domain_result, USER_ID, PROJECT_ID)
                                domain_result["metadata"]["graph_db_resource_enum_updated"] = True
                                domain_result["metadata"]["graph_db_resource_enum_stats"] = resource_stats
                                print(f"[+] Graph database updated with resource enumeration data")
                            else:
                                print(f"[!] Could not connect to Neo4j - skipping resource enum graph update")
                                domain_result["metadata"]["graph_db_resource_enum_updated"] = False
                    except ImportError:
                        print(f"[!] Neo4j client not available - skipping resource enum graph update")
                        domain_result["metadata"]["graph_db_resource_enum_updated"] = False
                    except Exception as e:
                        print(f"[!] Resource enum graph update failed: {e}")
                        domain_result["metadata"]["graph_db_resource_enum_updated"] = False
                        domain_result["metadata"]["graph_db_resource_enum_error"] = str(e)

                    with open(output_file, 'w') as f:
                        json.dump(domain_result, f, indent=2)

            # Run vuln_scan if in SCAN_MODULES (when domain_discovery is skipped)
            # vuln_scan automatically includes MITRE CWE/CAPEC enrichment
            if "vuln_scan" in SCAN_MODULES:
                domain_result = run_vuln_scan(domain_result, output_file=output_file, settings=_settings)
                if "metadata" in domain_result and "modules_executed" in domain_result["metadata"]:
                    if "vuln_scan" not in domain_result["metadata"]["modules_executed"]:
                        domain_result["metadata"]["modules_executed"].append("vuln_scan")
                with open(output_file, 'w') as f:
                    json.dump(domain_result, f, indent=2)

                # Automatically run MITRE CWE/CAPEC enrichment after vuln_scan
                domain_result = run_mitre_enrichment(domain_result, output_file=output_file, settings=_settings)
                with open(output_file, 'w') as f:
                    json.dump(domain_result, f, indent=2)

                # Update Graph DB with vuln scan data
                if UPDATE_GRAPH_DB:
                    print(f"\n[GRAPH UPDATE] Vuln Scan Data")
                    print("-" * 40)
                    try:
                        from graph_db import Neo4jClient
                        with Neo4jClient() as graph_client:
                            if graph_client.verify_connection():
                                vuln_stats = graph_client.update_graph_from_vuln_scan(domain_result, USER_ID, PROJECT_ID)
                                domain_result["metadata"]["graph_db_vuln_scan_updated"] = True
                                domain_result["metadata"]["graph_db_vuln_scan_stats"] = vuln_stats
                                print(f"[+] Graph database updated with vuln scan data")
                            else:
                                print(f"[!] Could not connect to Neo4j - skipping vuln scan graph update")
                                domain_result["metadata"]["graph_db_vuln_scan_updated"] = False
                    except ImportError:
                        print(f"[!] Neo4j client not available - skipping vuln scan graph update")
                        domain_result["metadata"]["graph_db_vuln_scan_updated"] = False
                    except Exception as e:
                        print(f"[!] Vuln scan graph update failed: {e}")
                        domain_result["metadata"]["graph_db_vuln_scan_updated"] = False
                        domain_result["metadata"]["graph_db_vuln_scan_error"] = str(e)

                    with open(output_file, 'w') as f:
                        json.dump(domain_result, f, indent=2)

    # Final summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("\n")
    print("─" * 50)
    print("  RECON PIPELINE COMPLETE")
    print("─" * 50)
    print(f"  Duration: {duration:.2f} seconds")
    print(f"  Target: {root_domain}")
    if filtered_mode:
        print(f"  Mode: Filtered ({len(full_subdomains)} subdomain(s))")
    else:
        print(f"  Mode: Full discovery")
        print(f"  Subdomains found: {domain_result.get('subdomain_count', 0)}")

    # Port scan stats
    if "port_scan" in SCAN_MODULES and "port_scan" in domain_result:
        port_summary = domain_result["port_scan"].get("summary", {})
        ports = port_summary.get('total_open_ports', 0)
        hosts = port_summary.get('hosts_with_open_ports', 0)
        print(f"  Port Scan: {hosts} hosts, {ports} ports")
    elif "port_scan" not in SCAN_MODULES:
        print("  Port Scan: SKIPPED")

    # HTTP probe stats
    if "http_probe" in SCAN_MODULES and "http_probe" in domain_result:
        http_summary = domain_result["http_probe"].get("summary", {})
        live = http_summary.get('live_urls', 0)
        techs = http_summary.get('technology_count', 0)
        print(f"  HTTP Probe: {live} live URLs, {techs} technologies")
    elif "http_probe" not in SCAN_MODULES:
        print("  HTTP Probe: SKIPPED")

    # Check if active scans were skipped due to no live targets
    active_scans_skipped = domain_result.get("metadata", {}).get("active_scans_skipped", False)
    skip_reason = domain_result.get("metadata", {}).get("active_scans_skip_reason", "")

    # Resource enumeration stats
    if active_scans_skipped:
        print(f"  Resources: SKIPPED (no live targets)")
    elif "resource_enum" in SCAN_MODULES and "resource_enum" in domain_result:
        res_summary = domain_result["resource_enum"].get("summary", {})
        endpoints = res_summary.get('total_endpoints', 0)
        params = res_summary.get('total_parameters', 0)
        forms = res_summary.get('total_forms', 0)
        print(f"  Resources: {endpoints} endpoints, {params} params, {forms} forms")
    elif "resource_enum" not in SCAN_MODULES:
        print("  Resources: SKIPPED")

    # Vuln scan stats (includes MITRE enrichment)
    if active_scans_skipped:
        print(f"  Vuln Scan: SKIPPED (no live targets)")
    elif "vuln_scan" in SCAN_MODULES and "vuln_scan" in domain_result:
        vuln_summary = domain_result["vuln_scan"].get("summary", {})
        total_findings = vuln_summary.get("total_findings", 0)
        crit = vuln_summary.get("critical", 0)
        high = vuln_summary.get("high", 0)
        vuln_info = f"{total_findings} findings"
        if crit > 0 or high > 0:
            vuln_info += f" ({crit} critical, {high} high)"
        print(f"  Vuln Scan: {vuln_info}")

        # MITRE enrichment stats (part of vuln_scan)
        mitre_meta = domain_result.get("metadata", {}).get("mitre_enrichment", {})
        if mitre_meta:
            enriched = mitre_meta.get('total_cves_enriched', 0)
            total = mitre_meta.get('total_cves_processed', 0)
            print(f"  MITRE CWE/CAPEC: {enriched}/{total} CVEs enriched")
    elif "vuln_scan" not in SCAN_MODULES:
        print("  Vuln Scan: SKIPPED")

    print("─" * 50)
    print("  Output: recon_{}.json".format(PROJECT_ID))
    print("─" * 50)
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())

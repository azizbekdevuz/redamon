#!/usr/bin/env bash
# =============================================================================
# RedAmon CLI - Simplified installation, update, and lifecycle management
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_FILE="$SCRIPT_DIR/VERSION"
GVM_FLAG_FILE="$SCRIPT_DIR/.gvm-enabled"

# Service lists
CORE_SERVICES="postgres neo4j recon-orchestrator kali-sandbox agent webapp"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

print_banner() {
    echo -e "${RED}${BOLD}"
    echo "  ____          _    _                         "
    echo " |  _ \\ ___  __| |  / \\   _ __ ___   ___  _ __"
    echo " | |_) / _ \\/ _\` | / _ \\ | '_ \` _ \\ / _ \\| '_ \\ "
    echo " |  _ <  __/ (_| |/ ___ \\| | | | | | (_) | | | |"
    echo " |_| \\_\\___|\\__,_/_/   \\_\\_| |_| |_|\\___/|_| |_|"
    echo -e "${NC}"
}

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }

get_version() {
    if [[ -f "$VERSION_FILE" ]]; then
        cat "$VERSION_FILE" | tr -d '[:space:]'
    else
        echo "unknown"
    fi
}

is_gvm_enabled() {
    [[ -f "$GVM_FLAG_FILE" ]]
}

check_prerequisites() {
    local missing=0

    if ! command -v docker &>/dev/null; then
        error "Docker is not installed. See: https://docs.docker.com/get-docker/"
        missing=1
    fi

    if ! docker compose version &>/dev/null; then
        error "Docker Compose v2 is not installed. See: https://docs.docker.com/compose/install/"
        missing=1
    fi

    if ! command -v git &>/dev/null; then
        error "Git is not installed."
        missing=1
    fi

    if [[ $missing -eq 1 ]]; then
        exit 1
    fi
}

export_version() {
    export REDAMON_VERSION
    REDAMON_VERSION="$(get_version)"
}

remove_redamon_images() {
    # Remove locally-built redamon images
    docker images --format '{{.Repository}}:{{.Tag}}' \
        | grep '^redamon-' \
        | xargs -r docker rmi 2>/dev/null || true

    # Remove GVM / Greenbone images
    docker images --format '{{.Repository}}:{{.Tag}}' \
        | grep 'registry.community.greenbone.net' \
        | xargs -r docker rmi 2>/dev/null || true

    # Remove ProjectDiscovery + recon tool images (pulled at runtime by entrypoint)
    local runtime_images=(
        "projectdiscovery/naabu"
        "projectdiscovery/httpx"
        "projectdiscovery/katana"
        "projectdiscovery/nuclei"
        "projectdiscovery/subfinder"
        "projectdiscovery/dnsx"
        "sxcurity/gau"
        "caffix/amass"
        "frost19k/puredns"
        "jauderho/hakrawler"
        "trufflesecurity/trufflehog"
    )
    for img in "${runtime_images[@]}"; do
        docker rmi "$img" 2>/dev/null || true
    done
}

pull_gvm_images() {
    # GVM images are large (~250MB each) and can fail with "unexpected EOF"
    # due to a known Docker+Go 1.24 bug (moby/moby#49513) and Greenbone
    # registry instability. Pull individually with retries.
    local max_retries=5
    local gvm_services
    gvm_services=$(docker compose config --services 2>/dev/null | grep '^gvm-')

    if [[ -z "$gvm_services" ]]; then
        return 0
    fi

    info "Pulling GVM images (with retry)..."
    local failed=()
    for svc in $gvm_services; do
        local attempt=1
        while [[ $attempt -le $max_retries ]]; do
            if docker compose pull "$svc" 2>/dev/null; then
                break
            fi
            if [[ $attempt -lt $max_retries ]]; then
                warn "Pull failed for $svc (attempt $attempt/$max_retries), retrying..."
                sleep 5
            fi
            ((attempt++))
        done
        if [[ $attempt -gt $max_retries ]]; then
            failed+=("$svc")
        fi
    done

    # Also pull gvmd separately (no gvm- prefix)
    local attempt=1
    while [[ $attempt -le $max_retries ]]; do
        if docker compose pull gvmd 2>/dev/null; then
            break
        fi
        if [[ $attempt -lt $max_retries ]]; then
            warn "Pull failed for gvmd (attempt $attempt/$max_retries), retrying..."
            sleep 3
        fi
        ((attempt++))
    done
    if [[ $attempt -gt $max_retries ]]; then
        failed+=(gvmd)
    fi

    if [[ ${#failed[@]} -gt 0 ]]; then
        error "Failed to pull after $max_retries attempts: ${failed[*]}"
        echo ""
        echo -e "  ${YELLOW}This is often caused by a Docker+Go 1.24 bug (moby/moby#49513).${NC}"
        echo -e "  ${YELLOW}Try: echo '{\"max-concurrent-downloads\":1}' | sudo tee /etc/docker/daemon.json${NC}"
        echo -e "  ${YELLOW}Then: sudo systemctl restart docker && ./redamon.sh up${NC}"
        exit 1
    fi
    success "All GVM images pulled successfully."
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

cmd_install() {
    local gvm_mode="false"
    if [[ "${1:-}" == "--gvm" ]]; then
        gvm_mode="true"
    fi

    print_banner
    check_prerequisites

    local version
    version="$(get_version)"
    info "Installing RedAmon v${version}..."
    if [[ "$gvm_mode" == "true" ]]; then
        info "Mode: Full stack (with GVM/OpenVAS)"
        touch "$GVM_FLAG_FILE"
    else
        info "Mode: Core services (without GVM/OpenVAS)"
        rm -f "$GVM_FLAG_FILE"
    fi
    echo ""

    # Export version for docker build arg
    export_version

    # Build all images (tools + core services)
    info "Building all images (this may take a while on first run)..."
    docker compose --profile tools build

    # Pull GVM images with retry (large images, unreliable registry)
    if [[ "$gvm_mode" == "true" ]]; then
        pull_gvm_images
    fi

    # Start services (force-recreate ensures compose changes like command: are applied)
    info "Starting services..."
    if [[ "$gvm_mode" == "true" ]]; then
        docker compose up -d --force-recreate
    else
        # shellcheck disable=SC2086
        docker compose up -d --force-recreate $CORE_SERVICES
    fi

    echo ""
    success "RedAmon v${version} installed and running!"
    echo ""
    echo -e "  ${CYAN}Webapp:${NC}  http://localhost:3000"
    echo -e "  ${CYAN}Status:${NC}  ./redamon.sh status"
    echo ""
    echo -e "  ${YELLOW}If RedAmon is useful to you, a GitHub star helps others find the project:${NC}"
    echo -e "  ${CYAN}https://github.com/samugit83/redamon${NC}"
    echo ""
    if [[ "$gvm_mode" == "true" ]]; then
        warn "GVM/OpenVAS feed sync takes ~30 minutes on first run."
        echo -e "  ${CYAN}GVM credentials:${NC} admin / admin"
    fi
}

cmd_update() {
    print_banner
    check_prerequisites

    local old_version
    old_version="$(get_version)"
    info "Current version: v${old_version}"
    info "Checking for updates..."
    echo ""

    # Save current HEAD
    local old_head new_head
    old_head="$(git -C "$SCRIPT_DIR" rev-parse HEAD)"

    # Pull latest (try upstream tracking branch first, then origin/master)
    if ! git -C "$SCRIPT_DIR" pull --ff-only 2>/dev/null; then
        if ! git -C "$SCRIPT_DIR" pull --ff-only origin master 2>/dev/null; then
            error "Could not pull updates. You may have local changes."
            echo ""
            echo "  Try one of:"
            echo "    git stash && ./redamon.sh update && git stash pop"
            echo "    git commit -am 'local changes' && ./redamon.sh update"
            exit 1
        fi
    fi

    new_head="$(git -C "$SCRIPT_DIR" rev-parse HEAD)"

    if [[ "$old_head" == "$new_head" ]]; then
        success "Already up to date (v$(get_version))."
        return
    fi

    local new_version
    new_version="$(get_version)"
    info "Updating v${old_version} -> v${new_version}"
    echo ""

    # Detect what changed
    local changed_files
    changed_files="$(git -C "$SCRIPT_DIR" diff --name-only "$old_head" "$new_head")"

    # Map changed paths to services
    local rebuild_core=()
    local rebuild_tools=()
    local rebuild_all=false

    if echo "$changed_files" | grep -q "^docker-compose\.yml$"; then
        rebuild_all=true
    fi

    # Track services that need restart only (volume-mounted source code changes)
    local restart_only=()

    if [[ "$rebuild_all" == "true" ]]; then
        info "docker-compose.yml changed -- rebuilding all images"
        rebuild_core=(recon-orchestrator kali-sandbox agent webapp)
        rebuild_tools=(recon vuln-scanner github-secret-hunter trufflehog-scanner)
    else
        # webapp: always needs rebuild (no volume mount in production)
        if echo "$changed_files" | grep -q "^webapp/"; then
            rebuild_core+=(webapp)
        fi

        # recon-orchestrator: rebuild only if Dockerfile/requirements changed, else restart
        if echo "$changed_files" | grep -q "^recon_orchestrator/\(Dockerfile\|requirements\)"; then
            rebuild_core+=(recon-orchestrator)
        elif echo "$changed_files" | grep -q "^recon_orchestrator/"; then
            restart_only+=(recon-orchestrator)
        fi

        # kali-sandbox: rebuild only if Dockerfile/entrypoint changed, else restart
        if echo "$changed_files" | grep -q "^mcp/kali-sandbox/\(Dockerfile\|entrypoint\)"; then
            rebuild_core+=(kali-sandbox)
        elif echo "$changed_files" | grep -q "^mcp/"; then
            restart_only+=(kali-sandbox)
        fi

        # agent: rebuild only if Dockerfile/requirements changed, else restart
        if echo "$changed_files" | grep -q "^agentic/\(Dockerfile\|requirements\)"; then
            rebuild_core+=(agent)
        elif echo "$changed_files" | grep -q "^agentic/"; then
            restart_only+=(agent)
        fi

        # Tool-profile images (build-only, not running containers)
        if echo "$changed_files" | grep -q "^recon/"; then
            rebuild_tools+=(recon)
        fi
        if echo "$changed_files" | grep -q "^gvm_scan/"; then
            rebuild_tools+=(vuln-scanner)
        fi
        if echo "$changed_files" | grep -q "^github_secret_hunt/"; then
            rebuild_tools+=(github-secret-hunter)
        fi
        if echo "$changed_files" | grep -q "^trufflehog_scan/"; then
            rebuild_tools+=(trufflehog-scanner)
        fi
    fi

    # Export version for build arg
    export_version

    # Rebuild tool-profile images
    if [[ ${#rebuild_tools[@]} -gt 0 ]]; then
        info "Rebuilding tool images: ${rebuild_tools[*]}"
        docker compose --profile tools build "${rebuild_tools[@]}"
    fi

    # Rebuild core service images
    if [[ ${#rebuild_core[@]} -gt 0 ]]; then
        info "Rebuilding service images: ${rebuild_core[*]}"
        docker compose build "${rebuild_core[@]}"
    fi

    # Clean up dangling images left by rebuilds
    if [[ ${#rebuild_core[@]} -gt 0 || ${#rebuild_tools[@]} -gt 0 ]]; then
        docker image prune -f >/dev/null 2>&1 || true
    fi

    # Restart rebuilt core services (tool images are build-only, not running)
    if [[ ${#rebuild_core[@]} -gt 0 ]]; then
        info "Restarting rebuilt services..."
        for svc in "${rebuild_core[@]}"; do
            docker compose up -d --no-deps "$svc"
        done
    fi

    # Recreate GVM containers when docker-compose.yml changed (picks up command/image/volume changes)
    if [[ "$rebuild_all" == "true" ]] && is_gvm_enabled; then
        info "Recreating GVM containers to apply compose changes..."
        pull_gvm_images
        docker compose up -d --force-recreate gvm-redis gvm-postgres gvmd gvm-ospd
    fi

    # Restart services with volume-mounted code changes (no rebuild needed)
    if [[ ${#restart_only[@]} -gt 0 ]]; then
        info "Restarting services for code changes: ${restart_only[*]}"
        docker compose restart "${restart_only[@]}"
    fi

    echo ""
    success "Updated to v${new_version}!"
    if [[ ${#rebuild_core[@]} -gt 0 || ${#rebuild_tools[@]} -gt 0 ]]; then
        local rebuilt_list="${rebuild_core[*]:+${rebuild_core[*]} }${rebuild_tools[*]}"
        echo -e "  ${CYAN}Rebuilt:${NC}  ${rebuilt_list}"
    fi
    if [[ ${#restart_only[@]} -gt 0 ]]; then
        echo -e "  ${CYAN}Restarted:${NC} ${restart_only[*]}"
    fi
    if [[ ${#rebuild_core[@]} -eq 0 && ${#rebuild_tools[@]} -eq 0 && ${#restart_only[@]} -eq 0 ]]; then
        info "No container images or source code needed updating."
    fi
    echo -e "  ${CYAN}Webapp:${NC}  http://localhost:3000"
}

cmd_up() {
    local gvm_mode="false"
    if is_gvm_enabled; then
        gvm_mode="true"
    fi

    info "Starting RedAmon (GVM: ${gvm_mode})..."

    # Pull GVM images with retry (large images, unreliable registry)
    if [[ "$gvm_mode" == "true" ]]; then
        pull_gvm_images
    fi

    if [[ "$gvm_mode" == "true" ]]; then
        docker compose up -d --force-recreate
    else
        # shellcheck disable=SC2086
        docker compose up -d --force-recreate $CORE_SERVICES
    fi

    success "RedAmon is running at http://localhost:3000"
}

cmd_down() {
    info "Stopping RedAmon..."
    docker compose down
    success "All services stopped. Volumes and images preserved."
}

cmd_clean() {
    warn "This will remove all RedAmon containers and images."
    warn "Your data (databases, reports, scan results) will be preserved in Docker volumes."
    echo ""
    read -rp "Continue? [y/N] " confirm
    if [[ "${confirm,,}" != "y" ]]; then
        info "Cancelled."
        return
    fi

    info "Stopping containers..."
    docker compose --profile tools down

    info "Removing RedAmon images..."
    remove_redamon_images
    docker image prune -f >/dev/null 2>&1 || true

    success "All RedAmon containers and images removed. Volumes preserved."
    echo ""
    info "To reinstall: ./redamon.sh install"
}

cmd_purge() {
    echo ""
    warn "This will PERMANENTLY DELETE:"
    warn "  - All RedAmon containers and images"
    warn "  - ALL DATA: PostgreSQL, Neo4j, GVM feeds, reports, scan results"
    echo ""
    echo -e "${RED}${BOLD}This action cannot be undone.${NC}"
    echo ""
    read -rp "Type 'yes' to confirm: " confirm
    if [[ "$confirm" != "yes" ]]; then
        info "Cancelled."
        return
    fi

    info "Stopping containers and removing volumes..."
    docker compose --profile tools down --volumes --remove-orphans

    info "Removing RedAmon images..."
    remove_redamon_images
    docker image prune -f >/dev/null 2>&1 || true

    rm -f "$GVM_FLAG_FILE"
    success "Full cleanup complete. All RedAmon data and images have been removed."
    echo ""
    info "To reinstall: ./redamon.sh install"
}

cmd_status() {
    local version
    version="$(get_version)"

    print_banner
    echo -e "  ${CYAN}Version:${NC}  v${version}"

    if is_gvm_enabled; then
        echo -e "  ${CYAN}GVM:${NC}      true"
    else
        echo -e "  ${CYAN}GVM:${NC}      false"
    fi
    echo ""

    docker compose ps
}

cmd_help() {
    print_banner
    echo -e "${BOLD}Usage:${NC} ./redamon.sh <command> [options]"
    echo ""
    echo -e "${BOLD}Commands:${NC}"
    echo -e "  ${GREEN}install${NC}          Build and start RedAmon (without GVM)"
    echo -e "  ${GREEN}install --gvm${NC}    Build and start RedAmon (with GVM/OpenVAS)"
    echo -e "  ${GREEN}update${NC}           Pull latest version and smart-rebuild changed services"
    echo -e "  ${GREEN}up${NC}               Start services"
    echo -e "  ${GREEN}down${NC}             Stop services (preserves data)"
    echo -e "  ${GREEN}clean${NC}            Remove containers and images (keeps data)"
    echo -e "  ${GREEN}purge${NC}            Remove everything including all data"
    echo -e "  ${GREEN}status${NC}           Show running services, version, and GVM mode"
    echo -e "  ${GREEN}help${NC}             Show this help message"
    echo ""
    echo -e "${BOLD}Examples:${NC}"
    echo "  ./redamon.sh install          # First-time setup (no GVM)"
    echo "  ./redamon.sh install --gvm    # First-time setup (full stack)"
    echo "  ./redamon.sh update           # Update to latest version"
    echo "  ./redamon.sh up               # Start after reboot"
    echo ""
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

cd "$SCRIPT_DIR"

cmd_start_claude_proxy() {
    local port="${CLAUDE_PROXY_PORT:-8099}"
    local pid_file="/tmp/redamon-claude-proxy.pid"

    if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        info "Claude Code proxy is already running (PID $(cat "$pid_file")) on port ${port}"
        return 0
    fi

    if ! command -v python3 &>/dev/null; then
        error "python3 not found. Install Python 3 to run the Claude Code proxy."
        exit 1
    fi

    info "Starting Claude Code proxy on port ${port}..."
    CLAUDE_PROXY_PORT="${port}" python3 "${SCRIPT_DIR}/claude_proxy/server.py" \
        > /tmp/redamon-claude-proxy.log 2>&1 &
    echo $! > "$pid_file"
    sleep 1

    if kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        success "Claude Code proxy started (PID $(cat "$pid_file")) — http://localhost:${port}/health"
        info "Logs: tail -f /tmp/redamon-claude-proxy.log"
    else
        error "Claude Code proxy failed to start. Check: cat /tmp/redamon-claude-proxy.log"
        rm -f "$pid_file"
        exit 1
    fi
}

cmd_stop_claude_proxy() {
    local pid_file="/tmp/redamon-claude-proxy.pid"

    if [[ ! -f "$pid_file" ]]; then
        info "Claude Code proxy is not running (no PID file found)"
        return 0
    fi

    local pid
    pid=$(cat "$pid_file")
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid"
        rm -f "$pid_file"
        success "Claude Code proxy stopped (PID ${pid})"
    else
        info "Claude Code proxy was not running (stale PID file removed)"
        rm -f "$pid_file"
    fi
}

case "${1:-help}" in
    install) cmd_install "${2:-}" ;;
    update)  cmd_update ;;
    up)      cmd_up ;;
    down)    cmd_down ;;
    clean)   cmd_clean ;;
    purge)   cmd_purge ;;
    status)  cmd_status ;;
    start-claude-proxy) cmd_start_claude_proxy ;;
    stop-claude-proxy)  cmd_stop_claude_proxy ;;
    help|--help|-h) cmd_help ;;
    *)
        error "Unknown command: $1"
        cmd_help
        exit 1
        ;;
esac

#!/bin/bash
# Created: 2025-09-11 
# Last Modified: 2025-09-11 22:48:17
# Author: Scott Cadreau

# SurgiCase Cache Management Script
# Comprehensive API-based cache management for all application caches

# Configuration
API_BASE_URL="${SURGICASE_API_URL:-http://localhost:8000}"
SCRIPT_NAME="$(basename "$0")"
LOG_PREFIX="🔧 [Cache Manager]"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}${LOG_PREFIX}${NC} $1"
}

log_success() {
    echo -e "${GREEN}${LOG_PREFIX}${NC} ✅ $1"
}

log_warning() {
    echo -e "${YELLOW}${LOG_PREFIX}${NC} ⚠️  $1"
}

log_error() {
    echo -e "${RED}${LOG_PREFIX}${NC} ❌ $1"
}

log_action() {
    echo -e "${PURPLE}${LOG_PREFIX}${NC} 🚀 $1"
}

# Function to check API connectivity
check_api_connectivity() {
    log_info "Checking API connectivity to $API_BASE_URL..."
    
    if curl -s --max-time 10 "$API_BASE_URL/health" > /dev/null 2>&1; then
        log_success "API is reachable"
        return 0
    else
        log_error "Cannot connect to API at $API_BASE_URL"
        log_error "Please check that the SurgiCase API is running"
        return 1
    fi
}

# Function to make API calls with error handling
api_call() {
    local method="$1"
    local endpoint="$2"
    local description="$3"
    local params="$4"
    
    log_action "$description..."
    
    local url="$API_BASE_URL$endpoint"
    if [ -n "$params" ]; then
        url="$url?$params"
    fi
    
    local response
    local http_code
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "%{http_code}" "$url" 2>/dev/null)
    elif [ "$method" = "POST" ]; then
        response=$(curl -s -w "%{http_code}" -X POST "$url" 2>/dev/null)
    else
        log_error "Unsupported HTTP method: $method"
        return 1
    fi
    
    http_code="${response: -3}"
    response_body="${response%???}"
    
    if [ "$http_code" = "200" ]; then
        log_success "$description completed successfully"
        if [ "$VERBOSE" = "true" ]; then
            echo "$response_body" | python3 -m json.tool 2>/dev/null || echo "$response_body"
        fi
        return 0
    else
        log_error "$description failed (HTTP $http_code)"
        if [ "$VERBOSE" = "true" ]; then
            echo "Response: $response_body"
        fi
        return 1
    fi
}

# Cache management functions
clear_all_caches() {
    log_info "=== CLEARING ALL CACHES ==="
    echo ""
    
    api_call "POST" "/admin/cache/clear-all" "Clear all application caches"
}

clear_user_cache() {
    local user_id="$1"
    
    if [ -z "$user_id" ]; then
        log_error "User ID is required for user-specific cache clearing"
        return 1
    fi
    
    log_info "=== CLEARING CACHE FOR USER: $user_id ==="
    echo ""
    
    api_call "POST" "/admin/cache/clear-user" "Clear cache for user $user_id" "user_id=$user_id"
}

get_cache_stats() {
    log_info "=== CACHE STATISTICS ==="
    echo ""
    
    log_info "📊 Comprehensive Cache Statistics:"
    api_call "GET" "/admin/cache/stats" "Get comprehensive cache statistics"
    
    echo ""
}

get_detailed_cache_stats() {
    local user_id="$1"
    
    log_info "=== DETAILED CACHE STATISTICS ==="
    echo ""
    
    if [ -n "$user_id" ]; then
        log_info "📊 Cache Statistics for User: $user_id"
        api_call "GET" "/cache_diagnostics" "Get detailed cache stats for user $user_id" "user_id=$user_id"
        echo ""
    fi
    
    log_info "📊 Comprehensive Cache Statistics:"
    api_call "GET" "/admin/cache/stats" "Get comprehensive cache statistics"
    
    echo ""
}

warm_caches() {
    log_info "=== CACHE WARMING ==="
    echo ""
    
    log_info "🔥 Warming secrets cache..."
    api_call "POST" "/admin/cache/warm-secrets" "Warm secrets cache"
    
    echo ""
    log_info "💡 Other caches warm automatically on access"
    log_info "💡 Tip: Use 'clear-and-warm' command for comprehensive cache refresh"
}

clear_and_warm() {
    log_info "=== CLEAR AND WARM CACHES ==="
    echo ""
    
    # Clear all caches first
    clear_all_caches
    
    echo ""
    log_info "🔥 Warming caches..."
    
    # Warm secrets cache
    api_call "POST" "/admin/cache/warm-secrets" "Warm secrets cache"
    
    echo ""
    log_success "Cache clear and warm cycle completed!"
    log_info "💡 Other caches will warm automatically as endpoints are accessed"
}

health_check() {
    log_info "=== SYSTEM HEALTH CHECK ==="
    echo ""
    
    log_info "🏥 Checking overall system health..."
    api_call "GET" "/health" "System health check"
    
    echo ""
    log_info "📊 Checking cache health..."
    api_call "GET" "/admin/cache/stats" "Get comprehensive cache health statistics"
}

# Help function
show_help() {
    cat << EOF
${CYAN}SurgiCase Cache Management Script${NC}

${YELLOW}DESCRIPTION:${NC}
    Comprehensive API-based cache management for all SurgiCase application caches.
    Manages user environment caches, secrets caches, and provides diagnostics.

${YELLOW}USAGE:${NC}
    $SCRIPT_NAME [OPTIONS] COMMAND [ARGUMENTS]

${YELLOW}COMMANDS:${NC}
    ${GREEN}clear-all${NC}                    Clear all application caches
    ${GREEN}clear-user <user_id>${NC}         Clear cache for specific user
    ${GREEN}stats${NC}                       Show basic cache statistics
    ${GREEN}stats-detailed [user_id]${NC}    Show detailed cache statistics (optionally for specific user)
    ${GREEN}warm${NC}                        Information about cache warming
    ${GREEN}clear-and-warm${NC}              Clear all caches and trigger re-warming
    ${GREEN}health${NC}                      Comprehensive system and cache health check
    ${GREEN}help${NC}                        Show this help message

${YELLOW}OPTIONS:${NC}
    ${GREEN}-v, --verbose${NC}               Enable verbose output (show API responses)
    ${GREEN}-u, --url <url>${NC}             Set API base URL (default: http://localhost:8000)
    ${GREEN}-h, --help${NC}                  Show this help message

${YELLOW}ENVIRONMENT VARIABLES:${NC}
    ${GREEN}SURGICASE_API_URL${NC}           Set the API base URL (overrides default)

${YELLOW}EXAMPLES:${NC}
    # Clear all caches
    $SCRIPT_NAME clear-all

    # Clear cache for specific user
    $SCRIPT_NAME clear-user USER123

    # Show cache statistics
    $SCRIPT_NAME stats

    # Show detailed stats for specific user
    $SCRIPT_NAME stats-detailed USER123

    # Clear and warm caches
    $SCRIPT_NAME clear-and-warm

    # Health check with verbose output
    $SCRIPT_NAME -v health

    # Use custom API URL
    $SCRIPT_NAME -u https://allstarsapi1.metoraymedical.com clear-all

${YELLOW}CACHE TYPES MANAGED:${NC}
    • ${GREEN}User Environment Cache${NC}     - User profiles, permissions, case statuses
    • ${GREEN}User Cases Cache${NC}           - Filtered case data per user
    • ${GREEN}Global Cases Cache${NC}         - Administrative case data
    • ${GREEN}Secrets Cache${NC}              - AWS Secrets Manager cached data

${YELLOW}NOTES:${NC}
    • Requires SurgiCase API to be running and accessible
    • Some operations may require administrative privileges
    • Cache warming happens automatically on endpoint access
    • All operations are logged with timestamps and status

EOF
}

# Parse command line arguments
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -u|--url)
            API_BASE_URL="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        clear-all)
            COMMAND="clear-all"
            shift
            ;;
        clear-user)
            COMMAND="clear-user"
            USER_ID="$2"
            shift 2
            ;;
        stats)
            COMMAND="stats"
            shift
            ;;
        stats-detailed)
            COMMAND="stats-detailed"
            USER_ID="$2"
            shift
            if [ -n "$2" ] && [[ ! "$2" =~ ^- ]]; then
                shift
            fi
            ;;
        warm)
            COMMAND="warm"
            shift
            ;;
        clear-and-warm)
            COMMAND="clear-and-warm"
            shift
            ;;
        health)
            COMMAND="health"
            shift
            ;;
        help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option or command: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
done

# Main execution
main() {
    echo -e "${CYAN}=== SurgiCase Cache Manager ===${NC}"
    echo -e "${BLUE}API URL: $API_BASE_URL${NC}"
    echo -e "${BLUE}Timestamp: $(date)${NC}"
    echo ""
    
    # Check if command was provided
    if [ -z "$COMMAND" ]; then
        log_error "No command specified"
        echo ""
        show_help
        exit 1
    fi
    
    # Check API connectivity first
    if ! check_api_connectivity; then
        exit 1
    fi
    
    echo ""
    
    # Execute the requested command
    case $COMMAND in
        clear-all)
            clear_all_caches
            ;;
        clear-user)
            clear_user_cache "$USER_ID"
            ;;
        stats)
            get_cache_stats
            ;;
        stats-detailed)
            get_detailed_cache_stats "$USER_ID"
            ;;
        warm)
            warm_caches
            ;;
        clear-and-warm)
            clear_and_warm
            ;;
        health)
            health_check
            ;;
        *)
            log_error "Unknown command: $COMMAND"
            exit 1
            ;;
    esac
    
    echo ""
    log_success "Cache management operation completed!"
    echo -e "${BLUE}Timestamp: $(date)${NC}"
}

# Run main function
main "$@"

#!/bin/bash
# Quick script to apply nginx timeout fixes

echo "=== Nginx Timeout Fix Script ==="
echo "This script will help you apply the necessary nginx configuration changes"
echo ""

# Check if nginx is installed
if ! command -v nginx &> /dev/null; then
    echo "❌ Nginx is not installed or not in PATH"
    exit 1
fi

echo "✅ Nginx found: $(nginx -v 2>&1)"
echo ""

# Find nginx configuration file
NGINX_CONF=$(nginx -t 2>&1 | grep "configuration file" | awk '{print $5}')
if [ -z "$NGINX_CONF" ]; then
    NGINX_CONF="/etc/nginx/nginx.conf"
fi

echo "📁 Nginx config file: $NGINX_CONF"
echo ""

# Check if we can write to the config
if [ ! -w "$NGINX_CONF" ]; then
    echo "⚠️  Cannot write to nginx config file. You may need sudo privileges."
    echo ""
fi

echo "🔧 Recommended changes for your nginx configuration:"
echo ""
echo "1. ADD THESE SETTINGS to your server block or location block:"
echo ""
cat << 'EOF'
# Timeout settings for large exports
proxy_connect_timeout       600s;
proxy_send_timeout          600s;
proxy_read_timeout          600s;
send_timeout                600s;

# Buffer settings
proxy_buffering             off;
proxy_buffer_size           128k;
proxy_buffers               4 256k;
client_max_body_size        50M;
EOF

echo ""
echo "2. FOR EXPORT ENDPOINTS SPECIFICALLY, add this location block:"
echo ""
cat << 'EOF'
location ~ ^/export_cases {
    proxy_pass http://127.0.0.1:8000;  # Adjust to your backend
    
    proxy_connect_timeout       600s;
    proxy_send_timeout          600s;
    proxy_read_timeout          600s;
    send_timeout                600s;
    
    proxy_buffering             off;
    proxy_cache                 off;
    
    add_header Cache-Control "no-cache, no-store, must-revalidate";
    proxy_set_header Connection "";
    proxy_http_version 1.1;
}
EOF

echo ""
echo "3. AFTER MAKING CHANGES:"
echo "   sudo nginx -t                    # Test configuration"
echo "   sudo systemctl reload nginx     # Reload nginx"
echo ""

# Offer to backup current config
read -p "📋 Would you like to backup your current nginx config? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    BACKUP_FILE="${NGINX_CONF}.backup.$(date +%Y%m%d_%H%M%S)"
    if sudo cp "$NGINX_CONF" "$BACKUP_FILE"; then
        echo "✅ Backup created: $BACKUP_FILE"
    else
        echo "❌ Failed to create backup"
    fi
fi

echo ""
echo "🚀 After applying these changes, your 502 Bad Gateway errors should be resolved!"
echo "💡 The key settings are the increased proxy_read_timeout and proxy_buffering off"

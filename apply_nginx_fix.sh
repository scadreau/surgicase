#!/bin/bash
# Script to apply the nginx timeout fix

echo "=== Applying Nginx Timeout Fix ==="
echo ""

# Backup current config
CURRENT_CONFIG="/etc/nginx/sites-available/fastapi-multiproxy"
BACKUP_FILE="${CURRENT_CONFIG}.backup.$(date +%Y%m%d_%H%M%S)"

echo "📋 Creating backup of current config..."
if sudo cp "$CURRENT_CONFIG" "$BACKUP_FILE"; then
    echo "✅ Backup created: $BACKUP_FILE"
else
    echo "❌ Failed to create backup. Exiting."
    exit 1
fi

echo ""
echo "🔧 Applying new configuration..."

# Copy the new config
if sudo cp "fastapi-multiproxy-fixed" "$CURRENT_CONFIG"; then
    echo "✅ New configuration applied"
else
    echo "❌ Failed to apply new configuration. Restoring backup."
    sudo cp "$BACKUP_FILE" "$CURRENT_CONFIG"
    exit 1
fi

echo ""
echo "🧪 Testing nginx configuration..."

# Test the configuration
if sudo nginx -t; then
    echo "✅ Configuration test passed"
else
    echo "❌ Configuration test failed. Restoring backup."
    sudo cp "$BACKUP_FILE" "$CURRENT_CONFIG"
    sudo nginx -t
    exit 1
fi

echo ""
echo "🔄 Reloading nginx..."

# Reload nginx
if sudo systemctl reload nginx; then
    echo "✅ Nginx reloaded successfully"
else
    echo "❌ Failed to reload nginx. Checking status..."
    sudo systemctl status nginx
    exit 1
fi

echo ""
echo "🎉 SUCCESS! Nginx timeout fix has been applied."
echo ""
echo "📊 Key changes made:"
echo "   ✅ proxy_read_timeout increased to 600s (10 minutes)"
echo "   ✅ proxy_buffering disabled for large responses"
echo "   ✅ Special handling for /export_cases endpoints"
echo "   ✅ Extended timeouts for streaming responses"
echo ""
echo "🚀 Your 502 Bad Gateway errors should now be resolved!"
echo "💡 Test your 129 case export - it should work without timeouts."
echo ""
echo "📁 Backup location: $BACKUP_FILE"

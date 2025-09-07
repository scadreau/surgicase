# Frontend Download Error Troubleshooting Guide

## Problem: "Failed to execute 'text' on 'Response': body stream already read"

This error occurs when the frontend JavaScript tries to read the HTTP response body multiple times, which is not allowed.

## Root Cause Analysis

### ❌ What's Happening (Broken Code):
```javascript
fetch('/get_case_images', {...})
.then(response => {
    if (!response.ok) {
        return response.text(); // ← Reads the body stream
    }
    return response.blob();     // ← Tries to read again - ERROR!
})
```

### ✅ The Fix:
```javascript
// Option 1: Use async/await with proper error handling
const response = await fetch('/get_case_images', {...});
if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText);
}
const blob = await response.blob(); // Only read once

// Option 2: Clone the response for error handling
.then(response => {
    if (!response.ok) {
        return response.clone().text().then(errorText => {
            throw new Error(errorText);
        });
    }
    return response.blob();
})
```

## Common Frontend Issues with Large File Downloads

### 1. **Memory Issues**
- **Problem**: Large ZIP files (100MB+) can cause browser memory issues
- **Solution**: Use streaming with progress tracking
- **Code**: See `downloadCaseImages_WITH_PROGRESS()` in the fix file

### 2. **Timeout on Frontend**
- **Problem**: Browser timeout before nginx timeout
- **Solution**: Increase fetch timeout or use streaming
```javascript
const controller = new AbortController();
setTimeout(() => controller.abort(), 30 * 60 * 1000); // 30 minutes

fetch(url, { 
    signal: controller.signal,
    // ... other options
});
```

### 3. **CORS Issues**
- **Problem**: Cross-origin requests blocked
- **Solution**: Ensure proper CORS headers in FastAPI
```python
# In your FastAPI app
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

### 4. **Content-Type Issues**
- **Problem**: Browser trying to parse ZIP as JSON
- **Solution**: Ensure proper headers
```javascript
// Don't try to parse as JSON
const data = await response.json(); // ❌ Wrong for ZIP files
const blob = await response.blob(); // ✅ Correct for binary files
```

## Testing Your Fix

### 1. **Check Network Tab**
- Open browser DevTools → Network tab
- Look for the `/get_case_images` request
- Check if it completes successfully (status 200)
- Verify response headers include `Content-Type: application/zip`

### 2. **Check Console Errors**
- Look for JavaScript errors in Console tab
- The "body stream already read" error should disappear

### 3. **Test with Different Sizes**
- Small batch (1-2 cases): Should work quickly
- Medium batch (10-20 cases): Should work in 30-60 seconds  
- Large batch (50+ cases): May take 5-15 minutes

## Backend Verification

Your backend (`get_case_images`) is working correctly if:
- ✅ FastAPI docs page works
- ✅ Returns proper ZIP file
- ✅ Includes correct headers
- ✅ No 502 errors (nginx timeouts fixed)

## Frontend Framework Specific Solutions

### React/Next.js:
```jsx
const [downloading, setDownloading] = useState(false);

const handleDownload = async (caseIds) => {
    setDownloading(true);
    try {
        const response = await fetch('/get_case_images?user_id=USER123', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case_ids: caseIds })
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const blob = await response.blob();
        // ... download logic
    } catch (error) {
        console.error('Download failed:', error);
    } finally {
        setDownloading(false);
    }
};
```

### Vue.js:
```javascript
methods: {
    async downloadImages(caseIds) {
        this.downloading = true;
        try {
            const response = await this.$http.post('/get_case_images', 
                { case_ids: caseIds },
                { responseType: 'blob' } // Important for binary data
            );
            // ... download logic
        } catch (error) {
            console.error('Download failed:', error);
        } finally {
            this.downloading = false;
        }
    }
}
```

### Vanilla JavaScript:
```javascript
// Use the fixed functions from frontend_download_fix.js
downloadCaseImages_FIXED(caseIds);
```

## Quick Diagnosis

Run this in your browser console to test:
```javascript
// Test if the endpoint is accessible
fetch('/get_case_images?user_id=TEST', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_ids: ['test-case-id'] })
})
.then(r => console.log('Status:', r.status, 'Headers:', [...r.headers.entries()]))
.catch(e => console.error('Error:', e));
```

The error you're seeing is **100% a frontend JavaScript issue**, not a backend problem. The nginx timeout fixes we applied will handle the server-side timeouts, but you need to fix the frontend response handling code.

// Frontend Fix for Large File Downloads from get_case_images
// This addresses the "body stream already read" error

// ❌ PROBLEMATIC CODE (causes the error):
function downloadCaseImages_BROKEN(caseIds) {
    fetch('/get_case_images?user_id=USER123', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ case_ids: caseIds })
    })
    .then(response => {
        // ❌ PROBLEM: Trying to read response.text() first
        if (!response.ok) {
            return response.text().then(text => {
                throw new Error(`HTTP ${response.status}: ${text}`);
            });
        }
        // ❌ PROBLEM: Then trying to read response.blob() - body already consumed!
        return response.blob();
    })
    .then(blob => {
        // This never executes because of the error above
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'case_images.zip';
        a.click();
    })
    .catch(error => {
        console.error('Download failed:', error);
        // This is where you see "body stream already read"
    });
}

// ✅ CORRECT CODE (fixes the error):
async function downloadCaseImages_FIXED(caseIds) {
    try {
        const response = await fetch('/get_case_images?user_id=USER123', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case_ids: caseIds })
        });

        // ✅ SOLUTION: Check status first, then handle appropriately
        if (!response.ok) {
            // For error responses, read as text
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        // ✅ SOLUTION: For success responses, read as blob (binary data)
        const blob = await response.blob();
        
        // Get filename from response headers
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'case_images.zip';
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename="(.+)"/);
            if (filenameMatch) {
                filename = filenameMatch[1];
            }
        }

        // Create download
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a); // Required for Firefox
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url); // Clean up memory

        console.log(`✅ Download completed: ${filename}`);
        
    } catch (error) {
        console.error('❌ Download failed:', error.message);
        
        // Show user-friendly error message
        alert(`Download failed: ${error.message}`);
    }
}

// ✅ ALTERNATIVE: Using .then() chain (if you prefer promises)
function downloadCaseImages_PROMISE_FIXED(caseIds) {
    return fetch('/get_case_images?user_id=USER123', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ case_ids: caseIds })
    })
    .then(response => {
        // ✅ SOLUTION: Clone response for error handling
        if (!response.ok) {
            // Use cloned response for error text
            return response.clone().text().then(errorText => {
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            });
        }
        // Original response for blob
        return response.blob();
    })
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'case_images.zip';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    })
    .catch(error => {
        console.error('Download failed:', error.message);
        alert(`Download failed: ${error.message}`);
    });
}

// ✅ ADVANCED: With progress tracking for large downloads
async function downloadCaseImages_WITH_PROGRESS(caseIds, progressCallback) {
    try {
        const response = await fetch('/get_case_images?user_id=USER123', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ case_ids: caseIds })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        // Get total size for progress tracking
        const contentLength = response.headers.get('Content-Length');
        const total = contentLength ? parseInt(contentLength, 10) : 0;

        // Read response with progress tracking
        const reader = response.body.getReader();
        const chunks = [];
        let loaded = 0;

        while (true) {
            const { done, value } = await reader.read();
            
            if (done) break;
            
            chunks.push(value);
            loaded += value.length;
            
            // Report progress
            if (progressCallback && total > 0) {
                const progress = (loaded / total) * 100;
                progressCallback(progress, loaded, total);
            }
        }

        // Create blob from chunks
        const blob = new Blob(chunks);
        
        // Download the file
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'case_images.zip';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        console.log('✅ Download completed with progress tracking');
        
    } catch (error) {
        console.error('❌ Download failed:', error.message);
        alert(`Download failed: ${error.message}`);
    }
}

// ✅ USAGE EXAMPLES:

// Basic usage
// downloadCaseImages_FIXED(['case1', 'case2', 'case3']);

// With progress tracking
// downloadCaseImages_WITH_PROGRESS(['case1', 'case2'], (progress, loaded, total) => {
//     console.log(`Download progress: ${progress.toFixed(1)}% (${loaded}/${total} bytes)`);
//     // Update progress bar in UI
// });

// ✅ REACT/MODERN FRAMEWORK EXAMPLE:
/*
const [downloading, setDownloading] = useState(false);
const [progress, setProgress] = useState(0);

const handleDownload = async (caseIds) => {
    setDownloading(true);
    setProgress(0);
    
    try {
        await downloadCaseImages_WITH_PROGRESS(caseIds, (prog) => {
            setProgress(prog);
        });
    } finally {
        setDownloading(false);
        setProgress(0);
    }
};
*/

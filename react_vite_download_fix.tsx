// React 19+ / Vite Frontend Fix for Large File Downloads
// Fixes CORS issues and "body stream already read" errors

import { useState, useCallback } from 'react';

// ✅ CORRECT: React 19+ / Vite Download Hook
export const useFileDownload = () => {
  const [downloading, setDownloading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const downloadFile = useCallback(async (
    endpoint: string,
    payload: any,
    filename?: string,
    onProgress?: (progress: number) => void
  ) => {
    setDownloading(true);
    setProgress(0);
    setError(null);

    try {
      // ✅ SOLUTION: Proper fetch configuration for large files
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          // Add any auth headers your app needs
          // 'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
        // ✅ CRITICAL: Don't set credentials: 'include' if CORS is configured with allow_origins: ["*"]
        credentials: 'same-origin', // Use 'same-origin' instead of 'include'
      });

      // ✅ SOLUTION: Check response status BEFORE reading body
      if (!response.ok) {
        // For error responses, read as text
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }

      // ✅ SOLUTION: Get content length for progress tracking
      const contentLength = response.headers.get('Content-Length');
      const total = contentLength ? parseInt(contentLength, 10) : 0;

      // ✅ SOLUTION: Stream the response for large files
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('Response body is not readable');
      }

      const chunks: Uint8Array[] = [];
      let loaded = 0;

      while (true) {
        const { done, value } = await reader.read();
        
        if (done) break;
        
        chunks.push(value);
        loaded += value.length;
        
        // Update progress
        if (total > 0) {
          const progressPercent = (loaded / total) * 100;
          setProgress(progressPercent);
          onProgress?.(progressPercent);
        }
      }

      // ✅ SOLUTION: Create blob from chunks
      const blob = new Blob(chunks);
      
      // ✅ SOLUTION: Get filename from headers or use default
      let downloadFilename = filename || 'download.zip';
      const contentDisposition = response.headers.get('Content-Disposition');
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
        if (filenameMatch) {
          downloadFilename = filenameMatch[1].replace(/['"]/g, '');
        }
      }

      // ✅ SOLUTION: Trigger download
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = downloadFilename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      console.log(`✅ Download completed: ${downloadFilename} (${loaded} bytes)`);
      
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Download failed';
      setError(errorMessage);
      console.error('❌ Download failed:', errorMessage);
      throw err;
    } finally {
      setDownloading(false);
      setProgress(0);
    }
  }, []);

  return {
    downloadFile,
    downloading,
    progress,
    error,
    clearError: () => setError(null)
  };
};

// ✅ EXAMPLE: Case Images Download Component
export const CaseImagesDownloader = () => {
  const { downloadFile, downloading, progress, error, clearError } = useFileDownload();
  const [caseIds, setCaseIds] = useState<string[]>([]);
  const [userId, setUserId] = useState('');

  const handleDownload = async () => {
    if (!userId || caseIds.length === 0) {
      alert('Please provide user ID and case IDs');
      return;
    }

    try {
      await downloadFile(
        `/get_case_images?user_id=${encodeURIComponent(userId)}`,
        { case_ids: caseIds },
        'case_images.zip',
        (progress) => console.log(`Download progress: ${progress.toFixed(1)}%`)
      );
    } catch (error) {
      // Error is already handled by the hook
    }
  };

  return (
    <div className="case-images-downloader">
      <h3>Download Case Images</h3>
      
      <div className="form-group">
        <label>User ID:</label>
        <input
          type="text"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          placeholder="Enter user ID"
        />
      </div>

      <div className="form-group">
        <label>Case IDs (one per line):</label>
        <textarea
          value={caseIds.join('\n')}
          onChange={(e) => setCaseIds(e.target.value.split('\n').filter(id => id.trim()))}
          placeholder="Enter case IDs, one per line"
          rows={10}
        />
      </div>

      {error && (
        <div className="error-message">
          ❌ {error}
          <button onClick={clearError}>✕</button>
        </div>
      )}

      {downloading && (
        <div className="progress-container">
          <div className="progress-bar">
            <div 
              className="progress-fill" 
              style={{ width: `${progress}%` }}
            />
          </div>
          <span>{progress.toFixed(1)}% - Downloading...</span>
        </div>
      )}

      <button 
        onClick={handleDownload}
        disabled={downloading || !userId || caseIds.length === 0}
        className="download-button"
      >
        {downloading ? 'Downloading...' : `Download ${caseIds.length} Cases`}
      </button>
    </div>
  );
};

// ✅ EXAMPLE: Case Export Download Component
export const CaseExportDownloader = () => {
  const { downloadFile, downloading, progress, error, clearError } = useFileDownload();
  const [caseIds, setCaseIds] = useState<string[]>([]);

  const handleExportJSON = async () => {
    if (caseIds.length === 0) {
      alert('Please provide case IDs');
      return;
    }

    try {
      await downloadFile(
        '/export_cases',
        { case_ids: caseIds },
        'case_export.json'
      );
    } catch (error) {
      // Error is already handled by the hook
    }
  };

  const handleExportCSV = async () => {
    if (caseIds.length === 0) {
      alert('Please provide case IDs');
      return;
    }

    try {
      await downloadFile(
        '/export_cases_csv',
        { case_ids: caseIds },
        'case_export.csv'
      );
    } catch (error) {
      // Error is already handled by the hook
    }
  };

  return (
    <div className="case-export-downloader">
      <h3>Export Cases</h3>
      
      <div className="form-group">
        <label>Case IDs (one per line):</label>
        <textarea
          value={caseIds.join('\n')}
          onChange={(e) => setCaseIds(e.target.value.split('\n').filter(id => id.trim()))}
          placeholder="Enter case IDs, one per line"
          rows={10}
        />
      </div>

      {error && (
        <div className="error-message">
          ❌ {error}
          <button onClick={clearError}>✕</button>
        </div>
      )}

      {downloading && (
        <div className="progress-container">
          <div className="progress-bar">
            <div 
              className="progress-fill" 
              style={{ width: `${progress}%` }}
            />
          </div>
          <span>{progress.toFixed(1)}% - Processing...</span>
        </div>
      )}

      <div className="button-group">
        <button 
          onClick={handleExportJSON}
          disabled={downloading || caseIds.length === 0}
          className="export-button"
        >
          {downloading ? 'Exporting...' : `Export ${caseIds.length} Cases (JSON)`}
        </button>

        <button 
          onClick={handleExportCSV}
          disabled={downloading || caseIds.length === 0}
          className="export-button"
        >
          {downloading ? 'Exporting...' : `Export ${caseIds.length} Cases (CSV)`}
        </button>
      </div>
    </div>
  );
};

// ✅ CSS for styling (add to your CSS file)
const styles = `
.case-images-downloader,
.case-export-downloader {
  max-width: 600px;
  margin: 20px auto;
  padding: 20px;
  border: 1px solid #ddd;
  border-radius: 8px;
}

.form-group {
  margin-bottom: 15px;
}

.form-group label {
  display: block;
  margin-bottom: 5px;
  font-weight: bold;
}

.form-group input,
.form-group textarea {
  width: 100%;
  padding: 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}

.error-message {
  background-color: #fee;
  color: #c33;
  padding: 10px;
  border-radius: 4px;
  margin: 10px 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.progress-container {
  margin: 15px 0;
}

.progress-bar {
  width: 100%;
  height: 20px;
  background-color: #f0f0f0;
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 5px;
}

.progress-fill {
  height: 100%;
  background-color: #4caf50;
  transition: width 0.3s ease;
}

.download-button,
.export-button {
  background-color: #007bff;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
  margin-right: 10px;
}

.download-button:disabled,
.export-button:disabled {
  background-color: #ccc;
  cursor: not-allowed;
}

.button-group {
  display: flex;
  gap: 10px;
}
`;

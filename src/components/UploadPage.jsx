import { useState, useRef, useCallback } from 'react';

const ACCEPT_TYPES = ['application/pdf'];
const ACCEPT_EXT = ['.pdf'];

function FileIcon({ type }) {
  if (type === 'application/pdf' || type?.includes('pdf')) {
    return (
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
        <line x1="16" y1="13" x2="8" y2="13"/>
        <line x1="16" y1="17" x2="8" y2="17"/>
        <polyline points="10 9 9 9 8 9"/>
      </svg>
    );
  }
  return (
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2"/>
      <circle cx="8.5" cy="8.5" r="1.5"/>
      <polyline points="21 15 16 10 5 21"/>
    </svg>
  );
}

export default function UploadPage({ onGenerateFromFile, onBack }) {
  const [dragOver, setDragOver] = useState(false);
  const [file, setFile] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);

  const validateFile = (f) => {
    if (!f) return 'No file selected.';
    const ok = ACCEPT_TYPES.includes(f.type) || ACCEPT_EXT.some(ext => f.name.toLowerCase().endsWith(ext));
    if (!ok) return 'Please upload a PDF resume.';
    if (f.size > 10 * 1024 * 1024) return 'File too large — max 10 MB.';
    return '';
  };

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    const err = validateFile(f);
    setError(err);
    if (!err) setFile(f);
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => setDragOver(false), []);

  const handleBrowse = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const err = validateFile(f);
    setError(err);
    if (!err) setFile(f);
  };

  const handleGenerate = async () => {
    if (!file) { setError('Please select a file first.'); return; }
    setLoading(true);
    setError('');
    try {
      await onGenerateFromFile(file);
    } catch (e) {
      setError(e.message || 'Failed to generate question from file.');
    } finally {
      setLoading(false);
    }
  };

  const clearFile = (e) => {
    e.stopPropagation();
    setFile(null);
    setError('');
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <div className="upload-page slide-up">
      <div className="upload-header">
        {onBack && (
          <button className="upload-back-btn" type="button" onClick={onBack}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><polyline points="15 18 9 12 15 6"/></svg>
            Back
          </button>
        )}
        <div className="upload-title-area">
          <h2 className="upload-title">Sheikh Mock Interview</h2>
          <p className="upload-sub">Upload your resume (PDF) and start a real, conversational mock interview with adaptive AI</p>
        </div>
      </div>

      <div
        className={`dropzone${dragOver ? ' dropzone--over' : ''}${file ? ' dropzone--has-file' : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => !file && inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ' ') && !file) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_EXT.join(',')}
          style={{ display: 'none' }}
          onChange={handleBrowse}
        />

        {file ? (
          <div className="dropzone-file">
            <div className="dropzone-file-icon">
              <FileIcon type={file.type} />
            </div>
            <div className="dropzone-file-info">
              <div className="dropzone-file-name">{file.name}</div>
              <div className="dropzone-file-size">{(file.size / 1024).toFixed(1)} KB</div>
            </div>
            <button className="dropzone-clear" type="button" onClick={clearFile} title="Remove file">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        ) : (
          <div className="dropzone-idle">
            <div className="dropzone-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="16 16 12 12 8 16"/>
                <line x1="12" y1="12" x2="12" y2="21"/>
                <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
              </svg>
            </div>
            <p className="dropzone-main">Drop your file here</p>
            <p className="dropzone-hint">or <span className="dropzone-browse">browse</span> to choose</p>
            <p className="dropzone-types">PDF resume · max 10 MB</p>
          </div>
        )}
      </div>

      {error && <p className="upload-error">{error}</p>}

      <div className="upload-actions">
        <button
          className="action-btn primary ai-gen-btn"
          type="button"
          onClick={handleGenerate}
          disabled={!file || loading}
        >
          {loading ? (
            <>
              <span className="think-dots" style={{ display: 'inline-flex', gap: 3 }}><span /><span /><span /></span>
              Reading your resume…
            </>
          ) : (
            <>
              ✨ Start Interview
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            </>
          )}
        </button>
      </div>

      <p className="upload-note">
        The interviewer reads your resume and asks adaptive, conversational questions tailored to your background.
      </p>
    </div>
  );
}

import React, { useRef, useEffect } from 'react';

export default function InputBox({
  input,
  setInput,
  onSend,
  loading,
  sidebarOpen,
  onOpenUploadModal,
  activeDatasetName
}) {
  const inputRef = useRef(null);

  useEffect(() => {
    if (!loading && inputRef.current) {
      inputRef.current.focus();
    }
  }, [loading]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;
    onSend(input);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const placeholderText = activeDatasetName
    ? `Ask about ${activeDatasetName} (e.g. find company, email, phone, role)...`
    : 'Ask Calispec AI something or search company records...';

  return (
    <div className={`input-dock-container ${!sidebarOpen ? 'sidebar-collapsed' : ''}`}>
      <div className="input-dock">
        <form className="input-form" onSubmit={handleSubmit}>
          {/* Upload Data Button inside Input Dock */}
          {onOpenUploadModal && (
            <button
              type="button"
              className="atlas-input-upload-btn"
              onClick={onOpenUploadModal}
              title="Upload Data (.csv, .xlsx, .json, .xml, .txt)"
              aria-label="Upload data file"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
              </svg>
            </button>
          )}

          <input
            ref={inputRef}
            type="text"
            className="chat-input"
            placeholder={placeholderText}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            autoComplete="off"
            aria-label="Search dataset records"
          />

          {input && !loading && (
            <button
              type="button"
              onClick={() => setInput('')}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-muted)',
                cursor: 'pointer',
                padding: '0.2rem',
                display: 'flex',
                alignItems: 'center',
              }}
              title="Clear input"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          )}

          <button
            type="submit"
            className="btn-send"
            disabled={!input.trim() || loading}
            aria-label="Send query"
          >
            {loading ? (
              <div className="spinner" style={{ width: 16, height: 16, borderTopColor: 'white' }}></div>
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            )}
          </button>
        </form>

        <div className="input-footer-hint">
          <span>Press <strong>Enter</strong> to search</span>
          <span>MongoDB Cloud • Private Natural Query Engine</span>
        </div>
      </div>
    </div>
  );
}

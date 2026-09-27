import React from 'react';

export default function DocumentInspectorModal({ record, onClose }) {
  if (!record) return null;

  const jsonString = JSON.stringify(record, null, 2);
  const docId = record.id ? (record.id.startsWith('OID_') ? record.id : `OID_${record.id}`) : '_id';

  const handleCopy = () => {
    navigator.clipboard.writeText(jsonString);
  };

  return (
    <div className="atlas-modal-backdrop" onClick={onClose}>
      <div className="atlas-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="atlas-modal-header">
          <div className="atlas-modal-title">
            <span className="atlas-modal-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="16 18 22 12 16 6" />
                <polyline points="8 6 2 12 8 18" />
              </svg>
            </span>
            <div>
              <div style={{ fontWeight: 700, fontSize: '1rem', color: '#0f172a' }}>
                Document Inspector
              </div>
              <div style={{ fontSize: '0.75rem', color: '#64748b', fontFamily: 'JetBrains Mono, monospace' }}>
                {docId} • Collection: {record.source_collection || 'calispec'}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="atlas-modal-btn" onClick={handleCopy} title="Copy Raw JSON">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
              Copy JSON
            </button>
            <button className="atlas-modal-close" onClick={onClose}>
              ✕
            </button>
          </div>
        </div>

        <div className="atlas-modal-body">
          <pre className="atlas-json-code">
            <code>{jsonString}</code>
          </pre>
        </div>

        <div className="atlas-modal-footer">
          <div style={{ fontSize: '0.78rem', color: '#64748b' }}>
            BSON Extended JSON Format • MongoDB Cloud Atlas
          </div>
          <button className="atlas-modal-done" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

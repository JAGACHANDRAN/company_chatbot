import React from 'react';

export default function DocumentInspectorModal({ record, onClose }) {
  if (!record) return null;

  const jsonString = JSON.stringify(record, null, 2);
  const docId = record.id ? (record.id.startsWith('OID_') ? record.id : `OID_${record.id}`) : '_id';

  const handleCopy = () => {
    navigator.clipboard?.writeText(jsonString);
  };

  return (
    <div
      className="fixed inset-0 bg-slate-900/30 backdrop-blur-sm z-[110] flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-2xl w-full overflow-hidden flex flex-col max-h-[85vh] animate-fadeIn"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-4 sm:p-5 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-sky-50 border border-sky-100 flex items-center justify-center text-sky-600">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="16 18 22 12 16 6" />
                <polyline points="8 6 2 12 8 18" />
              </svg>
            </div>
            <div>
              <div className="font-bold text-sm text-slate-900 font-headline-xl">
                Document Inspector
              </div>
              <div className="text-xs text-slate-500 font-mono">
                {docId} • Collection: {record.source_collection || record.dataset || 'MongoDB'}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 text-xs font-medium text-slate-700 transition-colors"
              onClick={handleCopy}
              title="Copy Raw JSON"
              type="button"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
              <span>Copy JSON</span>
            </button>
            <button
              className="w-7 h-7 rounded-lg border border-slate-200 text-slate-400 hover:text-slate-700 hover:bg-slate-100 flex items-center justify-center transition-colors text-xs font-bold"
              onClick={onClose}
              type="button"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="p-4 sm:p-5 overflow-y-auto flex-1 bg-slate-50/50">
          <pre className="p-3.5 rounded-xl bg-slate-900 text-sky-300 font-mono text-xs overflow-x-auto leading-relaxed border border-slate-800 shadow-inner">
            <code>{jsonString}</code>
          </pre>
        </div>

        {/* Footer */}
        <div className="p-3.5 sm:px-5 border-t border-slate-100 bg-white flex items-center justify-between text-xs text-slate-500">
          <span className="font-mono text-[11px]">BSON Extended JSON Format • MongoDB Atlas</span>
          <button
            className="px-4 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-700 text-white font-medium text-xs transition-colors"
            onClick={onClose}
            type="button"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import {
  fetchAdminCleanCollections,
  previewAdminCleanCollection,
  fetchAdminCleanChanges,
  downloadAdminCleanReportExcel,
  applyAdminClean,
} from '../api';
import CleaningReportView from './CleaningReportView';

export default function CleanExistingDataModal({ isOpen, onClose }) {
  // Stages: 'list' -> 'loading' -> 'report' -> 'applied'
  const [stage, setStage] = useState('list');
  const [collections, setCollections] = useState([]);
  const [loadingCollections, setLoadingCollections] = useState(false);
  const [selectedCollection, setSelectedCollection] = useState(null);

  // Loading state
  const [loading, setLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  // Report state
  const [previewData, setPreviewData] = useState(null);
  const [changeFilter, setChangeFilter] = useState('all');
  const [changePage, setChangePage] = useState(1);
  const [changePageSize, setChangePageSize] = useState(20);

  // Replace Confirmation Modal
  const [showReplaceDialog, setShowReplaceDialog] = useState(false);
  const [typedConfirmName, setTypedConfirmName] = useState('');

  // Apply state
  const [applying, setApplying] = useState(false);
  const [applyResult, setApplyResult] = useState(null);

  // Load collections when opened
  useEffect(() => {
    if (isOpen) {
      loadCollections();
    } else {
      resetState();
    }
  }, [isOpen]);

  const resetState = () => {
    setStage('list');
    setSelectedCollection(null);
    setLoading(false);
    setLoadingMessage('');
    setErrorMessage('');
    setPreviewData(null);
    setChangeFilter('all');
    setChangePage(1);
    setChangePageSize(20);
    setShowReplaceDialog(false);
    setTypedConfirmName('');
    setApplying(false);
    setApplyResult(null);
  };

  const handleClose = () => {
    if (loading || applying) return;
    resetState();
    onClose();
  };

  const loadCollections = async () => {
    setLoadingCollections(true);
    setErrorMessage('');
    try {
      const data = await fetchAdminCleanCollections();
      setCollections(data.collections || []);
    } catch (err) {
      setErrorMessage(err.message || 'Failed to load collections from database.');
    } finally {
      setLoadingCollections(false);
    }
  };

  // 1. Run preview for a selected collection
  const handleCheckCollection = async (colName) => {
    setSelectedCollection(colName);
    setErrorMessage('');
    setLoading(true);
    setStage('loading');
    setLoadingMessage(`Scanning and cleaning '${colName}' in memory...`);

    try {
      const data = await previewAdminCleanCollection(colName);
      setPreviewData(data);
      setChangeFilter('all');
      setChangePage(1);
      setStage('report');
    } catch (err) {
      setErrorMessage(err.message || `Failed to preview cleaning for '${colName}'.`);
      setStage('list');
    } finally {
      setLoading(false);
    }
  };

  // 2. Download Excel report
  const handleDownloadReport = async () => {
    if (!previewData?.preview_id) return;
    try {
      await downloadAdminCleanReportExcel(
        previewData.preview_id,
        selectedCollection || 'collection'
      );
    } catch (err) {
      setErrorMessage(err.message || 'Failed to download Excel report.');
    }
  };

  // 3. Apply mode: new_collection
  const handleApplyNewCollection = async () => {
    if (!previewData?.preview_id || applying) return;
    setApplying(true);
    setErrorMessage('');

    try {
      const result = await applyAdminClean(previewData.preview_id, 'new_collection');
      setApplyResult(result);
      setStage('applied');
      loadCollections(); // refresh list in background
    } catch (err) {
      setErrorMessage(err.message || 'Failed to create cleaned collection.');
    } finally {
      setApplying(false);
    }
  };

  // 4. Apply mode: replace
  const handleApplyReplace = async () => {
    if (!previewData?.preview_id || applying) return;

    if (typedConfirmName.trim() !== selectedCollection) {
      setErrorMessage(
        `Confirmation mismatch. Please type '${selectedCollection}' exactly.`
      );
      return;
    }

    setApplying(true);
    setErrorMessage('');

    try {
      const result = await applyAdminClean(
        previewData.preview_id,
        'replace',
        typedConfirmName.trim()
      );
      setApplyResult(result);
      setShowReplaceDialog(false);
      setTypedConfirmName('');
      setStage('applied');
      loadCollections(); // refresh list in background
    } catch (err) {
      setErrorMessage(err.message || `Failed to replace collection '${selectedCollection}'.`);
    } finally {
      setApplying(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-3 sm:p-5 transition-opacity duration-200"
      role="dialog"
      aria-modal="true"
      aria-labelledby="clean-modal-title"
    >
      {/* Dark frosted backdrop */}
      <div
        aria-hidden="true"
        className="fixed inset-0 bg-slate-950/75 backdrop-blur-md transition-opacity"
        onClick={handleClose}
      />

      {/* Main Glassmorphic Container */}
      <div className="relative w-full max-w-5xl bg-slate-900/95 text-slate-100 rounded-2xl shadow-2xl border border-slate-700/70 overflow-hidden flex flex-col max-h-[92vh] z-10">
        {/* Emerald to indigo top accent gradient */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-emerald-500 via-sky-500 to-indigo-500"></div>

        {/* Modal Header */}
        <header className="p-5 sm:p-6 pb-4 border-b border-slate-800 flex items-start justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-xl bg-emerald-500/10 border border-emerald-400/30 flex items-center justify-center text-emerald-400 shrink-0 shadow-inner">
              <svg className="w-6 h-6 stroke-[1.8]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"></path>
              </svg>
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-lg sm:text-xl font-bold tracking-tight text-white" id="clean-modal-title">
                  {stage === 'list' && 'Clean Existing MongoDB Data'}
                  {stage === 'loading' && 'Analyzing Collection...'}
                  {stage === 'report' && `Audit Report: ${selectedCollection}`}
                  {stage === 'applied' && 'Cleaning Successfully Applied'}
                </h2>
                <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-mono font-semibold rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                  ADMIN ONLY
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-400">
                {stage === 'list' && 'Inspect and clean stored records without external AI. Changes are only applied after your explicit confirmation.'}
                {stage === 'loading' && 'Running offline deterministic cleaning engine in memory...'}
                {stage === 'report' && 'Review what was cleaned, extracted, and normalized before writing anything.'}
                {stage === 'applied' && 'Records have been written to MongoDB. See next steps below.'}
              </p>
            </div>
          </div>

          <button
            aria-label="Close dialog"
            className="w-8 h-8 rounded-lg border border-slate-700 bg-slate-800/60 text-slate-400 hover:text-white hover:bg-slate-700 transition-colors flex items-center justify-center focus:outline-none"
            onClick={handleClose}
            disabled={loading || applying}
            type="button"
          >
            ✕
          </button>
        </header>

        {/* Modal Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-5 sm:p-6 space-y-6">
          {/* Error Message Alert */}
          {errorMessage && (
            <div className="rounded-xl border border-rose-500/40 bg-rose-950/50 p-4 flex items-start gap-3 shadow-sm">
              <svg className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
              </svg>
              <div className="flex-1">
                <div className="text-xs font-semibold text-rose-300">Notice:</div>
                <p className="text-xs text-rose-200 mt-0.5 font-medium">{errorMessage}</p>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* STAGE 1: Collections List */}
          {/* ========================================================================= */}
          {stage === 'list' && (
            <div className="space-y-5">
              <div className="rounded-xl border border-sky-500/25 bg-sky-950/20 p-4 flex items-start gap-3">
                <div className="p-1 rounded-md bg-sky-500/10 text-sky-400 border border-sky-500/30 shrink-0 mt-0.5">
                  ℹ️
                </div>
                <div className="text-xs leading-relaxed text-sky-200">
                  <span className="font-semibold text-sky-300">Deterministic &amp; Non-Destructive Preview:</span>
                  <span className="ml-1 text-slate-300">
                    Clicking &quot;Check&quot; runs the offline cleaning engine in memory only. Nothing is modified in MongoDB until you review the full audit report.
                  </span>
                </div>
              </div>

              {loadingCollections ? (
                <div className="py-12 text-center text-xs text-slate-400">
                  <span className="inline-block w-5 h-5 border-2 border-sky-400 border-t-transparent rounded-full animate-spin mb-2"></span>
                  <div>Loading MongoDB collections...</div>
                </div>
              ) : collections.length === 0 ? (
                <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-8 text-center text-xs text-slate-400">
                  No configured collections found in the database.
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                  {collections.map((col) => (
                    <div
                      key={col.name}
                      className="bg-slate-800/80 hover:bg-slate-800 border border-slate-700/80 hover:border-sky-500/40 rounded-xl p-4 transition-all flex flex-col justify-between gap-3 shadow-md"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-mono font-bold text-sm text-white truncate" title={col.name}>
                              {col.name}
                            </span>
                            {col.is_backup && (
                              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                                BACKUP
                              </span>
                            )}
                            {col.is_cleaned && (
                              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                                CLEANED
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-slate-400 mt-1">
                            <span className="font-semibold text-slate-200">
                              {col.count.toLocaleString()}
                            </span>{' '}
                            documents
                          </div>
                        </div>

                        <button
                          type="button"
                          onClick={() => handleCheckCollection(col.name)}
                          disabled={col.count === 0}
                          className="px-3.5 py-1.5 bg-sky-600 hover:bg-sky-500 disabled:opacity-40 disabled:pointer-events-none text-white text-xs font-semibold rounded-lg shadow-sm transition-all shrink-0 flex items-center gap-1.5"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                          </svg>
                          <span>Check</span>
                        </button>
                      </div>

                      {/* Associated collections indicator */}
                      {(col.has_backup || col.has_cleaned) && (
                        <div className="pt-2 border-t border-slate-700/60 text-[11px] text-slate-400 flex items-center gap-2 font-mono">
                          {col.has_backup && <span>• {col.name}_backup exists</span>}
                          {col.has_cleaned && <span>• {col.name}_cleaned exists</span>}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ========================================================================= */}
          {/* STAGE: Loading */}
          {/* ========================================================================= */}
          {stage === 'loading' && (
            <div className="bg-slate-800/60 border border-slate-700/80 rounded-2xl p-10 text-center space-y-4 shadow-inner">
              <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-emerald-500/15 border border-emerald-400/40 text-emerald-400 animate-spin text-xl">
                ⚙️
              </div>
              <div>
                <h3 className="text-base font-bold text-white tracking-wide">
                  {loadingMessage}
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  Querying documents, evaluating schema headers, formatting contact phones, and generating audit diffs...
                </p>
              </div>
              <div className="inline-block px-3 py-1 rounded-full bg-slate-900/80 border border-slate-700 text-[11px] font-mono text-emerald-400">
                100% In-Memory Dry Run • Zero Records Changed
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* STAGE 2: Report Screen (Reusing CleaningReportView) */}
          {/* ========================================================================= */}
          {stage === 'report' && previewData && (
            <div className="space-y-6">
              <CleaningReportView
                previewData={previewData}
                onDownloadReport={handleDownloadReport}
                changeFilter={changeFilter}
                onChangeFilter={setChangeFilter}
                changePage={changePage}
                onChangePage={setChangePage}
                changePageSize={changePageSize}
                onChangePageSize={setChangePageSize}
                isExistingCollection={true}
                loading={loading}
              />
            </div>
          )}

          {/* ========================================================================= */}
          {/* STAGE 3: Applied Result */}
          {/* ========================================================================= */}
          {stage === 'applied' && applyResult && (
            <div className="bg-slate-800/80 border border-emerald-500/40 rounded-2xl p-8 space-y-6 shadow-2xl">
              <div className="text-center space-y-3">
                <div className="w-16 h-16 rounded-full bg-emerald-500/20 border border-emerald-400 text-emerald-400 mx-auto flex items-center justify-center text-3xl shadow-inner">
                  ✓
                </div>
                <h3 className="text-xl font-bold text-white">{applyResult.message}</h3>
                <div className="text-xs text-slate-400">
                  Target collection:{' '}
                  <span className="font-mono text-emerald-300 font-bold">
                    {applyResult.target_collection}
                  </span>
                </div>
              </div>

              {/* Metrics */}
              <div className="grid grid-cols-2 gap-3 max-w-md mx-auto">
                <div className="bg-slate-900/90 p-4 rounded-xl border border-slate-800 text-center">
                  <div className="text-[10px] text-slate-400 uppercase font-mono font-semibold">Rows Written</div>
                  <div className="text-2xl font-bold text-emerald-400 mt-1">
                    {applyResult.rows_written.toLocaleString()}
                  </div>
                </div>
                <div className="bg-slate-900/90 p-4 rounded-xl border border-slate-800 text-center">
                  <div className="text-[10px] text-slate-400 uppercase font-mono font-semibold">Backup Collection</div>
                  <div className="text-sm font-mono font-bold text-white mt-2 truncate" title={applyResult.backup_collection || 'None'}>
                    {applyResult.backup_collection || '(Untouched)'}
                  </div>
                </div>
              </div>

              {/* Next Steps Guidance */}
              {applyResult.next_steps && applyResult.next_steps.length > 0 && (
                <div className="bg-slate-900/80 rounded-xl p-4 border border-slate-700/80 space-y-2">
                  <div className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                    <span>📌</span>
                    <span>Next Steps &amp; Instructions:</span>
                  </div>
                  <ul className="space-y-1.5 text-xs text-slate-300">
                    {applyResult.next_steps.map((stepItem, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <span className="text-sky-400 font-bold shrink-0">•</span>
                        <span>{stepItem}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Modal Footer / Navigation Controls */}
        <footer className="p-4 sm:p-5 border-t border-slate-800 bg-slate-950/70 flex items-center justify-between gap-3 flex-wrap">
          <button
            className="px-4 py-2 rounded-xl border border-slate-700 bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-300 transition-colors"
            onClick={handleClose}
            disabled={loading || applying}
            type="button"
          >
            {stage === 'applied' ? 'Close' : 'Cancel'}
          </button>

          <div className="flex items-center gap-3">
            {stage === 'report' && (
              <>
                <button
                  type="button"
                  onClick={() => setStage('list')}
                  className="px-4 py-2 rounded-xl border border-slate-700 bg-slate-900 hover:bg-slate-800 text-xs font-medium text-slate-300 transition-colors"
                >
                  ← Back to Collections
                </button>

                {/* Safe Option: Create cleaned copy */}
                <button
                  type="button"
                  onClick={handleApplyNewCollection}
                  disabled={applying}
                  className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-semibold text-white bg-sky-600 hover:bg-sky-500 shadow-md transition-all disabled:opacity-50"
                  title="Writes to <name>_cleaned and leaves the original untouched"
                >
                  <span>Create Cleaned Copy</span>
                  <span className="font-mono text-[10px] text-sky-200">({selectedCollection}_cleaned)</span>
                </button>

                {/* Destructive Option: Replace original */}
                <button
                  type="button"
                  onClick={() => {
                    setShowReplaceDialog(true);
                    setTypedConfirmName('');
                  }}
                  disabled={applying}
                  className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-semibold text-rose-200 bg-rose-950/80 hover:bg-rose-900/90 border border-rose-600/40 shadow-md transition-all disabled:opacity-50"
                  title="Backs up original to <name>_backup and replaces data in the collection"
                >
                  <span>Replace Original (Backup First)</span>
                </button>
              </>
            )}

            {stage === 'applied' && (
              <button
                type="button"
                onClick={() => setStage('list')}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs sm:text-sm font-semibold text-white bg-sky-600 hover:bg-sky-500 shadow-md transition-all"
              >
                Clean Another Collection
              </button>
            )}
          </div>
        </footer>
      </div>

      {/* Safety Dialog for "Replace original (backup first)" */}
      {showReplaceDialog && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-md bg-slate-900 border border-rose-500/50 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-rose-400">
              <span className="text-2xl">⚠️</span>
              <h3 className="text-base font-bold text-white">Confirm Collection Replacement</h3>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              This will create a verified backup at{' '}
              <span className="font-mono text-amber-300 font-bold">{selectedCollection}_backup</span>,
              and overwrite the documents in{' '}
              <span className="font-mono text-rose-300 font-bold">{selectedCollection}</span> with
              the cleaned data.
            </p>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                To confirm, type <span className="font-mono text-rose-300 font-bold">{selectedCollection}</span>:
              </label>
              <input
                type="text"
                className="w-full bg-slate-950 border border-slate-700 text-white rounded-xl px-3 py-2 text-xs focus:ring-2 focus:ring-rose-500 focus:outline-none font-mono"
                value={typedConfirmName}
                onChange={(e) => setTypedConfirmName(e.target.value)}
                placeholder={selectedCollection}
                autoFocus
              />
            </div>

            <div className="pt-2 flex items-center justify-end gap-2.5">
              <button
                type="button"
                className="px-4 py-2 rounded-xl border border-slate-700 bg-slate-800 text-xs text-slate-300 hover:bg-slate-700"
                onClick={() => {
                  setShowReplaceDialog(false);
                  setTypedConfirmName('');
                }}
                disabled={applying}
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={handleApplyReplace}
                disabled={typedConfirmName.trim() !== selectedCollection || applying}
                className="px-5 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 disabled:opacity-40 disabled:pointer-events-none text-white font-bold text-xs shadow-lg transition-all flex items-center gap-1.5"
              >
                {applying ? (
                  <>
                    <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                    <span>Backing up &amp; Replacing...</span>
                  </>
                ) : (
                  <span>I understand, replace collection</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

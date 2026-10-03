import React, { useState, useRef } from 'react';
import { previewDatasetFile, confirmDatasetUpload } from '../api';
import { exportCleaningReportToPdf } from '../utils/reportPdfExporter';

const SUPPORTED_EXTENSIONS = ['.csv', '.xlsx', '.xls'];

export default function FileUploadModal({ isOpen, onClose, onUploadSuccess }) {
  const [dragActive, setDragActive] = useState(false);
  const [filesQueue, setFilesQueue] = useState([]);
  const [activeReviewId, setActiveReviewId] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [globalError, setGlobalError] = useState('');
  const [confirmingId, setConfirmingId] = useState(null);
  const [savedSuccessId, setSavedSuccessId] = useState(null);
  const [isSavingAll, setIsSavingAll] = useState(false);
  const [downloadingReport, setDownloadingReport] = useState(false);

  const fileInputRef = useRef(null);

  if (!isOpen) return null;

  const resetState = () => {
    setFilesQueue([]);
    setActiveReviewId(null);
    setIsProcessing(false);
    setGlobalError('');
    setConfirmingId(null);
    setSavedSuccessId(null);
    setIsSavingAll(false);
    setDownloadingReport(false);
  };

  const handleClose = () => {
    if (isProcessing || isSavingAll) return;
    resetState();
    onClose();
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return '0.00 MB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  // Process a batch of files (supports single or multi-file uploads)
  const handleFilesSelected = async (fileList) => {
    setGlobalError('');
    if (!fileList || fileList.length === 0) return;

    const filesArray = Array.from(fileList);
    const validQueueItems = [];

    for (let i = 0; i < filesArray.length; i++) {
      const f = filesArray[i];
      const ext = '.' + f.name.split('.').pop().toLowerCase();
      if (!SUPPORTED_EXTENSIONS.includes(ext)) {
        setGlobalError(`Some files were skipped: only .csv, .xlsx, and .xls formats are supported.`);
        continue;
      }

      validQueueItems.push({
        id: `${f.name}-${Date.now()}-${i}`,
        file: f,
        name: f.name,
        size: f.size,
        status: 'queued', // queued | inspecting | saving | auto_saved | needs_review | confirmed | error
        errorMsg: '',
        previewData: null,
        saveResult: null,
      });
    }

    if (validQueueItems.length === 0) return;

    setFilesQueue(validQueueItems);
    setIsProcessing(true);

    const updatedQueue = [...validQueueItems];

    for (let idx = 0; idx < updatedQueue.length; idx++) {
      const item = { ...updatedQueue[idx] };
      item.status = 'inspecting';
      updatedQueue[idx] = item;
      setFilesQueue([...updatedQueue]);

      try {
        const previewRes = await previewDatasetFile(item.file);
        item.previewData = previewRes;

        // RULE: If dataset is already clean, directly save to MongoDB without report or confirmation
        const isClean = previewRes.is_fully_clean === true || (previewRes.total_changes === 0);

        if (isClean) {
          item.status = 'saving';
          updatedQueue[idx] = { ...item };
          setFilesQueue([...updatedQueue]);

          const baseName = item.name.replace(/\.[^/.]+$/, '');
          let saveRes;
          try {
            saveRes = await confirmDatasetUpload(previewRes.preview_id, baseName, 'append');
          } catch (confirmErr) {
            // Auto-heal if preview expired: re-preview and confirm
            if (confirmErr.message && (confirmErr.message.includes('expired') || confirmErr.message.includes('not found'))) {
              const fresh = await previewDatasetFile(item.file);
              saveRes = await confirmDatasetUpload(fresh.preview_id, baseName, 'append');
            } else {
              throw confirmErr;
            }
          }
          item.status = 'auto_saved';
          item.saveResult = saveRes;
        } else {
          // Dataset had fields separated or split -> presents review report
          item.status = 'needs_review';
        }
      } catch (err) {
        item.status = 'error';
        item.errorMsg = err.message || 'Error processing file';
      }

      updatedQueue[idx] = { ...item };
      setFilesQueue([...updatedQueue]);
    }

    setIsProcessing(false);

    // If single file uploaded and it needs review, open its review report directly
    if (updatedQueue.length === 1 && updatedQueue[0].status === 'needs_review') {
      setActiveReviewId(updatedQueue[0].id);
    }
  };

  const handleConfirmSingle = async (item) => {
    if (!item?.file) return;
    setConfirmingId(item.id);

    try {
      const baseName = item.name.replace(/\.[^/.]+$/, '');
      let previewId = item.previewData?.preview_id;

      if (!previewId) {
        const freshPreview = await previewDatasetFile(item.file);
        previewId = freshPreview.preview_id;
        item.previewData = freshPreview;
      }

      let saveRes;
      try {
        saveRes = await confirmDatasetUpload(previewId, baseName, 'append');
      } catch (err) {
        // Auto-heal expired preview
        if (err.message && (err.message.includes('expired') || err.message.includes('not found'))) {
          const fresh = await previewDatasetFile(item.file);
          saveRes = await confirmDatasetUpload(fresh.preview_id, baseName, 'append');
        } else {
          throw err;
        }
      }

      item.status = 'confirmed';
      item.saveResult = saveRes;
      setSavedSuccessId(item.id);
      setFilesQueue((prev) => prev.map((q) => (q.id === item.id ? { ...item } : q)));

      if (onUploadSuccess) onUploadSuccess(saveRes);

      // Show saved acknowledgment in button, then auto-close modal
      setTimeout(() => {
        handleClose();
      }, 1200);
    } catch (err) {
      item.status = 'error';
      item.errorMsg = err.message || 'Failed to save dataset';
      setFilesQueue((prev) => prev.map((q) => (q.id === item.id ? { ...item } : q)));
    } finally {
      setConfirmingId(null);
    }
  };

  const handleConfirmAll = async () => {
    const pendingItems = filesQueue.filter((i) => i.status === 'needs_review');
    if (pendingItems.length === 0) return;

    setIsSavingAll(true);
    let anySaved = false;

    for (const item of pendingItems) {
      try {
        const baseName = item.name.replace(/\.[^/.]+$/, '');
        let previewId = item.previewData?.preview_id;

        if (!previewId) {
          const fresh = await previewDatasetFile(item.file);
          previewId = fresh.preview_id;
        }

        let saveRes;
        try {
          saveRes = await confirmDatasetUpload(previewId, baseName, 'append');
        } catch (err) {
          if (err.message && (err.message.includes('expired') || err.message.includes('not found'))) {
            const fresh = await previewDatasetFile(item.file);
            saveRes = await confirmDatasetUpload(fresh.preview_id, baseName, 'append');
          } else {
            throw err;
          }
        }

        item.status = 'confirmed';
        item.saveResult = saveRes;
        anySaved = true;
      } catch (err) {
        item.status = 'error';
        item.errorMsg = err.message || 'Failed to save dataset';
      }
      setFilesQueue([...filesQueue]);
    }

    setIsSavingAll(false);
    if (anySaved && onUploadSuccess) {
      onUploadSuccess();
      setTimeout(() => {
        handleClose();
      }, 1200);
    }
  };

  const handleDownloadReportPdf = (item) => {
    if (!item?.previewData) return;
    setDownloadingReport(true);
    try {
      exportCleaningReportToPdf(item.previewData, item.name);
    } catch (err) {
      console.error('PDF generation error:', err);
    } finally {
      setDownloadingReport(false);
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFilesSelected(e.dataTransfer.files);
    }
  };

  const handleFileInputChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFilesSelected(e.target.files);
    }
  };

  const activeReviewItem = activeReviewId
    ? filesQueue.find((q) => q.id === activeReviewId)
    : null;

  const totalSavedCount = filesQueue.filter(
    (q) => q.status === 'auto_saved' || q.status === 'confirmed'
  ).length;

  const pendingReviewCount = filesQueue.filter(
    (q) => q.status === 'needs_review'
  ).length;

  const allCompleted =
    filesQueue.length > 0 &&
    !isProcessing &&
    !filesQueue.some((q) => q.status === 'queued' || q.status === 'inspecting' || q.status === 'saving' || q.status === 'needs_review');

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 overflow-y-auto animate-fadeIn"
      role="dialog"
      aria-modal="true"
    >
      {/* Backdrop */}
      <div
        aria-hidden="true"
        className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm transition-opacity"
        onClick={handleClose}
      />

      {/* Main Modal Card */}
      <div
        className={`relative w-full ${activeReviewItem ? 'max-w-4xl' : 'max-w-2xl'} bg-white text-slate-800 rounded-3xl shadow-xl shadow-slate-200/70 border border-slate-100 p-5 sm:p-7 relative flex flex-col justify-between max-h-[92vh] z-10`}
        data-purpose="modal-container"
      >
        {/* Top Close Button */}
        <button
          aria-label="Close dialog"
          className="absolute top-5 right-5 sm:top-6 sm:right-6 w-9 h-9 rounded-xl border border-slate-200/80 bg-slate-50/70 hover:bg-slate-100 text-slate-400 hover:text-slate-600 flex items-center justify-center transition-colors cursor-pointer"
          onClick={handleClose}
          disabled={isProcessing || isSavingAll || confirmingId !== null}
          type="button"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" viewBox="0 0 24 24">
            <line x1="18" x2="6" y1="6" y2="18"></line>
            <line x1="6" x2="18" y1="6" y2="18"></line>
          </svg>
        </button>

        {/* Modal Header Section */}
        <header className="flex items-start gap-4 mb-6 pr-10">
          <div className="w-12 h-12 rounded-2xl bg-sky-50 border border-sky-100 flex items-center justify-center shrink-0 text-sky-500 shadow-sm shadow-sky-100/50" data-purpose="header-icon">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" viewBox="0 0 24 24">
              <path d="M4 16.5v1.5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-1.5M12 14.5v-11M7.5 8 12 3.5 16.5 8"></path>
            </svg>
          </div>
          <div className="flex-1 pt-0.5">
            <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 leading-snug">
              {activeReviewItem
                ? `Cleaning Report: ${activeReviewItem.name}`
                : allCompleted
                ? 'Upload & Storage Completed'
                : 'Upload Dataset'}
            </h2>
            <p className="text-xs sm:text-sm text-slate-500 mt-1 leading-relaxed max-w-lg">
              {activeReviewItem
                ? 'Review the separated and cleaned records below. Click confirm below to save to MongoDB.'
                : 'Clean datasets are saved directly to MongoDB without confirmation. Files requiring cleaning present a simple report.'}
            </p>
          </div>
        </header>

        {/* Modal Body Container */}
        <div className="flex-1 overflow-y-auto pr-1 space-y-4">
          {/* Global Error Banner */}
          {globalError && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3.5 flex items-start gap-3 text-xs text-rose-700">
              <span className="text-rose-500 font-bold shrink-0">⚠️</span>
              <span className="flex-1">{globalError}</span>
            </div>
          )}

          {/* VIEW 1: ACTIVE REVIEW REPORT VIEW (STICKY BACK HEADER) */}
          {activeReviewItem ? (
            <div className="space-y-4">
              {/* STICKY TOP BACK BAR: pinned at the top while scrolling */}
              <div className="sticky top-0 z-20 bg-white/95 backdrop-blur-md -mx-5 -mt-2 px-5 py-2.5 border-b border-slate-100 flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => setActiveReviewId(null)}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-sky-600 hover:text-sky-700 cursor-pointer"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M15 19l-7-7 7-7" />
                  </svg>
                  <span>Back to all uploaded files</span>
                </button>

                <span className="text-[11px] font-mono text-slate-400">
                  {formatFileSize(activeReviewItem.size)}
                </span>
              </div>

              {/* Simple Metrics Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-1">
                <div className="bg-slate-50 rounded-2xl p-4 border border-slate-200/80">
                  <div className="text-[10px] text-slate-500 uppercase font-semibold font-mono">Records Found</div>
                  <div className="text-xl font-bold text-slate-900 mt-0.5">
                    {activeReviewItem.previewData?.summary?.rows_in?.toLocaleString() ?? 0}
                  </div>
                </div>

                <div className="bg-amber-50/70 rounded-2xl p-4 border border-amber-200/80">
                  <div className="text-[10px] text-amber-700 uppercase font-semibold font-mono">Separations / Fixes</div>
                  <div className="text-xl font-bold text-amber-700 mt-0.5">
                    {activeReviewItem.previewData?.total_changes?.toLocaleString() ?? 0}
                  </div>
                </div>

                <div className="bg-emerald-50/70 rounded-2xl p-4 border border-emerald-200/80 col-span-2 sm:col-span-1">
                  <div className="text-[10px] text-emerald-700 uppercase font-semibold font-mono">Clean Records Ready</div>
                  <div className="text-xl font-bold text-emerald-700 mt-0.5">
                    {activeReviewItem.previewData?.summary?.rows_out?.toLocaleString() ?? 0}
                  </div>
                </div>
              </div>

              {/* Plain-Language Explanation of What Changed */}
              <div className="bg-sky-50/70 border border-sky-200/80 rounded-2xl p-4">
                <h4 className="text-xs font-bold text-sky-950 uppercase tracking-wide font-mono mb-2">
                  What was cleaned in this dataset:
                </h4>
                <ul className="space-y-1.5 text-xs text-sky-900">
                  {Object.entries(activeReviewItem.previewData?.summary?.changes_by_type || {}).map(([action, count]) => {
                    const descriptions = {
                      phone_extracted_from_company: 'Contact numbers found inside Company Name were moved into the Phone column',
                      phone_extracted_from_name: 'Contact numbers found inside Contact Name were moved into the Phone column',
                      company_split: 'Multiple companies listed on separate lines were split into individual rows',
                      person_split: 'Multiple contact persons (separated by ;) were split into separate contacts',
                      location_split: 'Addresses and locations were structured into Address, City, and State',
                      multiple_phones_split: 'Multiple contact numbers were separated into Primary and Secondary Phone',
                      multiple_emails_split: 'Multiple email addresses were separated into Primary and Secondary Email',
                      empty_row_removed: 'Empty blank rows were removed',
                    };
                    const label = descriptions[action] || action.replace(/_/g, ' ');
                    return (
                      <li key={action} className="flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-sky-500"></span>
                        <span className="font-semibold">{label}:</span>
                        <span className="font-mono bg-white px-2 py-0.5 rounded border border-sky-200 text-sky-800 font-bold">
                          {count}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </div>

              {/* Human-Understandable Changes Table */}
              <div className="border border-slate-200 rounded-2xl overflow-hidden shadow-xs">
                <div className="bg-slate-100/80 px-4 py-2.5 border-b border-slate-200 flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-700 font-mono uppercase">
                    Preview of Separated Records (Before → After)
                  </span>
                  <span className="text-[11px] text-slate-500 font-mono">
                    Showing first {Math.min(15, activeReviewItem.previewData?.changes?.length || 0)} changes
                  </span>
                </div>

                <div className="overflow-x-auto max-h-60">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 text-slate-500 font-mono uppercase text-[10px] border-b border-slate-200">
                      <tr>
                        <th className="px-3.5 py-2">Row</th>
                        <th className="px-3.5 py-2">Field</th>
                        <th className="px-3.5 py-2">Original In File</th>
                        <th className="px-3.5 py-2">Separated Clean Value</th>
                        <th className="px-3.5 py-2">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {(activeReviewItem.previewData?.changes || []).slice(0, 15).map((ch, idx) => (
                        <tr key={idx} className="hover:bg-slate-50/80">
                          <td className="px-3.5 py-2.5 font-mono text-slate-400">#{ch.source_row}</td>
                          <td className="px-3.5 py-2.5 font-semibold text-slate-700 capitalize">{ch.field || 'Record'}</td>
                          <td className="px-3.5 py-2.5 text-rose-700 bg-rose-50/50 font-mono font-medium max-w-xs truncate">
                            {ch.before}
                          </td>
                          <td className="px-3.5 py-2.5 text-emerald-700 bg-emerald-50/50 font-mono font-medium max-w-xs truncate">
                            {ch.after}
                          </td>
                          <td className="px-3.5 py-2.5 text-slate-600 text-[11px]">
                            {ch.what_happened || ch.action}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : (
            /* VIEW 2: INITIAL UPLOAD VIEW & MULTI-FILE QUEUE */
            <div className="space-y-4">
              {/* DropzoneSection matching requested design */}
              <div
                className={`dashed-dropzone rounded-2xl py-10 px-4 sm:px-8 flex flex-col items-center justify-center text-center transition-all cursor-pointer ${
                  dragActive ? 'border-sky-600 bg-sky-50/80 scale-[1.01]' : ''
                }`}
                data-purpose="file-dropzone"
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                {/* Visual Flow Icons (Spreadsheet -> Exchange -> Database) */}
                <div className="flex items-center gap-3 sm:gap-4 mb-5">
                  {/* Spreadsheet Icon */}
                  <div className="w-12 h-12 rounded-xl bg-emerald-50 border border-emerald-200/80 text-emerald-600 flex items-center justify-center shadow-sm">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24">
                      <rect height="18" rx="2" width="18" x="3" y="3"></rect>
                      <path d="M3 9h18M3 15h18M9 9v12"></path>
                    </svg>
                  </div>
                  {/* Transfer / Sync Arrows */}
                  <div className="text-sky-400">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24">
                      <path d="M7 16V4M7 4L3 8M7 4l4 4M17 8v12M17 20l4-4M17 20l-4-4"></path>
                    </svg>
                  </div>
                  {/* Database Icon */}
                  <div className="w-12 h-12 rounded-xl bg-sky-50 border border-sky-200/80 text-sky-500 flex items-center justify-center shadow-sm">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24">
                      <ellipse cx="12" cy="5" rx="8" ry="3"></ellipse>
                      <path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"></path>
                    </svg>
                  </div>
                </div>

                {/* Instruction Text */}
                <h3 className="text-base sm:text-lg font-bold text-slate-800 tracking-tight mb-1.5">
                  Choose or drag a file here
                </h3>
                {/* Supported Extensions */}
                <p className="text-xs text-slate-400 mb-6 font-medium">
                  Supports <span className="font-mono font-semibold text-sky-600">.csv</span>, <span className="font-mono font-semibold text-sky-600">.xlsx</span>, <span className="font-mono font-semibold text-sky-600">.xls</span>
                </p>
                {/* Primary Action Button */}
                <button
                  type="button"
                  className="inline-flex items-center gap-2.5 px-6 py-2.5 rounded-full bg-[#0095FF] hover:bg-[#0082de] active:scale-[0.98] text-white font-medium text-sm sm:text-base shadow-sm shadow-sky-500/25 transition-all cursor-pointer"
                  onClick={(e) => {
                    e.stopPropagation();
                    fileInputRef.current?.click();
                  }}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" viewBox="0 0 24 24">
                    <path d="M3 7v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-6l-2-2H5a2 2 0 0 0-2 2z"></path>
                  </svg>
                  Select File
                </button>

                {/* Hidden file input */}
                <input
                  ref={fileInputRef}
                  accept=".csv,.xlsx,.xls"
                  className="hidden"
                  id="file-upload-input"
                  type="file"
                  multiple
                  onChange={handleFileInputChange}
                />
              </div>

              {/* Uploaded Files Queue List (When multiple files are selected) */}
              {filesQueue.length > 0 && (
                <div className="space-y-3 pt-2">
                  <div className="flex items-center justify-between pb-1">
                    <span className="text-xs font-bold text-slate-700 font-mono uppercase">
                      Selected Files ({filesQueue.length})
                    </span>
                    {pendingReviewCount > 0 && (
                      <span className="text-xs font-semibold text-sky-700 bg-sky-50 border border-sky-200 px-2 py-0.5 rounded-full">
                        {pendingReviewCount} ready for confirmation
                      </span>
                    )}
                  </div>

                  <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                    {filesQueue.map((item) => (
                      <div
                        key={item.id}
                        className="bg-slate-50 border border-slate-200 rounded-xl p-3 flex items-center justify-between gap-3 text-xs"
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          <div className="w-8 h-8 rounded-lg bg-white border border-slate-200 flex items-center justify-center shrink-0 text-slate-600 font-mono text-[10px] font-bold">
                            {item.name.split('.').pop().toUpperCase()}
                          </div>
                          <div className="min-w-0">
                            <div className="font-semibold text-slate-800 truncate max-w-xs sm:max-w-sm">
                              {item.name}
                            </div>
                            <div className="text-[10px] text-slate-400 font-mono">
                              {formatFileSize(item.size)}
                              {item.saveResult && (
                                <span className="text-emerald-600 ml-1.5 font-bold">
                                  • {item.saveResult.inserted ?? item.saveResult.record_count ?? 0} records saved
                                </span>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Status Badge & Actions */}
                        <div className="flex items-center gap-2 shrink-0">
                          {item.status === 'queued' && (
                            <span className="px-2 py-0.5 rounded-full bg-slate-200 text-slate-700 text-[10px] font-mono">
                              Queued
                            </span>
                          )}

                          {item.status === 'inspecting' && (
                            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-sky-50 text-sky-700 border border-sky-200 text-[10px] font-mono font-medium animate-pulse">
                              <span className="w-1.5 h-1.5 rounded-full bg-sky-500 animate-ping" />
                              Cleaning...
                            </span>
                          )}

                          {item.status === 'saving' && (
                            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200 text-[10px] font-mono font-medium animate-pulse">
                              Saving...
                            </span>
                          )}

                          {item.status === 'auto_saved' && (
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-[11px] font-semibold">
                              ✓ Auto-Saved (Clean)
                            </span>
                          )}

                          {item.status === 'confirmed' && (
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-[11px] font-semibold">
                              ✓ Saved to MongoDB
                            </span>
                          )}

                          {item.status === 'needs_review' && (
                            <button
                              type="button"
                              onClick={() => setActiveReviewId(item.id)}
                              className="px-2.5 py-1 rounded-lg bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-300 text-[11px] font-semibold transition-colors cursor-pointer"
                            >
                              Review Fixes ({item.previewData?.total_changes || 0})
                            </button>
                          )}

                          {item.status === 'error' && (
                            <span className="px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200 text-[10px] font-mono" title={item.errorMsg}>
                              Error
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Summary of Saved Files */}
              {allCompleted && (
                <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-4 flex items-center justify-between gap-3 text-xs">
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-full bg-emerald-500 text-white flex items-center justify-center font-bold text-sm shrink-0">
                      ✓
                    </div>
                    <div>
                      <div className="font-bold text-emerald-950">
                        {totalSavedCount} of {filesQueue.length} files successfully saved to MongoDB
                      </div>
                      <div className="text-[11px] text-emerald-700 font-mono mt-0.5">
                        Clean records indexed and ready for AI search.
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Modal Footer Actions */}
        <footer className="mt-6 pt-4 border-t border-slate-100 flex items-center justify-between gap-3 flex-wrap">
          {activeReviewItem ? (
            /* FOOTER: REVIEWING SINGLE FILE */
            <>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setActiveReviewId(null)}
                  className="px-4 py-2 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100 text-xs font-medium text-slate-700 cursor-pointer transition-colors"
                >
                  Cancel
                </button>
                {/* Download Audit Report in PDF Format */}
                <button
                  type="button"
                  onClick={() => handleDownloadReportPdf(activeReviewItem)}
                  disabled={downloadingReport}
                  className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-xs font-medium text-slate-700 cursor-pointer shadow-xs disabled:opacity-60 transition-colors"
                >
                  {downloadingReport ? (
                    <>
                      <svg className="animate-spin w-3.5 h-3.5 text-sky-600" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" fill="currentColor" />
                      </svg>
                      <span className="text-sky-700 font-semibold">Generating PDF...</span>
                    </>
                  ) : (
                    <>
                      <svg className="w-3.5 h-3.5 text-rose-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                      </svg>
                      <span>Download Audit Report (PDF)</span>
                    </>
                  )}
                </button>
              </div>

              {/* Save & Confirm Button with Saved Acknowledgment */}
              <div className="ml-auto">
                <button
                  type="button"
                  onClick={() => handleConfirmSingle(activeReviewItem)}
                  disabled={confirmingId === activeReviewItem.id || savedSuccessId === activeReviewItem.id || activeReviewItem.status === 'confirmed'}
                  className={`inline-flex items-center gap-2 px-6 py-2.5 rounded-full text-xs sm:text-sm font-semibold shadow-md cursor-pointer transition-all active:scale-95 ${
                    savedSuccessId === activeReviewItem.id || activeReviewItem.status === 'confirmed'
                      ? 'bg-emerald-600 text-white ring-2 ring-emerald-300'
                      : 'bg-[#0095FF] hover:bg-[#0082de] text-white shadow-sky-500/25'
                  }`}
                >
                  {confirmingId === activeReviewItem.id ? (
                    <>
                      <svg className="animate-spin w-4 h-4 text-white" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" fill="currentColor" />
                      </svg>
                      <span>Saving to MongoDB...</span>
                    </>
                  ) : savedSuccessId === activeReviewItem.id || activeReviewItem.status === 'confirmed' ? (
                    <>
                      <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                      <span>✓ Saved to MongoDB</span>
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                      <span>Confirm &amp; Save to MongoDB</span>
                    </>
                  )}
                </button>
              </div>
            </>
          ) : allCompleted ? (
            /* FOOTER: ALL FILES PROCESSED */
            <>
              <button
                type="button"
                onClick={resetState}
                className="px-5 py-2 rounded-xl text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-200/60 active:scale-95 transition-all cursor-pointer"
              >
                Upload More
              </button>
              <button
                type="button"
                onClick={handleClose}
                className="px-8 py-2.5 rounded-full text-xs font-bold text-white bg-[#0095FF] hover:bg-[#0082de] shadow-md cursor-pointer ml-auto transition-transform active:scale-95"
              >
                Done
              </button>
            </>
          ) : (
            /* FOOTER: INITIAL UPLOAD STATE */
            <>
              <button
                type="button"
                onClick={handleClose}
                disabled={isProcessing || isSavingAll}
                className="px-5 py-2 rounded-xl text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-200/60 active:scale-95 transition-all cursor-pointer disabled:opacity-50"
              >
                Cancel
              </button>

              {isProcessing ? (
                <div className="flex items-center gap-2 text-xs font-medium text-sky-700 ml-auto">
                  <svg className="animate-spin h-4 w-4 text-sky-600" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" fill="currentColor" />
                  </svg>
                  <span>Processing dataset...</span>
                </div>
              ) : pendingReviewCount > 0 ? (
                <button
                  type="button"
                  onClick={handleConfirmAll}
                  disabled={isSavingAll}
                  className="inline-flex items-center gap-2 px-6 py-2.5 rounded-full text-xs font-bold text-white bg-[#0095FF] hover:bg-[#0082de] shadow-md cursor-pointer ml-auto disabled:opacity-50 transition-all active:scale-95"
                >
                  {isSavingAll ? (
                    <>
                      <svg className="animate-spin w-4 h-4 text-white" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" fill="currentColor" />
                      </svg>
                      <span>Saving All to MongoDB...</span>
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                      <span>Confirm &amp; Save All {pendingReviewCount} Datasets</span>
                    </>
                  )}
                </button>
              ) : null}
            </>
          )}
        </footer>
      </div>
    </div>
  );
}

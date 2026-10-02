import React, { useState, useRef } from 'react';
import { uploadDatasetFile, inspectDatasetFile } from '../api';

const SUPPORTED_EXTENSIONS = ['.csv', '.xlsx', '.xls', '.json', '.xml', '.txt'];

export default function FileUploadModal({ isOpen, onClose, onUploadSuccess }) {
  const [dragActive, setDragActive] = useState(false);
  const [file, setFile] = useState(null);
  const [availableSheets, setAvailableSheets] = useState([]);
  const [selectedSheet, setSelectedSheet] = useState('');
  const [uploading, setUploading] = useState(false);
  const [pipelineStep, setPipelineStep] = useState(0); // 0=idle, 1=read, 2=schema, 3=mongo, 4=ready
  const [errorMessage, setErrorMessage] = useState('');
  const [previewMeta, setPreviewMeta] = useState(null);
  const fileInputRef = useRef(null);

  if (!isOpen) return null;

  const resetState = () => {
    setFile(null);
    setAvailableSheets([]);
    setSelectedSheet('');
    setUploading(false);
    setPipelineStep(0);
    setErrorMessage('');
    setPreviewMeta(null);
  };

  const handleClose = () => {
    if (uploading) return;
    resetState();
    onClose();
  };

  const validateAndProcessFile = async (selectedFile) => {
    setErrorMessage('');
    setPreviewMeta(null);
    setAvailableSheets([]);

    if (!selectedFile) return;

    const ext = '.' + selectedFile.name.split('.').pop().toLowerCase();
    if (!SUPPORTED_EXTENSIONS.includes(ext)) {
      setErrorMessage(
        `Unsupported file type '${ext}'. Please upload CSV, Excel (.xlsx, .xls), JSON, XML, or structured TXT data.`
      );
      setFile(null);
      return;
    }

    setFile(selectedFile);

    // If Excel, inspect sheets
    if (ext === '.xlsx' || ext === '.xls') {
      try {
        const inspectRes = await inspectDatasetFile(selectedFile);
        if (inspectRes?.available_sheets && inspectRes.available_sheets.length > 1) {
          setAvailableSheets(inspectRes.available_sheets);
          setSelectedSheet(inspectRes.available_sheets[0]);
        }
        if (inspectRes?.fields) {
          setPreviewMeta({
            fields: inspectRes.fields,
            recordCount: inspectRes.total_records_detected,
            sample: inspectRes.sample_records,
          });
        }
      } catch (err) {
        console.warn('Pre-inspection warning:', err);
      }
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
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndProcessFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files[0]) {
      validateAndProcessFile(e.target.files[0]);
    }
  };

  const handleUploadSubmit = async () => {
    if (!file || uploading) return;

    setUploading(true);
    setErrorMessage('');
    setPipelineStep(1); // Step 1: Read File

    try {
      await new Promise((r) => setTimeout(r, 450));
      setPipelineStep(2); // Step 2: Schema detection & JSON mapping

      const result = await uploadDatasetFile(file, selectedSheet || null);
      
      setPipelineStep(3); // Step 3: MongoDB Sync
      await new Promise((r) => setTimeout(r, 550));

      setPipelineStep(4); // Step 4: Ready

      setTimeout(() => {
        if (onUploadSuccess) {
          onUploadSuccess(result);
        }
        handleClose();
      }, 950);
    } catch (err) {
      setErrorMessage(err.message || 'The dataset could not be saved. Please try again.');
      setPipelineStep(0);
      setUploading(false);
    }
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return '0 MB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  return (
    <div
      className={`fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 lg:p-8 transition-opacity duration-200 ${
        isOpen ? 'opacity-100 visible' : 'opacity-0 invisible'
      }`}
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      {/* Soft neutral backdrop overlay with blur */}
      <div 
        aria-hidden="true" 
        className="fixed inset-0 bg-slate-900/25 backdrop-blur-sm transition-opacity"
        onClick={handleClose}
      />

      {/* Upload Modal Card */}
      <div className="relative w-full max-w-xl bg-white rounded-2xl shadow-xl shadow-slate-200/50 border border-slate-200 overflow-hidden transition-all duration-300 z-10">
        {/* Top Sky Accent Bar */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-sky-400 via-sky-500 to-sky-600"></div>

        {/* Modal Header */}
        <section className="p-6 sm:p-7 pb-4 border-b border-slate-100 relative">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-4">
              {/* Clean Upload Icon Badge */}
              <div className="w-12 h-12 rounded-xl border border-sky-100 bg-sky-50 flex items-center justify-center shadow-sm flex-shrink-0 text-sky-600">
                <svg className="w-6 h-6 stroke-[1.8]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" strokeLinecap="round" strokeLinejoin="round"></path>
                </svg>
              </div>

              {/* Title & Subtitle */}
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="text-xl font-bold tracking-tight text-slate-900" id="modal-title">
                    Upload Private Dataset
                  </h2>
                  <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-mono font-semibold rounded-full bg-sky-50 text-sky-700 border border-sky-200">
                    SECURE VAULT
                  </span>
                </div>
                <p className="mt-1.5 text-sm text-slate-500 leading-relaxed max-w-md">
                  Store structured records in MongoDB for AI search. Data is never sent to external LLMs.
                </p>
              </div>
            </div>

            {/* Close Modal Icon Button */}
            <button
              aria-label="Close dialog"
              className="w-8 h-8 rounded-lg border border-slate-200 bg-slate-50 text-slate-500 hover:text-slate-800 hover:bg-slate-100 hover:border-slate-300 transition-colors flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-sky-500/30"
              onClick={handleClose}
              disabled={uploading}
              type="button"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path d="M6 18L18 6M6 6l12 12" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"></path>
              </svg>
            </button>
          </div>
        </section>

        {/* Modal Body */}
        <section className="p-6 sm:p-7 space-y-5">
          {/* Stage 1: No file selected -> Drag & Drop Interactive Zone */}
          {!file && (
            <div
              className={`relative group rounded-xl p-8 sm:p-9 text-center bg-sky-50/40 border-2 border-dashed transition-all duration-200 cursor-pointer ${
                dragActive
                  ? 'border-sky-500 bg-sky-100/60 scale-[1.01]'
                  : 'border-sky-300 hover:border-sky-400 hover:bg-sky-50/70'
              }`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.xlsx,.xls,.json,.xml,.txt"
                onChange={handleFileInput}
                className="hidden"
              />

              {/* Multi-Icon Visual Badge */}
              <div className="flex items-center justify-center gap-3.5 mb-5">
                {/* Sheet / Table Record Icon */}
                <div className="w-12 h-12 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-600 flex items-center justify-center shadow-sm transform group-hover:-translate-y-1 transition-transform duration-200">
                  <svg className="w-6 h-6 stroke-[1.7]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path d="M3 10h18M3 14h18m-9-4v8m-7 4h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" strokeLinecap="round" strokeLinejoin="round"></path>
                  </svg>
                </div>
                {/* Intersecting Connection Flow Icon */}
                <div className="text-sky-400 text-lg select-none">⇄</div>
                {/* Database / Cloud Secure Storage Icon */}
                <div className="w-12 h-12 rounded-xl bg-sky-50 border border-sky-200 text-sky-600 flex items-center justify-center shadow-sm transform group-hover:-translate-y-1 transition-transform duration-200 delay-75">
                  <svg className="w-6 h-6 stroke-[1.7]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" strokeLinecap="round" strokeLinejoin="round"></path>
                  </svg>
                </div>
              </div>

              {/* Drag instructions */}
              <h3 className="text-base sm:text-lg font-semibold text-slate-900 tracking-tight mb-1.5">
                Drag &amp; Drop your dataset file here
              </h3>
              <p className="text-xs sm:text-sm text-slate-500 mb-6 font-mono">
                Supports <span className="text-sky-700 font-semibold">.csv</span>,{' '}
                <span className="text-sky-700 font-semibold">.xlsx</span>,{' '}
                <span className="text-sky-700 font-semibold">.xls</span>,{' '}
                <span className="text-sky-700 font-semibold">.json</span>,{' '}
                <span className="text-sky-700 font-semibold">.xml</span>,{' '}
                <span className="text-sky-700 font-semibold">.txt</span>{' '}
                <span className="text-slate-400">(up to 50MB)</span>
              </p>

              {/* Browse Files Action Button */}
              <button
                type="button"
                className="inline-flex items-center gap-2.5 px-5 py-2.5 rounded-xl text-sm font-medium text-white bg-sky-500 hover:bg-sky-600 shadow-sm hover:shadow transition-all duration-200 border border-sky-400 active:scale-98"
                onClick={(e) => {
                  e.stopPropagation();
                  fileInputRef.current?.click();
                }}
              >
                <svg className="w-4 h-4 text-sky-100" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"></path>
                </svg>
                <span>Browse Files</span>
              </button>
            </div>
          )}

          {/* Stage 2 & 3: File Selected State Card */}
          {file && (
            <div className="space-y-4">
              {/* Selected File Card */}
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex items-center justify-between">
                <div className="flex items-center space-x-3 min-w-0">
                  {/* Amber Document Icon */}
                  <div className="w-10 h-10 rounded-lg bg-amber-50 border border-amber-200 flex items-center justify-center shrink-0 text-amber-600">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                      <path d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" strokeLinecap="round" strokeLinejoin="round"></path>
                    </svg>
                  </div>
                  {/* File Details */}
                  <div className="min-w-0">
                    <h4 className="text-sm font-semibold text-slate-800 truncate">{file.name}</h4>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {formatFileSize(file.size)} <span className="mx-1">•</span> {file.name.split('.').pop().toUpperCase()} document
                    </p>
                  </div>
                </div>

                {/* Change File Button */}
                {!uploading && (
                  <button
                    className="text-xs font-medium text-sky-700 hover:text-sky-800 hover:underline shrink-0 ml-3"
                    onClick={() => {
                      setFile(null);
                      setPreviewMeta(null);
                      setAvailableSheets([]);
                    }}
                    type="button"
                  >
                    Change
                  </button>
                )}
              </div>

              {/* Optional Excel Worksheet Selector */}
              {!uploading && availableSheets.length > 1 && (
                <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl">
                  <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                    Select Worksheet to Import:
                  </label>
                  <select
                    className="w-full bg-white border border-slate-300 text-slate-800 text-xs rounded-lg p-2 focus:ring-2 focus:ring-sky-500 focus:outline-none"
                    value={selectedSheet}
                    onChange={(e) => setSelectedSheet(e.target.value)}
                  >
                    {availableSheets.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Processing Pipeline Stepper Card (When uploading) */}
              {uploading && (
                <div className="bg-slate-50/70 border border-slate-200 rounded-xl p-5">
                  {/* Stepper Header */}
                  <div className="flex items-center justify-between mb-6 pb-2.5 border-b border-slate-200/80">
                    <span className="text-xs font-semibold tracking-wider text-slate-500 uppercase font-mono">
                      PROCESSING PIPELINE
                    </span>
                    {/* In-progress animated status badge */}
                    <div className="flex items-center space-x-1.5 text-amber-600 text-xs font-medium">
                      <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-500 animate-ping"></span>
                      <span className="font-mono text-[11px] sm:text-xs font-medium">
                        {pipelineStep === 1
                          ? 'Validating file format...'
                          : pipelineStep === 2
                          ? 'Converting to JSON records...'
                          : pipelineStep === 3
                          ? 'Syncing to MongoDB Atlas...'
                          : 'Indexed & Ready!'}
                      </span>
                    </div>
                  </div>

                  {/* 4-Stage Stepper Track */}
                  <div className="relative flex items-center justify-between px-2 sm:px-4">
                    {/* Step 1: Read File */}
                    <div className="flex flex-col items-center relative z-10 group">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                        pipelineStep > 1
                          ? 'bg-emerald-500 text-white shadow-sm'
                          : 'border-2 border-amber-500 bg-amber-50 text-amber-700 glow-pulse-amber'
                      }`}>
                        {pipelineStep > 1 ? (
                          <svg className="w-4 h-4 stroke-[3]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path d="M4.5 12.75l6 6 9-13.5" strokeLinecap="round" strokeLinejoin="round"></path>
                          </svg>
                        ) : (
                          '1'
                        )}
                      </div>
                      <span className={`text-xs mt-2 ${pipelineStep >= 1 ? 'font-medium text-slate-700' : 'text-slate-400'}`}>
                        Read File
                      </span>
                    </div>

                    {/* Connector 1 -> 2 */}
                    <div className={`flex-1 h-[2px] mx-2 transition-all ${
                      pipelineStep > 1 ? 'bg-gradient-to-r from-emerald-400 to-amber-400' : 'bg-slate-200'
                    }`}></div>

                    {/* Step 2: Schema */}
                    <div className="flex flex-col items-center relative z-10 group">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                        pipelineStep > 2
                          ? 'bg-emerald-500 text-white shadow-sm'
                          : pipelineStep === 2
                          ? 'border-2 border-amber-500 bg-amber-50 text-amber-700 glow-pulse-amber'
                          : 'bg-slate-100 border border-slate-300 text-slate-400 font-medium'
                      }`}>
                        {pipelineStep > 2 ? (
                          <svg className="w-4 h-4 stroke-[3]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path d="M4.5 12.75l6 6 9-13.5" strokeLinecap="round" strokeLinejoin="round"></path>
                          </svg>
                        ) : (
                          '2'
                        )}
                      </div>
                      <span className={`text-xs mt-2 ${
                        pipelineStep === 2 ? 'font-semibold text-amber-600' : pipelineStep > 2 ? 'font-medium text-slate-700' : 'text-slate-400'
                      }`}>
                        Schema
                      </span>
                    </div>

                    {/* Connector 2 -> 3 */}
                    <div className={`flex-1 h-[2px] mx-2 transition-all ${
                      pipelineStep > 2 ? 'bg-gradient-to-r from-emerald-400 to-amber-400' : 'bg-slate-200'
                    }`}></div>

                    {/* Step 3: Mongo Sync */}
                    <div className="flex flex-col items-center relative z-10">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                        pipelineStep > 3
                          ? 'bg-emerald-500 text-white shadow-sm'
                          : pipelineStep === 3
                          ? 'border-2 border-amber-500 bg-amber-50 text-amber-700 glow-pulse-amber'
                          : 'bg-slate-100 border border-slate-300 text-slate-400 font-medium'
                      }`}>
                        {pipelineStep > 3 ? (
                          <svg className="w-4 h-4 stroke-[3]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path d="M4.5 12.75l6 6 9-13.5" strokeLinecap="round" strokeLinejoin="round"></path>
                          </svg>
                        ) : (
                          '3'
                        )}
                      </div>
                      <span className={`text-xs mt-2 ${
                        pipelineStep === 3 ? 'font-semibold text-amber-600' : pipelineStep > 3 ? 'font-medium text-slate-700' : 'text-slate-400'
                      }`}>
                        Mongo Sync
                      </span>
                    </div>

                    {/* Connector 3 -> 4 */}
                    <div className={`flex-1 h-[2px] mx-2 transition-all ${
                      pipelineStep >= 4 ? 'bg-emerald-400' : 'bg-slate-200'
                    }`}></div>

                    {/* Step 4: Ready */}
                    <div className="flex flex-col items-center relative z-10">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                        pipelineStep >= 4
                          ? 'bg-emerald-500 text-white shadow-sm'
                          : 'bg-slate-100 border border-slate-300 text-slate-400 font-medium'
                      }`}>
                        {pipelineStep >= 4 ? (
                          <svg className="w-4 h-4 stroke-[3]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path d="M4.5 12.75l6 6 9-13.5" strokeLinecap="round" strokeLinejoin="round"></path>
                          </svg>
                        ) : (
                          '4'
                        )}
                      </div>
                      <span className={`text-xs mt-2 ${pipelineStep >= 4 ? 'font-semibold text-emerald-600' : 'text-slate-400'}`}>
                        Ready
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Error Message Alert */}
          {errorMessage && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3.5 flex items-start gap-3">
              <svg className="w-5 h-5 text-rose-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
              </svg>
              <p className="text-xs text-rose-700 font-medium">{errorMessage}</p>
            </div>
          )}

          {/* Data Privacy Guaranteed Banner */}
          <div className="rounded-xl border border-emerald-200 bg-emerald-50/80 px-4 py-3.5 flex items-start gap-3 text-left">
            <div className="mt-0.5 p-1 rounded-md bg-emerald-100 text-emerald-700 border border-emerald-200 flex-shrink-0">
              {/* Shield Lock Icon */}
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"></path>
              </svg>
            </div>
            <div className="text-xs leading-relaxed text-emerald-950">
              <span className="font-semibold text-emerald-800 tracking-wide">Data Privacy Guaranteed:</span>
              <span className="text-emerald-700 ml-1">
                Uploaded contents stay safely inside MongoDB and are never transmitted to external AI/LLM models.
              </span>
            </div>
          </div>
        </section>

        {/* Modal Footer / Controls */}
        <footer className="p-6 sm:p-7 pt-3 pb-6 flex items-center justify-end gap-3 border-t border-slate-100 bg-slate-50/60">
          {/* Cancel Button */}
          <button
            className="px-5 py-2.5 rounded-xl border border-slate-200 bg-slate-100 hover:bg-slate-200 text-sm font-medium text-slate-700 transition-colors duration-150"
            onClick={handleClose}
            disabled={uploading}
            type="button"
          >
            Cancel
          </button>

          {/* Save / Processing Action Button */}
          {uploading ? (
            <button
              className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 text-white text-xs sm:text-sm font-semibold flex items-center space-x-2 shadow-md hover:opacity-95 cursor-wait transition-all"
              disabled
              type="button"
            >
              <svg className="animate-spin -ml-0.5 h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" fill="currentColor"></path>
              </svg>
              <span>Processing &amp; Saving...</span>
            </button>
          ) : (
            <button
              className="relative group inline-flex items-center gap-2.5 px-6 py-2.5 rounded-xl text-sm font-semibold text-white bg-sky-500 hover:bg-sky-600 shadow-sm hover:shadow active:scale-98 transition-all duration-200 border border-sky-400 disabled:opacity-50 disabled:pointer-events-none"
              onClick={handleUploadSubmit}
              disabled={!file}
              type="button"
            >
              <svg className="w-4 h-4 stroke-[2.2] text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" strokeLinecap="round" strokeLinejoin="round"></path>
              </svg>
              <span>Save Dataset to MongoDB</span>
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}

import React, { useState, useRef } from 'react';
import { uploadDatasetFile, inspectDatasetFile } from '../api';

const SUPPORTED_EXTENSIONS = ['.csv', '.xlsx', '.xls', '.json', '.xml', '.txt'];

export default function FileUploadModal({ isOpen, onClose, onUploadSuccess }) {
  const [dragActive, setDragActive] = useState(false);
  const [file, setFile] = useState(null);
  const [availableSheets, setAvailableSheets] = useState([]);
  const [selectedSheet, setSelectedSheet] = useState('');
  const [uploading, setUploading] = useState(false);
  const [pipelineStep, setPipelineStep] = useState(0); // 0=idle, 1=validating, 2=converting, 3=saving, 4=done
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
    setPipelineStep(1); // Validating

    try {
      await new Promise((r) => setTimeout(r, 400));
      setPipelineStep(2); // Converting & Detecting schema

      const result = await uploadDatasetFile(file, selectedSheet || null);
      
      setPipelineStep(3); // Saving to MongoDB
      await new Promise((r) => setTimeout(r, 500));

      setPipelineStep(4); // Completed

      setTimeout(() => {
        if (onUploadSuccess) {
          onUploadSuccess(result);
        }
        handleClose();
      }, 900);
    } catch (err) {
      setErrorMessage(err.message || 'The dataset could not be saved. Please try again.');
      setPipelineStep(0);
      setUploading(false);
    }
  };

  return (
    <div
      className={`fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 lg:p-8 transition-opacity ${isOpen ? 'opacity-100 visible' : 'opacity-0 invisible'}`}
      role="dialog"
      aria-modal="true"
    >
      <style>{`
        .glass-modal {
          background: rgba(8, 14, 27, 0.90);
          backdrop-filter: blur(24px);
          -webkit-backdrop-filter: blur(24px);
          border: 1px solid rgba(56, 189, 248, 0.28);
        }
        .dropzone-hover-glow:hover {
          box-shadow: inset 0 0 35px rgba(6, 182, 212, 0.12), 0 0 25px rgba(56, 189, 248, 0.18);
          border-color: rgba(56, 189, 248, 0.6);
        }
        .pipeline-card {
          background: rgba(13, 23, 40, 0.7);
          border: 1px solid rgba(255, 255, 255, 0.06);
        }
        .glow-pulse-amber {
          box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.4);
          animation: pulse-ring 2s infinite cubic-bezier(0.4, 0, 0.6, 1);
        }
        @keyframes pulse-ring {
          0% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.5); }
          70% { box-shadow: 0 0 0 8px rgba(245, 158, 11, 0); }
          100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0); }
        }
      `}</style>
      
      <div 
        className="fixed inset-0 bg-[#03060f]/80 backdrop-blur-md transition-opacity" 
        onClick={handleClose}
      />
      
      <div className="relative w-full max-w-xl glass-modal rounded-2xl shadow-[0_25px_60px_-15px_rgba(0,0,0,0.8),0_0_40px_-10px_rgba(6,182,212,0.15)] overflow-hidden border border-cyan-500/30 transition-all duration-300">
        <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-cyan-400 to-transparent shadow-[0_0_12px_rgba(56,189,248,0.8)]"></div>
        
        <section className="p-6 sm:p-7 pb-4 border-b border-cyan-900/35 relative">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-xl border border-cyan-400/40 bg-gradient-to-b from-cyan-950/60 to-slate-900/90 flex items-center justify-center shadow-[0_0_15px_-3px_rgba(56,189,248,0.35)] flex-shrink-0 text-cyan-300">
                <svg className="w-6 h-6 stroke-[1.8]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path>
                </svg>
              </div>
              <div>
                <h2 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                  Upload Private Dataset
                  <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-mono font-medium rounded-full bg-cyan-950 text-cyan-300 border border-cyan-500/30">
                    SECURE VAULT
                  </span>
                </h2>
                <p className="mt-1 text-sm text-slate-400 leading-relaxed max-w-md">
                  Store structured records in MongoDB for AI search. Data is never sent to external LLMs.
                </p>
              </div>
            </div>
            <button
              type="button"
              className="w-8 h-8 rounded-lg border border-slate-700/60 bg-slate-900/60 text-slate-400 hover:text-white hover:border-cyan-500/50 hover:bg-slate-800 transition-colors flex items-center justify-center focus:outline-none"
              onClick={handleClose}
              disabled={uploading}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path>
              </svg>
            </button>
          </div>
        </section>

        <section className="p-6 sm:p-7 space-y-5">
          {!file && (
            <div
              className={`relative group rounded-xl p-8 sm:p-9 text-center bg-[#070c18]/70 border-2 border-dashed transition-all duration-300 dropzone-hover-glow cursor-pointer ${
                dragActive ? 'border-cyan-400 bg-cyan-950/30 scale-[1.01]' : 'border-cyan-500/30 hover:border-cyan-400/70'
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
              <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(22,78,99,0.1)_0%,transparent_100%)] pointer-events-none rounded-xl"></div>
              
              <div className="flex items-center justify-center gap-3.5 mb-5 relative z-10">
                <div className="w-12 h-12 rounded-xl bg-emerald-950/40 border border-emerald-500/40 text-emerald-400 flex items-center justify-center shadow-[0_0_15px_rgba(16,185,129,0.2)] transform group-hover:-translate-y-1 transition-transform duration-300">
                  <svg className="w-6 h-6 stroke-[1.7]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 10h18M3 14h18m-9-4v8m-7 4h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"></path>
                  </svg>
                </div>
                <div className="text-cyan-500/40 text-lg">⇄</div>
                <div className="w-12 h-12 rounded-xl bg-cyan-950/40 border border-cyan-400/40 text-cyan-400 flex items-center justify-center shadow-[0_0_15px_rgba(6,182,212,0.2)] transform group-hover:-translate-y-1 transition-transform duration-300 delay-75">
                  <svg className="w-6 h-6 stroke-[1.7]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"></path>
                  </svg>
                </div>
              </div>
              <h3 className="text-base sm:text-lg font-semibold text-white tracking-wide mb-1.5 relative z-10">
                Drag &amp; Drop your dataset file here
              </h3>
              <p className="text-xs sm:text-sm text-slate-400 mb-6 font-mono relative z-10">
                Supports <span className="text-cyan-300 font-semibold">.csv</span>, <span className="text-cyan-300 font-semibold">.xlsx</span>, <span className="text-cyan-300 font-semibold">.xls</span>, <span className="text-cyan-300 font-semibold">.json</span>, <span className="text-cyan-300 font-semibold">.xml</span>, <span className="text-cyan-300 font-semibold">.txt</span> <span className="text-slate-500">(up to 50MB)</span>
              </p>
              <button
                type="button"
                className="relative z-10 inline-flex items-center gap-2.5 px-5 py-2.5 rounded-xl text-sm font-medium text-white bg-gradient-to-r from-cyan-600 via-teal-600 to-cyan-500 hover:from-cyan-500 hover:to-teal-400 shadow-[0_0_35px_-8px_rgba(56,189,248,0.35)] transition-all duration-200 border border-cyan-300/30 active:scale-95"
                onClick={(e) => {
                  e.stopPropagation();
                  fileInputRef.current?.click();
                }}
              >
                <svg className="w-4 h-4 text-cyan-100" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"></path>
                </svg>
                <span>Browse Files</span>
              </button>
            </div>
          )}

          {file && !uploading && (
            <div className="rounded-xl border border-slate-700/70 bg-gradient-to-b from-[#060d1a]/90 to-[#091322]/80 p-4 flex flex-col gap-4 shadow-inner">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3.5 min-w-0">
                  <div className="w-11 h-11 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center shrink-0">
                    <svg className="w-5 h-5 text-amber-400/90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                    </svg>
                  </div>
                  <div className="min-w-0 truncate">
                    <h3 className="text-sm font-semibold text-slate-100 truncate tracking-wide">
                      {file.name}
                    </h3>
                    <p className="text-[11px] text-slate-400 mt-0.5 font-mono">
                      {(file.size / (1024 * 1024)).toFixed(2)} MB <span className="text-slate-500">•</span> {file.name.split('.').pop().toUpperCase()} document
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  className="ml-4 px-3.5 py-1.5 rounded-full border border-slate-700 hover:border-slate-500 bg-[#0c1a2d] hover:bg-slate-800 text-xs font-medium text-slate-200 transition-all shrink-0"
                  onClick={() => {
                    setFile(null);
                    setPreviewMeta(null);
                    setAvailableSheets([]);
                  }}
                >
                  Change File
                </button>
              </div>

              {availableSheets.length > 1 && (
                <div className="pt-3 border-t border-slate-700/50">
                  <label className="flex items-center gap-2 text-xs font-medium text-slate-300 mb-2">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                    </svg>
                    Select Worksheet to Import:
                  </label>
                  <select
                    className="w-full bg-[#060d1a] border border-slate-700 text-slate-200 text-sm rounded-lg focus:ring-cyan-500 focus:border-cyan-500 block p-2 outline-none"
                    value={selectedSheet}
                    onChange={(e) => setSelectedSheet(e.target.value)}
                  >
                    {availableSheets.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          )}

          {uploading && (
            <div className="pipeline-card rounded-xl p-5">
              <div className="flex items-center justify-between mb-6 pb-2 border-b border-slate-800/40">
                <span className="text-xs font-semibold tracking-wider text-cyan-400/90 uppercase font-mono">
                  Processing Pipeline
                </span>
                <div className="flex items-center space-x-1.5 text-amber-400 text-xs font-medium">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping"></span>
                  <span className="font-mono text-[11px] sm:text-xs">
                    {pipelineStep === 1 ? 'Validating file...' : pipelineStep === 2 ? 'Converting to JSON records...' : pipelineStep === 3 ? 'Syncing to MongoDB Atlas...' : 'Finalizing...'}
                  </span>
                </div>
              </div>
              <div className="relative flex items-center justify-between px-2 sm:px-4">
                <div className="flex flex-col items-center relative z-10 group">
                  <div className={`w-9 h-9 rounded-full border-2 flex items-center justify-center ${pipelineStep > 1 ? 'bg-emerald-500/20 border-emerald-400 text-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.35)]' : 'bg-amber-500/20 border-amber-400 text-amber-300 glow-pulse-amber font-bold text-xs'}`}>
                    {pipelineStep > 1 ? (
                      <svg className="w-4 h-4 stroke-[3]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5"></path></svg>
                    ) : '1'}
                  </div>
                  <span className={`text-xs mt-2.5 ${pipelineStep > 1 ? 'font-medium text-slate-300' : 'font-medium text-amber-400'}`}>Read File</span>
                </div>
                <div className={`flex-1 h-[2px] mx-2 ${pipelineStep > 1 ? 'bg-gradient-to-r from-emerald-400 to-amber-500' : 'bg-slate-800'}`}></div>

                <div className="flex flex-col items-center relative z-10 group">
                  <div className={`w-9 h-9 rounded-full border-2 flex items-center justify-center text-xs ${pipelineStep > 2 ? 'bg-emerald-500/20 border-emerald-400 text-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.35)]' : pipelineStep === 2 ? 'bg-amber-500/20 border-amber-400 text-amber-300 glow-pulse-amber font-bold' : 'bg-slate-900 border-slate-700/80 text-slate-500 font-medium'}`}>
                    {pipelineStep > 2 ? (
                      <svg className="w-4 h-4 stroke-[3]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5"></path></svg>
                    ) : '2'}
                  </div>
                  <span className={`text-xs mt-2.5 ${pipelineStep > 2 ? 'font-medium text-slate-300' : pipelineStep === 2 ? 'font-medium text-amber-400' : 'text-slate-500'}`}>Schema</span>
                </div>
                <div className={`flex-1 h-[2px] mx-2 ${pipelineStep > 2 ? 'bg-gradient-to-r from-emerald-400 to-amber-500' : 'bg-slate-800'}`}></div>

                <div className="flex flex-col items-center relative z-10 group">
                  <div className={`w-9 h-9 rounded-full border-2 flex items-center justify-center text-xs ${pipelineStep > 3 ? 'bg-emerald-500/20 border-emerald-400 text-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.35)]' : pipelineStep === 3 ? 'bg-amber-500/20 border-amber-400 text-amber-300 glow-pulse-amber font-bold' : 'bg-slate-900 border-slate-700/80 text-slate-500 font-medium'}`}>
                    {pipelineStep > 3 ? (
                      <svg className="w-4 h-4 stroke-[3]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5"></path></svg>
                    ) : '3'}
                  </div>
                  <span className={`text-xs mt-2.5 ${pipelineStep > 3 ? 'font-medium text-slate-300' : pipelineStep === 3 ? 'font-medium text-amber-400' : 'text-slate-500'}`}>Mongo Sync</span>
                </div>
                <div className={`flex-1 h-[2px] mx-2 ${pipelineStep > 3 ? 'bg-gradient-to-r from-emerald-400 to-emerald-500' : 'bg-slate-800'}`}></div>

                <div className="flex flex-col items-center relative z-10 group">
                  <div className={`w-9 h-9 rounded-full border-2 flex items-center justify-center text-xs ${pipelineStep >= 4 ? 'bg-emerald-500/20 border-emerald-400 text-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.35)] font-bold' : 'bg-slate-900 border-slate-700/80 text-slate-500 font-medium'}`}>
                    4
                  </div>
                  <span className={`text-xs mt-2.5 ${pipelineStep >= 4 ? 'font-medium text-emerald-400' : 'text-slate-500'}`}>Ready</span>
                </div>
              </div>
            </div>
          )}

          {errorMessage && (
            <div className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-3.5 flex items-start gap-3 mt-4">
              <svg className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
              </svg>
              <p className="text-sm text-rose-300">{errorMessage}</p>
            </div>
          )}

          <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 px-4 py-3.5 flex items-start gap-3 text-left backdrop-blur-sm mt-4">
            <div className="mt-0.5 p-1 rounded-md bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex-shrink-0">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
              </svg>
            </div>
            <div className="text-xs leading-relaxed text-slate-300">
              <span className="font-semibold text-emerald-400 tracking-wide">Data Privacy Guaranteed:</span>
              <span className="text-slate-400 ml-1">Uploaded contents stay safely inside MongoDB and are never transmitted to external AI/LLM models.</span>
            </div>
          </div>
        </section>

        <footer className="p-6 sm:p-7 pt-3 pb-6 flex items-center justify-end gap-3 border-t border-cyan-900/30 bg-[#060a14]/60">
          <button
            type="button"
            className="px-5 py-2.5 rounded-xl border border-slate-700/80 bg-slate-900/60 hover:bg-slate-800 text-sm font-medium text-slate-300 hover:text-white transition-colors duration-150"
            onClick={handleClose}
            disabled={uploading}
          >
            Cancel
          </button>
          
          {uploading ? (
            <button
              type="button"
              disabled
              className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-amber-600/90 to-amber-700 text-white text-xs sm:text-sm font-semibold flex items-center gap-2 shadow-[0_0_20px_-3px_rgba(245,158,11,0.35)] cursor-wait opacity-95 transition-all"
            >
              <svg className="animate-spin -ml-0.5 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              <span>Processing & Saving...</span>
            </button>
          ) : (
            <button
              type="button"
              className="relative group inline-flex items-center gap-2.5 px-6 py-2.5 rounded-xl text-sm font-semibold text-[#050811] bg-gradient-to-r from-cyan-400 via-teal-300 to-cyan-400 hover:brightness-110 shadow-[0_0_35px_-8px_rgba(56,189,248,0.35)] active:scale-95 transition-all duration-200 border border-cyan-200/50 disabled:opacity-50 disabled:pointer-events-none"
              onClick={handleUploadSubmit}
              disabled={!file}
            >
              <svg className="w-4 h-4 stroke-[2.2]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"></path>
              </svg>
              <span>Save Dataset to MongoDB</span>
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}

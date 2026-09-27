import React, { useState } from 'react';

const FIELD_LABELS = {
  email: 'Email',
  email_1: 'Email 1',
  email_2: 'Email 2',
  mobile_no: 'Mobile No.',
  landline_telephone: 'Telephone',
  landline_other_no: 'Other No.',
  address: 'Address',
  city: 'City',
  state: 'State',
  pin: 'PIN Code',
  designation: 'Designation',
  contact_person: 'Contact Person',
  company_name: 'Company Name',
  company: 'Company',
  group: 'Group',
  remarks: 'Remarks',
};

function prettyLabel(key) {
  return FIELD_LABELS[key] || key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

const INTERNAL_FIELDS = new Set([
  'id', '_id', 'raw_data', 'data', 'normalized_data', 'source_fields',
  'search_text', 'embedding', 'vector_score', 'similarity_score', 'retrieval_score', 'chunk_text', 'internal_id',
  'norm_company_name', 'norm_person_name', 'norm_designation', 'norm_department',
  'norm_state', 'norm_city', 'norm_country', 'norm_location',
  '_norm_company_name', '_norm_person_name', '_norm_designation', '_norm_department',
  '_norm_state', '_norm_city', '_norm_country', '_norm_location',
  'dataset', 'dataset_id', 'dataset_name', 'source_collection',
  'database_source', 'database', 'source_file', 'source_sheet', 'source_row', 'record_index'
]);

/**
 * Renders a clean source-accurate card for database records
 */
function TelemetryCard({ record, returnFields, onInspect }) {
  const [copied, setCopied] = useState(false);
  if (!record || typeof record !== 'object') return null;

  // Extract only genuine source fields that are not internal or metadata and not nested objects
  const allDataKeys = Object.keys(record).filter(
    (k) => !INTERNAL_FIELDS.has(k.toLowerCase()) && !k.startsWith('_') && typeof record[k] !== 'object' && record[k] != null && record[k] !== ''
  );

  const entityDisplay =
    record.company_name ||
    record['Company Name'] ||
    record.company ||
    record['Company'] ||
    record.contact_person ||
    record['Contact Person'] ||
    record.name ||
    'Target Entity';

  const sourceName = record.dataset || record.dataset_name || record.source_collection || 'dataset_records';
  const databaseName = record.database || record.database_source || 'MongoDB Atlas';
  const sourceFile = record.source_file;
  const sourceSheet = record.source_sheet;
  const sourceRow = record.source_row;
  const docId = record.id ? (record.id.startsWith('OID_') ? record.id : `OID_${record.id}`) : 'OID_rec_1';

  // Identify requested or prominent field
  let primaryValueField = null;
  if (returnFields && returnFields.length > 0 && !returnFields.includes('*')) {
    primaryValueField = allDataKeys.find((k) =>
      returnFields.some(
        (rf) =>
          k.toLowerCase().replace(/[^a-z0-9]/g, '') === rf.toLowerCase().replace(/[^a-z0-9]/g, '')
      )
    );
  }
  if (!primaryValueField) {
    primaryValueField = allDataKeys.find((k) => /email/i.test(k)) || allDataKeys.find((k) => /phone|mobile/i.test(k)) || allDataKeys[0];
  }

  const handleCopy = () => {
    const lines = [
      `Dataset: ${sourceName}`,
      `Database: ${databaseName}`,
      sourceFile ? `Source File: ${sourceFile}` : '',
      sourceSheet && sourceSheet !== 'Not Available' ? `Source Sheet: ${sourceSheet}` : '',
      sourceRow && sourceRow !== 'Not Available' ? `Source Row: ${sourceRow}` : '',
    ].filter(Boolean);
    
    allDataKeys.forEach((k) => {
      lines.push(`${prettyLabel(k)}: ${record[k]}`);
    });
    navigator.clipboard?.writeText(lines.join('\n'));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleExport = (format) => {
    let content = '';
    let mimeType = '';
    let ext = format;

    if (format === 'csv' || format === 'xls') {
      const headers = allDataKeys.map(prettyLabel).join(',');
      const values = allDataKeys.map((k) => `"${String(record[k]).replace(/"/g, '""')}"`).join(',');
      content = headers + '\n' + values;
      mimeType = format === 'csv' ? 'text/csv' : 'application/vnd.ms-excel';
    } else if (format === 'pdf') {
      // Basic text representation for PDF fallback if no library is available
      content = `Entity: ${entityDisplay}\nDataset: ${sourceName}\n\n`;
      allDataKeys.forEach((k) => {
        content += `${prettyLabel(k)}: ${record[k]}\n`;
      });
      mimeType = 'text/plain'; // Real PDF requires jsPDF, using txt fallback
      ext = 'txt'; 
    }

    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${entityDisplay.replace(/[^a-z0-9]/gi, '_')}_export.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
    setExportOpen(false);
  };

  const [exportOpen, setExportOpen] = useState(false);

  return (
    <div className="mt-4 rounded-xl bg-slate-900/60 border border-cyan-500/20 overflow-hidden shadow-[inset_0_0_18px_rgba(0,242,254,0.08)] backdrop-blur-md">
      {/* Top Banner */}
      <div className="px-3.5 py-2.5 bg-gradient-to-r from-cyan-950/60 via-slate-900/90 to-slate-950 border-b border-cyan-500/20 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-sm text-cyan-400">database</span>
          <span className="text-[11px] font-label-sm font-semibold uppercase tracking-wider text-cyan-200">
            Source Record Inspection
          </span>
        </div>
        <div className="flex items-center gap-1.5 font-label-sm text-[10px] text-emerald-400 bg-emerald-950/70 border border-emerald-500/40 px-2 py-0.5 rounded">
          <span className="material-symbols-outlined text-[12px]">verified</span>
          <span>RECORD RETRIEVED</span>
        </div>
      </div>

      {/* Source Metadata Section: Only show Source File, Sheet, Row */}
      <div className="px-3.5 py-2.5 bg-slate-950/90 border-b border-cyan-500/20 text-xs font-mono space-y-1">
        {sourceFile && (
          <div className="flex items-center gap-1.5 text-slate-300">
            <span className="text-slate-400">Source File:</span>
            <span className="text-emerald-300 font-semibold">{sourceFile}</span>
          </div>
        )}
        {sourceSheet && sourceSheet !== 'Not Available' && (
          <div className="flex items-center gap-1.5 text-slate-300">
            <span className="text-slate-400">Source Sheet:</span>
            <span>{sourceSheet}</span>
          </div>
        )}
        {sourceRow != null && sourceRow !== 'Not Available' && (
          <div className="flex items-center gap-1.5 text-slate-300">
            <span className="text-slate-400">Source Row:</span>
            <span className="text-cyan-400 font-bold">{sourceRow}</span>
          </div>
        )}
      </div>

      {/* 3-Column Telemetry Grid */}
      <div className="p-3.5 grid grid-cols-1 sm:grid-cols-3 gap-2.5">
        {/* Card 1: Target Entity */}
        <div className="p-2.5 rounded-lg bg-slate-950/80 border border-cyan-500/10 hover:border-cyan-500/40 transition-colors shadow-sm">
          <span className="text-[10px] font-label-sm text-slate-400 uppercase tracking-tight block">
            Target Record
          </span>
          <div className="mt-1 flex items-baseline gap-1.5">
            <span className="text-sm sm:text-base font-bold text-cyan-300 font-label-sm truncate">
              {entityDisplay}
            </span>
          </div>
          <span className="text-[10px] font-label-sm text-slate-400 mt-0.5 block truncate">
            {record.designation || record.contact_person || 'Indexed Entity'}
          </span>
        </div>

        {/* Card 2: Primary Retrieved Field */}
        <div className="p-2.5 rounded-lg bg-slate-950/80 border border-cyan-500/10 hover:border-cyan-500/40 transition-colors shadow-sm">
          <span className="text-[10px] font-label-sm text-slate-400 uppercase tracking-tight block truncate">
            {primaryValueField ? prettyLabel(primaryValueField) : 'Primary Value'}
          </span>
          <div className="mt-1 flex items-baseline gap-1.5 truncate">
            {primaryValueField && /email/i.test(primaryValueField) ? (
              <a
                href={`mailto:${record[primaryValueField]}`}
                className="text-sm sm:text-base font-bold text-emerald-400 font-label-sm hover:underline truncate"
              >
                {String(record[primaryValueField])}
              </a>
            ) : primaryValueField && /phone|mobile|tel/i.test(primaryValueField) ? (
              <a
                href={`tel:${record[primaryValueField]}`}
                className="text-sm sm:text-base font-bold text-emerald-400 font-label-sm hover:underline truncate"
              >
                {String(record[primaryValueField])}
              </a>
            ) : (
              <span className="text-sm sm:text-base font-bold text-emerald-400 font-label-sm truncate">
                {primaryValueField ? String(record[primaryValueField]) : 'Active'}
              </span>
            )}
          </div>
          <span className="text-[10px] font-label-sm text-emerald-400/90 mt-0.5 block">
            Verified in MongoDB ✓
          </span>
        </div>

        {/* Card 3: Source & Compliance */}
        <div className="p-2.5 rounded-lg bg-slate-950/80 border border-cyan-500/10 hover:border-cyan-500/40 transition-colors shadow-sm">
          <span className="text-[10px] font-label-sm text-slate-400 uppercase tracking-tight block">
            Repository Source
          </span>
          <div className="mt-1 flex items-center gap-1 text-cyan-300 font-medium text-xs font-label-sm truncate">
            <span className="material-symbols-outlined text-sm text-cyan-400 flex-shrink-0">check_circle</span>
            <span className="truncate">{sourceName}</span>
          </div>
          <span className="text-[10px] font-label-sm text-slate-400 mt-0.5 block truncate">
            {docId}
          </span>
        </div>
      </div>

      {/* Expanded Key-Value Rows (if more than primary field) */}
      {allDataKeys.length > 1 && (
        <div className="px-3.5 py-2.5 border-t border-slate-800/60 bg-slate-950/50 space-y-1.5">
          {allDataKeys.map((key) => {
            const val = record[key];
            if (val === null || val === undefined || val === '') return null;
            return (
              <div key={key} className="flex items-baseline justify-between text-xs gap-2 py-0.5 border-b border-slate-900/80 last:border-b-0">
                <span className="text-[11px] font-label-sm text-slate-400 uppercase tracking-wider min-w-[100px] flex-shrink-0">
                  {prettyLabel(key)}:
                </span>
                <span className="font-body-md text-slate-200 text-right truncate">
                  {/email/i.test(key) && typeof val === 'string' && val.includes('@') ? (
                    <a href={`mailto:${val}`} className="text-cyan-300 hover:underline">
                      {val}
                    </a>
                  ) : /phone|mobile|tel/i.test(key) ? (
                    <a href={`tel:${val}`} className="text-cyan-300 hover:underline">
                      {val}
                    </a>
                  ) : /linkedin|url|website|link/i.test(key) || (typeof val === 'string' && (val.startsWith('http') || val.startsWith('www.') || val.includes('linkedin.com'))) ? (
                    <a
                      href={String(val).startsWith('http') ? String(val) : `https://${val}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-cyan-300 hover:underline break-all"
                    >
                      {String(val)}
                    </a>
                  ) : (
                    String(val)
                  )}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Footer Info Line */}
      <div className="px-3.5 py-2 border-t border-slate-800/60 bg-slate-950/60 flex items-center justify-between text-[11px] font-label-sm text-slate-400 flex-wrap gap-2">
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(0,242,254,0.9)]"></span>
          Source: {sourceFile || sourceName}
        </span>
        <span className="text-cyan-400/90 font-medium">BSON Atlas Synced</span>
      </div>

      {/* Interactive Action Buttons */}
      <div className="p-2.5 bg-slate-950/90 border-t border-cyan-500/20 flex flex-wrap items-center gap-2 relative">
        <div className="relative">
          <button
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900/90 hover:bg-slate-800 border border-slate-700/80 hover:border-cyan-500/40 text-slate-200 text-xs font-medium transition-all shadow-sm"
            onClick={() => setExportOpen(!exportOpen)}
            type="button"
          >
            <span className="material-symbols-outlined text-sm text-emerald-400">download</span>
            <span>Export</span>
          </button>
          
          {exportOpen && (
            <div className="absolute bottom-full left-0 mb-2 w-32 bg-slate-900 border border-cyan-500/30 rounded-lg shadow-lg overflow-hidden z-10">
              <button
                className="w-full text-left px-4 py-2 text-xs text-slate-300 hover:bg-slate-800 hover:text-cyan-300 transition-colors"
                onClick={() => handleExport('csv')}
              >
                CSV
              </button>
              <button
                className="w-full text-left px-4 py-2 text-xs text-slate-300 hover:bg-slate-800 hover:text-cyan-300 transition-colors"
                onClick={() => handleExport('xls')}
              >
                Excel
              </button>
              <button
                className="w-full text-left px-4 py-2 text-xs text-slate-300 hover:bg-slate-800 hover:text-cyan-300 transition-colors"
                onClick={() => handleExport('pdf')}
              >
                PDF (Text)
              </button>
            </div>
          )}
        </div>

        <button
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900/90 hover:bg-slate-800 border border-slate-700/80 hover:border-cyan-500/40 text-slate-200 text-xs font-medium transition-all shadow-sm"
          onClick={handleCopy}
          type="button"
        >
          <span className="material-symbols-outlined text-sm text-cyan-400">
            {copied ? 'check' : 'content_copy'}
          </span>
          <span>{copied ? 'Copied!' : 'Copy'}</span>
        </button>
      </div>
    </div>
  );
}

/**
 * Helper to render message text with clickable hyperlinks for URLs/emails,
 * bolding for **markdown**, and dividers for ---.
 */
function FormattedMessageText({ text }) {
  if (!text) return null;

  const lines = text.split('\n');

  return (
    <div className="space-y-1">
      {lines.map((line, idx) => {
        const trimmed = line.trim();
        if (trimmed === '---') {
          return <hr key={idx} className="my-3 border-slate-700/70" />;
        }
        if (!line) {
          return <div key={idx} className="h-1.5" />;
        }

        // Regex matches:
        // 1) Markdown link: \[([^\]]+)\]\(([^)]+)\)
        // 2) Raw URL: ((?:https?:\/\/|www\.)[^\s<>"']+)
        // 3) Raw Email: ([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)
        // 4) Bold: \*\*([^*]+)\*\*
        const tokenRegex = /(\[([^\]]+)\]\(([^)]+)\))|((?:https?:\/\/|www\.)[^\s<>"']+)|([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)|(\*\*([^*]+)\*\*)/g;

        const tokens = [];
        let lastIndex = 0;
        let match;
        let keyIdx = 0;

        while ((match = tokenRegex.exec(line)) !== null) {
          if (match.index > lastIndex) {
            tokens.push(line.slice(lastIndex, match.index));
          }

          if (match[1]) {
            // Markdown link [label](url)
            const label = match[2];
            const href = match[3].startsWith('http') || match[3].startsWith('mailto:') ? match[3] : `https://${match[3]}`;
            tokens.push(
              <a
                key={`mlink-${idx}-${keyIdx++}`}
                href={href}
                target={href.startsWith('mailto:') ? '_self' : '_blank'}
                rel="noopener noreferrer"
                className="text-cyan-400 underline hover:text-cyan-300 break-all font-medium"
              >
                {label}
              </a>
            );
          } else if (match[4]) {
            // Raw URL
            const rawUrl = match[4];
            const href = rawUrl.startsWith('http') ? rawUrl : `https://${rawUrl}`;
            tokens.push(
              <a
                key={`url-${idx}-${keyIdx++}`}
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-cyan-400 underline hover:text-cyan-300 break-all font-medium"
              >
                {rawUrl}
              </a>
            );
          } else if (match[5]) {
            // Raw email
            const email = match[5];
            tokens.push(
              <a
                key={`mail-${idx}-${keyIdx++}`}
                href={`mailto:${email}`}
                className="text-cyan-400 underline hover:text-cyan-300 break-all font-medium"
              >
                {email}
              </a>
            );
          } else if (match[6]) {
            // Bold **text**
            tokens.push(
              <strong key={`b-${idx}-${keyIdx++}`} className="font-semibold text-slate-100">
                {match[7]}
              </strong>
            );
          }

          lastIndex = tokenRegex.lastIndex;
        }

        if (lastIndex < line.length) {
          tokens.push(line.slice(lastIndex));
        }

        return (
          <div key={idx} className="leading-relaxed">
            {tokens}
          </div>
        );
      })}
    </div>
  );
}

export default function ChatMessage({ message, onInspect }) {
  const isUser = message.role === 'user';
  const now = new Date();
  const timeStr = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;

  // 1. User Message
  if (isUser) {
    const [userCopied, setUserCopied] = useState(false);
    return (
      <div className="flex justify-end items-end gap-3 w-full animate-fadeIn">
        <div className="max-w-[85%] sm:max-w-[78%] flex flex-col items-end">
          <div className="flex items-center gap-2 mb-1 px-1">
            <span className="text-[11px] font-label-sm text-cyan-300/80 font-medium">You</span>
            <span className="text-[10px] font-label-sm text-slate-500">{timeStr}</span>
          </div>
          <div className="rounded-2xl rounded-tr-xs bg-gradient-to-r from-cyan-950/80 via-blue-900/60 to-slate-900/90 border border-cyan-400/50 text-slate-100 px-5 py-3.5 text-sm md:text-[15px] shadow-[0_4px_24px_rgba(0,242,254,0.22),inset_0_1px_1px_rgba(255,255,255,0.2)] backdrop-blur-xl">
            <p className="leading-relaxed">{message.content}</p>
          </div>
          <div className="flex items-center gap-2 mt-1 px-2 text-slate-400">
            <button 
              className="flex items-center gap-1 hover:text-cyan-300 transition-colors"
              onClick={() => {
                navigator.clipboard?.writeText(message.content);
                setUserCopied(true);
                setTimeout(() => setUserCopied(false), 2000);
              }}
            >
              <span className="material-symbols-outlined text-[13px]">{userCopied ? 'check' : 'content_copy'}</span>
              <span className="text-[10px] font-medium">{userCopied ? 'Copied' : 'Copy'}</span>
            </button>
            <button className="flex items-center gap-1 hover:text-cyan-300 transition-colors">
              <span className="material-symbols-outlined text-[13px]">edit</span>
              <span className="text-[10px] font-medium">Edit</span>
            </button>
          </div>
        </div>
        <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-cyan-600 to-sky-400 p-[1px] flex-shrink-0 shadow-[0_0_12px_rgba(0,242,254,0.4)]">
          <div className="w-full h-full rounded-full bg-slate-950 flex items-center justify-center text-cyan-300 font-headline-xl text-xs font-bold">
            U
          </div>
        </div>
      </div>
    );
  }

  // 2. Assistant Message
  const { data, count, found, query_intent, error, loading, text, dataset_name, is_system_notice } = message;
  const isLookup = query_intent?.intent === 'lookup_field';
  const returnFields = query_intent?.return_fields || [];
  const searchCondition = query_intent?.conditions?.[0];

  return (
    <div className="flex justify-start items-start gap-3 w-full animate-fadeIn">
      {/* Bot Avatar Badge */}
      <div className="relative flex-shrink-0 mt-0.5">
        <div className="absolute -inset-1 rounded-full bg-gradient-to-tr from-cyan-500 to-blue-600 blur-sm opacity-60 animate-pulse pointer-events-none"></div>
        <div className="relative w-8 h-8 rounded-full bg-gradient-to-tr from-cyan-400 via-sky-400 to-blue-600 p-[1px] shadow-[0_0_16px_rgba(0,242,254,0.6)]">
          <div className="w-full h-full rounded-full bg-slate-950 flex items-center justify-center text-cyan-300">
            <span className="material-symbols-outlined text-[17px] drop-shadow-[0_0_8px_rgba(0,242,254,0.9)]">
              smart_toy
            </span>
          </div>
        </div>
      </div>

      {/* Bot Response Payload */}
      <div className="max-w-[92%] sm:max-w-[86%] space-y-3 w-full">
        {/* Header line */}
        <div className="flex items-center gap-2 mb-1 px-1 flex-wrap">
          <span className="text-xs font-semibold text-cyan-400 flex items-center gap-1.5 font-headline-xl tracking-wide">
            <span className="material-symbols-outlined text-xs text-cyan-300">neurology</span>
            CALISPEC AI
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-300 animate-pulse"></span>
          </span>
          {dataset_name && (
            <span className="text-[10px] font-label-sm text-cyan-300/80 bg-cyan-950/60 px-2 py-0.5 rounded-full border border-cyan-500/30 truncate max-w-[200px]">
              {dataset_name}
            </span>
          )}
          <span className="text-[10px] font-label-sm text-slate-500">{timeStr}</span>
        </div>

        {/* Loading Indicator */}
        {loading ? (
          <div className="rounded-2xl rounded-tl-xs bg-slate-950/90 border border-cyan-500/30 text-slate-200 p-4 sm:p-5 shadow-[0_0_30px_rgba(0,242,254,0.18)] backdrop-blur-xl flex items-center gap-3">
            <span className="material-symbols-outlined text-cyan-400 animate-spin-clockwise text-xl" style={{ animationDuration: '30s' }}>
              settings
            </span>
            <span className="text-sm font-label-sm text-cyan-300">
              Searching MongoDB records across indexed datasets...
            </span>
          </div>
        ) : error ? (
          <div className="rounded-2xl rounded-tl-xs bg-rose-950/40 border border-rose-500/40 text-rose-200 p-4 shadow-[0_0_20px_rgba(244,63,94,0.2)] backdrop-blur-xl flex items-center gap-3">
            <span className="material-symbols-outlined text-rose-400 text-xl flex-shrink-0">warning</span>
            <div>
              <strong className="block text-xs uppercase font-headline-xl">Database Search Error</strong>
              <span className="text-xs text-rose-300">{error}</span>
            </div>
          </div>
        ) : is_system_notice ? (
          <div className="rounded-2xl rounded-tl-xs bg-slate-950/90 border border-emerald-500/40 text-slate-200 p-4 sm:p-5 shadow-[0_0_30px_rgba(16,185,129,0.2)] backdrop-blur-xl">
            <div className="flex items-center gap-2 text-emerald-400 mb-2 font-semibold text-xs font-headline-xl uppercase tracking-wider">
              <span className="material-symbols-outlined text-sm">verified</span>
              <span>Dataset Indexed & Ready for AI Search</span>
            </div>
            <p className="text-sm leading-relaxed whitespace-pre-line text-slate-300">{text}</p>
          </div>
        ) : (
          <div className="rounded-2xl rounded-tl-xs bg-slate-950/90 border border-cyan-500/30 text-slate-200 p-4 sm:p-5 shadow-[0_0_30px_rgba(0,242,254,0.18),inset_0_1px_1px_rgba(255,255,255,0.1)] backdrop-blur-xl">
            {/* Narrative text */}
            {text && (
              <div className="text-sm md:text-[15px] leading-relaxed text-slate-200 font-sans mb-3">
                <FormattedMessageText text={text} />
              </div>
            )}

            {/* Single Record Result (e.g. lookup or 1 record) */}
            {found && data && !Array.isArray(data) && (
              <TelemetryCard
                record={data}
                returnFields={returnFields}
                onInspect={onInspect}
              />
            )}

            {/* Multiple Records Result */}
            {found && Array.isArray(data) && data.length > 0 && (
              <div className="space-y-4 mt-2">
                {data.map((rec, idx) => (
                  <TelemetryCard
                    key={rec.id || idx}
                    record={rec}
                    returnFields={returnFields}
                    onInspect={onInspect}
                  />
                ))}
              </div>
            )}

            {/* No Match Result */}
            {!found && (
              <div className="mt-3 p-3 rounded-lg bg-slate-900/60 border border-slate-800 text-xs text-slate-400">
                <span className="block font-medium text-slate-300 mb-1">No matching records found in indexed datasets.</span>
                <span>Tip: Verify spelling or try searching by exact company name, email address, or key parameters.</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

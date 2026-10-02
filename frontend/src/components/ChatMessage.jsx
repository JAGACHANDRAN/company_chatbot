import React, { useState, useRef, useEffect } from 'react';
import { jsPDF } from 'jspdf';

const FIELD_LABELS = {
  email: 'Email',
  email_1: 'Email 1',
  email_2: 'Email 2',
  mobile_no: 'Mobile No.',
  landline_telephone: 'Landline / Telephone',
  landline_other_no: 'Landline / Other No.',
  telephone_1: 'Telephone 1',
  telephone_2: 'Telephone 2',
  address: 'Address',
  city: 'City',
  state: 'State',
  pin: 'PIN Code',
  pincode: 'PIN Code',
  designation: 'Designation',
  contact_person: 'Contact Person',
  company_name: 'Company Name',
  company: 'Company',
  group: 'Group',
  records_merged: 'Records Merged',
  review_required: 'Review Required',
  remarks: 'Remarks',
  linkedin: 'LinkedIn',
  linkedin_url: 'LinkedIn URL',
  linkedin_profile: 'LinkedIn Profile',
  website: 'Website',
  department: 'Department',
  employee_name: 'Employee Name',
  customer_name: 'Customer Name',
  instrument_name: 'Instrument Name',
};

function prettyLabel(key) {
  if (!key) return '';
  const lower = key.toLowerCase().replace(/[\s-]+/g, '_');
  return FIELD_LABELS[lower] || key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function getInitials(name) {
  if (!name || typeof name !== 'string') return 'CS';
  const clean = name.replace(/^(mr\.|ms\.|mrs\.|dr\.)\s*/i, '').trim();
  const parts = clean.split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return clean.substring(0, 2).toUpperCase() || 'CS';
}

function getFieldIcon(key) {
  const k = key.toLowerCase();
  if (k.includes('company') || k.includes('organization')) return 'apartment';
  if (k.includes('contact') || k.includes('person') || k.includes('name') || k.includes('employee')) return 'person';
  if (k.includes('designation') || k.includes('role') || k.includes('title') || k.includes('position')) return 'badge';
  if (k.includes('mobile') || k.includes('cell')) return 'phone_iphone';
  if (k.includes('phone') || k.includes('tel') || k.includes('landline')) return 'call';
  if (k.includes('email') || k.includes('mail')) return 'mail';
  if (k.includes('linkedin')) return 'work';
  if (k.includes('website') || k.includes('url') || k.includes('link')) return 'link';
  if (k.includes('address') || k.includes('location')) return 'location_on';
  if (k.includes('city')) return 'location_city';
  if (k.includes('state') || k.includes('country')) return 'map';
  if (k.includes('pin') || k.includes('zip')) return 'pin_drop';
  if (k.includes('group') || k.includes('division') || k.includes('dept')) return 'corporate_fare';
  if (k.includes('date') || k.includes('due') || k.includes('time')) return 'event';
  if (k.includes('status') || k.includes('review')) return 'verified';
  if (k.includes('merged')) return 'merge_type';
  return 'label';
}

const INTERNAL_FIELDS = new Set([
  'id', '_id', 'raw_data', 'data', 'normalized_data', 'source_fields',
  'search_text', 'embedding', 'vector_score', 'similarity_score', 'retrieval_score', 'chunk_text', 'internal_id',
  'norm_company_name', 'norm_person_name', 'norm_designation', 'norm_department',
  'norm_state', 'norm_city', 'norm_country', 'norm_location',
  '_norm_company_name', '_norm_person_name', '_norm_designation', '_norm_department',
  '_norm_state', '_norm_city', '_norm_country', '_norm_location',
  'dataset', 'dataset_id', 'dataset_name', 'source_collection',
  'database_source', 'database', 'source_file', 'source_sheet', 'source_row', 'record_index',
]);

/**
 * Checks if a value is meaningful and populated.
 */
function isValidValue(val) {
  if (val === null || val === undefined) return false;
  const str = String(val).trim().toLowerCase();
  return (
    str !== '' &&
    str !== 'not available' &&
    str !== 'not_available' &&
    str !== 'none' &&
    str !== 'null' &&
    str !== 'nan' &&
    str !== 'undefined' &&
    str !== 'n/a' &&
    str !== 'na' &&
    str !== '-' &&
    str !== '--'
  );
}

/**
 * Extracts and deduplicates the genuine fields available in that specific file/record.
 * Only returns columns that actually exist in the file.
 */
function getRecordFields(record) {
  if (!record || typeof record !== 'object') return [];

  const seenNormKeys = new Set();
  const fields = [];

  for (const rawKey of Object.keys(record)) {
    if (!rawKey || rawKey.startsWith('_')) continue;

    const normKey = rawKey.toLowerCase().replace(/[^a-z0-9]/g, '_').replace(/_+/g, '_');
    if (INTERNAL_FIELDS.has(normKey) || seenNormKeys.has(normKey)) {
      continue;
    }

    const val = record[rawKey];
    if (typeof val === 'object' && val !== null) continue;

    seenNormKeys.add(normKey);

    fields.push({
      key: rawKey,
      normKey,
      label: prettyLabel(rawKey),
      value: val,
      icon: getFieldIcon(rawKey),
    });
  }

  return fields;
}

/**
 * Parses raw text dumps (such as Image 2 format) into structured record objects
 * so they are never displayed as plain text.
 */
function parseTextToRecords(text) {
  if (!text || typeof text !== 'string') return [];

  // Check if text looks like a structured key-value dump
  const hasKvIndicators =
    text.includes('Company Name:') ||
    text.includes('Contact Person:') ||
    text.includes('Sources:') ||
    text.includes('Source:') ||
    text.includes('Source File:') ||
    text.includes('Source Collection:') ||
    text.includes('Database:') ||
    text.includes('Collection:') ||
    text.includes('Designation:') ||
    text.includes('Mobile No.:');

  if (!hasKvIndicators) return [];

  // Split by divider '---' or double newlines before source headers or 'Company Name:'
  const sections = text
    .split(/\n\s*---\s*\n|\n+(?=(?:(?:\*\*|\#\#)?\s*(?:Sources?|Source File|Source Collection|Database|Collection)\s*:|Company Name:))/i)
    .map((s) => s.trim())
    .filter(Boolean);

  const parsedList = [];

  for (const sec of sections) {
    const lines = sec.split('\n').map((l) => l.trim()).filter(Boolean);
    const rec = {};
    let fileFound = '';
    let sheetFound = '';
    let dbFound = '';
    let colFound = '';

    for (const line of lines) {
      // Source Header regex: File
      const srcMatch = line.match(
        /^(?:\*\*|\#\#)?\s*(?:Sources?|Source File)\s*:\s*\**\s*([^|\n*]+?)(?:\s*\|\s*([^*\n]+))?\s*(?:\*\*)?$/i
      );
      if (srcMatch) {
        const val = srcMatch[1].trim();
        if (/^Database\s*:/i.test(val) || val.includes('Collection:')) {
          const dbPart = val.match(/Database:\s*([^|*]+)/i);
          const colPart = (val + (srcMatch[2] ? ` | ${srcMatch[2]}` : '')).match(/Collection:\s*([^*]+)/i);
          if (dbPart) dbFound = dbPart[1].trim();
          if (colPart) colFound = colPart[1].trim();
        } else {
          fileFound = val;
          if (srcMatch[2]) sheetFound = srcMatch[2].trim();
        }
        continue;
      }

      // Source Header regex: Database & Collection
      const dbMatch = line.match(
        /^(?:\*\*|\#\#)?\s*Database\s*:\s*\**\s*([^|\n*]+?)(?:\s*\|\s*Collection\s*:\s*([^*\n]+))?\s*(?:\*\*)?$/i
      );
      if (dbMatch) {
        dbFound = dbMatch[1].trim();
        if (dbMatch[2]) colFound = dbMatch[2].trim();
        continue;
      }

      const colMatch = line.match(
        /^(?:\*\*|\#\#)?\s*(?:Source Collection|Collection)\s*:\s*\**\s*([^*\n]+)\s*(?:\*\*)?$/i
      );
      if (colMatch) {
        colFound = colMatch[1].trim();
        continue;
      }

      const sheetMatch = line.match(
        /^(?:\*\*|\#\#)?\s*Source Sheet\s*:\s*\**\s*([^*\n]+)\s*(?:\*\*)?$/i
      );
      if (sheetMatch) {
        sheetFound = sheetMatch[1].trim();
        continue;
      }

      // Key-Value match (supports bullet points e.g. - LinkedIn: ... or - Name: ...)
      const kvMatch = line.match(/^(?:[-*•]\s*)?(?:\*\*)?([A-Za-z0-9\s/._-]+?)(?:\*\*)?\s*:\s*(.+)$/);
      if (kvMatch) {
        const rawKey = kvMatch[1].trim();
        const rawVal = kvMatch[2].trim().replace(/^\*\*|\*\*$/g, '');

        // Clean link formats like [ravi@domain.com](mailto:ravi@domain.com) -> ravi@domain.com
        const linkMatch = rawVal.match(/^\[([^\]]+)\]\([^)]+\)$/);
        const cleanVal = linkMatch ? linkMatch[1] : rawVal;

        const normalizedKey = rawKey
          .toLowerCase()
          .replace(/[^a-z0-9]/g, '_')
          .replace(/_+/g, '_');

        rec[normalizedKey] = cleanVal;
        rec[rawKey] = cleanVal;
      }
    }

    if (fileFound) rec.source_file = fileFound;
    if (sheetFound) rec.source_sheet = sheetFound;
    if (dbFound) rec.database = dbFound;
    if (colFound) rec.source_collection = colFound;

    const hasCore =
      rec.company_name ||
      rec.contact_person ||
      rec.designation ||
      rec.linkedin ||
      rec.linkedin_url ||
      rec.email_1 ||
      rec.email ||
      rec.mobile_no ||
      rec.city;

    if (hasCore) {
      parsedList.push(rec);
    }
  }

  return parsedList;
}

/**
 * Smart value renderer that converts Emails, LinkedIn URLs, Websites, and Phones
 * into clickable hyperlinks with appropriate protocols and targets.
 * Shows 'Not Available' in clean muted italics if value is missing/empty.
 */
function FormattedFieldValue({ value }) {
  if (value === null || value === undefined) {
    return <span className="text-slate-400 italic font-normal">Not Available</span>;
  }

  const str = String(value).trim();
  if (
    !str ||
    str.toLowerCase() === 'not available' ||
    str.toLowerCase() === 'not_available' ||
    str.toLowerCase() === 'none' ||
    str.toLowerCase() === 'null' ||
    str.toLowerCase() === 'nan' ||
    str.toLowerCase() === 'undefined' ||
    str.toLowerCase() === 'n/a' ||
    str.toLowerCase() === 'na' ||
    str === '-' ||
    str === '--'
  ) {
    return <span className="text-slate-400 italic font-normal">Not Available</span>;
  }

  // 1. Email address -> clickable mailto: hyperlink
  const emailRegex = /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/;
  const emailMatch = str.match(emailRegex);
  if (emailMatch && !str.startsWith('http')) {
    const email = emailMatch[0];
    return (
      <a
        href={`mailto:${email}`}
        className="font-medium text-sky-600 hover:text-sky-700 hover:underline break-all inline-flex items-center gap-1"
      >
        <span className="material-symbols-outlined text-[13px] text-sky-500">mail</span>
        <span>{str}</span>
      </a>
    );
  }

  // 2. LinkedIn URL -> clickable https://... hyperlink opening in new tab
  if (str.toLowerCase().includes('linkedin.com')) {
    const href = str.startsWith('http') ? str : `https://${str}`;
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="font-medium text-sky-600 hover:text-sky-700 hover:underline break-all inline-flex items-center gap-1"
      >
        <span className="material-symbols-outlined text-[13px] text-sky-500">open_in_new</span>
        <span>{str}</span>
      </a>
    );
  }

  // 3. Web URL -> clickable https://... hyperlink opening in new tab
  if (/^https?:\/\/|www\./i.test(str)) {
    const href = str.startsWith('http') ? str : `https://${str}`;
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="font-medium text-sky-600 hover:text-sky-700 hover:underline break-all inline-flex items-center gap-1"
      >
        <span className="material-symbols-outlined text-[13px] text-sky-500">link</span>
        <span>{str}</span>
      </a>
    );
  }

  // 4. Phone / Mobile number -> clickable tel: hyperlink
  if (/^(\+?\d[\d\s-]{7,15}\d)$/.test(str)) {
    return (
      <a
        href={`tel:${str.replace(/[^0-9+]/g, '')}`}
        className="font-medium text-sky-600 hover:text-sky-700 hover:underline break-all inline-flex items-center gap-1"
      >
        <span className="material-symbols-outlined text-[13px] text-sky-500">call</span>
        <span>{str}</span>
      </a>
    );
  }

  // Default clean text
  return <span className="font-semibold text-slate-800 break-words">{str}</span>;
}

/**
 * Dedicated component to display a single attribute row with label and formatted value.
 */
function FieldRow({ label, value, icon }) {
  return (
    <div className="flex items-start gap-2.5 py-1">
      {icon && (
        <span className="material-symbols-outlined text-sm text-sky-500 mt-0.5 shrink-0 select-none">
          {icon}
        </span>
      )}
      <div className="min-w-0 flex-1">
        <span className="text-slate-500 block text-[11px] font-label-sm uppercase font-semibold tracking-wider">
          {label}
        </span>
        <FormattedFieldValue value={value} />
      </div>
    </div>
  );
}

/**
 * Separate full card rendered for EVERY individual retrieved record.
 * Displays ONLY the columns/fields available in that specific file,
 * renders Emails, LinkedIn URLs, and Web URLs as hyperlinks,
 * displays 'Not Available' for empty fields, and removes 'View Profile'.
 */
function RecordResultCard({ record, index, totalCount }) {
  const [copied, setCopied] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);

  if (!record || typeof record !== 'object') return null;

  // 1. Resolve source information
  const sourceFileName =
    record.source_file &&
    !['mongodb', 'mongodb atlas', 'dataset_records', 'ecg database repository', 'not available', 'none', 'null'].includes(
      String(record.source_file).toLowerCase().trim()
    ) &&
    !String(record.source_file).toLowerCase().startsWith('mongodb:')
      ? record.source_file
      : (record['Source File'] || record['source_file'] || null);

  const dbName =
    record.database ||
    record.database_source ||
    '';

  const colName =
    record.source_collection ||
    record.dataset ||
    '';

  const sourceSheet =
    record.source_sheet ||
    record['Source Sheet'] ||
    record['Source Sheets'] ||
    null;

  const sourceRow =
    record.source_row && String(record.source_row).toLowerCase() !== 'not available'
      ? record.source_row
      : null;

  // 2. Extract strictly the fields that are actually available in this file
  const recordFields = getRecordFields(record);

  // 3. Resolve display spotlight title & role based on actual file data
  const nameField = recordFields.find(
    (f) =>
      ['contact_person', 'name', 'person_name', 'employee_name', 'customer_name'].includes(f.normKey) &&
      isValidValue(f.value)
  );

  const companyField = recordFields.find(
    (f) =>
      ['company_name', 'company', 'organization'].includes(f.normKey) &&
      isValidValue(f.value)
  );

  const roleField = recordFields.find(
    (f) =>
      ['designation', 'role', 'title', 'department', 'position'].includes(f.normKey) &&
      isValidValue(f.value)
  );

  const entityName =
    nameField?.value ||
    companyField?.value ||
    `Record #${index + 1}`;

  const entityRole =
    roleField?.value ||
    (companyField?.value && entityName !== companyField.value
      ? companyField.value
      : 'Indexed Record');

  const handleCopy = () => {
    const lines = [
      sourceFileName ? `Sources: ${sourceFileName}${sourceSheet ? ` | ${sourceSheet}` : ''}` : '',
      ...recordFields.map((f) => `${f.label}: ${f.value || 'Not Available'}`),
    ].filter(Boolean);

    navigator.clipboard?.writeText(lines.join('\n'));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleExport = (format) => {
    let content = '';
    let mimeType = '';
    let ext = format;

    if (format === 'csv' || format === 'xls') {
      const headers = recordFields.map((f) => f.label).join(',');
      const row = recordFields
        .map((f) => `"${String(f.value ?? 'Not Available').replace(/"/g, '""')}"`)
        .join(',');
      content = headers + '\n' + row;
      mimeType = format === 'csv' ? 'text/csv' : 'application/vnd.ms-excel';
    } else {
      content = `Sources: ${sourceFileName}${sourceSheet ? ` | ${sourceSheet}` : ''}\n\n`;
      recordFields.forEach((f) => {
        content += `${f.label}: ${f.value || 'Not Available'}\n`;
      });
      mimeType = 'text/plain';
      ext = 'txt';
    }

    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${entityName.replace(/[^a-z0-9]/gi, '_')}_record.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
    setExportOpen(false);
  };

  return (
    <div
      className="bg-white/95 backdrop-blur-md border border-sky-100 shadow-md text-slate-800 rounded-2xl p-5 sm:p-6 w-full max-w-3xl space-y-4 hover:border-sky-300 hover:shadow-lg transition-all"
      style={{
        boxShadow:
          'rgba(2, 132, 199, 0.08) 0px 10px 30px -5px, rgba(15, 23, 42, 0.04) 0px 2px 8px -2px',
      }}
    >
      {/* Prominent Header stating exact file and sheet retrieved */}
      <div className="flex items-center justify-between border-b border-sky-100 pb-3.5 flex-wrap gap-2">
        <div className="flex items-center gap-2.5 flex-wrap min-w-0">
          <div className="w-8 h-8 rounded-lg bg-sky-50 text-sky-600 flex items-center justify-center border border-sky-200/60 shrink-0">
            <span className="material-symbols-outlined text-base">table_chart</span>
          </div>
          <div className="truncate">
            <div className="flex items-center gap-2 flex-wrap">
              {sourceFileName ? (
                <span className="text-xs font-bold text-slate-800 font-mono tracking-tight">
                  Source File: {sourceFileName}
                </span>
              ) : (
                <span className="text-xs font-bold text-slate-800 font-mono tracking-tight">
                  {dbName ? `Database: ${dbName}` : ''}{dbName && colName ? ' • ' : ''}{colName ? `Collection: ${colName}` : ''}
                </span>
              )}
              {sourceSheet && (
                <span className="text-[10px] font-label-sm text-sky-700 bg-sky-50 px-2 py-0.5 rounded border border-sky-200 font-semibold">
                  {sourceSheet}
                </span>
              )}
              {sourceRow && (
                <span className="text-[10px] font-label-sm text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                  Row #{sourceRow}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[10px] font-label-sm font-semibold text-emerald-700 bg-emerald-50 border border-emerald-300 px-2.5 py-0.5 rounded-full inline-flex items-center gap-1">
            <span className="material-symbols-outlined text-[13px] text-emerald-600">verified</span>
            Verified Record
          </span>
          {totalCount > 1 && (
            <span className="text-[10px] font-label-sm text-sky-700 bg-sky-100 px-2.5 py-0.5 rounded-full font-bold">
              Record #{index + 1} of {totalCount}
            </span>
          )}
        </div>
      </div>

      {/* Profile Spotlight Banner without View Profile button */}
      <div className="bg-gradient-to-b from-sky-50/70 to-white/95 border border-sky-100/90 rounded-xl p-4 sm:p-5 space-y-4 shadow-xs">
        <div className="flex items-center gap-3 border-b border-sky-100/80 pb-3">
          <div className="w-11 h-11 rounded-full bg-gradient-to-tr from-sky-500 to-blue-600 text-white flex items-center justify-center font-bold text-sm shadow-md shadow-sky-500/25 ring-2 ring-sky-400/30 shrink-0">
            {getInitials(entityName)}
          </div>
          <div className="min-w-0">
            <h4 className="font-headline-xl text-base font-bold text-slate-900 leading-tight truncate">
              {entityName}
            </h4>
            <p className="text-xs text-slate-600 font-medium mt-0.5 truncate">{entityRole}</p>
          </div>
        </div>

        {/* Dynamic Attributes Grid: Displays only the fields present in that file */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5 text-xs">
          {recordFields.map((field) => (
            <FieldRow
              key={field.normKey}
              label={field.label}
              value={field.value}
              icon={field.icon}
            />
          ))}
        </div>
      </div>

      {/* Footer Actions */}
      <div className="flex items-center justify-end gap-2 pt-2 border-t border-sky-100 relative">
        <button
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 hover:text-sky-700 hover:border-sky-200 font-body-sm text-xs font-medium transition-colors cursor-pointer shadow-xs"
          onClick={handleCopy}
          type="button"
        >
          <span className="material-symbols-outlined text-sm text-slate-400">
            {copied ? 'check' : 'content_copy'}
          </span>
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>

        <div className="relative">
          <button
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 hover:text-sky-700 hover:border-sky-200 font-body-sm text-xs font-medium transition-colors cursor-pointer shadow-xs"
            onClick={() => setExportOpen(!exportOpen)}
            type="button"
          >
            <span className="material-symbols-outlined text-sm text-slate-400">file_download</span>
            <span>Export</span>
          </button>

          {exportOpen && (
            <div className="absolute bottom-full right-0 mb-2 w-32 bg-white border border-slate-200 rounded-lg shadow-lg overflow-hidden z-20">
              <button
                className="w-full text-left px-3.5 py-2 text-xs text-slate-700 hover:bg-slate-50 hover:text-sky-600 transition-colors"
                onClick={() => handleExport('csv')}
                type="button"
              >
                CSV
              </button>
              <button
                className="w-full text-left px-3.5 py-2 text-xs text-slate-700 hover:bg-slate-50 hover:text-sky-600 transition-colors"
                onClick={() => handleExport('xls')}
                type="button"
              >
                Excel
              </button>
              <button
                className="w-full text-left px-3.5 py-2 text-xs text-slate-700 hover:bg-slate-50 hover:text-sky-600 transition-colors"
                onClick={() => handleExport('pdf')}
                type="button"
              >
                PDF (Text)
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Helper to render message text with hyperlinks for URLs/emails/LinkedIn,
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
          return <hr key={idx} className="my-3 border-sky-100" />;
        }
        if (!line) {
          return <div key={idx} className="h-1.5" />;
        }

        const tokenRegex =
          /(\[([^\]]+)\]\(([^)]+)\))|((?:https?:\/\/|www\.)[^\s<>"']+)|([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)|(\*\*([^*]+)\*\*)/g;

        const tokens = [];
        let lastIndex = 0;
        let match;
        let keyIdx = 0;

        while ((match = tokenRegex.exec(line)) !== null) {
          if (match.index > lastIndex) {
            tokens.push(line.slice(lastIndex, match.index));
          }

          if (match[1]) {
            const label = match[2];
            const href =
              match[3].startsWith('http') || match[3].startsWith('mailto:')
                ? match[3]
                : `https://${match[3]}`;
            tokens.push(
              <a
                key={`mlink-${idx}-${keyIdx++}`}
                href={href}
                target={href.startsWith('mailto:') ? '_self' : '_blank'}
                rel="noopener noreferrer"
                className="text-sky-600 underline hover:text-sky-700 break-all font-medium"
              >
                {label}
              </a>
            );
          } else if (match[4]) {
            const rawUrl = match[4];
            const href = rawUrl.startsWith('http') ? rawUrl : `https://${rawUrl}`;
            tokens.push(
              <a
                key={`url-${idx}-${keyIdx++}`}
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sky-600 underline hover:text-sky-700 break-all font-medium"
              >
                {rawUrl}
              </a>
            );
          } else if (match[5]) {
            const email = match[5];
            tokens.push(
              <a
                key={`mail-${idx}-${keyIdx++}`}
                href={`mailto:${email}`}
                className="text-sky-600 underline hover:text-sky-700 break-all font-medium"
              >
                {email}
              </a>
            );
          } else if (match[6]) {
            tokens.push(
              <strong key={`b-${idx}-${keyIdx++}`} className="font-semibold text-slate-900">
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



function parseEmailLink(raw) {
  if (!raw) return { text: 'Not Available', href: null };
  const match = raw.match(/\[([^\]]+)\]\(([^)]+)\)/);
  if (match) {
    return { text: match[1], href: match[2] };
  }
  if (raw.toLowerCase() === 'not available') {
    return { text: 'Not Available', href: null };
  }
  if (raw.includes('@')) {
    return { text: raw, href: `mailto:${raw}` };
  }
  return { text: raw, href: null };
}

function parseStrictCompanyText(text) {
  if (!text || typeof text !== 'string') return [];
  if (!text.includes('Company Name:')) return [];

  const lines = text.split('\n');
  const companies = [];
  let currentCompany = null;
  let currentContact = null;
  let pendingSource = '';
  let currentRawLines = [];

  for (let rawLine of lines) {
    const line = rawLine.replace(/^[•\-\*]\s*/, '').trim();
    if (!line) {
      if (currentRawLines.length > 0) currentRawLines.push('');
      continue;
    }

    if (/^(?:Source File|Sources?)\s*:/i.test(line)) {
      pendingSource = line.replace(/^(?:Source File|Sources?)\s*:\s*/i, '').trim();
      currentRawLines.push(rawLine);
      continue;
    }
    if (/^(?:Database|Collection)\s*:/i.test(line)) {
      pendingSource = line.trim();
      currentRawLines.push(rawLine);
      continue;
    }

    if (line.startsWith('---')) {
      if (currentCompany) {
        if (currentContact) currentCompany.contacts.push(currentContact);
        currentCompany.rawText = currentRawLines.join('\n').trim();
        companies.push(currentCompany);
        currentCompany = null;
        currentContact = null;
        currentRawLines = [];
      }
      pendingSource = '';
      continue;
    }

    if (line.startsWith('Company Name:')) {
      if (currentCompany) {
        if (currentContact) currentCompany.contacts.push(currentContact);
        currentCompany.rawText = currentRawLines.join('\n').trim();
        companies.push(currentCompany);
        currentCompany = null;
        currentContact = null;
        currentRawLines = [];
      }
      currentCompany = {
        sourceFile: pendingSource || null,
        companyName: line.replace('Company Name:', '').trim(),
        contacts: [],
      };
      pendingSource = '';
      currentRawLines.push(rawLine);
      continue;
    }

    currentRawLines.push(rawLine);

    if (/^Contact Person \d+:?/i.test(line)) {
      if (currentContact && currentCompany) {
        currentCompany.contacts.push(currentContact);
      }
      currentContact = {
        title: line.replace(':', '').trim(),
        name: 'Not Available',
        designation: 'Not Available',
        linkedin: 'Not Available',
        numbers: [],
        emails: [],
        locations: [],
      };
      continue;
    }

    if (currentContact) {
      if (line.startsWith('Name:')) {
        currentContact.name = line.replace('Name:', '').trim() || 'Not Available';
      } else if (line.startsWith('Designation:')) {
        currentContact.designation = line.replace('Designation:', '').trim() || 'Not Available';
      } else if (/^(?:LinkedIn|Linkedin)\s*:/i.test(line)) {
        const val = line.replace(/^(?:LinkedIn|Linkedin)\s*:\s*/i, '').trim();
        currentContact.linkedin = val || 'Not Available';
      } else if (/^Contact Number \d+:/i.test(line)) {
        const colonIdx = line.indexOf(':');
        const label = line.substring(0, colonIdx).trim();
        const val = line.substring(colonIdx + 1).trim();
        currentContact.numbers.push({ label, val });
      } else if (/^Email \d+:/i.test(line)) {
        const colonIdx = line.indexOf(':');
        const label = line.substring(0, colonIdx).trim();
        const val = line.substring(colonIdx + 1).trim();
        currentContact.emails.push({ label, ...parseEmailLink(val) });
      } else if (line.startsWith('Address:')) {
        currentContact.locations.push({ label: 'Address', val: line.replace('Address:', '').trim() });
      } else if (line.startsWith('City:')) {
        currentContact.locations.push({ label: 'City', val: line.replace('City:', '').trim() });
      } else if (line.startsWith('State:')) {
        currentContact.locations.push({ label: 'State', val: line.replace('State:', '').trim() });
      } else if (line.startsWith('Location:')) {
        currentContact.locations.push({ label: 'Location', val: line.replace('Location:', '').trim() });
      }
    }
  }

  if (currentCompany) {
    if (currentContact) currentCompany.contacts.push(currentContact);
    currentCompany.rawText = currentRawLines.join('\n').trim();
    companies.push(currentCompany);
  }

  return companies;
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function flattenCompaniesForExport(companies) {
  const rows = [];
  companies.forEach((comp) => {
    const sourceFile = comp.sourceFile || 'Not Available';
    const companyName = comp.companyName || 'Not Available';

    if (!comp.contacts || comp.contacts.length === 0) {
      rows.push({
        sourceFile,
        companyName,
        contactTitle: 'Contact Person 1',
        name: 'Not Available',
        designation: 'Not Available',
        linkedin: 'Not Available',
        phones: 'Not Available',
        emails: 'Not Available',
        address: '',
        city: '',
        state: '',
        location: '',
      });
      return;
    }

    comp.contacts.forEach((contact, idx) => {
      const contactTitle = contact.title || `Contact Person ${idx + 1}`;
      const name = contact.name || 'Not Available';
      const designation = contact.designation || 'Not Available';
      const linkedin = contact.linkedin || 'Not Available';
      const phones = (contact.numbers || []).map((n) => n.val).join(', ') || 'Not Available';
      const emails = (contact.emails || []).map((e) => e.text).join(', ') || 'Not Available';

      const addrObj = (contact.locations || []).find((l) => l.label === 'Address');
      const cityObj = (contact.locations || []).find((l) => l.label === 'City');
      const stateObj = (contact.locations || []).find((l) => l.label === 'State');
      const locObj = (contact.locations || []).find((l) => l.label === 'Location');

      rows.push({
        sourceFile,
        companyName,
        contactTitle,
        name,
        designation,
        linkedin,
        phones,
        emails,
        address: addrObj ? addrObj.val : '',
        city: cityObj ? cityObj.val : '',
        state: stateObj ? stateObj.val : '',
        location: locObj ? locObj.val : '',
      });
    });
  });
  return rows;
}

function exportToCsv(filename, companies) {
  const rows = flattenCompaniesForExport(companies);
  const headers = [
    'Source File',
    'Company Name',
    'Contact Person',
    'Name',
    'Designation',
    'LinkedIn',
    'Contact Numbers',
    'Email Addresses',
    'Address',
    'City',
    'State',
  ];

  const csvRows = [headers.join(',')];
  rows.forEach((r) => {
    const values = [
      r.sourceFile,
      r.companyName,
      r.contactTitle,
      r.name,
      r.designation,
      r.linkedin,
      r.phones,
      r.emails,
      r.address,
      r.city,
      r.state,
    ];
    csvRows.push(
      values.map((v) => `"${String(v || '').replace(/"/g, '""')}"`).join(',')
    );
  });

  const blob = new Blob(['\uFEFF' + csvRows.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
  downloadBlob(blob, `${filename}.csv`);
}

function exportToExcel(filename, companies) {
  const rows = flattenCompaniesForExport(companies);
  const tableRows = rows
    .map(
      (r) => `
    <tr>
      <td>${escapeHtml(r.sourceFile)}</td>
      <td><strong>${escapeHtml(r.companyName)}</strong></td>
      <td>${escapeHtml(r.contactTitle)}</td>
      <td>${escapeHtml(r.name)}</td>
      <td>${escapeHtml(r.designation)}</td>
      <td>${escapeHtml(r.linkedin)}</td>
      <td>${escapeHtml(r.phones)}</td>
      <td>${escapeHtml(r.emails)}</td>
      <td>${escapeHtml(r.address)}</td>
      <td>${escapeHtml(r.city)}</td>
      <td>${escapeHtml(r.state)}</td>
    </tr>`
    )
    .join('');

  const template = `
    <html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns="http://www.w3.org/TR/REC-html40">
    <head>
      <meta charset="utf-8">
      <!--[if gte mso 9]>
      <xml>
        <x:ExcelWorkbook>
          <x:ExcelWorksheets>
            <x:ExcelWorksheet>
              <x:Name>Contacts</x:Name>
              <x:WorksheetOptions><x:DisplayGridlines/></x:WorksheetOptions>
            </x:ExcelWorksheet>
          </x:ExcelWorksheets>
        </x:ExcelWorkbook>
      </xml>
      <![endif]-->
      <style>
        table { border-collapse: collapse; font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; font-size: 11pt; }
        th { background-color: #0284c7; color: #ffffff; font-weight: bold; border: 1px solid #cbd5e1; padding: 10px 14px; text-align: left; }
        td { border: 1px solid #cbd5e1; padding: 8px 12px; vertical-align: top; }
        tr:nth-child(even) td { background-color: #f8fafc; }
      </style>
    </head>
    <body>
      <table>
        <thead>
          <tr>
            <th>Source File</th>
            <th>Company Name</th>
            <th>Contact Person</th>
            <th>Name</th>
            <th>Designation</th>
            <th>LinkedIn</th>
            <th>Contact Numbers</th>
            <th>Email Addresses</th>
            <th>Address</th>
            <th>City</th>
            <th>State</th>
          </tr>
        </thead>
        <tbody>
          ${tableRows}
        </tbody>
      </table>
    </body>
    </html>
  `;

  const blob = new Blob([template], { type: 'application/vnd.ms-excel;charset=utf-8;' });
  downloadBlob(blob, `${filename}.xls`);
}

function exportToPdf(filename, companies) {
  try {
    const doc = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: 'a4',
    });

    const pageWidth = doc.internal.pageSize.getWidth();
    const margin = 14;
    const contentWidth = pageWidth - margin * 2;
    let y = 18;

    // Header banner
    doc.setFillColor(2, 132, 199); // #0284c7 Sky 600
    doc.rect(margin, y, contentWidth, 12, 'F');
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(13);
    doc.setFont('helvetica', 'bold');
    doc.text('Calispec Confidential Database Report', margin + 6, y + 8);
    y += 18;

    doc.setTextColor(100, 116, 139); // slate-500
    doc.setFontSize(8.5);
    doc.setFont('helvetica', 'normal');
    doc.text(`Generated: ${new Date().toLocaleString()}`, margin, y);
    y += 8;

    companies.forEach((comp) => {
      if (y > 245) {
        doc.addPage();
        y = 18;
      }

      // Company header card
      const headerHeight = comp.sourceFile ? 16 : 11;
      doc.setFillColor(240, 249, 255); // sky-50
      doc.setDrawColor(186, 230, 253); // sky-200
      doc.rect(margin, y, contentWidth, headerHeight, 'FD');

      if (comp.sourceFile) {
        doc.setTextColor(3, 105, 161); // sky-700
        doc.setFontSize(8);
        doc.setFont('helvetica', 'bold');
        doc.text(`Source File: ${comp.sourceFile}`, margin + 4, y + 5);
        y += 6;
      }

      doc.setTextColor(15, 23, 42); // slate-900
      doc.setFontSize(11);
      doc.setFont('helvetica', 'bold');
      doc.text(comp.companyName || 'Not Available', margin + 4, y + 6);
      y += 12;

      // Contacts list
      (comp.contacts || []).forEach((contact, ctIdx) => {
        if (y > 255) {
          doc.addPage();
          y = 18;
        }

        doc.setTextColor(2, 132, 199); // sky-600
        doc.setFontSize(9);
        doc.setFont('helvetica', 'bold');
        doc.text(contact.title || `Contact Person ${ctIdx + 1}`, margin + 4, y);
        y += 5;

        const fields = [
          { label: 'Name', val: contact.name },
          { label: 'Designation', val: contact.designation },
          { label: 'LinkedIn', val: contact.linkedin },
          ...(contact.numbers || []).map((n) => ({ label: n.label, val: n.val })),
          ...(contact.emails || []).map((e) => ({ label: e.label, val: e.text })),
          ...(contact.locations || []).map((l) => ({ label: l.label, val: l.val })),
        ];

        fields.forEach((f) => {
          if (!f.val) return;
          if (y > 275) {
            doc.addPage();
            y = 18;
          }
          doc.setTextColor(71, 85, 105); // slate-600
          doc.setFontSize(8);
          doc.setFont('helvetica', 'bold');
          doc.text(`${f.label}:`, margin + 6, y);

          doc.setTextColor(15, 23, 42); // slate-900
          doc.setFont('helvetica', 'normal');
          doc.text(String(f.val), margin + 42, y);
          y += 4.5;
        });

        y += 3;
      });

      y += 6;
    });

    doc.save(`${filename}.pdf`);
  } catch (err) {
    console.error('jsPDF generation failed, using print fallback:', err);
    window.print();
  }
}

function ExportDropdown({ companies, filename = 'calispec_data', label = 'Export', className = '' }) {
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [open]);

  const handleDownload = (format) => {
    const cleanFilename = (filename || 'export').replace(/[^a-z0-9_-]/gi, '_');
    if (format === 'csv') {
      exportToCsv(cleanFilename, companies);
    } else if (format === 'excel') {
      exportToExcel(cleanFilename, companies);
    } else if (format === 'pdf') {
      exportToPdf(cleanFilename, companies);
    }
    setOpen(false);
  };

  return (
    <div className={`relative inline-block text-left ${className}`} ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-50 hover:bg-sky-50 hover:text-sky-700 border border-slate-200 text-slate-600 text-xs font-medium transition-colors cursor-pointer shadow-2xs"
        title="Export response options (CSV, Excel, PDF)"
      >
        <span className="material-symbols-outlined text-sm text-slate-500">file_download</span>
        <span>{label}</span>
        <span className="material-symbols-outlined text-xs text-slate-400">
          {open ? 'expand_less' : 'expand_more'}
        </span>
      </button>

      {open && (
        <div className="absolute right-0 bottom-full mb-1.5 sm:bottom-auto sm:top-full sm:mt-1.5 w-44 bg-white border border-slate-200/90 rounded-xl shadow-xl z-50 py-1.5 animate-fadeIn backdrop-blur-md">
          <div className="px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100">
            Export Format
          </div>

          {/* CSV Option */}
          <button
            type="button"
            onClick={() => handleDownload('csv')}
            className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-sky-50 hover:text-sky-700 flex items-center gap-2.5 transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-base text-emerald-600">table_view</span>
            <div>
              <div className="font-semibold leading-tight">CSV</div>
              <div className="text-[10px] text-slate-400">Comma-separated (.csv)</div>
            </div>
          </button>

          {/* Excel Option */}
          <button
            type="button"
            onClick={() => handleDownload('excel')}
            className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-sky-50 hover:text-sky-700 flex items-center gap-2.5 transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-base text-emerald-700">grid_on</span>
            <div>
              <div className="font-semibold leading-tight">Excel</div>
              <div className="text-[10px] text-slate-400">Spreadsheet (.xls)</div>
            </div>
          </button>

          {/* PDF Option */}
          <button
            type="button"
            onClick={() => handleDownload('pdf')}
            className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-sky-50 hover:text-sky-700 flex items-center gap-2.5 transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-base text-rose-600">picture_as_pdf</span>
            <div>
              <div className="font-semibold leading-tight">PDF</div>
              <div className="text-[10px] text-slate-400">Document (.pdf)</div>
            </div>
          </button>
        </div>
      )}
    </div>
  );
}

function StrictCompanyCard({ company, index }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (company.rawText) {
      navigator.clipboard?.writeText(company.rawText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div
      className="bg-white/95 backdrop-blur-md border border-sky-100 rounded-2xl p-5 sm:p-6 shadow-md transition-all hover:shadow-lg w-full max-w-3xl"
      style={{
        boxShadow:
          'rgba(2, 132, 199, 0.08) 0px 10px 30px -5px, rgba(15, 23, 42, 0.04) 0px 2px 8px -2px',
      }}
    >
      {/* Company Header */}
      <div className="flex items-start justify-between gap-3 pb-4 border-b border-slate-100">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-sky-500 to-sky-600 text-white flex items-center justify-center shadow-sm shadow-sky-600/20">
            <span className="material-symbols-outlined text-xl">apartment</span>
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-sky-700 font-headline-xl">
              Company Name
            </div>
            <h3 className="text-base sm:text-lg font-bold text-slate-900 tracking-tight">
              {company.companyName}
            </h3>
            {company.sourceFile && (
              <div className="flex items-center gap-1.5 mt-1 text-[11px] font-medium text-slate-600 bg-sky-50/80 border border-sky-100 px-2 py-0.5 rounded-md w-fit">
                <span className="material-symbols-outlined text-xs text-sky-600">
                  {company.sourceFile.includes('Collection:') || company.sourceFile.includes('Database:') ? 'database' : 'description'}
                </span>
                <span>
                  {company.sourceFile.startsWith('Source File:') || company.sourceFile.startsWith('Database:') || company.sourceFile.startsWith('Collection:') || company.sourceFile.startsWith('Source:')
                    ? company.sourceFile
                    : `Source File: ${company.sourceFile}`}
                </span>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={handleCopy}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-50 hover:bg-sky-50 hover:text-sky-700 border border-slate-200 text-slate-600 text-xs font-medium transition-colors cursor-pointer"
            title="Copy company details"
          >
            <span className="material-symbols-outlined text-sm">
              {copied ? 'check' : 'content_copy'}
            </span>
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>

          <ExportDropdown
            companies={[company]}
            filename={`${company.companyName || 'company'}_details`}
            label="Export"
          />
        </div>
      </div>

      {/* Contact Persons */}
      <div className="mt-4 space-y-4">
        {company.contacts.map((contact, cIdx) => (
          <div
            key={cIdx}
            className="bg-slate-50/80 border border-slate-200/80 rounded-xl p-4 sm:p-5 space-y-3.5"
          >
            {/* Contact Person Header */}
            <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-slate-200/60">
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-0.5 rounded-full bg-sky-100 text-sky-800 text-[11px] font-bold border border-sky-200/80">
                  {contact.title || `Contact Person ${cIdx + 1}`}
                </span>
                <span className="text-sm sm:text-base font-bold text-slate-800">
                  {contact.name}
                </span>
              </div>
              <div className="flex items-center gap-1 text-xs text-slate-600 font-medium bg-white px-2.5 py-1 rounded-lg border border-slate-200 shadow-2xs">
                <span className="material-symbols-outlined text-sm text-sky-600">badge</span>
                <span>{contact.designation}</span>
              </div>
            </div>

            {/* Details Grid: Numbers, Emails, Location, LinkedIn */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-1">
              {/* Contact Numbers */}
              <div className="bg-white rounded-lg p-3 border border-slate-200/80 shadow-2xs space-y-1.5 min-w-0">
                <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  <span className="material-symbols-outlined text-sm text-sky-600">call</span>
                  <span>Contact Numbers</span>
                </div>
                <div className="space-y-1">
                  {contact.numbers.length > 0 ? (
                    contact.numbers.map((num, nIdx) => (
                      <div key={nIdx} className="text-xs font-medium text-slate-700">
                        <span className="text-slate-400 text-[10px] block">{num.label}:</span>
                        {num.val !== 'Not Available' ? (
                          <a
                            href={`tel:${num.val.replace(/\s+/g, '')}`}
                            className="text-sky-700 hover:text-sky-900 font-semibold transition-colors"
                          >
                            {num.val}
                          </a>
                        ) : (
                          <span className="text-slate-400">Not Available</span>
                        )}
                      </div>
                    ))
                  ) : (
                    <div className="text-xs text-slate-400">Not Available</div>
                  )}
                </div>
              </div>

              {/* Email Addresses */}
              <div className="bg-white rounded-lg p-3 border border-slate-200/80 shadow-2xs space-y-1.5 min-w-0">
                <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  <span className="material-symbols-outlined text-sm text-sky-600">mail</span>
                  <span>Email Addresses</span>
                </div>
                <div className="space-y-1">
                  {contact.emails.length > 0 ? (
                    contact.emails.map((em, eIdx) => (
                      <div key={eIdx} className="text-xs font-medium text-slate-700 break-all">
                        <span className="text-slate-400 text-[10px] block">{em.label}:</span>
                        {em.href ? (
                          <a
                            href={em.href}
                            className="text-sky-600 hover:text-sky-800 underline font-semibold transition-colors"
                          >
                            {em.text}
                          </a>
                        ) : (
                          <span className="text-slate-400">{em.text}</span>
                        )}
                      </div>
                    ))
                  ) : (
                    <div className="text-xs text-slate-400">Not Available</div>
                  )}
                </div>
              </div>

              {/* Location */}
              <div className="bg-white rounded-lg p-3 border border-slate-200/80 shadow-2xs space-y-1.5 min-w-0">
                <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  <span className="material-symbols-outlined text-sm text-sky-600">location_on</span>
                  <span>Location</span>
                </div>
                <div className="space-y-1">
                  {contact.locations.length > 0 ? (
                    contact.locations.map((loc, lIdx) => (
                      <div key={lIdx} className="text-xs font-medium text-slate-700">
                        <span className="text-slate-400 text-[10px]">{loc.label}: </span>
                        <span className={loc.val === 'Not Available' ? 'text-slate-400' : 'text-slate-800 font-semibold'}>
                          {loc.val}
                        </span>
                      </div>
                    ))
                  ) : (
                    <div className="text-xs text-slate-400">Location: Not Available</div>
                  )}
                </div>
              </div>

              {/* LinkedIn */}
              <div className="bg-white rounded-lg p-3 border border-slate-200/80 shadow-2xs space-y-1.5 min-w-0 overflow-hidden">
                <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  <span className="material-symbols-outlined text-sm text-sky-600">work</span>
                  <span>LinkedIn</span>
                </div>
                <div className="space-y-1 min-w-0">
                  {contact.linkedin &&
                  contact.linkedin !== 'Not Available' &&
                  contact.linkedin.toLowerCase() !== 'not available' ? (
                    <div className="text-xs font-medium text-slate-700 min-w-0">
                      <span className="text-slate-400 text-[10px] block">Profile:</span>
                      <a
                        href={
                          contact.linkedin.startsWith('http')
                            ? contact.linkedin
                            : `https://${contact.linkedin}`
                        }
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sky-600 hover:text-sky-800 underline font-semibold flex items-center justify-between gap-1 w-full min-w-0 max-w-full transition-colors group/link"
                        title={contact.linkedin}
                      >
                        <span className="truncate min-w-0 flex-1">
                          {contact.linkedin}
                        </span>
                        <span className="material-symbols-outlined text-[13px] flex-shrink-0 text-sky-500 group-hover/link:text-sky-700">open_in_new</span>
                      </a>
                    </div>
                  ) : (
                    <div className="text-xs font-medium text-slate-700">
                      <span className="text-slate-400 text-[10px] block">Profile:</span>
                      <span className="text-slate-400">Not Available</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ChatMessage({ message, onInspect, onEdit }) {
  const isUser = message.role === 'user';
  const now = new Date();
  const timeStr = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;

  // 1. User Message Row with Copy and Edit controls underneath
  if (isUser) {
    const [copied, setCopied] = useState(false);

    const handleCopy = () => {
      navigator.clipboard?.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    };

    return (
      <div className="flex flex-col items-end w-full group animate-fadeIn">
        <div className="bg-gradient-to-r from-sky-700 via-sky-600 to-blue-600 text-white rounded-2xl rounded-tr-xs p-4 shadow-md shadow-sky-900/10 border border-sky-500/30 max-w-2xl text-left">
          <p className="font-body-md text-sm md:text-base leading-relaxed text-white selection:bg-sky-200 selection:text-sky-900">
            {message.content}
          </p>
        </div>

        {/* Copy option under the chat sending (Edit option removed) */}
        <div className="flex items-center gap-3 mt-1.5 px-2 text-slate-400">
          <button
            type="button"
            onClick={handleCopy}
            className="flex items-center gap-1 hover:text-sky-600 transition-colors text-[11px] font-medium cursor-pointer"
            title="Copy message"
          >
            <span className="material-symbols-outlined text-[13px]">
              {copied ? 'check' : 'content_copy'}
            </span>
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>
        </div>
      </div>
    );
  }

  // 2. Assistant Bot Response Row
  const { error, loading, text, is_system_notice } = message;
  const [copied, setCopied] = useState(false);

  const handleCopyFormatted = () => {
    if (text) {
      navigator.clipboard?.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const parsedCompanies = text ? parseStrictCompanyText(text) : [];

  return (
    <div className="flex flex-col items-start w-full animate-fadeIn">
      {/* Bot Header Line */}
      <div className="flex items-center gap-2.5 mb-2 pl-1">
        <div className="w-7 h-7 rounded-full bg-sky-600 text-white flex items-center justify-center shadow-md">
          <span className="material-symbols-outlined text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>
            smart_toy
          </span>
        </div>
        <span className="font-headline-xl text-xs font-bold text-slate-800 tracking-wide">
          Calispec chatbot
        </span>
        <span className="font-label-sm text-[10px] text-slate-400">{timeStr}</span>
      </div>

      {/* Loading State */}
      {loading && (
        <div
          className="bg-white/95 backdrop-blur-md border border-sky-100 shadow-md text-slate-800 rounded-2xl p-6 w-full max-w-3xl flex items-center gap-3"
          style={{
            boxShadow:
              'rgba(2, 132, 199, 0.08) 0px 10px 30px -5px, rgba(15, 23, 42, 0.04) 0px 2px 8px -2px',
          }}
        >
          <span className="material-symbols-outlined text-sky-600 animate-spin text-xl">
            progress_activity
          </span>
          <span className="text-sm font-label-sm text-slate-600">
            Searching database records...
          </span>
        </div>
      )}

      {/* Error State */}
      {!loading && error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-2xl p-5 w-full max-w-3xl flex items-start gap-3 shadow-xs">
          <span className="material-symbols-outlined text-rose-500 text-xl flex-shrink-0">warning</span>
          <div>
            <h4 className="font-headline-xl text-xs font-bold uppercase tracking-wider text-rose-900">
              Database Search Error
            </h4>
            <p className="text-xs text-rose-700 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* System Notice State (e.g. dataset uploaded) */}
      {!loading && !error && is_system_notice && (
        <div
          className="bg-white/95 backdrop-blur-md border border-emerald-200 shadow-md text-slate-800 rounded-2xl p-6 w-full max-w-3xl space-y-2"
          style={{
            boxShadow:
              'rgba(2, 132, 199, 0.08) 0px 10px 30px -5px, rgba(15, 23, 42, 0.04) 0px 2px 8px -2px',
          }}
        >
          <div className="flex items-center gap-2 text-emerald-700 font-semibold text-xs font-headline-xl uppercase tracking-wider">
            <span className="material-symbols-outlined text-sm text-emerald-600">verified</span>
            <span>Dataset Indexed &amp; Ready for AI Search</span>
          </div>
          <p className="text-sm leading-relaxed whitespace-pre-line text-slate-700">{text}</p>
        </div>
      )}

      {/* Normal Query Response - Strict Formatted Structure */}
      {!loading && !error && !is_system_notice && (
        <div className="space-y-4 w-full">
          {parsedCompanies.length > 0 ? (
            /* Render Nice Structured UI Cards for Companies */
            <div className="space-y-4 w-full">
              {parsedCompanies.map((comp, idx) => (
                <StrictCompanyCard key={idx} company={comp} index={idx} />
              ))}

              {/* Bot Response Bottom Action Toolbar for the entire response */}
              <div className="flex items-center justify-between gap-3 pt-1 px-1 text-slate-500 w-full max-w-3xl">
                <div className="text-[11px] text-slate-400 font-medium">
                  {parsedCompanies.length > 1 ? (
                    <span>{parsedCompanies.length} companies retrieved</span>
                  ) : null}
                </div>

                <div className="flex items-center gap-2 ml-auto">
                  <button
                    type="button"
                    onClick={handleCopyFormatted}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-50 hover:bg-sky-50 hover:text-sky-700 border border-slate-200 text-slate-600 text-xs font-medium transition-colors cursor-pointer"
                    title="Copy entire response"
                  >
                    <span className="material-symbols-outlined text-sm">
                      {copied ? 'check' : 'content_copy'}
                    </span>
                    <span>{copied ? 'Copied' : 'Copy Response'}</span>
                  </button>

                  <ExportDropdown
                    companies={parsedCompanies}
                    filename="calispec_response_data"
                    label={parsedCompanies.length > 1 ? "Export All" : "Export Response"}
                  />
                </div>
              </div>
            </div>
          ) : text && text !== 'No data found' ? (
            /* Fallback formatted message for general notifications */
            <div
              className="bg-white/95 backdrop-blur-md border border-sky-100 shadow-md text-slate-800 rounded-2xl p-5 sm:p-6 w-full max-w-3xl"
              style={{
                boxShadow:
                  'rgba(2, 132, 199, 0.08) 0px 10px 30px -5px, rgba(15, 23, 42, 0.04) 0px 2px 8px -2px',
              }}
            >
              <div className="text-sm md:text-[14.5px] leading-relaxed text-slate-800 font-sans">
                <FormattedMessageText text={text} />
              </div>

              {/* Action Toolbar */}
              <div className="flex items-center justify-end gap-2 pt-3 mt-4 border-t border-slate-100 text-slate-400">
                <button
                  type="button"
                  onClick={handleCopyFormatted}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-50 hover:bg-sky-50 hover:text-sky-700 border border-slate-200 text-slate-600 text-xs font-medium transition-colors cursor-pointer"
                  title="Copy formatted contact details"
                >
                  <span className="material-symbols-outlined text-sm">
                    {copied ? 'check' : 'content_copy'}
                  </span>
                  <span>{copied ? 'Copied' : 'Copy'}</span>
                </button>

                <ExportDropdown
                  companies={[{ companyName: 'Search_Result', rawText: text, contacts: [] }]}
                  filename="calispec_response_data"
                  label="Export"
                />
              </div>
            </div>
          ) : (
            <div
              className="bg-white/95 backdrop-blur-md border border-sky-100 shadow-md text-slate-800 rounded-2xl p-5 w-full max-w-3xl text-xs text-slate-600"
              style={{
                boxShadow:
                  'rgba(2, 132, 199, 0.08) 0px 10px 30px -5px, rgba(15, 23, 42, 0.04) 0px 2px 8px -2px',
              }}
            >
              <span className="block font-semibold text-slate-800">
                No data found
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}



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
    str.toLowerCase() === 'no data available' ||
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

function TableCellRenderer({ value, headerName }) {
  if (!value || value === '-' || value === '--' || value.toLowerCase() === 'not available') {
    return <span className="text-slate-400 italic text-[11px]">Not Available</span>;
  }

  // Email column or email address detected
  if (
    headerName.includes('email') ||
    headerName.includes('mail') ||
    /^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/.test(value.trim())
  ) {
    const rawEmail = value.replace(/^\[mailto:/i, '').replace(/[\[\]]/g, '').trim();
    return (
      <a
        href={`mailto:${rawEmail}`}
        className="inline-flex items-center gap-1 text-sky-600 hover:text-sky-800 hover:underline font-medium break-all"
        title={`Send email to ${rawEmail}`}
      >
        <span className="material-symbols-outlined text-[14px] text-sky-500 shrink-0">mail</span>
        <span>{rawEmail}</span>
      </a>
    );
  }

  // Phone column or phone numbers
  if (
    headerName.includes('phone') ||
    headerName.includes('mobile') ||
    headerName.includes('contact no') ||
    /^\+?[\d\s\-()]{7,}$/.test(value.trim())
  ) {
    const cleanTel = value.replace(/[^\d+]/g, '');
    return (
      <a
        href={`tel:${cleanTel}`}
        className="inline-flex items-center gap-1 font-mono text-[11.5px] text-slate-800 hover:text-sky-700 bg-slate-50 hover:bg-sky-50 px-2 py-0.5 rounded border border-slate-200 transition-colors whitespace-nowrap"
        title={`Call ${value}`}
      >
        <span className="material-symbols-outlined text-[13px] text-slate-400 shrink-0">call</span>
        <span>{value}</span>
      </a>
    );
  }

  // City or location
  if (headerName.includes('city') || headerName.includes('location')) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-medium text-[11px] border border-slate-200/60 whitespace-nowrap">
        <span className="material-symbols-outlined text-[13px] text-slate-400 shrink-0">location_on</span>
        <span>{value}</span>
      </span>
    );
  }

  // Company column
  if (headerName.includes('company')) {
    return (
      <span className="font-semibold text-slate-900 flex items-center gap-1.5">
        <span className="material-symbols-outlined text-[15px] text-sky-600 shrink-0">apartment</span>
        <span>{value}</span>
      </span>
    );
  }

  // Designation column
  if (headerName.includes('designation') || headerName.includes('role')) {
    return (
      <span className="inline-flex items-center gap-1 text-slate-700 font-medium">
        <span className="material-symbols-outlined text-[14px] text-amber-500 shrink-0">badge</span>
        <span>{value}</span>
      </span>
    );
  }

  return <span>{renderInlineTokens(value)}</span>;
}

function ModernMarkdownTable({ headers, rows }) {
  const [copied, setCopied] = useState(false);

  const handleCopyTable = () => {
    const tsv = [
      headers.join('\t'),
      ...rows.map((r) => r.join('\t'))
    ].join('\n');
    navigator.clipboard?.writeText(tsv);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleExportCsv = () => {
    const escapeCsv = (str) => {
      const s = String(str || '').replace(/"/g, '""');
      return `"${s}"`;
    };
    const csv = [
      headers.map(escapeCsv).join(','),
      ...rows.map((r) => r.map(escapeCsv).join(','))
    ].join('\r\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    downloadBlob(blob, 'calispec_search_results.csv');
  };

  return (
    <div className="my-3.5 rounded-2xl border border-sky-100 bg-white shadow-sm overflow-hidden transition-all hover:shadow-md w-full max-w-4xl">
      {/* Table Header Bar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-gradient-to-r from-sky-50/80 to-slate-50 border-b border-sky-100/80">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-sky-600 text-base">table_view</span>
          <span className="text-xs font-bold text-slate-800 uppercase tracking-wider font-headline-xl">
            Retrieved Records ({rows.length})
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={handleCopyTable}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-white hover:bg-sky-50 text-slate-600 hover:text-sky-700 border border-slate-200 text-xs font-medium transition-colors shadow-2xs cursor-pointer"
            title="Copy table to clipboard"
          >
            <span className="material-symbols-outlined text-[13px]">{copied ? 'check' : 'content_copy'}</span>
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>
          <button
            type="button"
            onClick={handleExportCsv}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-sky-600 hover:bg-sky-700 text-white text-xs font-medium transition-colors shadow-2xs cursor-pointer"
            title="Export CSV"
          >
            <span className="material-symbols-outlined text-[13px]">file_download</span>
            <span>CSV</span>
          </button>
        </div>
      </div>

      {/* Table Container */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="bg-slate-50/90 border-b border-slate-200 text-slate-700 font-semibold tracking-wide">
              {headers.map((h, hIdx) => (
                <th key={hIdx} className="px-3.5 py-2.5 whitespace-nowrap">
                  <div className="flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-[15px] text-sky-600">
                      {getFieldIcon(h)}
                    </span>
                    <span>{h}</span>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((row, rIdx) => (
              <tr key={rIdx} className="hover:bg-sky-50/40 transition-colors even:bg-slate-50/30">
                {row.map((cell, cIdx) => {
                  const headerName = (headers[cIdx] || '').toLowerCase();
                  return (
                    <td key={cIdx} className="px-3.5 py-2.5 align-middle text-slate-800">
                      <TableCellRenderer value={cell} headerName={headerName} />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function renderInlineTokens(line, lineKey = 0) {
  if (!line) return null;

  const tokenRegex =
    /(\[([^\]]+)\]\(([^)]+)\))|((?:https?:\/\/|www\.)[^\s<>"']+)|([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)|(\*\*([^*]+)\*\*)|(`([^`]+)`)/g;

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
        match[3].startsWith('http') || match[3].startsWith('mailto:') || match[3].startsWith('tel:')
          ? match[3]
          : `https://${match[3]}`;
      tokens.push(
        <a
          key={`mlink-${lineKey}-${keyIdx++}`}
          href={href}
          target={href.startsWith('mailto:') || href.startsWith('tel:') ? '_self' : '_blank'}
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
          key={`url-${lineKey}-${keyIdx++}`}
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
          key={`mail-${lineKey}-${keyIdx++}`}
          href={`mailto:${email}`}
          className="text-sky-600 underline hover:text-sky-700 break-all font-medium"
        >
          {email}
        </a>
      );
    } else if (match[6]) {
      tokens.push(
        <strong key={`b-${lineKey}-${keyIdx++}`} className="font-semibold text-slate-900">
          {match[7]}
        </strong>
      );
    } else if (match[8]) {
      tokens.push(
        <code
          key={`c-${lineKey}-${keyIdx++}`}
          className="px-1.5 py-0.5 rounded bg-slate-100 font-mono text-[11px] text-sky-800 border border-slate-200"
        >
          {match[9]}
        </code>
      );
    }

    lastIndex = tokenRegex.lastIndex;
  }

  if (lastIndex < line.length) {
    tokens.push(line.slice(lastIndex));
  }

  return tokens;
}

function parseMarkdownBlocks(text) {
  if (!text) return [];
  const rawLines = text.split('\n');
  const blocks = [];
  let i = 0;

  while (i < rawLines.length) {
    const line = rawLines[i];
    const trimmed = line.trim();

    // Markdown table detection: current line has '|' and next line is separator '|---|---|'
    if (trimmed.includes('|') && i + 1 < rawLines.length) {
      const nextTrimmed = rawLines[i + 1].trim();
      const isSep = /^\|?(\s*:?-{2,}:?\s*\|?)+$/.test(nextTrimmed) && nextTrimmed.includes('-');
      if (isSep) {
        const cleanHeaderLine = trimmed.replace(/^\|/, '').replace(/\|$/, '');
        const headers = cleanHeaderLine.split('|').map((s) => s.trim());
        const rows = [];
        i += 2; // skip header and separator lines
        while (i < rawLines.length) {
          const rowLine = rawLines[i].trim();
          if (!rowLine || !rowLine.includes('|')) {
            break;
          }
          const cleanRowLine = rowLine.replace(/^\|/, '').replace(/\|$/, '');
          const cells = cleanRowLine.split('|').map((s) => s.trim());
          rows.push(cells);
          i++;
        }
        blocks.push({
          type: 'table',
          headers,
          rows,
        });
        continue;
      }
    }

    // Markdown horizontal divider rule: ---, ***, ___
    if (/^(?:-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      blocks.push({ type: 'divider' });
      i++;
      continue;
    }

    // Headings: #, ##, ###, ####
    if (/^#{1,4}\s+/.test(trimmed)) {
      const match = trimmed.match(/^(#{1,4})\s+(.*)$/);
      if (match) {
        blocks.push({
          type: 'heading',
          level: match[1].length,
          text: match[2].trim(),
        });
        i++;
        continue;
      }
    }

    // Bullet lists: -, *, •
    if (/^[•\-\*]\s+/.test(trimmed)) {
      blocks.push({
        type: 'bullet',
        text: trimmed.replace(/^[•\-\*]\s+/, '').trim(),
      });
      i++;
      continue;
    }

    // Numbered lists: 1., 2.
    if (/^\d+\.\s+/.test(trimmed)) {
      const match = trimmed.match(/^(\d+)\.\s+(.*)$/);
      if (match) {
        blocks.push({
          type: 'numbered',
          num: match[1],
          text: match[2].trim(),
        });
        i++;
        continue;
      }
    }

    // Empty line
    if (!trimmed) {
      blocks.push({ type: 'empty' });
      i++;
      continue;
    }

    // Normal paragraph line
    blocks.push({ type: 'paragraph', text: line });
    i++;
  }

  return blocks;
}

/**
 * Helper to render message text with hyperlinks for URLs/emails/LinkedIn,
 * bolding for **markdown**, dividers for ---, and full responsive Markdown tables.
 */
function FormattedMessageText({ text }) {
  if (!text) return null;

  const blocks = parseMarkdownBlocks(text);

  return (
    <div className="space-y-1.5 w-full">
      {blocks.map((block, idx) => {
        if (block.type === 'table') {
          return (
            <ModernMarkdownTable
              key={`tbl-${idx}`}
              headers={block.headers}
              rows={block.rows}
            />
          );
        }

        if (block.type === 'divider') {
          return <hr key={idx} className="my-3 border-sky-100" />;
        }

        if (block.type === 'empty') {
          return <div key={idx} className="h-1.5" />;
        }

        if (block.type === 'heading') {
          if (block.level === 1) {
            return (
              <h2 key={idx} className="text-base sm:text-lg font-bold text-slate-900 mt-2 mb-1">
                {renderInlineTokens(block.text, idx)}
              </h2>
            );
          }
          if (block.level === 2) {
            return (
              <h3 key={idx} className="text-sm sm:text-base font-bold text-slate-800 mt-2 mb-1">
                {renderInlineTokens(block.text, idx)}
              </h3>
            );
          }
          return (
            <h4 key={idx} className="text-xs sm:text-sm font-semibold text-sky-900 mt-1.5 mb-0.5">
              {renderInlineTokens(block.text, idx)}
            </h4>
          );
        }

        if (block.type === 'bullet') {
          return (
            <div key={idx} className="flex items-start gap-2 pl-1 py-0.5 text-xs text-slate-700">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-500 mt-1.5 shrink-0" />
              <div className="flex-1 leading-relaxed">{renderInlineTokens(block.text, idx)}</div>
            </div>
          );
        }

        if (block.type === 'numbered') {
          return (
            <div key={idx} className="flex items-start gap-2 pl-1 py-0.5 text-xs text-slate-700">
              <span className="font-semibold text-sky-700 text-xs shrink-0">{block.num}.</span>
              <div className="flex-1 leading-relaxed">{renderInlineTokens(block.text, idx)}</div>
            </div>
          );
        }

        return (
          <div key={idx} className="leading-relaxed text-xs sm:text-[13.5px] text-slate-800">
            {renderInlineTokens(block.text, idx)}
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

function cleanDesignation(raw) {
  if (!raw) return 'Not Available';
  const parts = String(raw)
    .split(/[/;]+/)
    .map((p) => p.trim())
    .filter((p) => {
      if (!p) return false;
      const lower = p.toLowerCase();
      return (
        lower !== 'not publicly available' &&
        lower !== 'publicly not available' &&
        lower !== 'not available publicly' &&
        lower !== 'not available' &&
        lower !== 'not provided' &&
        lower !== 'not mentioned' &&
        lower !== 'n/a' &&
        lower !== 'na' &&
        lower !== 'null' &&
        lower !== 'none' &&
        lower !== '-' &&
        lower !== '--' &&
        lower !== 'nil' &&
        lower !== 'undefined'
      );
    });
  if (parts.length > 0) {
    return parts.join(' / ');
  }
  return 'Not Available';
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
    const trimmedRaw = rawLine.trim();
    if (!trimmedRaw) {
      if (currentRawLines.length > 0) currentRawLines.push('');
      continue;
    }

    // Markdown horizontal divider rule: ---, ***, ___
    if (/^(?:-{3,}|\*{3,}|_{3,})$/.test(trimmedRaw)) {
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

    // Only strip leading bullet points if followed by whitespace (e.g., "- item", "• item", "* item")
    const line = trimmedRaw.replace(/^[•\-\*]\s+/, '').trim();

    if (/^(?:Source File|Sources?)\s*:/i.test(line)) {
      const srcVal = line.replace(/^(?:Source File|Sources?)\s*:\s*/i, '').trim();
      pendingSource = srcVal;
      if (currentCompany) {
        currentCompany.sourceFile = srcVal;
      }
      currentRawLines.push(rawLine);
      continue;
    }
    if (/^(?:Database|Collection)\s*:/i.test(line)) {
      const srcVal = line.trim();
      pendingSource = srcVal;
      if (currentCompany) {
        currentCompany.sourceFile = srcVal;
      }
      currentRawLines.push(rawLine);
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
        currentContact.designation = cleanDesignation(line.replace('Designation:', '').trim());
      } else if (/^(?:LinkedIn URL|LinkedIn|Linkedin)\s*:/i.test(line)) {
        const val = line.replace(/^(?:LinkedIn URL|LinkedIn|Linkedin)\s*:\s*/i, '').trim();
        currentContact.linkedin = val || 'Not Available';
      } else if (/^Contact Number(?:\s*\d+)?\s*:/i.test(line)) {
        const colonIdx = line.indexOf(':');
        const label = line.substring(0, colonIdx).trim();
        const val = line.substring(colonIdx + 1).trim();
        currentContact.numbers.push({ label, val });
      } else if (/^Email(?:\s*\d+)?\s*:/i.test(line)) {
        const colonIdx = line.indexOf(':');
        const label = line.substring(0, colonIdx).trim();
        const val = line.substring(colonIdx + 1).trim();
        currentContact.emails.push({ label, ...parseEmailLink(val) });
      } else if (/^(?:Location|City|State|Address)\s*:/i.test(line)) {
        const colonIdx = line.indexOf(':');
        const val = line.substring(colonIdx + 1).trim();
        if (val && val !== 'Not Available') {
          if (!currentContact.location || currentContact.location === 'Not Available') {
            currentContact.location = val;
          } else if (!currentContact.location.includes(val)) {
            currentContact.location += `, ${val}`;
          }
        }
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

function ExportDropdown({
  companies,
  filename = 'calispec_data',
  label = 'Export',
  className = '',
  direction = 'auto',
  onOpenChange
}) {
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef(null);

  const toggleOpen = (nextState) => {
    setOpen(nextState);
    if (onOpenChange) {
      onOpenChange(nextState);
    }
  };

  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        toggleOpen(false);
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
    toggleOpen(false);
  };

  const isUp = direction === 'up' || (direction === 'auto' && (label.toLowerCase().includes('all') || label.toLowerCase().includes('response')));
  const positionClasses = isUp
    ? 'bottom-full mb-2 right-0 origin-bottom-right'
    : 'top-full mt-2 right-0 origin-top-right';

  return (
    <div className={`relative inline-block text-left ${open ? 'z-50' : 'z-10'} ${className}`} ref={dropdownRef}>
      <button
        type="button"
        onClick={() => toggleOpen(!open)}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all duration-150 cursor-pointer shadow-2xs ${
          open
            ? 'bg-sky-50 text-sky-700 border-sky-300 ring-2 ring-sky-200/50'
            : 'bg-slate-50 hover:bg-sky-50 hover:text-sky-700 border border-slate-200 text-slate-600'
        }`}
        title="Export response options (CSV, Excel, PDF)"
        aria-expanded={open}
      >
        <span className="material-symbols-outlined text-sm text-slate-500">file_download</span>
        <span>{label}</span>
        <span
          className="material-symbols-outlined text-xs text-slate-400 transition-transform duration-200"
          style={{ transform: open ? 'rotate(180deg)' : 'none' }}
        >
          expand_more
        </span>
      </button>

      {open && (
        <div
          className={`absolute ${positionClasses} w-52 bg-white/98 backdrop-blur-md border border-slate-200/90 rounded-xl shadow-2xl z-50 py-1.5 animate-fadeIn`}
          style={{
            boxShadow: '0 12px 30px -4px rgba(15, 23, 42, 0.18), 0 4px 10px -2px rgba(15, 23, 42, 0.08)',
          }}
        >
          <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 flex items-center justify-between">
            <span>Export Format</span>
            <span className="material-symbols-outlined text-xs text-slate-400">download</span>
          </div>

          {/* CSV Option */}
          <button
            type="button"
            onClick={() => handleDownload('csv')}
            className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-sky-50 hover:text-sky-800 flex items-center gap-2.5 transition-colors cursor-pointer group"
          >
            <div className="w-7 h-7 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0 group-hover:bg-emerald-100 transition-colors">
              <span className="material-symbols-outlined text-base">table_view</span>
            </div>
            <div>
              <div className="font-semibold leading-tight text-slate-800 group-hover:text-sky-900">CSV</div>
              <div className="text-[10px] text-slate-400">Comma-separated (.csv)</div>
            </div>
          </button>

          {/* Excel Option */}
          <button
            type="button"
            onClick={() => handleDownload('excel')}
            className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-sky-50 hover:text-sky-800 flex items-center gap-2.5 transition-colors cursor-pointer group"
          >
            <div className="w-7 h-7 rounded-lg bg-emerald-50 text-emerald-700 flex items-center justify-center shrink-0 group-hover:bg-emerald-100 transition-colors">
              <span className="material-symbols-outlined text-base">grid_on</span>
            </div>
            <div>
              <div className="font-semibold leading-tight text-slate-800 group-hover:text-sky-900">Excel</div>
              <div className="text-[10px] text-slate-400">Spreadsheet (.xls)</div>
            </div>
          </button>

          {/* PDF Option */}
          <button
            type="button"
            onClick={() => handleDownload('pdf')}
            className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-sky-50 hover:text-sky-800 flex items-center gap-2.5 transition-colors cursor-pointer group"
          >
            <div className="w-7 h-7 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center shrink-0 group-hover:bg-rose-100 transition-colors">
              <span className="material-symbols-outlined text-base">picture_as_pdf</span>
            </div>
            <div>
              <div className="font-semibold leading-tight text-slate-800 group-hover:text-sky-900">PDF</div>
              <div className="text-[10px] text-slate-400">Document (.pdf)</div>
            </div>
          </button>
        </div>
      )}
    </div>
  );
}

function StrictCompanyCard({ company, index, totalCount, onOpenChange }) {
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
            {/* Source File Badge on every result */}
            {company.sourceFile ? (
              <div className="flex items-center gap-1.5 mt-1.5 text-xs font-semibold text-sky-800 bg-sky-50 border border-sky-200 px-2.5 py-1 rounded-md w-fit shadow-2xs">
                <span className="material-symbols-outlined text-sm text-sky-600">
                  {company.sourceFile.includes('Collection:') || company.sourceFile.includes('Database:') ? 'database' : 'description'}
                </span>
                <span>
                  {company.sourceFile.startsWith('Source:') || company.sourceFile.startsWith('Source File:')
                    ? company.sourceFile
                    : `Source: ${company.sourceFile}`}
                </span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 mt-1.5 text-xs font-semibold text-slate-600 bg-slate-50 border border-slate-200 px-2.5 py-1 rounded-md w-fit">
                <span className="material-symbols-outlined text-sm text-slate-500">description</span>
                <span>Source: Database Records</span>
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
            direction="down"
            onOpenChange={onOpenChange}
          />
        </div>
      </div>

      {/* Contact Persons */}
      <div className="mt-4 space-y-4">
        {company.contacts.map((contact, cIdx) => {
          // Parse structured address, city, state from contact fields or location string
          const rawLoc = contact.location || '';
          const locParts =
            rawLoc && rawLoc.includes('/')
              ? rawLoc.split('/').map((p) => p.trim()).filter(Boolean)
              : rawLoc && rawLoc.includes(';')
              ? rawLoc.split(';').map((p) => p.trim()).filter(Boolean)
              : [];
          const dispAddr = contact.address || (locParts.length >= 3 ? locParts[0] : null);
          const dispCity =
            contact.city ||
            (locParts.length >= 3 ? locParts[1] : locParts.length === 2 ? locParts[0] : null);
          const dispState =
            contact.state ||
            (locParts.length >= 3
              ? locParts.slice(2).join(', ')
              : locParts.length === 2
              ? locParts[1]
              : null);

          return (
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
                    {contact.name || 'Not Available'}
                  </span>
                </div>
              </div>

              {/* Details Grid: Designation, Location, Emails, Contact Numbers, LinkedIn */}
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 pt-1">
                {/* Designation */}
                <div className="bg-white rounded-lg p-3 border border-slate-200/80 shadow-2xs space-y-1.5 min-w-0">
                  <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    <span className="material-symbols-outlined text-sm text-sky-600">badge</span>
                    <span>Designation</span>
                  </div>
                  <div className="space-y-1">
                    <div className="text-xs font-semibold text-slate-800">
                      {cleanDesignation(contact.designation) !== 'Not Available' ? (
                        cleanDesignation(contact.designation)
                      ) : (
                        <span className="text-slate-400 font-normal">Not Available</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Location (Structured: Address / City / State) */}
                <div className="bg-white rounded-lg p-3 border border-slate-200/80 shadow-2xs space-y-1.5 min-w-0">
                  <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    <span className="material-symbols-outlined text-sm text-sky-600">location_on</span>
                    <span>Location</span>
                  </div>
                  <div className="space-y-1.5 text-xs">
                    {dispAddr && dispAddr !== 'Not Available' ? (
                      <div>
                        <span className="text-[10px] text-slate-400 block font-mono">Address:</span>
                        <span className="font-semibold text-slate-800 break-words">{dispAddr}</span>
                      </div>
                    ) : null}
                    {dispCity && dispCity !== 'Not Available' ? (
                      <div>
                        <span className="text-[10px] text-slate-400 block font-mono">City:</span>
                        <span className="font-semibold text-slate-800">{dispCity}</span>
                      </div>
                    ) : null}
                    {dispState && dispState !== 'Not Available' ? (
                      <div>
                        <span className="text-[10px] text-slate-400 block font-mono">State:</span>
                        <span className="font-semibold text-slate-800">{dispState}</span>
                      </div>
                    ) : null}
                    {!dispAddr && !dispCity && !dispState && (
                      <div>
                        {contact.location &&
                        contact.location !== 'Not Available' &&
                        contact.location.toLowerCase() !== 'not available' ? (
                          <span className="font-semibold text-slate-800 break-words">
                            {contact.location}
                          </span>
                        ) : (
                          <span className="text-slate-400 font-normal">Not Available</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>

              {/* Email Addresses: Email 1 and Email 2 if multiple */}
              <div className="bg-white rounded-lg p-3 border border-slate-200/80 shadow-2xs space-y-1.5 min-w-0">
                <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  <span className="material-symbols-outlined text-sm text-sky-600">mail</span>
                  <span>Email Addresses</span>
                </div>
                <div className="space-y-1.5">
                  {contact.emails && contact.emails.length > 0 ? (
                    contact.emails.map((em, eIdx) => {
                      const label = contact.emails.length > 1 ? `Email ${eIdx + 1}` : 'Email';
                      return (
                        <div key={eIdx} className="text-xs font-medium text-slate-700 break-all">
                          <span className="text-slate-400 text-[10px] block font-mono">{label}:</span>
                          {em.href && em.text !== 'Not Available' ? (
                            <a
                              href={em.href}
                              className="text-sky-600 hover:text-sky-800 underline font-semibold transition-colors"
                            >
                              {em.text}
                            </a>
                          ) : (
                            <span className="text-slate-400">{em.text || 'Not Available'}</span>
                          )}
                        </div>
                      );
                    })
                  ) : (
                    <div className="text-xs text-slate-400">Not Available</div>
                  )}
                </div>
              </div>

              {/* Contact Numbers: Contact Number 1 and Contact Number 2 if multiple */}
              <div className="bg-white rounded-lg p-3 border border-slate-200/80 shadow-2xs space-y-1.5 min-w-0">
                <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  <span className="material-symbols-outlined text-sm text-sky-600">call</span>
                  <span>Contact Numbers</span>
                </div>
                <div className="space-y-1.5">
                  {contact.numbers && contact.numbers.length > 0 ? (
                    contact.numbers.map((num, nIdx) => {
                      const label = contact.numbers.length > 1 ? `Contact Number ${nIdx + 1}` : 'Contact Number';
                      const val = num.val || num;
                      return (
                        <div key={nIdx} className="text-xs font-medium text-slate-700">
                          <span className="text-slate-400 text-[10px] block font-mono">{label}:</span>
                          {val && val !== 'Not Available' ? (
                            <a
                              href={`tel:${String(val).replace(/\s+/g, '')}`}
                              className="text-sky-700 hover:text-sky-900 font-semibold transition-colors"
                            >
                              {val}
                            </a>
                          ) : (
                            <span className="text-slate-400">Not Available</span>
                          )}
                        </div>
                      );
                    })
                  ) : (
                    <div className="text-xs text-slate-400">Not Available</div>
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
                  !['not available', 'no data available', 'not_available', 'none', 'null', 'nan', 'n/a', 'na', '-', '--', 'undefined'].includes(
                    String(contact.linkedin).trim().toLowerCase()
                  ) &&
                  !String(contact.linkedin).toLowerCase().includes('no data available') &&
                  !String(contact.linkedin).toLowerCase().includes('not available') ? (
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
                      <span className="text-slate-400">{contact.linkedin || 'No data available'}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function ChatMessage({ message, onInspect, onEdit, onRunSearch }) {
  const isUser = message.role === 'user';
  const now = new Date();
  const timeStr = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
  const [hasOpenDropdown, setHasOpenDropdown] = useState(false);

  // 1. User Message Row with Copy and Edit controls underneath
  if (isUser) {
    const [copied, setCopied] = useState(false);

    const handleCopy = () => {
      navigator.clipboard?.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    };

    return (
      <div className="flex flex-col items-end w-full group animate-fadeIn relative z-0">
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

  // Build parsed companies list with 100% accurate source file per company
  let parsedCompanies = [];

  if (message.data && Array.isArray(message.data) && message.data.length > 0) {
    const seenExactSignatures = new Set();
    const groupMap = new Map();

    message.data.forEach((r) => {
      const cName = r.company || r['Company Name'] || r.company_name || 'Company';
      const pName = r.person || r['Person Name'] || r['Contact Person'] || r['name'] || 'No data available';
      const pDesig = r.designation || r['Designation'] || r['Role'] || 'No data available';
      const pLinkedin = r.linkedin || r['LinkedIn'] || r['LinkedIn URL'] || 'No data available';
      const srcFile = r.source_file || r['Source File'] || r.dataset_name || r.dataset || 'Database';

      const rawNums = [r.phone, r.phone_2, r['Contact Number'], r['Phone 2'], r['Mobile'], r['Contact Number 1'], r['Contact Number 2']];
      const validNums = [];
      const seenNums = new Set();
      for (const n of rawNums) {
        if (n && n !== 'No data available' && n !== 'Not Available' && !seenNums.has(n)) {
          seenNums.add(n);
          validNums.push(n);
        }
      }

      const rawEmails = [r.email, r.email_2, r['Email 1'], r['Email 2'], r['Email'], r['Email Address']];
      const validEmails = [];
      const seenEmails = new Set();
      for (const e of rawEmails) {
        if (e && e !== 'No data available' && e !== 'Not Available' && !seenEmails.has(e.toLowerCase())) {
          seenEmails.add(e.toLowerCase());
          validEmails.push(e);
        }
      }

      const addrVal = r.address && r.address !== 'No data available' ? r.address : '';
      const cityVal = r.city && r.city !== 'No data available' ? r.city : '';
      const stateVal = r.state && r.state !== 'No data available' ? r.state : '';
      const locString = [addrVal, cityVal, stateVal].filter(Boolean).join(', ') || 'No data available';

      // Exact duplicate check
      const exactSig = `${cName.toLowerCase()}::${locString.toLowerCase()}::${pName.toLowerCase()}::${pDesig.toLowerCase()}::${pLinkedin.toLowerCase()}::${validEmails.join(',')}::${validNums.join(',')}::${srcFile.toLowerCase()}`;
      if (seenExactSignatures.has(exactSig)) {
        return;
      }
      seenExactSignatures.add(exactSig);

      // Group key: same company name AND exact same location
      const groupKey = `${cName.toLowerCase().trim()}::${locString.toLowerCase().trim()}::${srcFile.toLowerCase().trim()}`;

      const contactObj = {
        title: 'Contact Person 1',
        name: pName,
        designation: pDesig,
        linkedin: pLinkedin,
        numbers: validNums.length > 0
          ? validNums.map((p, pIdx) => ({ label: `Contact Number ${pIdx + 1}`, val: p }))
          : [{ label: 'Contact Number 1', val: 'No data available' }],
        emails: validEmails.length > 0
          ? validEmails.map((e, eIdx) => ({ label: `Email ${eIdx + 1}`, text: e, href: `mailto:${e}` }))
          : [{ label: 'Email 1', text: 'No data available', href: null }],
        location: locString,
        locations: [
          addrVal && { label: 'Address', val: addrVal },
          cityVal && { label: 'City', val: cityVal },
          stateVal && { label: 'State', val: stateVal }
        ].filter(Boolean)
      };

      if (groupMap.has(groupKey)) {
        const existingComp = groupMap.get(groupKey);
        contactObj.title = `Contact Person ${existingComp.contacts.length + 1}`;
        existingComp.contacts.push(contactObj);
      } else {
        const newComp = {
          companyName: cName,
          sourceFile: srcFile,
          rawText: text,
          contacts: [contactObj]
        };
        groupMap.set(groupKey, newComp);
        parsedCompanies.push(newComp);
      }
    });
  } else if (text) {
    parsedCompanies = parseStrictCompanyText(text);
  }

  return (
    <div className={`flex flex-col items-start w-full animate-fadeIn relative ${hasOpenDropdown ? 'z-40' : 'z-10'}`}>
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
            /* Render Previous Structured UI Cards for Companies (StrictCompanyCard) */
            <div className="space-y-4 w-full">

              {parsedCompanies.map((comp, idx) => (
                <StrictCompanyCard
                  key={idx}
                  company={comp}
                  index={idx}
                  totalCount={parsedCompanies.length}
                  onOpenChange={setHasOpenDropdown}
                />
              ))}

              {/* If some companies were not found in multi-company search */}
              {message.not_found && message.not_found.length > 0 && (
                <div className="p-4 rounded-xl bg-amber-50/90 border border-amber-200/80 text-xs text-amber-900 space-y-2">
                  <p className="font-semibold">
                    No records found for: {message.not_found.map(n => `"${n}"`).join(', ')}
                  </p>
                  {message.suggestions && Object.keys(message.suggestions).length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 pt-1">
                      <span className="text-slate-500 font-medium">Suggestions:</span>
                      {Object.entries(message.suggestions).map(([k, sugs]) =>
                        sugs.map((sug, sIdx) => (
                          <button
                            key={`${k}-${sIdx}`}
                            type="button"
                            onClick={() => onRunSearch?.(sug)}
                            className="px-2.5 py-0.5 rounded-full bg-white hover:bg-sky-50 text-sky-700 border border-sky-200 font-semibold shadow-2xs cursor-pointer"
                          >
                            {sug}
                          </button>
                        ))
                      )}
                    </div>
                  )}
                </div>
              )}

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
                    direction="up"
                    onOpenChange={setHasOpenDropdown}
                  />
                </div>
              </div>
            </div>
          ) : message.not_found && message.not_found.length > 0 ? (
            /* Render Not Found Banner if no companies parsed */
            <div className="bg-gradient-to-r from-amber-50/90 to-sky-50/60 border border-amber-200/80 rounded-2xl p-5 sm:p-6 shadow-sm space-y-4">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center shrink-0 border border-amber-300/60 shadow-2xs">
                  <span className="material-symbols-outlined text-xl">travel_explore</span>
                </div>
                <div className="space-y-1">
                  <h4 className="text-sm sm:text-base font-bold text-slate-900">
                    {message.not_found.length === 1
                      ? `No records found for "${message.not_found[0]}"`
                      : `No records found for ${message.not_found.map(n => `"${n}"`).join(', ')}`}
                  </h4>
                  <p className="text-xs text-slate-600">
                    The requested company or contact was not found in the active datasets.
                  </p>
                </div>
              </div>

              {message.not_found.some(n => (message.suggestions?.[n] || []).length > 0) && (
                <div className="pt-2 border-t border-amber-200/60 space-y-2">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-slate-800">
                    <span className="material-symbols-outlined text-sm text-sky-600">lightbulb</span>
                    <span>Did you mean one of these companies?</span>
                  </div>
                  <div className="flex flex-wrap gap-2 pt-1">
                    {message.not_found.map(name => {
                      const sugs = message.suggestions?.[name] || [];
                      return sugs.map((sug, sIdx) => (
                        <button
                          key={`${name}-${sIdx}`}
                          type="button"
                          onClick={() => onRunSearch?.(sug)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white hover:bg-sky-50 text-sky-700 hover:text-sky-900 border border-sky-300 font-semibold text-xs shadow-2xs hover:shadow-xs hover:scale-102 transition-all cursor-pointer"
                        >
                          <span className="material-symbols-outlined text-xs text-sky-600">apartment</span>
                          <span>{sug}</span>
                        </button>
                      ));
                    })}
                  </div>
                </div>
              )}
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
                  direction="up"
                  onOpenChange={setHasOpenDropdown}
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



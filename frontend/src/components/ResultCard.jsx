import React, { useState } from 'react';

const CUSTOM_LABELS = {
  company_name: 'Company Name',
  contact_person: 'Contact Person',
  designation: 'Designation',
  mobile_no: 'Mobile No.',
  landline_telephone: 'Landline / Telephone',
  landline_other_no: 'Landline / Other No.',
  telephone_1: 'Telephone 1',
  telephone_2: 'Telephone 2',
  email: 'Email',
  email_1: 'Email 1',
  email_2: 'Email 2',
  address: 'Address',
  city: 'City',
  state: 'State',
  pin: 'PIN',
  pincode: 'PIN Code',
  group: 'Group',
  records_merged: 'Records Merged',
  review_required: 'Review Required',
  sources: 'Sources',
  remarks: 'Remarks',
  source_collection: 'Collection',
  employee_id: 'Employee ID',
  employee_name: 'Employee Name',
  customer_id: 'Customer ID',
  customer_name: 'Customer Name',
  department: 'Department',
  salary: 'Salary',
  joining_date: 'Joining Date',
  purchase_amount: 'Purchase Amount',
};

/**
 * Validates whether a value is populated and meaningful.
 */
function isValidValue(val) {
  if (val === null || val === undefined) return false;
  if (typeof val === 'string') {
    const trimmed = val.trim().toLowerCase();
    if (!trimmed || trimmed === 'none' || trimmed === 'null' || trimmed === 'nan' || trimmed === 'n/a' || trimmed === 'na' || trimmed === '-' || trimmed === 'undefined') {
      return false;
    }
  }
  if (Array.isArray(val)) {
    return val.length > 0;
  }
  return true;
}

/**
 * Converts field key into readable, cleanly formatted Title Case label.
 */
function formatFieldLabel(key) {
  if (!key) return '';
  const lower = key.toLowerCase().replace(/[\s-]+/g, '_');
  if (CUSTOM_LABELS[lower]) {
    return CUSTOM_LABELS[lower];
  }
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function getInitials(name) {
  if (!name) return 'DB';
  const parts = String(name).trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return parts[0].substring(0, 2).toUpperCase();
}

function getAvatarColor(name) {
  const colors = [
    { bg: '#e0e7ff', text: '#3730a3' },
    { bg: '#a7f3d0', text: '#065f46' },
    { bg: '#fed7aa', text: '#9a3412' },
    { bg: '#fbcfe8', text: '#9d174d' },
    { bg: '#c7d2fe', text: '#4338ca' },
    { bg: '#bae6fd', text: '#0369a1' },
    { bg: '#e2e8f0', text: '#334155' }
  ];
  let hash = 0;
  const str = String(name || '');
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
}

export default function ResultCard({ record, index, onInspect }) {
  const [copied, setCopied] = useState(false);

  if (!record || typeof record !== 'object') {
    return null;
  }

  // Find primary heading dynamically across diverse dataset schemas
  const findFieldValue = (keys) => {
    for (const k of keys) {
      if (k in record && isValidValue(record[k])) return record[k];
      // Case-insensitive check
      const foundKey = Object.keys(record).find(
        (rk) => rk.toLowerCase().replace(/[\s_-]/g, '') === k.toLowerCase().replace(/[\s_-]/g, '')
      );
      if (foundKey && isValidValue(record[foundKey])) return record[foundKey];
    }
    return null;
  };

  const primaryTitle =
    findFieldValue([
      'company_name',
      'company',
      'Company Name',
      'employee_name',
      'Employee Name',
      'customer_name',
      'Customer Name',
      'name',
      'Name',
      'title',
      'item_name'
    ]) || `Record #${record.id ? String(record.id).substring(0, 8) : index + 1}`;

  const personName =
    findFieldValue([
      'contact_person',
      'Contact Person',
      'contact',
      'person_name',
      'person',
      'manager',
      'representative'
    ]) || null;

  const designation =
    findFieldValue([
      'designation',
      'Designation',
      'role',
      'Role',
      'title',
      'department',
      'Department',
      'job_title'
    ]) || null;

  const datasetBadge = record.dataset || record.dataset_name || record.source_collection || 'dataset_records';
  const docId = record.id ? (record.id.startsWith('OID_') ? record.id : `OID_${record.id}`) : `OID_rec_${index + 1}`;

  // Build list of all visible fields excluding internal IDs, normalized search keys, and raw objects
  const excludedKeys = new Set([
    'id', '_id', 'raw_data', 'data', 'normalized_data', 'source_fields',
    'search_text', 'embedding', 'vector_score', 'similarity_score', 'retrieval_score', 'chunk_text', 'internal_id',
    'norm_company_name', 'norm_person_name', 'norm_designation', 'norm_department',
    'norm_state', 'norm_city', 'norm_country', 'norm_location',
    '_norm_company_name', '_norm_person_name', '_norm_designation', '_norm_department',
    '_norm_state', '_norm_city', '_norm_country', '_norm_location',
    'dataset', 'dataset_id', 'dataset_name', 'source_collection', '_collection',
    'database_source', 'database', 'source_file', 'source_sheet', 'source_row', 'record_index'
  ]);

  // Only display actual original source fields; never display [object Object] or internal fields
  const allKeys = Object.keys(record).filter(
    (k) => !excludedKeys.has(k.toLowerCase()) && !k.startsWith('_') && typeof record[k] !== 'object' && isValidValue(record[k])
  );

  const handleCopy = () => {
    const lines = [`Title: ${primaryTitle}`];
    if (personName) lines.push(`Contact: ${personName}`);
    if (designation) lines.push(`Role / Dept: ${designation}`);
    if (datasetBadge) lines.push(`Dataset: ${datasetBadge}`);
    
    allKeys.forEach((k) => {
      lines.push(`${formatFieldLabel(k)}: ${record[k]}`);
    });

    navigator.clipboard.writeText(lines.join('\n')).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const avatar = getAvatarColor(personName || primaryTitle);
  const initials = getInitials(personName || primaryTitle);

  return (
    <div className="atlas-result-card">
      {/* Top Header */}
      <div className="atlas-card-header">
        <div className="atlas-header-left">
          <div className="atlas-company-title">
            <span className="atlas-active-dot" />
            <span className="company-text">{primaryTitle}</span>
          </div>
          <div className="atlas-id-tag">_id: {docId}</div>
        </div>

        <div className="atlas-header-right">
          <span className="atlas-indexed-badge" title="Source Dataset">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            {datasetBadge}
          </span>
          <button
            className="atlas-btn-copy"
            onClick={handleCopy}
            title={copied ? "Copied to clipboard!" : "Copy record details"}
            type="button"
          >
            {copied ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Person / Role Highlight Box if present */}
      {(personName || designation) && (
        <div className="atlas-person-box">
          <div className="atlas-person-left">
            <div
              className="atlas-avatar-circle"
              style={{ backgroundColor: avatar.bg, color: avatar.text }}
            >
              {initials}
            </div>
            <div>
              {personName && <div className="atlas-person-name">{personName}</div>}
              {designation && <div className="atlas-person-role">{designation}</div>}
            </div>
          </div>
          <div className="atlas-vector-badge" style={{ background: '#f0fdf4', color: '#166534', border: '1px solid #bbf7d0' }}>
            MongoDB Source
          </div>
        </div>
      {/* Source Metadata Header (Requirements 3 & 10) */}
      {(record.source_file || record.source_row != null || record.source_collection) && (
        <div style={{ fontSize: '11px', fontFamily: 'monospace', padding: '8px 14px', background: '#0f172a', borderBottom: '1px solid rgba(148, 163, 184, 0.15)', color: '#94a3b8', lineHeight: '1.4' }}>
          <div><strong style={{ color: '#cbd5e1' }}>Dataset:</strong> {record.dataset || record.source_collection || 'dataset_records'} &bull; <strong style={{ color: '#cbd5e1' }}>Database:</strong> {record.database || record.database_source || 'MongoDB Atlas'}</div>
          {record.source_file && (
            <div><strong style={{ color: '#cbd5e1' }}>Source File:</strong> <span style={{ color: '#34d399' }}>{record.source_file}</span>{record.source_row != null && record.source_row !== 'Not Available' ? ` (Row: ${record.source_row})` : ''}</div>
          )}
        </div>
      )}

      {/* Dynamic Populated Fields */}
      {allKeys.length > 0 && (
        <div className="atlas-fields-list">
          {allKeys.map((key) => {
            const val = record[key];
            const label = formatFieldLabel(key);

            return (
              <div key={key} className="atlas-field-row">
                <div className="atlas-field-key">
                  {getFieldIcon(key)}
                  <span>{label}</span>
                </div>
                <div className="atlas-field-val">
                  {renderFormattedValue(key, val)}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Action Footer: Inspect Document Button */}
      <div className="atlas-card-footer">
        <button
          className="atlas-btn-inspect"
          type="button"
          onClick={() => onInspect ? onInspect(record) : handleCopy()}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="16 18 22 12 16 6" />
            <polyline points="8 6 2 12 8 18" />
          </svg>
          Inspect Raw Document
        </button>
      </div>
    </div>
  );
}

/**
 * Returns contextual icon for each column header.
 */
function getFieldIcon(key) {
  const k = key.toLowerCase();

  if (k.includes('contact') || k.includes('person') || k.includes('employee') || k.includes('customer') || k.includes('user') || k.includes('client')) {
    return (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
        <circle cx="12" cy="7" r="4"></circle>
      </svg>
    );
  }

  if (k.includes('designation') || k.includes('title') || k.includes('role') || k.includes('dept') || k.includes('department')) {
    return (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path>
        <rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect>
      </svg>
    );
  }

  if (k.includes('mobile')) {
    return (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="5" y="2" width="14" height="20" rx="2" ry="2"></rect>
        <line x1="12" y1="18" x2="12.01" y2="18"></line>
      </svg>
    );
  }

  if (k.includes('telephone') || k.includes('phone') || k.includes('landline') || k.includes('tel')) {
    return (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"></path>
      </svg>
    );
  }

  if (k.includes('email') || k.includes('mail')) {
    return (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path>
        <polyline points="22,6 12,13 2,6"></polyline>
      </svg>
    );
  }

  if (k.includes('city') || k.includes('state') || k.includes('address') || k.includes('location') || k.includes('country')) {
    return (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
        <circle cx="12" cy="10" r="3"></circle>
      </svg>
    );
  }

  if (k.includes('pin') || k.includes('zip') || k.includes('postal')) {
    return (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="4" y1="9" x2="20" y2="9"></line>
        <line x1="4" y1="15" x2="20" y2="15"></line>
        <line x1="10" y1="3" x2="8" y2="21"></line>
        <line x1="16" y1="3" x2="14" y2="21"></line>
      </svg>
    );
  }

  if (k.includes('salary') || k.includes('amount') || k.includes('price') || k.includes('revenue') || k.includes('cost') || k.includes('fee')) {
    return (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="12" y1="1" x2="12" y2="23"></line>
        <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
      </svg>
    );
  }

  if (k.includes('id') || k.includes('code') || k.includes('sku') || k.includes('number')) {
    return (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <line x1="4" y1="9" x2="20" y2="9"></line>
        <line x1="4" y1="15" x2="20" y2="15"></line>
        <line x1="10" y1="3" x2="8" y2="21"></line>
        <line x1="16" y1="3" x2="14" y2="21"></line>
      </svg>
    );
  }

  if (k.includes('date') || k.includes('time') || k.includes('year') || k.includes('created')) {
    return (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
        <line x1="16" y1="2" x2="16" y2="6"></line>
        <line x1="8" y1="2" x2="8" y2="6"></line>
        <line x1="3" y1="10" x2="21" y2="10"></line>
      </svg>
    );
  }

  // Default Icon
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="2"></circle>
    </svg>
  );
}

/**
 * Formats URLs as clickable links, phone/mobile numbers as tel: links, emails as mailto:.
 */
function renderFormattedValue(key, val) {
  if (Array.isArray(val)) {
    return val.join(', ');
  }
  if (typeof val === 'boolean') {
    return val ? 'Yes' : 'No';
  }
  if (val === null || val === undefined) {
    return <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>Not available</span>;
  }

  const k = key.toLowerCase();
  const strVal = String(val);

  if ((k.includes('email') || k.includes('mail')) && strVal.includes('@')) {
    return <a href={`mailto:${strVal}`}>{strVal}</a>;
  }
  if (k.includes('phone') || k.includes('mobile') || k.includes('telephone') || k.includes('landline') || k.includes('tel')) {
    const cleanTel = strVal.replace(/[^\d+]/g, '');
    return <a href={`tel:${cleanTel}`}>{strVal}</a>;
  }
  if (k.includes('website') || k.includes('url') || (strVal.startsWith('http') || (strVal.includes('.') && !strVal.includes(' ')))) {
    if (strVal.startsWith('http://') || strVal.startsWith('https://')) {
      return <a href={strVal} target="_blank" rel="noopener noreferrer">{strVal}</a>;
    }
  }

  return strVal;
}

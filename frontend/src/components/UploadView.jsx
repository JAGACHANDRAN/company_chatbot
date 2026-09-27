import React, { useState } from 'react';

const SAMPLE_PREVIEW_DATA = [
  { company: 'ABC Automotive', person: 'Marcus Sterling', role: 'VP Supply Chain', contact: 'in/m-sterling', email: 'm.sterling@abcauto.com' },
  { company: 'TechNova Systems', person: 'Aria Chen', role: 'Principal Data Architect', contact: 'in/ariachen-ai', email: 'aria@technova.io' },
  { company: 'Apex Industrial', person: 'Devon Brooks', role: 'Director of Logistics', contact: 'in/dbrooks-apex', email: 'dbrooks@apexind.com' },
  { company: 'Vertex Solutions', person: 'Elena Rostova', role: 'Head of Infrastructure', contact: 'in/erostova-dev', email: 'elena@vertexsol.com' },
  { company: 'Kinetics Global', person: 'Tariq Mansoor', role: 'Chief Security Officer', contact: 'in/tmansoor-sec', email: 'tariq@kinetics.global' },
  { company: 'OmniCloud AI', person: 'Sarah Lindqvist', role: 'Data Operations Lead', contact: 'in/slindqvist', email: 'sarah@omnicloud.ai' },
  { company: 'Helix Biotech', person: 'Dr. Julian Vance', role: 'Research Director', contact: 'in/jvance-helix', email: 'julian@helixbio.org' },
  { company: 'Beacon Robotics', person: 'Chloe Moreau', role: 'Hardware Eng Manager', contact: 'in/cmoreau-bot', email: 'chloe@beaconrobotics.com' },
];

export default function UploadView({ onSwitchToData }) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState({
    name: 'employee_data.xlsx',
    records: 5240,
    columns: 12,
    size: '4.8 MB',
    ready: true,
  });
  const [previewFilter, setPreviewFilter] = useState('');
  const [imported, setImported] = useState(false);

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
      const file = e.dataTransfer.files[0];
      setSelectedFile({
        name: file.name,
        records: Math.floor(Math.random() * 4000) + 1200,
        columns: 12,
        size: `${(file.size / (1024 * 1024)).toFixed(1)} MB`,
        ready: true,
      });
    }
  };

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile({
        name: file.name,
        records: 5240,
        columns: 12,
        size: `${(file.size / (1024 * 1024)).toFixed(1)} MB`,
        ready: true,
      });
    }
  };

  const handleImport = () => {
    setImported(true);
    setTimeout(() => {
      if (onSwitchToData) onSwitchToData();
    }, 1500);
  };

  const filteredPreview = SAMPLE_PREVIEW_DATA.filter(
    (row) =>
      row.company.toLowerCase().includes(previewFilter.toLowerCase()) ||
      row.person.toLowerCase().includes(previewFilter.toLowerCase()) ||
      row.role.toLowerCase().includes(previewFilter.toLowerCase())
  );

  return (
    <div className="atlas-upload-view">
      {/* Title */}
      <div className="atlas-view-header">
        <div className="atlas-upload-title-wrap">
          <span className="atlas-upload-icon-box">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="12" y1="18" x2="12" y2="12"/>
              <line x1="9" y1="15" x2="12" y2="12"/>
              <line x1="15" y1="15" x2="12" y2="12"/>
            </svg>
          </span>
          <div>
            <h1 className="atlas-page-title">Upload Your Data</h1>
            <p className="atlas-page-subtitle">
              Upload an Excel file to store and search your data using AI.
            </p>
          </div>
        </div>
      </div>

      {/* Drag & Drop Box (Image 1 style) */}
      <div
        className={`atlas-drop-zone ${dragActive ? 'drag-active' : ''}`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <div className="atlas-drop-icons">
          <div className="atlas-drop-icon-green">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <line x1="3" y1="9" x2="21" y2="9"/>
              <line x1="9" y1="21" x2="9" y2="9"/>
            </svg>
          </div>
          <div className="atlas-drop-icon-blue">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>
            </svg>
          </div>
        </div>

        <div className="atlas-drop-heading">Drag & Drop your Excel file here</div>
        <div className="atlas-drop-subtext">
          or browse from your computer (.xlsx, .xls up to 50MB)
        </div>

        <label className="atlas-choose-btn">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
          Choose Excel File
          <input type="file" accept=".xlsx,.xls,.csv" onChange={handleFileInput} style={{ display: 'none' }} />
        </label>
      </div>

      {/* Stepper Pipeline (Image 1 style) */}
      <div className="atlas-pipeline-card">
        <div className="atlas-pipeline-top">
          <span className="atlas-pipeline-title">PIPELINE STATE</span>
          <span className="atlas-pipeline-step">Step 2 of 4 Active</span>
        </div>

        <div className="atlas-stepper-row">
          <div className="atlas-step-item done">
            <div className="atlas-step-circle">✓</div>
            <span className="atlas-step-text">Excel Uploaded</span>
          </div>
          <div className="atlas-step-line active" />
          <div className="atlas-step-item active">
            <div className="atlas-step-circle">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
            </div>
            <span className="atlas-step-text active">Validating Schema</span>
          </div>
          <div className="atlas-step-line" />
          <div className="atlas-step-item">
            <div className="atlas-step-circle">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <ellipse cx="12" cy="5" rx="9" ry="3"/>
                <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
                <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
              </svg>
            </div>
            <span className="atlas-step-text">Mongo Sync</span>
          </div>
          <div className="atlas-step-line" />
          <div className="atlas-step-item">
            <div className="atlas-step-circle">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a4 4 0 0 1 4 4v2a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z"/>
                <path d="M6 10v1a6 6 0 0 0 12 0v-1"/>
              </svg>
            </div>
            <span className="atlas-step-text">AI Index Ready</span>
          </div>
        </div>
      </div>

      {/* Selected File Card */}
      {selectedFile && (
        <div className="atlas-file-card">
          <div className="atlas-file-top">
            <div className="atlas-file-meta">
              <div className="atlas-file-icon">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                </svg>
              </div>
              <div>
                <div className="atlas-file-name">{selectedFile.name}</div>
                <div className="atlas-file-desc">Validated spreadsheet document</div>
              </div>
            </div>

            <span className="atlas-ready-pill">
              <span className="atlas-active-dot" /> Ready to Import
            </span>
          </div>

          <div className="atlas-metrics-grid" style={{ marginTop: '1rem', background: '#f8fafc' }}>
            <div className="atlas-metric-box">
              <div className="atlas-metric-title">RECORDS</div>
              <div className="atlas-metric-num">{selectedFile.records.toLocaleString()}</div>
            </div>
            <div className="atlas-metric-box">
              <div className="atlas-metric-title">COLUMNS</div>
              <div className="atlas-metric-num">{selectedFile.columns}</div>
            </div>
            <div className="atlas-metric-box">
              <div className="atlas-metric-title">SIZE</div>
              <div className="atlas-metric-num">{selectedFile.size}</div>
            </div>
          </div>

          <button className="atlas-btn-import" onClick={handleImport} disabled={imported}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/>
            </svg>
            {imported ? '✓ Synchronizing with MongoDB Cloud...' : 'Import to MongoDB'}
          </button>
        </div>
      )}

      {/* Data Preview Section (Image 1 style) */}
      <div className="atlas-preview-card">
        <div className="atlas-preview-header">
          <div>
            <div className="atlas-preview-title">Data Preview</div>
            <div className="atlas-preview-sub">Showing 8 of 5,240 records</div>
          </div>
          <span className="atlas-bson-tag">Live BSON Sample</span>
        </div>

        <div className="atlas-preview-search">
          <div className="atlas-search-input-wrap">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8"/>
              <line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input
              type="text"
              className="atlas-input-field"
              placeholder="Search columns or entities..."
              value={previewFilter}
              onChange={(e) => setPreviewFilter(e.target.value)}
            />
          </div>
          <button type="button" className="atlas-btn-filter-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="4" y1="6" x2="20" y2="6"/>
              <line x1="7" y1="12" x2="17" y2="12"/>
              <line x1="10" y1="18" x2="14" y2="18"/>
            </svg>
          </button>
        </div>

        <div className="atlas-table-wrapper">
          <table className="atlas-preview-table">
            <thead>
              <tr>
                <th>COMPANY NAME</th>
                <th>PERSON NAME</th>
                <th>DESIGNATION</th>
                <th>LINKEDIN / CONTACT</th>
              </tr>
            </thead>
            <tbody>
              {filteredPreview.map((row, i) => (
                <tr key={i}>
                  <td style={{ fontWeight: 600, color: '#0f172a' }}>{row.company}</td>
                  <td>{row.person}</td>
                  <td>{row.role}</td>
                  <td style={{ color: '#2563eb', fontFamily: 'JetBrains Mono, monospace' }}>{row.contact}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Validation banner */}
        <div className="atlas-validation-alert">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          <span>
            Data validated with <strong>0 schema conflicts</strong>. Ready for MongoDB indexing across all 6 collections.
          </span>
        </div>
      </div>
    </div>
  );
}

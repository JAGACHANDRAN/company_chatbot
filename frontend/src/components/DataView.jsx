import React, { useState, useEffect } from 'react';
import ResultCard from './ResultCard';
import { sendDirectSearch } from '../api';

export default function DataView({ collections, health, onInspect }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCol, setSelectedCol] = useState('all');
  const [viewMode, setViewMode] = useState('cards'); // 'cards' | 'grid'
  const [loading, setLoading] = useState(false);
  const [records, setRecords] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(6);

  // Active filter chips state
  const [activeFilters, setActiveFilters] = useState([
    { id: 'f1', label: 'status: indexed' },
    { id: 'f2', label: 'source: calispec' },
  ]);

  // Load records on mount or filter change
  useEffect(() => {
    loadData(searchTerm, selectedCol);
  }, [selectedCol]);

  const loadData = async (query = '', colName = 'all') => {
    setLoading(true);
    try {
      const q = query.trim() || 'company';
      const res = await sendDirectSearch(q);
      let list = Array.isArray(res?.data) ? res.data : [];

      if (colName !== 'all') {
        list = list.filter((r) => r.source_collection?.toLowerCase() === colName.toLowerCase());
      }

      setRecords(list);
      setTotalCount(res?.count || list.length);
    } catch (err) {
      console.warn('DataView search error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    loadData(searchTerm, selectedCol);
  };

  const removeFilter = (id) => {
    setActiveFilters((prev) => prev.filter((f) => f.id !== id));
  };

  const clearAllFilters = () => {
    setActiveFilters([]);
    setSearchTerm('');
    setSelectedCol('all');
    loadData('', 'all');
  };

  // Pagination calculation
  const totalPages = Math.max(1, Math.ceil(records.length / pageSize));
  const displayedRecords = records.slice((page - 1) * pageSize, page * pageSize);

  const totalMongoDocs = collections.reduce((acc, c) => acc + (c.document_count || 0), 0) || 12458;

  return (
    <div className="atlas-data-view">
      {/* Page Title */}
      <div className="atlas-view-header">
        <div className="atlas-view-title-row">
          <h1 className="atlas-page-title">MongoDB Database</h1>
          <span className="atlas-version-tag">v6.0.12 Atlas</span>
        </div>
        <p className="atlas-page-subtitle">
          View and manage the data currently available for AI search.
        </p>
      </div>

      {/* Cluster Status Card (Image 2 style) */}
      <div className="atlas-cluster-card">
        <div className="atlas-cluster-top">
          <div className="atlas-cluster-brand">
            <div className="atlas-mongo-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
              </svg>
            </div>
            <div>
              <div className="atlas-cluster-title">MongoDB Atlas Cluster</div>
              <div className="atlas-cluster-host">cluster0.dflwehg.mongodb.net</div>
            </div>
          </div>
          <span className="atlas-connected-pill">
            <span className="atlas-active-dot" /> Connected
          </span>
        </div>

        {/* Database & Collection target selectors */}
        <div className="atlas-target-row">
          <div className="atlas-target-box">
            <span className="atlas-target-label">TARGET DB</span>
            <div className="atlas-target-val">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              <span>calispec</span>
            </div>
          </div>

          <div className="atlas-target-box">
            <span className="atlas-target-label">ACTIVE COLLECTION</span>
            <div className="atlas-target-val">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                <line x1="3" y1="9" x2="21" y2="9"/>
                <line x1="9" y1="21" x2="9" y2="9"/>
              </svg>
              <select
                className="atlas-select-collection"
                value={selectedCol}
                onChange={(e) => {
                  setSelectedCol(e.target.value);
                  setPage(1);
                }}
              >
                <option value="all">All 6 Collections ({collections.length || 6})</option>
                {collections.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name} ({c.document_count?.toLocaleString()} docs)
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Metrics Grid */}
        <div className="atlas-metrics-grid">
          <div className="atlas-metric-box">
            <div className="atlas-metric-title">RECORDS</div>
            <div className="atlas-metric-num">{totalMongoDocs.toLocaleString()}</div>
          </div>
          <div className="atlas-metric-box">
            <div className="atlas-metric-title">STORAGE</div>
            <div className="atlas-metric-num">48.2 MB</div>
          </div>
          <div className="atlas-metric-box">
            <div className="atlas-metric-title">VECTOR INDEX</div>
            <div className="atlas-metric-num" style={{ color: '#059669', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              Synced
            </div>
          </div>
        </div>
      </div>

      {/* Search Input Bar */}
      <form className="atlas-search-bar" onSubmit={handleSearchSubmit}>
        <div className="atlas-search-input-wrap">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8"/>
            <line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            type="text"
            className="atlas-input-field"
            placeholder="Search records by company, name, designation, email, phone..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="atlas-search-actions">
          <button type="button" className="atlas-btn-outline" onClick={() => loadData(searchTerm, selectedCol)}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
            </svg>
            Filters <span className="atlas-chip-badge">3</span>
          </button>

          <button type="button" className="atlas-btn-outline">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3v18M18 9l-6-6-6 6" />
            </svg>
            Upload Date (Newest)
          </button>

          <button
            type="button"
            className="atlas-btn-outline"
            onClick={() => {
              const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(records, null, 2));
              const downloadAnchor = document.createElement('a');
              downloadAnchor.setAttribute('href', dataStr);
              downloadAnchor.setAttribute('download', `mongodb_export_${selectedCol}.json`);
              document.body.appendChild(downloadAnchor);
              downloadAnchor.click();
              downloadAnchor.remove();
            }}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            Export
          </button>
        </div>
      </form>

      {/* Active Filter Chips */}
      {activeFilters.length > 0 && (
        <div className="atlas-filter-chips-row">
          {activeFilters.map((f) => (
            <span key={f.id} className="atlas-filter-chip">
              {f.label}
              <button type="button" onClick={() => removeFilter(f.id)}>✕</button>
            </span>
          ))}
          <button type="button" className="atlas-clear-all" onClick={clearAllFilters}>
            Clear all
          </button>
        </div>
      )}

      {/* Controls Bar */}
      <div className="atlas-controls-bar">
        <div className="atlas-available-docs">
          {(totalCount || totalMongoDocs).toLocaleString()} DOCUMENTS AVAILABLE
        </div>

        <div className="atlas-view-toggle">
          <button
            type="button"
            className={`atlas-toggle-btn ${viewMode === 'cards' ? 'active' : ''}`}
            onClick={() => setViewMode('cards')}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="7" height="7" />
              <rect x="14" y="3" width="7" height="7" />
              <rect x="14" y="14" width="7" height="7" />
              <rect x="3" y="14" width="7" height="7" />
            </svg>
            Cards
          </button>
          <button
            type="button"
            className={`atlas-toggle-btn ${viewMode === 'grid' ? 'active' : ''}`}
            onClick={() => setViewMode('grid')}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="8" y1="6" x2="21" y2="6"/>
              <line x1="8" y1="12" x2="21" y2="12"/>
              <line x1="8" y1="18" x2="21" y2="18"/>
              <line x1="3" y1="6" x2="3.01" y2="6"/>
              <line x1="3" y1="12" x2="3.01" y2="12"/>
              <line x1="3" y1="18" x2="3.01" y2="18"/>
            </svg>
            Grid
          </button>
        </div>
      </div>

      {/* Records Display */}
      {loading ? (
        <div className="atlas-loading-state">
          <div className="atlas-spinner" />
          <span>Querying MongoDB Cloud collections...</span>
        </div>
      ) : displayedRecords.length > 0 ? (
        viewMode === 'cards' ? (
          <div className="atlas-records-list">
            {displayedRecords.map((rec, i) => (
              <ResultCard
                key={rec.id || i}
                record={rec}
                index={(page - 1) * pageSize + i}
                onInspect={onInspect}
              />
            ))}
          </div>
        ) : (
          <div className="atlas-table-wrapper">
            <table className="atlas-preview-table">
              <thead>
                <tr>
                  <th>COMPANY NAME</th>
                  <th>PERSON NAME</th>
                  <th>DESIGNATION</th>
                  <th>MOBILE NO.</th>
                  <th>EMAIL</th>
                  <th>COLLECTION</th>
                  <th>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {displayedRecords.map((r, idx) => (
                  <tr key={r.id || idx}>
                    <td style={{ fontWeight: 600, color: '#0f172a' }}>{r.company_name || '—'}</td>
                    <td>{r.contact_person || '—'}</td>
                    <td>{r.designation || '—'}</td>
                    <td style={{ fontFamily: 'JetBrains Mono, monospace', color: '#2563eb' }}>{r.mobile_no || '—'}</td>
                    <td style={{ color: '#2563eb' }}>{r.email_1 || r.email || '—'}</td>
                    <td>
                      <span className="atlas-table-badge">{r.source_collection || 'calispec'}</span>
                    </td>
                    <td>
                      <button
                        className="atlas-table-btn"
                        onClick={() => onInspect(r)}
                        title="Inspect Document"
                      >
                        {'{ }'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : (
        <div className="atlas-empty-card">
          <p>No documents found matching the current search criteria.</p>
          <button className="atlas-modal-done" onClick={() => loadData('', 'all')} style={{ marginTop: '10px' }}>
            Reset Filters
          </button>
        </div>
      )}

      {/* Pagination Bar (Image 2 style) */}
      <div className="atlas-pagination-bar">
        <div className="atlas-pag-left">
          Showing {records.length ? (page - 1) * pageSize + 1 : 0}-{Math.min(page * pageSize, records.length)} of {records.length.toLocaleString()} records
        </div>
        <div className="atlas-pag-pages">
          Page {page} of {totalPages}
        </div>
        <div className="atlas-pag-buttons">
          <button
            type="button"
            className="atlas-pag-btn"
            disabled={page === 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            ‹ Prev
          </button>
          {[...Array(Math.min(5, totalPages))].map((_, i) => {
            const num = i + 1;
            return (
              <button
                key={num}
                type="button"
                className={`atlas-pag-num ${page === num ? 'active' : ''}`}
                onClick={() => setPage(num)}
              >
                {num}
              </button>
            );
          })}
          {totalPages > 5 && <span className="atlas-pag-dots">...</span>}
          {totalPages > 5 && (
            <button
              type="button"
              className={`atlas-pag-num ${page === totalPages ? 'active' : ''}`}
              onClick={() => setPage(totalPages)}
            >
              {totalPages}
            </button>
          )}
          <button
            type="button"
            className="atlas-pag-btn"
            disabled={page === totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            Next ›
          </button>
        </div>
      </div>
    </div>
  );
}

import React, { useState, useRef, useEffect } from 'react';

export default function DatasetSelector({
  datasets = [],
  activeDatasetId,
  onSelectDataset,
  onOpenUploadModal,
  onDeleteDataset,
}) {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const containerRef = useRef(null);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const activeDataset = datasets.find((d) => d.dataset_id === activeDatasetId);
  const isAll = !activeDatasetId || activeDatasetId === 'all' || activeDatasetId === 'default';

  return (
    <div className="atlas-dataset-selector-wrap" ref={containerRef}>
      {/* Selector Trigger Button */}
      <button
        type="button"
        className={`atlas-dataset-pill-btn ${!isAll ? 'active-custom' : ''}`}
        onClick={() => setDropdownOpen(!dropdownOpen)}
        title="Switch dataset search scope"
      >
        <span className="atlas-dataset-pill-icon">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <ellipse cx="12" cy="5" rx="9" ry="3"/>
            <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
            <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
          </svg>
        </span>

        <div className="atlas-dataset-pill-text">
          <span className="atlas-dataset-pill-label">Search Scope:</span>
          <span className="atlas-dataset-pill-name">
            {isAll ? 'All Datasets (Default)' : activeDataset?.filename || 'Uploaded Dataset'}
          </span>
          {isAll && datasets.length > 0 && (
            <span className="atlas-dataset-pill-count">
              ({datasets.length} files)
            </span>
          )}
          {!isAll && activeDataset?.record_count && (
            <span className="atlas-dataset-pill-count">
              ({activeDataset.record_count.toLocaleString()} rows)
            </span>
          )}
        </div>

        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ transform: dropdownOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {/* Dropdown Menu */}
      {dropdownOpen && (
        <div className="atlas-dataset-dropdown-menu">
          <div className="atlas-dataset-dropdown-header">
            <span>Select Search Scope</span>
            <button
              type="button"
              className="atlas-dropdown-upload-btn"
              onClick={() => {
                setDropdownOpen(false);
                onOpenUploadModal();
              }}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              Upload Data
            </button>
          </div>

          <div className="atlas-dataset-list">
            {/* All Datasets (Default) */}
            <div
              className={`atlas-dataset-item ${isAll ? 'selected' : ''}`}
              onClick={() => {
                onSelectDataset('all');
                setDropdownOpen(false);
              }}
            >
              <div className="atlas-dataset-item-left">
                <div className="atlas-dataset-icon-circle default">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <ellipse cx="12" cy="5" rx="9" ry="3"/>
                    <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
                    <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
                  </svg>
                </div>
                <div>
                  <div className="atlas-dataset-name-row">
                    <strong>All Datasets (Default)</strong>
                    {isAll && <span className="atlas-active-badge">Active</span>}
                  </div>
                  <div className="atlas-dataset-meta-row">
                    {datasets.length > 0
                      ? `Search across all ${datasets.length} uploaded files & database`
                      : '6 MongoDB Collections • 10,197 Records'}
                  </div>
                </div>
              </div>
            </div>

            {/* Uploaded Datasets */}
            {datasets.map((d) => {
              const isSelected = activeDatasetId === d.dataset_id;
              const fieldCount = d.fields?.length || 0;

              return (
                <div
                  key={d.dataset_id}
                  className={`atlas-dataset-item ${isSelected ? 'selected' : ''}`}
                  onClick={() => {
                    onSelectDataset(d.dataset_id);
                    setDropdownOpen(false);
                  }}
                >
                  <div className="atlas-dataset-item-left">
                    <div className="atlas-dataset-icon-circle uploaded">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                      </svg>
                    </div>
                    <div>
                      <div className="atlas-dataset-name-row">
                        <strong>{d.filename}</strong>
                        {isSelected && <span className="atlas-active-badge">Active</span>}
                      </div>
                      <div className="atlas-dataset-meta-row">
                        {d.record_count?.toLocaleString()} records • {fieldCount} columns
                        {d.original_type ? ` • .${d.original_type}` : ''}
                      </div>
                    </div>
                  </div>

                  <button
                    type="button"
                    className="atlas-btn-delete-dataset"
                    title="Delete Dataset"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (window.confirm(`Delete dataset "${d.filename}" and its records?`)) {
                        onDeleteDataset(d.dataset_id);
                      }
                    }}
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6"/>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                  </button>
                </div>
              );
            })}
          </div>

          <div className="atlas-dataset-dropdown-footer">
            <button
              type="button"
              className="atlas-btn-upload-more"
              onClick={() => {
                setDropdownOpen(false);
                onOpenUploadModal();
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              Upload New Data File (.csv, .xlsx, .json, .xml, .txt)
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

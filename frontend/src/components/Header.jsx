import React from 'react';

export default function Header({ activeTab, health, collections, onToggleMenu }) {
  const isConnected = health?.database_connected ?? true;
  const colCount = collections?.length || 6;

  const viewTitles = {
    dash: 'Dashboard',
    upload: 'Upload Data',
    chat: 'AI Search',
    data: 'Database',
    history: 'Search History',
    settings: 'Settings',
  };

  return (
    <header className="atlas-app-header">
      {/* Top Navbar Row */}
      <div className="atlas-header-top">
        <div className="atlas-header-left">
          <button
            type="button"
            className="atlas-hamburger-btn"
            onClick={onToggleMenu}
            aria-label="Toggle Navigation Menu"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>

          <div className="atlas-brand-box">
            <div className="atlas-brand-logo">
              <img src="/calispec-icon.png" alt="Calispec AI" className="atlas-brand-logo-img" />
            </div>
            <div>
              <div className="atlas-brand-name">Calispec AI</div>
              <div className="atlas-brand-subtitle">Proficient and Nimble</div>
            </div>
          </div>
        </div>

        <div className="atlas-header-right">
          <button type="button" className="atlas-user-avatar-btn" title="Jagathchandran Account">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
          </button>
        </div>
      </div>

      {/* Pill Status Subheader Row (Matching Image 1 & Image 2) */}
      <div className="atlas-status-bar">
        <div className={`atlas-status-chip ${isConnected ? 'online' : 'offline'}`}>
          <span className="atlas-status-dot" />
          <span>
            {isConnected
              ? `MongoDB Connected • calispec (${colCount} Collections)`
              : 'MongoDB Disconnected • Checking Cluster'}
          </span>
        </div>

        <div className="atlas-view-indicator">
          {viewTitles[activeTab] || 'Upload Data'}
        </div>
      </div>
    </header>
  );
}

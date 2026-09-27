import React from 'react';

export default function EmptyState({ onSelectPrompt, onOpenUploadModal, activeDatasetName, activeDatasetFields = [] }) {
  const defaultPrompts = [
    'Find ABC Industries',
    'Find the company with abc@gmail.com',
    'What is the phone number of ABC Industries?',
    'Show me all companies in Chennai',
  ];

  // Dynamic sample prompts based on active dataset fields
  const dynamicPrompts = React.useMemo(() => {
    if (!activeDatasetFields || activeDatasetFields.length === 0) {
      return defaultPrompts;
    }
    const prompts = [];
    const fields = activeDatasetFields;
    
    // Check if email field exists
    const emailField = fields.find((f) => f.toLowerCase().includes('email') || f.toLowerCase().includes('mail'));
    if (emailField) {
      prompts.push(`Find record with ${emailField}: abc@gmail.com`);
    }

    // Check if company/name field exists
    const nameField = fields.find(
      (f) => f.toLowerCase().includes('company') || f.toLowerCase().includes('name') || f.toLowerCase().includes('employee')
    );
    if (nameField) {
      prompts.push(`Search ${nameField}: ABC`);
    }

    // Check if phone field exists
    const phoneField = fields.find((f) => f.toLowerCase().includes('phone') || f.toLowerCase().includes('mobile') || f.toLowerCase().includes('tel'));
    if (phoneField) {
      prompts.push(`Look up phone number 9876543210`);
    }

    // Check location / city
    const cityField = fields.find((f) => f.toLowerCase().includes('city') || f.toLowerCase().includes('address') || f.toLowerCase().includes('location'));
    if (cityField) {
      prompts.push(`Show records located in Chennai`);
    }

    return prompts.length >= 2 ? prompts : defaultPrompts;
  }, [activeDatasetFields]);

  return (
    <div className="atlas-empty-state-wrap">
      {/* Central Welcome Box */}
      <div className="atlas-empty-card-box">
        <div className="atlas-empty-logo-circle">
          <img src="/calispec-icon.png" alt="Calispec AI" className="atlas-empty-logo-img" />
        </div>

        <h2 className="atlas-empty-title">
          {activeDatasetName ? `Search in ${activeDatasetName}` : 'Search Your Data with Calispec AI'}
        </h2>

        <p className="atlas-empty-subtitle">
          Upload spreadsheets, CSVs, or JSON files to search your data privately using MongoDB Cloud.
        </p>

        {/* Upload Action Button */}
        <div className="atlas-empty-actions-row">
          <button
            type="button"
            className="atlas-empty-upload-btn"
            onClick={onOpenUploadModal}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            <span>Upload Data (.xlsx, .csv, .json, .xml, .txt)</span>
          </button>
        </div>

        {/* Example Query Prompts */}
        <div className="atlas-prompts-section">
          <div className="atlas-prompts-label">Try asking:</div>
          <div className="atlas-prompts-grid">
            {dynamicPrompts.map((promptText, idx) => (
              <button
                key={idx}
                type="button"
                className="atlas-prompt-chip"
                onClick={() => onSelectPrompt && onSelectPrompt(promptText)}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="11" cy="11" r="8"/>
                  <line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>
                <span>{promptText}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Strict Privacy Badge */}
        <div className="atlas-privacy-pill">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
          <span>Strict Privacy Guarantee • Zero database records or user files sent to AI models</span>
        </div>
      </div>
    </div>
  );
}

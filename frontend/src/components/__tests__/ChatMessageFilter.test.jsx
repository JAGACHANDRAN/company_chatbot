import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import ChatMessage, { getContactValues, recordToCompanyItem, flattenCompaniesForExport } from '../ChatMessage';

// Mock scrollIntoView and scrollTo
beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.scrollTo = vi.fn();
});

function createMockDataset(count = 70, withEmailCount = 50, chennaiWithEmail = 15, chennaiNoEmail = 5) {
  const records = [];
  for (let i = 0; i < count; i++) {
    const hasEmail = i < withEmailCount;
    const isChennai = hasEmail ? i < chennaiWithEmail : (i - withEmailCount) < chennaiNoEmail;

    records.push({
      id: `record-${i + 1}`,
      company: `Company ${i + 1}`,
      person: `Person ${i + 1}`,
      designation: i % 2 === 0 ? 'Quality Manager' : 'Purchase Officer',
      email: hasEmail ? `user${i + 1}@example.com` : 'No data available',
      email_2: 'No data available',
      phone: i % 3 === 0 ? `+91 98765 4321${i % 10}` : 'No data available',
      phone_2: 'No data available',
      city: isChennai ? 'Chennai' : (i % 2 === 0 ? 'Bangalore' : 'Mumbai'),
      state: isChennai ? 'Tamil Nadu' : (i % 2 === 0 ? 'Karnataka' : 'Maharashtra'),
      linkedin: i % 4 === 0 ? `https://linkedin.com/in/user${i + 1}` : 'No data available',
      source_file: 'Dataset_Test_2026.csv',
      embedding: [0.12, 0.45, -0.67],
    });
  }
  return records;
}

describe('ChatMessage UI & Filter Tests', () => {
  it('renders records with page size 9 and pagination controls', () => {
    const mockData = createMockDataset(98, 70);
    const message = {
      id: 'assistant-test-98',
      role: 'assistant',
      loading: false,
      found: true,
      data: mockData,
    };

    const { container } = render(<ChatMessage message={message} />);

    // Top bar shows "Showing 1 – 9 of 98 records"
    expect(container.textContent).toMatch(/Showing\s+1\s*[–-]\s*9\s+of\s+98\s+records/);

    // Footer shows "Page 1 of 11"
    expect(container.textContent).toMatch(/Page\s+1\s+of\s+11/);
    expect(screen.getByText(/98 records retrieved/i)).toBeInTheDocument();

    // Click Next
    const nextButton = screen.getAllByRole('button', { name: /Next/i })[0];
    fireEvent.click(nextButton);

    // Top bar shows "Showing 10 – 18 of 98 records"
    expect(container.textContent).toMatch(/Showing\s+10\s*[–-]\s*18\s+of\s+98\s+records/);

    // Footer shows "Page 2 of 11"
    expect(container.textContent).toMatch(/Page\s+2\s+of\s+11/);
  });

  it('filters records properly and updates count in top and footer pagination', () => {
    const mockData = createMockDataset(70, 50, 15, 5);
    const message = {
      id: 'assistant-test-20-filtered',
      role: 'assistant',
      loading: false,
      found: true,
      data: mockData,
    };

    const { container } = render(<ChatMessage message={message} />);

    // Filter by City = Chennai (20 records)
    const cityButton = screen.getByRole('button', { name: /City:/i });
    fireEvent.click(cityButton);
    const chennaiOption = screen.getByRole('option', { name: /Chennai/i });
    fireEvent.click(chennaiOption);

    // Top bar shows "Showing 1 – 9 of 20 records"
    expect(container.textContent).toMatch(/Showing\s+1\s*[–-]\s*9\s+of\s+20\s+records/);

    // Footer shows "Page 1 of 3 (20 total records)"
    expect(container.textContent).toMatch(/Page\s+1\s+of\s+3/);

    // Export button shows filtered records label
    expect(screen.getByText(/Exporting 20 filtered records/i)).toBeInTheDocument();
  });

  it('renders side-by-side filter sidebar and cards container', () => {
    const mockData = createMockDataset(30, 20);
    const message = {
      id: 'assistant-test-layout',
      role: 'assistant',
      loading: false,
      found: true,
      data: mockData,
    };

    const { container } = render(<ChatMessage message={message} />);

    // Sidebar aside is rendered
    const sidebar = container.querySelector('aside');
    expect(sidebar).toBeInTheDocument();
    expect(container.querySelector('[data-purpose="filters-panel"]')).toBeInTheDocument();

    // Company cards are rendered
    expect(screen.getByText('Company 1')).toBeInTheDocument();
  });

  it('exports flattened data correctly with filtered set', () => {
    const mockData = createMockDataset(70, 50, 15, 5);
    const filteredRecords = mockData.filter((r) => getContactValues(r).city === 'Chennai');
    const companyItems = filteredRecords.map((r, idx) => recordToCompanyItem(r, idx));
    const exportRows = flattenCompaniesForExport(companyItems);

    expect(exportRows.length).toBe(20);
    exportRows.forEach((row) => {
      expect(row.embedding).toBeUndefined();
      expect(row.city).toBe('Chennai');
    });
  });

  it('calculates option counts matching direct data counts and clear filters works', () => {
    const mockData = createMockDataset(70, 50, 15, 5);
    const message = {
      id: 'assistant-test-facets',
      role: 'assistant',
      loading: false,
      found: true,
      data: mockData,
    };

    const { container } = render(<ChatMessage message={message} />);

    const emailButton = screen.getByRole('button', { name: /Email:/i });
    fireEvent.click(emailButton);
    const hasEmailOption = screen.getByRole('option', { name: /Email Available/i });
    const noEmailOption = screen.getByRole('option', { name: /Email Not Available/i });

    expect(within(hasEmailOption).getByText('50')).toBeInTheDocument();
    expect(within(noEmailOption).getByText('20')).toBeInTheDocument();

    fireEvent.click(hasEmailOption);
    expect(container.textContent).toMatch(/Showing\s+1\s*[–-]\s*9\s+of\s+50\s+records/);

    // Clear filters
    const clearBtn = screen.getByRole('button', { name: /Clear filters/i });
    fireEvent.click(clearBtn);
    expect(container.textContent).toMatch(/Showing\s+1\s*[–-]\s*9\s+of\s+70\s+records/);
  });
});

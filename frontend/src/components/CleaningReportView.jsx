import React from 'react';
import { exportCleaningReportToPdf } from '../utils/reportPdfExporter';

const STANDARD_FIELDS = [
  { value: 'company', label: 'Company Name' },
  { value: 'person', label: 'Person / Contact Name' },
  { value: 'designation', label: 'Designation / Job Title' },
  { value: 'phone', label: 'Phone Number' },
  { value: 'phone_2', label: 'Phone Number (Secondary)' },
  { value: 'email', label: 'Email Address' },
  { value: 'email_2', label: 'Email Address (Secondary)' },
  { value: 'location', label: 'Location / Address / City' },
  { value: 'linkedin', label: 'LinkedIn URL' },
  { value: '', label: '(Keep as Extra Column)' },
];

/**
 * Reusable component displaying the 6-stage cleaning audit report in modern light theme:
 * 1. Summary metrics & count badges + plain language lines
 * 2. Column mapping table with dropdowns
 * 3. What changed table with type filter and pagination
 * 4. Needs review table
 * 5. First 50 cleaned rows sample
 * 6. Download Excel report button
 */
export default function CleaningReportView({
  previewData,
  columnOverrides = {},
  onColumnOverrideChange = null,
  hasMappingChanges = false,
  onReClean = null,
  onDownloadReport,
  changeFilter = 'all',
  onChangeFilter,
  changePage = 1,
  onChangePage,
  changePageSize = 20,
  onChangePageSize,
  isExistingCollection = false,
  loading = false,
}) {
  if (!previewData || (!previewData.summary && (!previewData.cleaned_preview || previewData.cleaned_preview.length === 0))) {
    return (
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center space-y-3">
        <div className="text-3xl">⚠️</div>
        <h3 className="text-base font-bold text-slate-800">Cleaning Report is Empty</h3>
        <p className="text-xs text-slate-500 max-w-md mx-auto">
          The selected file returned no report data or valid contact records.
        </p>
      </div>
    );
  }

  const allChanges = previewData.changes || [];
  const filteredChanges = changeFilter === 'all'
    ? allChanges
    : allChanges.filter((c) => c.action === changeFilter);

  const totalChangePages = Math.max(1, Math.ceil(filteredChanges.length / changePageSize));
  const currentPagedChanges = filteredChanges.slice(
    (changePage - 1) * changePageSize,
    changePage * changePageSize
  );

  const changeTypes = previewData.summary?.changes_by_type
    ? Object.keys(previewData.summary.changes_by_type)
    : [];

  const cleanedPreviewRows = previewData.cleaned_preview || previewData.cleaned_rows || [];

  return (
    <div className="space-y-6">
      {/* ------------------------------------------------------------- */}
      {/* 1. Plain-language summary lines at the top, with count badges */}
      {/* ------------------------------------------------------------- */}
      <section className="bg-white border border-slate-200 rounded-2xl p-5 sm:p-6 space-y-4 shadow-xs">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100 flex-wrap gap-2">
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800 font-mono">
              1. Cleaning Summary &amp; Metrics
            </h3>
            <span className="text-xs text-slate-500 font-mono">
              ({previewData.collection || previewData.filename})
            </span>
          </div>
          <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-sky-50 text-sky-700 border border-sky-200 font-medium font-mono">
            Unsaved Preview
          </span>
        </div>

        {/* Count Badges Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-slate-50 rounded-xl p-3 border border-slate-200 text-center">
            <div className="text-[10px] text-slate-500 uppercase font-mono font-semibold">Rows In</div>
            <div className="text-xl font-bold text-slate-900 mt-1">
              {previewData.summary?.rows_in?.toLocaleString() ?? 0}
            </div>
          </div>

          <div className="bg-emerald-50/60 rounded-xl p-3 border border-emerald-200 text-center">
            <div className="text-[10px] text-emerald-700 uppercase font-mono font-semibold">Clean Rows Out</div>
            <div className="text-xl font-bold text-emerald-700 mt-1">
              {previewData.summary?.rows_out?.toLocaleString() ?? 0}
            </div>
          </div>

          <div className="bg-sky-50/60 rounded-xl p-3 border border-sky-200 text-center">
            <div className="text-[10px] text-sky-700 uppercase font-mono font-semibold">Phones From Names</div>
            <div className="text-xl font-bold text-sky-700 mt-1">
              {previewData.summary?.phones_pulled_from_names ?? 0}
            </div>
          </div>

          <div className="bg-amber-50/60 rounded-xl p-3 border border-amber-200 text-center">
            <div className="text-[10px] text-amber-700 uppercase font-mono font-semibold">Needs Review</div>
            <div className="text-xl font-bold text-amber-700 mt-1">
              {previewData.summary?.needs_review ?? 0}
            </div>
          </div>

          <div className="bg-slate-50 rounded-xl p-3 border border-slate-200 text-center">
            <div className="text-[10px] text-slate-500 uppercase font-mono font-semibold">Empty Rows Removed</div>
            <div className="text-base font-bold text-slate-700 mt-1">
              {previewData.summary?.empty_rows ?? 0}
            </div>
          </div>

          <div className="bg-indigo-50/60 rounded-xl p-3 border border-indigo-200 text-center">
            <div className="text-[10px] text-indigo-700 uppercase font-mono font-semibold">Rows Added By Split</div>
            <div className="text-base font-bold text-indigo-700 mt-1">
              {previewData.summary?.rows_added_by_split ?? 0}
            </div>
          </div>

          <div className="bg-rose-50/60 rounded-xl p-3 border border-rose-200 text-center">
            <div className="text-[10px] text-rose-700 uppercase font-mono font-semibold">Duplicates Removed</div>
            <div className="text-base font-bold text-rose-700 mt-1">
              {previewData.summary?.duplicates_removed ?? 0}
            </div>
          </div>

          <div className="bg-teal-50/60 rounded-xl p-3 border border-teal-200 text-center">
            <div className="text-[10px] text-teal-700 uppercase font-mono font-semibold">Total Changes</div>
            <div className="text-base font-bold text-teal-700 mt-1">
              {previewData.total_changes ?? previewData.changes?.length ?? 0}
            </div>
          </div>
        </div>

        {/* Plain Language Summary Bullet Lines */}
        {previewData.summary?.plain_language && previewData.summary.plain_language.length > 0 && (
          <div className="pt-2">
            <div className="text-xs font-semibold text-slate-700 mb-2">Detailed Audit Notes:</div>
            <ul className="space-y-1.5 text-xs text-slate-600 bg-slate-50 rounded-xl p-3.5 border border-slate-200">
              {previewData.summary.plain_language.map((line, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="text-sky-600 font-bold shrink-0">•</span>
                  <span className="leading-relaxed">{line}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {/* ------------------------------------------------------------- */}
      {/* 2. Column mapping table with dropdown on every row to correct */}
      {/* ------------------------------------------------------------- */}
      <section className="bg-white border border-slate-200 rounded-2xl p-5 sm:p-6 space-y-3.5 shadow-xs">
        <div className="flex items-center justify-between pb-2 border-b border-slate-100 flex-wrap gap-2">
          <div>
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800 font-mono">
              2. Column Mapping
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Detected column attributes and concept associations.
            </p>
          </div>

          {hasMappingChanges && onReClean && (
            <button
              type="button"
              onClick={onReClean}
              disabled={loading}
              className="px-3.5 py-1.5 bg-amber-500 hover:bg-amber-600 text-white font-bold text-xs rounded-xl transition-all shadow-sm flex items-center gap-1.5 cursor-pointer"
            >
              <span>🔄</span>
              <span>Apply &amp; Re-clean with Updated Mapping</span>
            </button>
          )}
        </div>

        <div className="overflow-x-auto rounded-xl border border-slate-200">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-50 text-slate-600 border-b border-slate-200">
                <th className="py-2.5 px-3.5 font-semibold">Source Field / Column</th>
                <th className="py-2.5 px-3.5 font-semibold">Mapped Concept (Dropdown to Correct)</th>
                <th className="py-2.5 px-3.5 font-semibold">Detection Method</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {previewData.column_mapping?.map((col, idx) => {
                const methodLower = (col.method || '').toLowerCase();
                const isGuessed =
                  methodLower === 'content guess' ||
                  methodLower === 'content' ||
                  methodLower === 'keyword';

                const currentValue =
                  columnOverrides[col.column] !== undefined
                    ? columnOverrides[col.column]
                    : col.mapped_to === '(kept as extra column)'
                    ? ''
                    : col.mapped_to;

                return (
                  <tr
                    key={idx}
                    className={`transition-colors ${
                      isGuessed
                        ? 'bg-amber-50/50 border-l-4 border-l-amber-500'
                        : 'hover:bg-slate-50'
                    }`}
                  >
                    <td className="py-2.5 px-3.5 font-mono text-slate-800 font-medium">
                      {col.column}
                    </td>
                    <td className="py-2.5 px-3.5">
                      {onColumnOverrideChange ? (
                        <select
                          className="w-full max-w-xs bg-white border border-slate-300 text-slate-800 rounded-lg p-1.5 text-xs focus:ring-2 focus:ring-sky-500 focus:outline-none"
                          value={currentValue}
                          onChange={(e) => onColumnOverrideChange(col.column, e.target.value)}
                        >
                          {STANDARD_FIELDS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className="font-mono text-sky-700 font-semibold">
                          {col.mapped_to || '(Extra)'}
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 px-3.5">
                      <span
                        className={`inline-block px-2.5 py-0.5 rounded text-[11px] font-mono font-medium ${
                          isGuessed
                            ? 'bg-amber-100 text-amber-800 border border-amber-300'
                            : 'bg-slate-100 text-slate-700 border border-slate-200'
                        }`}
                      >
                        {col.method || 'exact'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* ------------------------------------------------------------- */}
      {/* 3. "What changed" table: row, what happened, field, before, after */}
      {/* ------------------------------------------------------------- */}
      <section className="bg-white border border-slate-200 rounded-2xl p-5 sm:p-6 space-y-3.5 shadow-xs">
        <div className="flex items-center justify-between pb-2 border-b border-slate-100 flex-wrap gap-2">
          <div>
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800 font-mono">
              3. What Changed (Row-by-Row Audit Log)
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Every data change, phone extraction, splitting, and normalization step.
            </p>
          </div>

          {/* Filter by change type */}
          {changeTypes.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap text-xs">
              <span className="text-slate-500 mr-1 font-mono">Filter:</span>
              <button
                type="button"
                onClick={() => {
                  onChangeFilter?.('all');
                  onChangePage?.(1);
                }}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors cursor-pointer ${
                  changeFilter === 'all'
                    ? 'bg-sky-500 text-white shadow-xs'
                    : 'bg-slate-100 text-slate-600 hover:text-slate-900 border border-slate-200'
                }`}
              >
                All ({allChanges.length})
              </button>
              {changeTypes.map((act) => (
                <button
                  key={act}
                  type="button"
                  onClick={() => {
                    onChangeFilter?.(act);
                    onChangePage?.(1);
                  }}
                  className={`px-2.5 py-1 rounded-lg font-mono text-[11px] transition-colors cursor-pointer ${
                    changeFilter === act
                      ? 'bg-sky-500 text-white font-semibold shadow-xs'
                      : 'bg-slate-100 text-slate-600 hover:text-slate-900 border border-slate-200'
                  }`}
                >
                  {act} ({previewData.summary?.changes_by_type[act]})
                </button>
              ))}
            </div>
          )}
        </div>

        {filteredChanges.length === 0 ? (
          <div className="bg-slate-50 rounded-xl p-6 text-center text-xs text-slate-500 border border-slate-200">
            No changes found matching the selected filter.
          </div>
        ) : (
          <>
            <div className="overflow-x-auto rounded-xl border border-slate-200 max-h-80">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="sticky top-0 bg-slate-50 text-slate-700 border-b border-slate-200 shadow-2xs">
                  <tr>
                    <th className="py-2.5 px-3 font-semibold">Row #</th>
                    {isExistingCollection && (
                      <th className="py-2.5 px-3 font-semibold">Source Doc ID</th>
                    )}
                    <th className="py-2.5 px-3 font-semibold">What Happened</th>
                    <th className="py-2.5 px-3 font-semibold">Field</th>
                    <th className="py-2.5 px-3 font-semibold">Before</th>
                    <th className="py-2.5 px-3 font-semibold">After</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {currentPagedChanges.map((ch, idx) => (
                    <tr key={idx} className="hover:bg-slate-50 transition-colors">
                      <td className="py-2 px-3 font-mono text-slate-500 whitespace-nowrap">
                        {ch.source_row}
                      </td>
                      {isExistingCollection && (
                        <td className="py-2 px-3 font-mono text-slate-500 text-[10px] whitespace-nowrap">
                          {ch.source_doc_id ? ch.source_doc_id.slice(-8) : '-'}
                        </td>
                      )}
                      <td className="py-2 px-3 text-slate-800">
                        <div className="font-medium text-slate-900">
                          {ch.what_happened || ch.action}
                        </div>
                        <div className="text-[10px] text-sky-600 font-mono mt-0.5">
                          {ch.action}
                        </div>
                      </td>
                      <td className="py-2 px-3 font-mono text-slate-600 whitespace-nowrap">
                        {ch.field || '-'}
                      </td>
                      <td className="py-2 px-3 text-rose-700 max-w-xs break-words font-mono text-[11px] bg-rose-50/40">
                        {ch.before !== '' && ch.before !== null && ch.before !== undefined
                          ? String(ch.before)
                          : '-'}
                      </td>
                      <td className="py-2 px-3 text-emerald-700 max-w-xs break-words font-mono text-[11px] bg-emerald-50/40">
                        {ch.after !== '' && ch.after !== null && ch.after !== undefined
                          ? String(ch.after)
                          : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <div className="flex items-center justify-between pt-2 text-xs text-slate-500 flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <span>
                  Showing {((changePage - 1) * changePageSize) + 1} -{' '}
                  {Math.min(changePage * changePageSize, filteredChanges.length)} of{' '}
                  {filteredChanges.length} changes
                </span>
                <span className="text-slate-300">|</span>
                <select
                  className="bg-white border border-slate-300 text-slate-700 rounded px-2 py-0.5 text-xs focus:outline-none"
                  value={changePageSize}
                  onChange={(e) => {
                    onChangePageSize?.(Number(e.target.value));
                    onChangePage?.(1);
                  }}
                >
                  <option value={10}>10 / page</option>
                  <option value={20}>20 / page</option>
                  <option value={50}>50 / page</option>
                  <option value={100}>100 / page</option>
                </select>
              </div>

              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => onChangePage?.(Math.max(1, changePage - 1))}
                  disabled={changePage <= 1}
                  className="px-2.5 py-1 rounded bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:pointer-events-none cursor-pointer"
                >
                  Previous
                </button>
                <span className="px-2 text-xs font-mono text-slate-700">
                  Page {changePage} of {totalChangePages}
                </span>
                <button
                  type="button"
                  onClick={() => onChangePage?.(Math.min(totalChangePages, changePage + 1))}
                  disabled={changePage >= totalChangePages}
                  className="px-2.5 py-1 rounded bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:pointer-events-none cursor-pointer"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </section>

      {/* ------------------------------------------------------------- */}
      {/* 4. "Needs review" table with the reason for each row */}
      {/* ------------------------------------------------------------- */}
      <section className="bg-white border border-slate-200 rounded-2xl p-5 sm:p-6 space-y-3.5 shadow-xs">
        <div className="pb-2 border-b border-slate-100 flex items-center justify-between flex-wrap gap-2">
          <div>
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800 font-mono">
              4. Needs Review
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Records with minor anomalies or ambiguous formats requiring administrative review.
            </p>
          </div>
          <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-semibold bg-amber-100 text-amber-800 border border-amber-300">
            {previewData.needs_review?.length ?? 0} rows flagged
          </span>
        </div>

        {!previewData.needs_review || previewData.needs_review.length === 0 ? (
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex items-center gap-3 text-xs text-emerald-800">
            <span className="text-base text-emerald-600">✓</span>
            <span>All records passed verification checks cleanly. Zero rows require manual inspection.</span>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200 max-h-72">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="sticky top-0 bg-slate-50 text-slate-700 border-b border-slate-200">
                <tr>
                  <th className="py-2.5 px-3 font-semibold">Row #</th>
                  <th className="py-2.5 px-3 font-semibold">Company</th>
                  <th className="py-2.5 px-3 font-semibold">Person</th>
                  <th className="py-2.5 px-3 font-semibold">Phone</th>
                  <th className="py-2.5 px-3 font-semibold">Email</th>
                  <th className="py-2.5 px-3 font-semibold">Review Reason</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {previewData.needs_review.map((r, idx) => (
                  <tr key={idx} className="hover:bg-slate-50 transition-colors">
                    <td className="py-2 px-3 font-mono text-slate-500">{r.source_row}</td>
                    <td className="py-2 px-3 text-slate-900 font-medium">{r.company || '-'}</td>
                    <td className="py-2 px-3 text-slate-700">{r.person || '-'}</td>
                    <td className="py-2 px-3 text-slate-700 font-mono">{r.phone || '-'}</td>
                    <td className="py-2 px-3 text-slate-700">{r.email || '-'}</td>
                    <td className="py-2 px-3">
                      <span className="inline-block px-2 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-300 font-mono text-[11px]">
                        {r.review_reasons}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ------------------------------------------------------------- */}
      {/* 5. First 50 cleaned rows */}
      {/* ------------------------------------------------------------- */}
      <section className="bg-white border border-slate-200 rounded-2xl p-5 sm:p-6 space-y-3.5 shadow-xs">
        <div className="pb-2 border-b border-slate-100 flex items-center justify-between flex-wrap gap-2">
          <div>
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800 font-mono">
              5. Cleaned Records Preview (First 50 Rows)
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Sample of normalized records formatted and indexed for search.
            </p>
          </div>
          <span className="text-xs font-mono text-slate-500">
            Showing {cleanedPreviewRows.length} sample records
          </span>
        </div>

        {cleanedPreviewRows.length === 0 ? (
          <div className="bg-slate-50 rounded-xl p-6 text-center text-xs text-slate-500 border border-slate-200">
            No cleaned rows available for preview.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200 max-h-80">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="sticky top-0 bg-slate-50 text-slate-700 border-b border-slate-200">
                <tr>
                  <th className="py-2.5 px-3 font-semibold">#</th>
                  <th className="py-2.5 px-3 font-semibold">Company</th>
                  <th className="py-2.5 px-3 font-semibold">Person</th>
                  <th className="py-2.5 px-3 font-semibold">Designation</th>
                  <th className="py-2.5 px-3 font-semibold">Phone</th>
                  <th className="py-2.5 px-3 font-semibold">Email</th>
                  <th className="py-2.5 px-3 font-semibold">Location</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {cleanedPreviewRows.map((r, idx) => (
                  <tr key={idx} className="hover:bg-slate-50 transition-colors">
                    <td className="py-2 px-3 font-mono text-slate-400">{idx + 1}</td>
                    <td className="py-2 px-3 text-slate-900 font-medium">{r.company || '-'}</td>
                    <td className="py-2 px-3 text-slate-700">{r.person || '-'}</td>
                    <td className="py-2 px-3 text-slate-600">{r.designation || '-'}</td>
                    <td className="py-2 px-3 font-mono text-emerald-700">{r.phone || '-'}</td>
                    <td className="py-2 px-3 text-sky-700">{r.email || '-'}</td>
                    <td className="py-2 px-3 text-slate-600">{r.location || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ------------------------------------------------------------- */}
      {/* 6. "Download Report (PDF)" button */}
      {/* ------------------------------------------------------------- */}
      <section className="bg-white border border-slate-200 rounded-2xl p-5 sm:p-6 shadow-xs flex items-center justify-between flex-wrap gap-4">
        <div>
          <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800 font-mono">
            6. Download Full Audit Report (.pdf)
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Download comprehensive audit report with cleaning summary, field mapping, and before/after separations.
          </p>
        </div>

        <button
          type="button"
          onClick={() => {
            if (onDownloadReport) {
              onDownloadReport();
            } else {
              exportCleaningReportToPdf(previewData, previewData.collection || previewData.filename || 'cleaning_report');
            }
          }}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs sm:text-sm font-semibold bg-rose-50 hover:bg-rose-100 text-rose-800 border border-rose-200 shadow-xs transition-all cursor-pointer"
        >
          <svg className="w-4 h-4 text-rose-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
          </svg>
          <span>Download Audit Report (PDF)</span>
        </button>
      </section>
    </div>
  );
}

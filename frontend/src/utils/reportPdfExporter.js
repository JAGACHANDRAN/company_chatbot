import { jsPDF } from 'jspdf';

/**
 * Generates and downloads a clean, professional PDF audit report for dataset cleaning.
 */
export function exportCleaningReportToPdf(previewData, rawFilename = 'dataset') {
  try {
    const doc = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: 'a4',
    });

    const pageWidth = doc.internal.pageSize.getWidth();
    const margin = 14;
    const contentWidth = pageWidth - margin * 2;
    let y = 16;

    // Header banner
    doc.setFillColor(2, 132, 199); // #0284c7 Sky 600
    doc.rect(margin, y, contentWidth, 14, 'F');
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(13);
    doc.setFont('helvetica', 'bold');
    doc.text('Calispec Dataset Cleaning & Audit Report', margin + 6, y + 9);
    y += 20;

    // Metadata
    doc.setTextColor(71, 85, 105);
    doc.setFontSize(9);
    doc.setFont('helvetica', 'normal');
    doc.text(`File: ${previewData.filename || rawFilename}`, margin, y);
    doc.text(`Date: ${new Date().toLocaleString()}`, margin + 95, y);
    y += 8;

    // Summary Metrics Box
    const summary = previewData.summary || {};
    doc.setFillColor(240, 249, 255); // sky-50
    doc.setDrawColor(186, 230, 253); // sky-200
    doc.rect(margin, y, contentWidth, 22, 'FD');

    doc.setTextColor(3, 105, 161);
    doc.setFontSize(8.5);
    doc.setFont('helvetica', 'bold');
    doc.text(`Rows In: ${summary.rows_in ?? 0}`, margin + 6, y + 7);
    doc.text(`Clean Rows Out: ${summary.rows_out ?? 0}`, margin + 60, y + 7);
    doc.text(`Needs Review: ${summary.needs_review ?? 0}`, margin + 120, y + 7);

    doc.text(`Phones From Names: ${summary.phones_pulled_from_names ?? 0}`, margin + 6, y + 16);
    doc.text(`Duplicates Removed: ${summary.duplicates_removed ?? 0}`, margin + 60, y + 16);
    doc.text(`Total Changes: ${previewData.total_changes ?? (previewData.changes?.length ?? 0)}`, margin + 120, y + 16);
    y += 28;

    // Detailed Changes Table
    const changes = previewData.changes || [];
    if (changes.length > 0) {
      doc.setTextColor(15, 23, 42);
      doc.setFontSize(11);
      doc.setFont('helvetica', 'bold');
      doc.text('Detailed Changes & Field Separations', margin, y);
      y += 6;

      // Table header
      doc.setFillColor(241, 245, 249);
      doc.rect(margin, y, contentWidth, 7, 'F');
      doc.setTextColor(100, 116, 139);
      doc.setFontSize(8);
      doc.text('Row', margin + 2, y + 5);
      doc.text('Field', margin + 14, y + 5);
      doc.text('Action', margin + 38, y + 5);
      doc.text('Original Value', margin + 85, y + 5);
      doc.text('Cleaned Value', margin + 130, y + 5);
      y += 8;

      changes.slice(0, 200).forEach((ch) => {
        if (y > 275) {
          doc.addPage();
          y = 16;
          // Subheader
          doc.setFillColor(241, 245, 249);
          doc.rect(margin, y, contentWidth, 7, 'F');
          doc.setTextColor(100, 116, 139);
          doc.setFontSize(8);
          doc.text('Row', margin + 2, y + 5);
          doc.text('Field', margin + 14, y + 5);
          doc.text('Action', margin + 38, y + 5);
          doc.text('Original Value', margin + 85, y + 5);
          doc.text('Cleaned Value', margin + 130, y + 5);
          y += 8;
        }

        doc.setTextColor(71, 85, 105);
        doc.setFontSize(7.5);
        doc.setFont('helvetica', 'normal');
        doc.text(`#${ch.source_row ?? '-'}`, margin + 2, y);
        doc.text(String(ch.field || '').substring(0, 12), margin + 14, y);
        doc.text(String(ch.what_happened || ch.action || '').substring(0, 24), margin + 38, y);

        doc.setTextColor(190, 18, 60); // rose-700
        doc.text(String(ch.before || '').substring(0, 24), margin + 85, y);

        doc.setTextColor(4, 120, 87); // emerald-700
        doc.text(String(ch.after || '').substring(0, 28), margin + 130, y);

        y += 5.5;
      });
    }

    const cleanStem = (rawFilename || 'dataset')
      .replace(/\.[^/.]+$/, '')
      .replace(/[^a-zA-Z0-9_-]/g, '_');
    doc.save(`${cleanStem}_cleaning_report.pdf`);
  } catch (err) {
    console.error('Failed to generate PDF audit report:', err);
    window.print();
  }
}

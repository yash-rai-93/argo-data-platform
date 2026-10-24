import { toCanvas } from "html-to-image";
import jsPDF from "jspdf";

const TARGET_ID = "argo-workspace";
const BACKGROUND = "#020408";
const FILENAME = "ARGO_Executive_Board_Report.pdf";
const MARGIN = 24;
const FOOTER = 20;

// Keep rows, short text blocks, controls, and charts together when they fit.
// Large sections can span pages without shrinking the whole workspace.
function pageSlices(
  target: HTMLElement,
  canvas: HTMLCanvasElement,
  pagePixels: number,
): Array<[number, number]> {
  const bounds = target.getBoundingClientRect();
  const pixelScale = canvas.width / bounds.width;
  const rectangles = Array.from(
    target.querySelectorAll("tr, h2, h3, input, button, .recharts-wrapper"),
    (element) => element.getBoundingClientRect(),
  );
  // A paragraph or outreach draft may be tall. Protect its individual lines,
  // rather than moving the whole paragraph onto a mostly empty next page.
  for (const element of target.querySelectorAll("p, pre")) {
    const range = document.createRange();
    range.selectNodeContents(element);
    rectangles.push(...Array.from(range.getClientRects()));
    range.detach();
  }
  const blocks = rectangles
    .map((rect) => ({
      start: (rect.top - bounds.top) * pixelScale,
      end: (rect.bottom - bounds.top) * pixelScale,
    }))
    .filter((block) => block.end > block.start && block.end - block.start <= pagePixels);

  const slices: Array<[number, number]> = [];
  let start = 0;
  while (start < canvas.height) {
    let end = Math.min(start + pagePixels, canvas.height);
    if (end < canvas.height) {
      while (true) {
        // Adjacent row edges can differ by a fractional capture pixel.
        // Ignore that overlap so rounding cannot walk backwards through rows.
        const crossing = blocks.filter(
          (block) =>
            block.start < end - 1 &&
            block.end > end + 1 &&
            block.start > start + pagePixels * 0.45,
        );
        if (crossing.length === 0) break;
        const safeEnd = Math.round(Math.min(...crossing.map((block) => block.start)));
        if (safeEnd <= start || safeEnd >= end) break;
        end = safeEnd;
      }
    }
    slices.push([start, end]);
    start = end;
  }
  return slices;
}

// Capture with the browser renderer so Tailwind v4 colors and SVG charts work.
// Encode only each page's pixels as JPEG: embedding a full uncompressed PNG
// produced a roughly 49 MB single-page export and made long reports unreadable.
export async function generateBoardReport(): Promise<void> {
  const target = document.getElementById(TARGET_ID);
  if (!target) throw new Error("The report workspace is unavailable.");
  await document.fonts.ready;

  const capture = await toCanvas(target, {
    backgroundColor: BACKGROUND,
    pixelRatio: 1.5,
    cacheBust: true,
  });
  if (!capture.width || !capture.height) {
    throw new Error("The report workspace is empty.");
  }

  const doc = new jsPDF({
    orientation: "landscape",
    unit: "px",
    format: "a4",
    compress: true,
  });
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const contentWidth = pageWidth - 2 * MARGIN;
  const contentHeight = pageHeight - 2 * MARGIN - FOOTER;
  const scale = contentWidth / capture.width;
  const slices = pageSlices(target, capture, Math.max(1, Math.floor(contentHeight / scale)));

  slices.forEach(([start, end], index) => {
    if (index > 0) doc.addPage();
    const page = document.createElement("canvas");
    page.width = capture.width;
    page.height = end - start;
    const context = page.getContext("2d");
    if (!context) throw new Error("The report image could not be created.");
    context.drawImage(capture, 0, start, capture.width, end - start, 0, 0, page.width, page.height);

    doc.setFillColor(BACKGROUND);
    doc.rect(0, 0, pageWidth, pageHeight, "F");
    doc.addImage(
      page.toDataURL("image/jpeg", 0.88),
      "JPEG",
      MARGIN,
      MARGIN,
      contentWidth,
      page.height * scale,
      undefined,
      "FAST",
    );
    doc.setFontSize(9);
    doc.setTextColor("#94a3b8");
    doc.text(
      "ARGO - Page " + (index + 1) + " / " + slices.length,
      pageWidth - MARGIN,
      pageHeight - 12,
      { align: "right" },
    );
    page.width = 0;
    page.height = 0;
  });
  capture.width = 0;
  capture.height = 0;
  doc.save(FILENAME);
}

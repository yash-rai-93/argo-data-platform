import { toPng } from "html-to-image";
import jsPDF from "jspdf";

const TARGET_ID = "argo-workspace";
const BACKGROUND = "#020408";
const FILENAME = "ARGO_Executive_Board_Report.pdf";

// Loads a data URL into an Image so the true pixel dimensions are known before
// the PDF page is laid out. html-to-image returns only the encoded string.
function loadImage(dataUrl: string): Promise<HTMLImageElement> {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Failed to decode captured PNG"));
    image.src = dataUrl;
  });
}

// Captures the live workspace DOM and exports it as a landscape PDF board report.
// html-to-image serialises the node to SVG foreignObject and rasterises it in the
// browser's own renderer, so Tailwind v4 oklch() colors and backdrop-filter
// glassmorphism survive the capture. html2canvas reimplements CSS itself and
// throws on both.
export async function generateBoardReport(): Promise<void> {
  try {
    const target: HTMLElement | null = document.getElementById(TARGET_ID);
    if (!target) {
      throw new Error(`Workspace element #${TARGET_ID} not found`);
    }

    const dataUrl: string = await toPng(target, {
      quality: 0.95,
      backgroundColor: BACKGROUND,
      pixelRatio: 2,
      cacheBust: true,
    });

    const image: HTMLImageElement = await loadImage(dataUrl);

    // Initialize a landscape PDF sized to the captured aspect ratio.
    const doc = new jsPDF({
      orientation: "landscape",
      unit: "px",
      format: "a4",
    });
    const pageWidth: number = doc.internal.pageSize.getWidth();
    const pageHeight: number = doc.internal.pageSize.getHeight();

    // Scale the capture to fit within the page while preserving proportions.
    const ratio: number = Math.min(
      pageWidth / image.width,
      pageHeight / image.height,
    );
    const renderWidth: number = image.width * ratio;
    const renderHeight: number = image.height * ratio;
    const offsetX: number = (pageWidth - renderWidth) / 2;
    const offsetY: number = (pageHeight - renderHeight) / 2;

    doc.setFillColor(BACKGROUND);
    doc.rect(0, 0, pageWidth, pageHeight, "F");
    doc.addImage(dataUrl, "PNG", offsetX, offsetY, renderWidth, renderHeight);
    doc.save(FILENAME);
  } catch (error) {
    // Surface the failure without crashing the dashboard.
    console.error("Board report export failed:", error);
  }
}

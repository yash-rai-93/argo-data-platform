import jsPDF from "jspdf";
import html2canvas from "html2canvas";

// Captures the live workspace DOM and exports it as a landscape PDF board report.
export async function generateBoardReport(): Promise<void> {
  try {
    const target = document.getElementById("argo-workspace");
    if (!target) {
      throw new Error("Workspace element #argo-workspace not found");
    }

    // Render the DOM node to a high-fidelity canvas.
    const canvas = await html2canvas(target, {
      scale: 2,
      useCORS: true,
      backgroundColor: "#020408",
    });

    const imageData = canvas.toDataURL("image/png");

    // Initialize a landscape PDF sized to the captured aspect ratio.
    const doc = new jsPDF({ orientation: "landscape", unit: "px", format: "a4" });
    const pageWidth = doc.internal.pageSize.getWidth();
    const pageHeight = doc.internal.pageSize.getHeight();

    // Scale the capture to fit within the page while preserving proportions.
    const ratio = Math.min(
      pageWidth / canvas.width,
      pageHeight / canvas.height,
    );
    const renderWidth = canvas.width * ratio;
    const renderHeight = canvas.height * ratio;
    const offsetX = (pageWidth - renderWidth) / 2;
    const offsetY = (pageHeight - renderHeight) / 2;

    doc.addImage(
      imageData,
      "PNG",
      offsetX,
      offsetY,
      renderWidth,
      renderHeight,
    );
    doc.save("ARGO_Executive_Board_Report.pdf");
  } catch (error) {
    // Surface the failure without crashing the dashboard.
    console.error("Board report export failed:", error);
  }
}

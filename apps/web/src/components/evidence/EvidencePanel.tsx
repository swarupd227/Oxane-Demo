import { FileText, ZoomIn, ZoomOut } from "lucide-react";
import { useState } from "react";
import { packUrl, type Citation, type DocumentInfo } from "../../lib/workbench";
import { PdfPage } from "./PdfPage";

// A full page is unreadable from the back of a room, so evidence opens zoomed on the clause.
const ZOOMS = [1, 1.5, 2];

interface EvidencePanelProps {
  citation: Citation | null | undefined;
  documents: DocumentInfo[];
  emptyText?: string;
}

export function EvidencePanel({ citation, documents, emptyText }: EvidencePanelProps) {
  const [zoomIndex, setZoomIndex] = useState(1);
  const document = documents.find((item) => item.id === citation?.document);

  if (!citation || !document) {
    return (
      <div className="grid min-h-48 place-items-center rounded-lg border border-dashed border-line p-6 text-center text-sm text-muted">
        <span>
          <FileText aria-hidden className="mx-auto mb-2 size-5" />
          {emptyText ?? "No source page for this item."}
        </span>
      </div>
    );
  }

  const zoomButton = "cursor-pointer rounded p-1 text-muted hover:bg-sand disabled:opacity-40";

  return (
    <div className="overflow-hidden rounded-lg border border-line">
      <div className="flex items-center justify-between gap-3 border-b border-line bg-canvas px-3 py-1.5 text-xs font-medium text-muted">
        <span className="truncate">{document.title}</span>
        <span className="flex shrink-0 items-center gap-2">
          <span className="numeric">Page {citation.page}</span>
          <button
            type="button"
            aria-label="Zoom out"
            disabled={zoomIndex === 0}
            onClick={() => setZoomIndex((index) => index - 1)}
            className={zoomButton}
          >
            <ZoomOut aria-hidden className="size-3.5" />
          </button>
          <button
            type="button"
            aria-label="Zoom in"
            disabled={zoomIndex === ZOOMS.length - 1}
            onClick={() => setZoomIndex((index) => index + 1)}
            className={zoomButton}
          >
            <ZoomIn aria-hidden className="size-3.5" />
          </button>
        </span>
      </div>
      <div
        data-evidence-scroll
        tabIndex={0}
        role="region"
        aria-label="Source page"
        className="max-h-[calc(100vh-36rem)] min-h-64 overflow-auto"
      >
        <div style={{ width: `${ZOOMS[zoomIndex] * 100}%` }}>
          <PdfPage
            // PDF.js refuses to reuse a canvas mid-render, so each page gets its own.
            key={`${citation.document}-${citation.page}-${zoomIndex}`}
            url={packUrl(document.file)}
            page={citation.page}
            rects={citation.rects}
            label={`${document.title}, page ${citation.page}, with the cited clause highlighted`}
          />
        </div>
      </div>
    </div>
  );
}

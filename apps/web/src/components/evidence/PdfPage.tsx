import { AnimatePresence, motion } from "motion/react";
import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { useEffect, useRef, useState } from "react";
import type { Rect } from "../../lib/workbench";
import { Skeleton } from "../ui/layout";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

const documents = new Map<string, Promise<pdfjs.PDFDocumentProxy>>();

function openDocument(url: string) {
  let task = documents.get(url);
  if (!task) {
    task = pdfjs.getDocument({ url, standardFontDataUrl: "/pdfjs/standard_fonts/" }).promise;
    documents.set(url, task);
  }
  return task;
}

interface PdfPageProps {
  url: string;
  page: number;
  rects: Rect[];
  label: string;
}

export function PdfPage({ url, page, rects, label }: PdfPageProps) {
  const holder = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [ratio, setRatio] = useState(11 / 8.5);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let render: pdfjs.RenderTask | undefined;
    setReady(false);
    setFailed(false);

    (async () => {
      const pdf = await openDocument(url);
      const pdfPage = await pdf.getPage(page);
      if (cancelled || !canvas.current || !holder.current) {
        return;
      }
      const base = pdfPage.getViewport({ scale: 1 });
      setRatio(base.height / base.width);
      const scale = (holder.current.clientWidth / base.width) * (window.devicePixelRatio || 1);
      const viewport = pdfPage.getViewport({ scale });
      canvas.current.width = viewport.width;
      canvas.current.height = viewport.height;
      render = pdfPage.render({ canvas: canvas.current, viewport });
      await render.promise;
      if (!cancelled) {
        setReady(true);
      }
    })().catch((error: unknown) => {
      if (!cancelled && !(error instanceof pdfjs.RenderingCancelledException)) {
        setFailed(true);
      }
    });

    return () => {
      cancelled = true;
      render?.cancel();
    };
  }, [url, page]);

  useEffect(() => {
    // Scroll only the evidence pane. Moving the whole page would lose the analyst's place.
    const scroller = holder.current?.closest<HTMLElement>("[data-evidence-scroll]");
    const first = rects[0];
    if (!ready || !first || !scroller || !holder.current) {
      return;
    }
    const { offsetWidth: width, offsetHeight: height } = holder.current;
    scroller.scrollTo({
      top: first.top * height - scroller.clientHeight / 3,
      left: ((first.x0 + first.x1) / 2) * width - scroller.clientWidth / 2,
      behavior: "smooth",
    });
  }, [ready, rects]);

  return (
    <div
      ref={holder}
      role="img"
      aria-label={label}
      className="relative w-full overflow-hidden bg-surface"
      style={{ aspectRatio: `1 / ${ratio}` }}
    >
      <canvas ref={canvas} className="block size-full" />
      {!ready && !failed && (
        <div className="absolute inset-0 space-y-3 p-10">
          {[...Array(9).keys()].map((line) => (
            <Skeleton key={line} className="h-3 w-full" />
          ))}
        </div>
      )}
      {failed && (
        <p role="alert" className="absolute inset-0 grid place-items-center text-sm text-danger">
          This page could not be opened.
        </p>
      )}
      <AnimatePresence>
        {ready &&
          rects.map((rect, index) => (
            <motion.span
              key={`${page}-${index}`}
              data-highlight
              initial={{ opacity: 0, scaleX: 0.97 }}
              animate={{ opacity: 1, scaleX: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.22, delay: index * 0.03, ease: "easeOut" }}
              className="pointer-events-none absolute origin-left rounded-[3px] bg-accent/40 ring-1 ring-ink/70"
              style={{
                left: `${(rect.x0 - 0.004) * 100}%`,
                top: `${(rect.top - 0.002) * 100}%`,
                width: `${(rect.x1 - rect.x0 + 0.008) * 100}%`,
                height: `${(rect.bottom - rect.top + 0.004) * 100}%`,
              }}
            />
          ))}
      </AnimatePresence>
    </div>
  );
}

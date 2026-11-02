import clsx from "clsx";
import { ArrowRight, CheckCircle2, FileQuestion, Link2, Loader2, UploadCloud } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { Card, Skeleton } from "../components/ui/layout";
import { PageHeader, SeedNotice } from "../components/ui/PageHeader";
import { formatDate } from "../lib/format";
import { useSession } from "../lib/session";
import { useWorkbench, type DocumentInfo } from "../lib/workbench";

const STEP_MS = 420;

interface PackCheck {
  recognised: number;
  refused: string[];
  absent: string[];
}

async function verifyFile(file: File): Promise<{ name: string; recognised: boolean; file: string | null }> {
  const response = await fetch(`/api/intake/verify?name=${encodeURIComponent(file.name)}`, {
    method: "POST",
    body: file,
  });
  if (!response.ok) {
    throw new Error(`Verify failed with ${response.status}`);
  }
  return response.json();
}

const shownDate = (value: string | null) => (value ? formatDate(value) : "Not stated");

function FileRow({ doc, done, links }: { doc: DocumentInfo; done: boolean; links?: string }) {
  return (
    <motion.tr
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="border-b border-sand last:border-0"
    >
      <td className="w-10 py-3 pl-5">
        {done ? (
          <CheckCircle2 aria-label="Classified" className="size-[1.125rem] text-ok" />
        ) : (
          <Loader2 aria-label="Classifying" className="size-[1.125rem] animate-spin text-muted" />
        )}
      </td>
      <td className="py-3 pr-4">
        <p className="text-sm font-medium">{doc.title}</p>
        <p className="mt-0.5 text-xs text-muted">{doc.file}</p>
      </td>
      <td className="py-3 pr-4 text-sm text-muted">{done ? doc.kind : ""}</td>
      <td className="numeric py-3 pr-4 text-sm text-muted">{done ? doc.version : ""}</td>
      <td className="numeric py-3 pr-4 text-sm text-muted">{done ? shownDate(doc.dated) : ""}</td>
      <td className="numeric py-3 pr-4 text-sm font-medium">
        {done ? shownDate(doc.effective) : ""}
      </td>
      <td className="numeric py-3 pr-4 text-sm text-muted">{done ? doc.size : ""}</td>
      <td className="py-3 pr-5 text-xs text-muted">
        {done && links && (
          <span className="inline-flex items-center gap-1 font-medium text-ink">
            <Link2 aria-hidden className="size-3.5" />
            {links}
          </span>
        )}
        {done && !links && doc.note}
      </td>
    </motion.tr>
  );
}

export function IntakePage() {
  const { data } = useWorkbench();
  const { state, dispatch } = useSession();
  const navigate = useNavigate();
  const [revealed, setRevealed] = useState(state.intakeDone ? 99 : 0);
  const [running, setRunning] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [checking, setChecking] = useState(false);
  const [verified, setVerified] = useState(false);
  const [result, setResult] = useState<PackCheck | null>(null);

  const total = data?.documents.length ?? 0;
  const classified = state.intakeDone || (running && revealed > total);

  useEffect(() => {
    if (!running || !data) {
      return;
    }
    if (revealed > total) {
      if (!state.intakeDone) {
        dispatch({ type: "intake-done", workbench: data, verified });
      }
      return;
    }
    const timer = setTimeout(() => setRevealed((count) => count + 1), STEP_MS);
    return () => clearTimeout(timer);
  }, [running, revealed, total, data, dispatch, state.intakeDone, verified]);

  async function check(files: File[]) {
    if (!data || files.length === 0) {
      return;
    }
    setChecking(true);
    setResult(null);
    try {
      const checks = await Promise.all(files.map(verifyFile));
      const matched = new Set(checks.flatMap((item) => (item.file ? [item.file] : [])));
      const refused = checks.filter((item) => !item.recognised).map((item) => item.name);
      const absent = data.documents.filter((doc) => !matched.has(doc.file)).map((doc) => doc.title);
      if (absent.length === 0 && refused.length === 0) {
        setVerified(true);
        setRunning(true);
      } else {
        setResult({ recognised: matched.size, refused, absent });
      }
    } finally {
      setChecking(false);
    }
  }

  if (!data) {
    return <Skeleton className="h-96 w-full" />;
  }

  const started = running || state.intakeDone;
  const titles = Object.fromEntries(data.documents.map((doc) => [doc.id, doc.title]));

  return (
    <div>
      <PageHeader
        title="Document intake"
        summary="Documents received, classified by type, version and effective date."
        actions={
          classified && (
            <Button size="lg" onClick={() => navigate("/terms")}>
              Review facility terms
              <ArrowRight aria-hidden className="size-4" />
            </Button>
          )
        }
      />
      {data?.seed && (
        <SeedNotice>
          Reference data: expected classification. Extraction has not run for this case.
        </SeedNotice>
      )}

      {!started && (
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            void check([...event.dataTransfer.files]);
          }}
          className={clsx(
            "flex h-80 w-full flex-col items-center justify-center rounded-xl border-2 border-dashed transition-colors",
            dragging ? "border-ink bg-sand" : "border-stone bg-surface",
          )}
        >
          <UploadCloud aria-hidden className="size-8 text-muted" />
          <p className="mt-3 text-lg font-medium">Drop the document pack here</p>
          <p className="mt-1 text-sm text-muted">
            8 files for onboarding case 0412. Each file is matched by its content.
          </p>
          <div className="mt-5 flex items-center gap-3">
            <Button size="lg" onClick={() => setRunning(true)} disabled={checking}>
              Load sandbox pack
            </Button>
            <label className="flex h-12 cursor-pointer items-center rounded-lg border border-line bg-surface px-5 text-[0.9375rem] font-medium hover:border-stone hover:bg-canvas">
              Choose files
              <input
                type="file"
                multiple
                className="sr-only"
                onChange={(event) => void check([...(event.target.files ?? [])])}
              />
            </label>
          </div>
          {checking && (
            <p role="status" className="mt-4 flex items-center gap-2 text-sm text-muted">
              <Loader2 aria-hidden className="size-4 animate-spin" />
              Matching files
            </p>
          )}
        </div>
      )}

      {!started && result && (
        <div role="alert" className="mt-4 rounded-xl border border-warn/40 bg-warn-tint p-4 text-sm">
          <p className="font-semibold text-warn">
            {result.recognised} of {total} files matched. The pack was not loaded.
          </p>
          {result.refused.length > 0 && (
            <p className="mt-1">Not part of this case: {result.refused.join(", ")}.</p>
          )}
          {result.absent.length > 0 && <p className="mt-1">Still needed: {result.absent.join(", ")}.</p>}
        </div>
      )}

      {started && (
        <Card className="overflow-hidden">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-line text-[0.6875rem] font-semibold tracking-[0.06em] text-muted uppercase">
                <th className="py-2.5 pl-5">
                  <span className="sr-only">Status</span>
                </th>
                <th className="py-2.5 pr-4">Document</th>
                <th className="py-2.5 pr-4">Type</th>
                <th className="py-2.5 pr-4">Version</th>
                <th className="py-2.5 pr-4">Dated</th>
                <th className="py-2.5 pr-4">Effective</th>
                <th className="py-2.5 pr-4">Size</th>
                <th className="py-2.5 pr-5">Notes</th>
              </tr>
            </thead>
            <tbody>
              {data.documents.slice(0, state.intakeDone ? undefined : revealed).map((doc, index) => (
                <FileRow
                  key={doc.id}
                  doc={doc}
                  done={state.intakeDone || index < revealed - 1}
                  links={doc.links_to ? `Linked to ${titles[doc.links_to]}` : undefined}
                />
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {classified && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          className="mt-4 flex items-center gap-4 rounded-xl border-2 border-dashed border-danger/50 bg-danger-tint/50 p-5"
        >
          <FileQuestion aria-hidden className="size-6 shrink-0 text-danger" />
          <div>
            <p className="font-semibold">Expected but not received</p>
            {data.missing_documents.map((item) => (
              <p key={item.name} className="mt-0.5 text-sm text-muted">
                <span className="font-medium text-ink">{item.name}.</span> {item.reason}.
              </p>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}

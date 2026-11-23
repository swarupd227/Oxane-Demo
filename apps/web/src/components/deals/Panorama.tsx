/* The hand-off to Oxane's platform. The demo posts to an in-app mock (a stub), said plainly. */
import { Send } from "lucide-react";
import type { PanoramaSend } from "../../lib/deals";
import { Badge } from "../../monitoring/ui";

export function PanoramaReceipt({ sent, what }: { sent: PanoramaSend | null | undefined; what: string }) {
  if (!sent) {
    return null;
  }
  const mock = sent.request.mode === "mock";
  return (
    <div className="mt-2 rounded-md border border-line bg-canvas px-2 py-1.5 text-xs" data-testid="panorama-receipt">
      <p className="flex flex-wrap items-center gap-1.5 font-medium">
        <Send aria-hidden className="size-3.5" />
        {sent.ok ? <>Sent to Panorama · receipt <span className="font-mono">{sent.receipt}</span></> : <>Panorama did not accept {what} (status {sent.response.status})</>}
        {mock && <Badge tone="neutral">Stub: in-app mock</Badge>}
      </p>
      <p className="text-muted">
        {sent.request.method} {sent.request.url} · {sent.request.bytes.toLocaleString()} bytes · sha256 {sent.request.sha256.slice(0, 12)} · by {sent.by} · logged in the audit trail ({sent.audit_hash.slice(0, 10)})
      </p>
    </div>
  );
}

/* The mapping library: every stored layout per document type and sender, its versions, the
 * facilities that use it and this cycle's files in it. */
import { useState } from "react";
import type { Cycle, LibraryEntry } from "../cycle";
import { NoAiBadge } from "../parts";
import {
  Badge,
  DataTable,
  FilterSelect,
  Kpis,
  Panel,
  Person,
  RecordId,
  when,
  type Column,
} from "../ui";

export function MappingLibrary({
  cycle,
  client,
}: {
  cycle: Cycle;
  client: string;
}) {
  const library = cycle.mapping.library.filter(
    (e) => client === "all" || e.client === client,
  );
  const [selected, setSelected] = useState<string | null>(
    library.find((e) => e.versions.length > 1)?.id ?? library[0]?.id ?? null,
  );
  const [type, setType] = useState("all");
  const types = [...new Set(library.map((e) => e.document))].sort();
  const rows = library.filter((e) => type === "all" || e.document === type);
  const entry = library.find((e) => e.id === selected);
  const clients = Object.fromEntries(cycle.clients.map((c) => [c.id, c]));
  const columns: Column<LibraryEntry>[] = [
    {
      key: "id",
      header: "Layout",
      sort: (e) => e.id,
      render: (e) => <RecordId>{e.id}</RecordId>,
    },
    {
      key: "document",
      header: "Document type",
      sort: (e) => e.document,
      render: (e) => (
        <span className="font-medium whitespace-nowrap">{e.document}</span>
      ),
    },
    {
      key: "sender",
      header: "Sender or layout",
      sort: (e) => e.sender,
      render: (e) => (
        <span className="block max-w-64 truncate">{e.sender}</span>
      ),
    },
    {
      key: "format",
      header: "Format",
      render: (e) => <span className="font-mono text-xs">{e.format}</span>,
    },
    {
      key: "version",
      header: "Version",
      align: "right",
      sort: (e) => e.version,
      render: (e) => <span className="numeric">v{e.version}</span>,
    },
    {
      key: "facilities",
      header: "Used by",
      sort: (e) => e.facilities.length,
      render: (e) => (
        <span
          className="block max-w-56 truncate text-xs"
          title={e.facility_names.join(", ")}
        >
          {e.facility_names.map((n) => n.split(" ")[0]).join(", ")}
        </span>
      ),
    },
    {
      key: "count",
      header: "This cycle",
      align: "right",
      sort: (e) => e.count,
      render: (e) => (
        <span className="numeric whitespace-nowrap">
          {e.count}{" "}
          <span className="text-xs text-muted">
            {e.count === 1 ? e.unit.replace(/s$/, "") : e.unit}
          </span>
        </span>
      ),
    },
    {
      key: "changed",
      header: "Last changed",
      sort: (e) => e.last_changed,
      render: (e) => (
        <span className="numeric whitespace-nowrap text-xs">
          {when(e.last_changed)}{" "}
          <span className="text-muted">· {e.changed_by}</span>
        </span>
      ),
    },
  ];
  return (
    <>
      <Kpis
        items={[
          { label: "Stored layouts", value: library.length },
          { label: "Document types", value: types.length },
          {
            label: "Senders",
            value: new Set(library.map((e) => e.sender)).size,
          },
          {
            label: "Files this cycle",
            value: library
              .filter((e) => e.unit === "files")
              .reduce((n, e) => n + e.count, 0),
          },
          {
            label: "Obligor documents",
            value: library
              .filter((e) => e.unit === "obligors")
              .reduce((n, e) => n + e.count, 0),
          },
          {
            label: "Daily files",
            value: library
              .filter((e) => e.unit === "daily files")
              .reduce((n, e) => n + e.count, 0),
          },
        ]}
      />
      <div className="grid grid-cols-[minmax(0,1fr)_22rem] gap-3">
        <DataTable
          rows={rows}
          columns={columns}
          rowKey={(e) => e.id}
          search={(e) =>
            `${e.id} ${e.document} ${e.sender} ${e.facility_names.join(" ")}`
          }
          searchPlaceholder="Filter layouts"
          initialSort={{ key: "document", dir: "asc" }}
          onRowClick={(e) => setSelected(e.id)}
          selected={selected}
          toolbar={
            <FilterSelect
              label="Document type"
              value={type}
              onChange={setType}
              options={[
                { value: "all", label: "All document types" },
                ...types.map((t) => ({ value: t, label: t })),
              ]}
            />
          }
        />
        {entry && (
          <div className="space-y-3 self-start">
            <Panel title={entry.document} meta={entry.id}>
              <dl className="grid grid-cols-[6rem_1fr] gap-x-2 gap-y-1 text-xs">
                <dt className="text-muted">Sender</dt>
                <dd>{entry.sender}</dd>
                <dt className="text-muted">Format</dt>
                <dd className="font-mono">{entry.format}</dd>
                {entry.columns && (
                  <>
                    <dt className="text-muted">Columns</dt>
                    <dd className="numeric">{entry.columns}</dd>
                  </>
                )}
                {entry.signature && (
                  <>
                    <dt className="text-muted">Recognised by</dt>
                    <dd>
                      Heading <q className="font-medium">{entry.signature}</q>
                    </dd>
                  </>
                )}
                <dt className="text-muted">Client memory</dt>
                <dd className="flex items-center gap-1.5">
                  {clients[entry.client]?.name}
                  {!clients[entry.client]?.ai_permitted && (
                    <NoAiBadge compact />
                  )}
                </dd>
                <dt className="text-muted">Used by</dt>
                <dd>{entry.facility_names.join(", ")}</dd>
                <dt className="text-muted">This cycle</dt>
                <dd className="numeric">
                  {entry.count} {entry.unit}
                </dd>
              </dl>
              {entry.obligors.length > 0 && (
                <p className="mt-2 font-mono text-[0.6875rem] leading-relaxed text-muted">
                  {entry.obligors.join(" ")}
                </p>
              )}
            </Panel>
            <Panel title="Version history" meta={`${entry.versions.length}`}>
              <ol className="space-y-2">
                {[...entry.versions].reverse().map((v) => (
                  <li key={v.version} className="text-xs">
                    <p className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5">
                        <Badge
                          tone={
                            v.version === entry.version ? "info" : "neutral"
                          }
                        >
                          v{v.version}
                        </Badge>
                        <span className="numeric text-muted">
                          {when(v.date)}
                        </span>
                      </span>
                      <Person name={v.by} />
                    </p>
                    <p className="mt-0.5">{v.change}</p>
                  </li>
                ))}
              </ol>
            </Panel>
          </div>
        )}
      </div>
    </>
  );
}

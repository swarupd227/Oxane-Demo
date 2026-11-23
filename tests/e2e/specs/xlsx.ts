/* Read a downloaded .xlsx without a dependency: an .xlsx is a zip of XML parts, so this reads the
 * zip's central directory, inflates each part with node's zlib and pulls out sheets, cell values
 * and formulas. Enough for the tests to check what a workbook holds, not a general reader. */
import { inflateRawSync } from "node:zlib";

export interface Cell {
  ref: string;
  value: string;
  formula: string | null;
}

export interface Sheet {
  name: string;
  cells: Map<string, Cell>;
  /** Column A of each row, in row order, from row 1. */
  rows: Cell[][];
}

function unzip(buffer: Buffer): Map<string, string> {
  const files = new Map<string, string>();
  // End of central directory: signature 0x06054b50, searched from the end.
  let end = buffer.length - 22;
  while (end >= 0 && buffer.readUInt32LE(end) !== 0x06054b50) {
    end -= 1;
  }
  if (end < 0) {
    throw new Error("Not a zip file");
  }
  const count = buffer.readUInt16LE(end + 10);
  let at = buffer.readUInt32LE(end + 16);
  for (let i = 0; i < count; i++) {
    const method = buffer.readUInt16LE(at + 10);
    const size = buffer.readUInt32LE(at + 20);
    const nameLength = buffer.readUInt16LE(at + 28);
    const extraLength = buffer.readUInt16LE(at + 30);
    const commentLength = buffer.readUInt16LE(at + 32);
    const local = buffer.readUInt32LE(at + 42);
    const name = buffer.toString("utf8", at + 46, at + 46 + nameLength);
    const dataAt = local + 30 + buffer.readUInt16LE(local + 26) + buffer.readUInt16LE(local + 28);
    const raw = buffer.subarray(dataAt, dataAt + size);
    files.set(name, (method === 8 ? inflateRawSync(raw) : raw).toString("utf8"));
    at += 46 + nameLength + extraLength + commentLength;
  }
  return files;
}

function unescape(text: string): string {
  return text
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, "&");
}

export function readWorkbook(buffer: Buffer): Map<string, Sheet> {
  const files = unzip(buffer);
  const shared = [...(files.get("xl/sharedStrings.xml") ?? "").matchAll(/<si>([\s\S]*?)<\/si>/g)].map((m) =>
    unescape([...m[1].matchAll(/<t[^>]*>([\s\S]*?)<\/t>/g)].map((t) => t[1]).join("")),
  );
  const rels = new Map(
    [...(files.get("xl/_rels/workbook.xml.rels") ?? "").matchAll(/<Relationship [^>]*>/g)].map((m) => [
      m[0].match(/\bId="([^"]+)"/)?.[1] ?? "",
      m[0].match(/\bTarget="([^"]+)"/)?.[1] ?? "",
    ]),
  );
  const sheets = new Map<string, Sheet>();
  for (const m of (files.get("xl/workbook.xml") ?? "").matchAll(/<sheet [^>]*name="([^"]+)"[^>]*r:id="([^"]+)"/g)) {
    const name = unescape(m[1]);
    const target = rels.get(m[2]) ?? "";
    const xml = files.get(target.startsWith("/") ? target.slice(1) : `xl/${target}`) ?? "";
    const cells = new Map<string, Cell>();
    const rows: Cell[][] = [];
    for (const row of xml.matchAll(/<row [^>]*>([\s\S]*?)<\/row>/g)) {
      const line: Cell[] = [];
      for (const c of row[1].matchAll(/<c r="([A-Z]+\d+)"([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g)) {
        const body = c[3] ?? "";
        const type = c[2].match(/t="(\w+)"/)?.[1];
        const formula = body.match(/<f[^>]*>([\s\S]*?)<\/f>/)?.[1];
        const v = body.match(/<v>([\s\S]*?)<\/v>/)?.[1];
        const inline = body.match(/<is>[\s\S]*?<t[^>]*>([\s\S]*?)<\/t>/)?.[1];
        const value = type === "s" && v !== undefined ? shared[Number(v)] : unescape(inline ?? v ?? "");
        const cell = { ref: c[1], value, formula: formula !== undefined ? unescape(formula) : null };
        cells.set(c[1], cell);
        line.push(cell);
      }
      rows.push(line);
    }
    sheets.set(name, { name, cells, rows });
  }
  return sheets;
}

export async function readDownload(download: { createReadStream: () => Promise<NodeJS.ReadableStream> }): Promise<Buffer> {
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) {
    chunks.push(Buffer.from(chunk as Buffer));
  }
  return Buffer.concat(chunks);
}

/* The workbook reader the monitoring and onboarding specs use, checked on a workbook built here in
 * openpyxl's own layout (relationship Target before Id, inline strings, shared strings, formulas).
 * No browser and no server: it only guards the helper. */
import { expect, test } from "@playwright/test";
import { deflateRawSync } from "node:zlib";
import { readWorkbook } from "./xlsx";

function zip(files: Record<string, string>): Buffer {
  const locals: Buffer[] = [];
  const central: Buffer[] = [];
  let offset = 0;
  for (const [name, text] of Object.entries(files)) {
    const data = deflateRawSync(Buffer.from(text, "utf8"));
    const nameBytes = Buffer.from(name, "utf8");
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(8, 8);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(Buffer.byteLength(text), 22);
    local.writeUInt16LE(nameBytes.length, 26);
    locals.push(local, nameBytes, data);
    const entry = Buffer.alloc(46);
    entry.writeUInt32LE(0x02014b50, 0);
    entry.writeUInt16LE(20, 4);
    entry.writeUInt16LE(20, 6);
    entry.writeUInt16LE(8, 10);
    entry.writeUInt32LE(data.length, 20);
    entry.writeUInt32LE(Buffer.byteLength(text), 24);
    entry.writeUInt16LE(nameBytes.length, 28);
    entry.writeUInt32LE(offset, 42);
    central.push(entry, nameBytes);
    offset += 30 + nameBytes.length + data.length;
  }
  const directory = Buffer.concat(central);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(Object.keys(files).length, 8);
  end.writeUInt16LE(Object.keys(files).length, 10);
  end.writeUInt32LE(directory.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, directory, end]);
}

const NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"';

test("the workbook reader finds sheets, inline and shared strings, numbers and formulas", () => {
  const book = readWorkbook(
    zip({
      "xl/workbook.xml": `<workbook ${NS} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Summary" sheetId="1" r:id="rId1"/><sheet name="Calc &amp; QC" sheetId="2" r:id="rId2"/></sheets></workbook>`,
      // openpyxl writes Type, then Target, then Id, with absolute targets.
      "xl/_rels/workbook.xml.rels": `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Type="worksheet" Target="/xl/worksheets/sheet1.xml" Id="rId1" /><Relationship Type="worksheet" Target="worksheets/sheet2.xml" Id="rId2" /></Relationships>`,
      "xl/sharedStrings.xml": `<sst ${NS}><si><t>Eligible pool</t></si><si><r><t>Borrowing</t></r><r><t xml:space="preserve"> base</t></r></si></sst>`,
      "xl/worksheets/sheet1.xml": `<worksheet ${NS}><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Title</t></is></c></row><row r="2"><c r="A2" s="2" t="inlineStr"><is><t>PROVISIONAL: not for release until every approval level has signed off</t></is></c></row></sheetData></worksheet>`,
      "xl/worksheets/sheet2.xml": `<worksheet ${NS}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>67818516.5</v></c></row><row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><f>ROUND(B1*0.825,2)</f><v></v></c><c r="C2"/></row></sheetData></worksheet>`,
    }),
  );
  expect([...book.keys()]).toEqual(["Summary", "Calc & QC"]);
  expect(book.get("Summary")!.cells.get("A2")!.value).toBe("PROVISIONAL: not for release until every approval level has signed off");
  const calc = book.get("Calc & QC")!;
  expect(calc.cells.get("A1")!.value).toBe("Eligible pool");
  expect(calc.cells.get("A2")!.value).toBe("Borrowing base");
  expect(calc.cells.get("B1")!.value).toBe("67818516.5");
  expect(calc.cells.get("B2")!.formula).toBe("ROUND(B1*0.825,2)");
  expect(calc.rows.map((r) => r.length)).toEqual([2, 3]);
});

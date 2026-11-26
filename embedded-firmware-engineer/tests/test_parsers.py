import base64
import importlib.util
import shutil
from urllib.parse import quote
import zlib
from zipfile import ZipFile

from support import ProjectCase


class ParserTests(ProjectCase):
    def parse(self, path, *options, code=0):
        return self.report("parse_documents", "--file", path, *options, code=code)["documents"][0]

    def package(self, path, parts):
        file = self.put(path, b"")
        with ZipFile(file, "w") as bundle:
            for name, content in parts.items():
                bundle.writestr(name, content)

    def test_svg_label_and_document_fingerprint_scope(self):
        self.run_cli("init_project")
        body = '<svg xmlns="http://www.w3.org/2000/svg"><text id="board-pad" x="4">PA9</text></svg>'
        doc = self.prepare_document("docs/board.svg", body)
        doc.update(version="A", scope="R1")
        self.write_state("documents", {"schema_version": 1, "documents": [doc]})
        fact, = self.parse(doc["path"])["facts"]
        self.assertEqual((fact["document_id"], fact["version"], fact["scope"]), (doc["id"], "A", "R1"))
        self.assertEqual((fact["category"], fact["evidence"], fact["confirmation"]), ("pin", "drawing_label", "Unconfirmed"))
        self.assertEqual(fact["location"]["id"], "board-pad")
        self.assertEqual(fact["id"], self.parse(doc["path"])["facts"][0]["id"])
        self.put(doc["path"], body.replace("PA9", "PA8"))
        changed = self.parse(doc["path"])
        self.assertFalse(changed["baseline_match"])
        self.assertIsNone(changed["facts"][0]["scope"])

    def test_excel_has_actual_sheet_cells_formulas_and_cache(self):
        self.package("board.xlsx", {
            "xl/workbook.xml": '<workbook xmlns:r="urn:rels"><sheets><sheet name="Pins" r:id="r1"/></sheets></workbook>',
            "xl/_rels/workbook.xml.rels": '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>',
            "xl/worksheets/sheet1.xml": '<worksheet><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row>'
            '<row r="2"><c r="B2"><f>A2*2</f><v>12</v></c><c r="C2"><f>A2*3</f></c></row></sheetData></worksheet>',
            "xl/sharedStrings.xml": '<sst><si><t>Voltage</t></si></sst>',
        })
        cells = {item["location"]["cell"]: item for item in self.parse("board.xlsx")["facts"]}
        self.assertEqual(cells["A1"]["content"]["value"], "Voltage")
        self.assertTrue(cells["A1"]["content"]["header_candidate"])
        self.assertEqual(cells["B2"]["location"]["sheet"], "Pins")
        self.assertEqual(cells["B2"]["raw"], {"value": "12", "formula": "A2*2"})
        self.assertIsNone(cells["C2"]["content"]["cached_value"])

    def test_word_and_powerpoint_extract_tables_and_image_references(self):
        self.package("board.docx", {
            "word/document.xml": '<document xmlns:r="urn:r"><body><p><r><t>Board</t><blip r:embed="img"/></r></p>'
            '<tbl><tr><tc><p><r><t>PA9</t></r></p></tc></tr></tbl></body></document>',
            "word/_rels/document.xml.rels": '<Relationships><Relationship Id="img" Target="media/a.png"/></Relationships>',
            "word/media/a.png": b"\x89PNG",
        })
        facts = self.parse("board.docx")["facts"]
        self.assertEqual({row["category"] for row in facts}, {"paragraph", "image", "table_row"})
        self.assertEqual(next(row for row in facts if row["category"] == "table_row")["location"]["block"], 2)
        self.assertNotIn("image_data", next(row for row in facts if row["category"] == "image")["content"])
        image = next(row for row in self.parse("board.docx", "--include-images")["facts"] if row["category"] == "image")
        self.assertEqual(base64.b64decode(image["content"]["image_data"]["value"]), b"\x89PNG")
        self.package("board.pptx", {
            "ppt/presentation.xml": '<presentation xmlns:r="urn:r"><sldId id="9" r:id="s"/></presentation>',
            "ppt/_rels/presentation.xml.rels": '<Relationships><Relationship Id="s" Target="slides/slide3.xml"/></Relationships>',
            "ppt/slides/slide3.xml": '<sld><p><t>Oscillator</t></p></sld>',
        })
        fact, = self.parse("board.pptx")["facts"]
        self.assertEqual(fact["location"]["slide"], 1)
        self.assertEqual(fact["raw"], "Oscillator")

    def test_compressed_drawio_and_visio_connection_locations(self):
        page = '<mxGraphModel><root><mxCell id="w1" edge="1" source="U1" target="U2"/></root></mxGraphModel>'
        compressor = zlib.compressobj(wbits=-15)
        data = base64.b64encode(compressor.compress(quote(page).encode("ascii")) + compressor.flush()).decode("ascii")
        self.put("drawing.drawio", f"<mxfile><diagram>{data}</diagram></mxfile>")
        edge, = self.parse("drawing.drawio")["facts"]
        self.assertEqual((edge["location"]["id"], edge["content"]["target"]), ("w1", "U2"))
        self.package("drawing.vsdx", {
            "visio/pages/pages.xml": '<Pages xmlns:r="urn:r"><Page ID="2"><Rel r:id="r1"/></Page></Pages>',
            "visio/pages/_rels/pages.xml.rels": '<Relationships><Relationship Id="r1" Target="page2.xml"/></Relationships>',
            "visio/pages/page2.xml": '<PageContents><Shapes><Shape ID="7"><Text>Sensor</Text></Shape></Shapes><Connects>'
            '<Connect FromSheet="7" ToSheet="8"/></Connects></PageContents>',
        })
        facts = self.parse("drawing.vsdx")["facts"]
        self.assertEqual([row["category"] for row in facts], ["diagram_shape", "diagram_edge"])
        self.assertEqual(facts[1]["content"]["ToSheet"], "8")

    def test_kicad_netlist_and_native_drawing_have_distinct_evidence(self):
        self.put("fixture.kicad_sch", '(kicad_sch\n(symbol (lib_id "MCU:STM32F103") (at 10 20 0)'
                 ' (property "Reference" "U1"))\n(label "VDD" (at 10 20 0))\n(wire (pts (xy 10 20) (xy 20 20))))')
        facts = self.parse("fixture.kicad_sch")["facts"]
        self.assertEqual([(row["category"], row["location"]["line"]) for row in facts],
                         [("component", 2), ("power", 3), ("wire_geometry", 4)])
        self.put("fixture.xml", '<export><nets><net name="VDD"><node ref="U1" pin="8"/></net></nets></export>')
        net, = self.parse("fixture.xml")["facts"]
        self.assertEqual(net["content"], {"net": "VDD", "ref": "U1", "pin": "8"})
        self.assertEqual(net["evidence"], "netlist")
        self.put("fixture.SchDoc", "|RECORD=1|DESIGNATOR=U1|COMMENT=STM32|")
        self.assertEqual(self.parse("fixture.SchDoc")["facts"][0]["content"]["DESIGNATOR"], "U1")

    def test_csv_multiline_and_source_locations(self):
        self.put("bom.csv", 'Ref,Value\nU1,"two\nlines"\n')
        self.assertEqual(self.parse("bom.csv")["facts"][1]["location"], {"row": 2, "line": 2, "line_end": 3})
        self.put("board.cpp", '#include "pin.h"\n\n#define LED_PIN 8\n')
        self.assertEqual([fact["location"]["line"] for fact in self.parse("board.cpp")["facts"]], [1, 3])
        self.put("board.yml", "u1: PA9\n")
        if importlib.util.find_spec("yaml"):
            self.assertEqual(self.parse("board.yml")["facts"][1]["location"], {"line": 1, "column": 5})
        else:
            self.assertEqual(self.parse("board.yml", code=1)["status"], "unavailable")

    def test_real_pdf_has_page_location_and_scanned_page_is_partial(self):
        draw = (b"BT /F1 12 Tf 10 80 Td (Voltage 3.3 V) Tj ET\n"
                b"10 10 m 110 10 l S 10 30 m 110 30 l S 10 50 m 110 50 l S\n"
                b"10 10 m 10 50 l S 60 10 m 60 50 l S 110 10 m 110 50 l S\n"
                b"BT /F1 9 Tf 15 38 Td (Pin) Tj ET\nq 20 0 0 20 125 30 cm /Im1 Do Q")
        objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R 6 0 R] /Count 2 >>",
                   b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 160 100] /Resources << /Font << /F1 4 0 R >> /XObject << /Im1 7 0 R >> >> /Contents 5 0 R >>",
                   b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
                   b"<< /Length %d >>\nstream\n" % len(draw) + draw + b"\nendstream",
                   b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 160 100] >>",
                   b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Length 3 >>\nstream\n"
                   b"\xFF\x00\x00\nendstream"]
        content = bytearray(b"%PDF-1.4\n")
        offsets = []
        for number, obj in enumerate(objects, 1):
            offsets.append(len(content))
            content.extend(b"%d 0 obj\n" % number + obj + b"\nendobj\n")
        xref = len(content)
        content.extend(b"xref\n0 8\n0000000000 65535 f \n")
        for offset in offsets:
            content.extend(b"%010d 00000 n \n" % offset)
        content.extend(b"trailer\n<< /Size 8 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref)
        self.put("board.pdf", bytes(content))
        if importlib.util.find_spec("pdfplumber") or shutil.which("pdftotext"):
            report = self.parse("board.pdf", "--include-images")
            self.assertEqual(report["status"], "partial")
            page, = [fact for fact in report["facts"] if fact["category"] == "page_text"]
            self.assertEqual(page["location"], {"page": 1})
            self.assertIn("Voltage 3.3 V", page["raw"])
            if report["method"] == "pdfplumber":
                table, = [fact for fact in report["facts"] if fact["category"] == "table"]
                self.assertEqual(table["content"][0][0], "Pin")
                image, = [fact for fact in report["facts"] if fact["category"] == "image"]
                self.assertEqual(image["location"]["page"], 1)
                self.assertTrue(base64.b64decode(image["content"]["image_data"]["value"]).startswith(b"\x89PNG"))
        else:
            self.assertIn("pdfplumber", self.parse("board.pdf", code=1)["error"])

    def test_legacy_binary_and_unsafe_inputs_are_explicit(self):
        for path in ("board.doc", "board.xls", "board.ppt", "drawing.vsd", "board.PcbDoc"):
            self.put(path, b"\xd0\xcf\x11\xe0")
            result = self.parse(path, code=1)
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["facts"], [])
        self.put("broken.svg", '<!DOCTYPE svg [<!ENTITY x "example">]><svg><text>&x;</text></svg>')
        self.assertIn("DTD", self.parse("broken.svg", code=1)["error"])
        self.run_cli("parse_documents", "--file", "../document.pdf", code=2)

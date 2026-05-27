import tempfile
import unittest
from pathlib import Path

import fitz

from src.qa import QAError, find_text_overflow, run_qa


class QATextOverflowTest(unittest.TestCase):
    def write_pdf(self, draw):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / 'sample.pdf'
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        draw(doc, page)
        doc.save(path)
        doc.close()
        self.addCleanup(tmp.cleanup)
        return path

    def test_run_qa_reports_bottom_text_overflow_with_page_and_coordinate(self):
        pdf_path = self.write_pdf(
            lambda _doc, page: page.insert_text((72, 835), 'Texte coupe sous la marge basse', fontsize=12)
        )

        with self.assertRaises(QAError) as ctx:
            run_qa(pdf_path)

        report = ctx.exception.report
        hit = report['text_overflow_hits'][0]
        self.assertFalse(report['passed'])
        self.assertEqual(hit['page'], 1)
        self.assertEqual(hit['side'], 'bottom')
        self.assertGreater(hit['coordinate'], hit['limit'])
        self.assertIn('Texte hors zone lisible page 1', hit['message'])
        self.assertIn('Texte coupe', hit['text'])

    def test_image_near_bottom_does_not_trigger_text_overflow(self):
        pdf_path = self.write_pdf(
            lambda doc, page: page.insert_image(
                fitz.Rect(100, 800, 160, 840),
                pixmap=fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), 0),
            )
        )
        doc = fitz.open(pdf_path)
        self.addCleanup(doc.close)

        self.assertEqual(find_text_overflow(doc), [])

    def test_regular_text_inside_readable_area_passes_overflow_helper(self):
        pdf_path = self.write_pdf(
            lambda _doc, page: page.insert_text((72, 120), 'Texte normal dans la zone lisible', fontsize=12)
        )
        doc = fitz.open(pdf_path)
        self.addCleanup(doc.close)

        self.assertEqual(find_text_overflow(doc), [])


if __name__ == '__main__':
    unittest.main()

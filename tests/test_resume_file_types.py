import io
import unittest
import zipfile

from features.resume_documents import file_types


class ResumeFileTypeTests(unittest.TestCase):
    def zip_bytes(self, entries):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for name, content in entries.items():
                archive.writestr(name, content)
        return output.getvalue()

    def test_all_requested_document_and_image_extensions_are_supported(self):
        self.assertEqual(file_types.DOCUMENT_EXTENSIONS, (
            '.txt', '.md', '.mdx', '.markdown', '.pdf', '.html', '.xlsx', '.xls',
            '.doc', '.docx', '.csv', '.eml', '.msg', '.pptx', '.ppt', '.xml', '.epub',
        ))
        self.assertEqual(file_types.IMAGE_EXTENSIONS, (
            '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg',
        ))

    def test_content_validation_covers_each_supported_file_family(self):
        ole = bytes.fromhex('D0CF11E0A1B11AE1') + b'legacy-office'
        fixtures = {
            '.txt': b'Resume text', '.md': b'# Resume', '.mdx': b'# Resume',
            '.markdown': b'# Resume', '.html': b'<!doctype html><html></html>',
            '.csv': b'name,phone\nTest,123', '.eml': b'From: test@example.com\nSubject: Resume\n',
            '.xml': b'<?xml version="1.0"?><resume/>', '.svg': b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
            '.pdf': b'%PDF-1.4\nresume', '.jpg': b'\xff\xd8\xffresume', '.jpeg': b'\xff\xd8\xffresume',
            '.png': b'\x89PNG\r\n\x1a\nresume', '.gif': b'GIF89aresume',
            '.webp': b'RIFF\x0c\x00\x00\x00WEBPresume',
            '.doc': ole, '.xls': ole, '.msg': ole, '.ppt': ole,
            '.docx': self.zip_bytes({'[Content_Types].xml': '', 'word/document.xml': '<w:document/>'}),
            '.xlsx': self.zip_bytes({'[Content_Types].xml': '', 'xl/workbook.xml': '<workbook/>'}),
            '.pptx': self.zip_bytes({'[Content_Types].xml': '', 'ppt/presentation.xml': '<presentation/>'}),
            '.epub': self.zip_bytes({'mimetype': 'application/epub+zip', 'META-INF/container.xml': '<container/>'}),
        }
        self.assertEqual(set(fixtures), set(file_types.ALL_EXTENSIONS))
        for extension, content in fixtures.items():
            with self.subTest(extension=extension):
                self.assertTrue(file_types.valid_content(extension, content))
        self.assertFalse(file_types.valid_content('.pdf', b'not a pdf'))
        self.assertFalse(file_types.valid_content('.svg', b'<script>alert(1)</script>'))

    def test_dify_kind_and_mime_follow_the_original_file(self):
        self.assertEqual(file_types.dify_kind('resume.png'), 'image')
        self.assertEqual(file_types.dify_kind('resume.docx'), 'document')
        self.assertEqual(file_types.mime_type('resume.PNG'), 'image/png')
        self.assertEqual(file_types.mime_type('resume.docx'), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')


if __name__ == '__main__':
    unittest.main()

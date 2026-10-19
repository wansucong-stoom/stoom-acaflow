"""Release validation detects omissions and stale bytes, not just ZIP readability."""
import importlib.util
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('release_verifier', ROOT / 'scripts/verify_release.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class ReleaseVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def archive(self, entries):
        path = self.root / 'release.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            for name, value in entries:
                archive.writestr(name, value)
        return path

    def test_missing_recovery_reference_is_rejected(self):
        path = self.archive([('academyinfo-flow/SKILL.md', b'skill')])
        with self.assertRaisesRegex(ValueError, 'inventory differs'):
            verifier.archive_bytes(path, {'academyinfo-flow/SKILL.md': b'skill',
                'academyinfo-flow/references/report-recovery.md': b'recovery'})

    def test_old_source_with_same_filename_is_rejected(self):
        path = self.archive([('academyinfo-flow/SKILL.md', b'old')])
        with self.assertRaisesRegex(ValueError, 'stale source'):
            verifier.archive_bytes(path, {'academyinfo-flow/SKILL.md': b'new'})

    def test_escaping_archive_member_is_rejected(self):
        path = self.archive([('../outside', b'data')])
        with self.assertRaisesRegex(ValueError, 'Unsafe archive member'):
            verifier.archive_bytes(path, {'../outside': b'data'})

    def test_relative_links_are_resolved_from_the_document(self):
        (self.root / 'docs').mkdir()
        (self.root / 'README.md').write_text('[guide](docs/guide.md)', encoding='utf-8')
        guide = self.root / 'docs/guide.md'
        guide.write_text('[home](../README.md#intro)', encoding='utf-8')
        self.assertEqual(verifier.markdown_links(self.root), 2)
        guide.write_text('[missing](absent.md)', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Broken or escaping local link'):
            verifier.markdown_links(self.root)

    def test_download_checksum_rejects_changed_binary(self):
        artifact = self.root / 'release.zip'
        artifact.write_bytes(b'original')
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        (self.root / 'SHA256SUMS').write_text(digest + '  release.zip\n', encoding='utf-8')
        self.assertEqual(verifier.download_checksums(self.root), 1)
        artifact.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'checksum differs'):
            verifier.download_checksums(self.root)

    def test_download_checksum_requires_every_published_archive(self):
        (self.root / 'release.zip').write_bytes(b'original')
        (self.root / 'SHA256SUMS').write_text('', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'inventory differs'):
            verifier.download_checksums(self.root)


if __name__ == '__main__':
    unittest.main()

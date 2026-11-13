import io
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
from PIL import Image
from core import Game, SERIAL, SIZES, complete, disc_serial, download, process, scan, serial_id, valid_cover, write_pair


def fixture(vcd=False, ps1=False):
    data = bytearray(24 * 2048)
    data[16 * 2048:16 * 2048 + 6] = b'\x01CD001'
    struct.pack_into('<I', data, 16 * 2048 + 158, 18)
    struct.pack_into('<I', data, 16 * 2048 + 166, 2048)
    pos = 18 * 2048
    data[pos] = 46
    struct.pack_into('<I', data, pos + 2, 20)
    text = b'BOOT = cdrom:\\SLUS_007.47;1\r\n' if ps1 else b'BOOT2 = cdrom0:\\SLUS_213.76;1\r\n'
    struct.pack_into('<I', data, pos + 10, len(text))
    data[pos + 32] = 12
    data[pos + 33:pos + 45] = b'SYSTEM.CNF;1'
    data[20 * 2048:20 * 2048 + len(text)] = text
    if not vcd:
        return bytes(data)
    raw = bytearray(0x100000 + 24 * 2352)
    for lba in range(24):
        raw[0x100000 + lba * 2352 + 24:0x100000 + lba * 2352 + 24 + 2048] = data[lba * 2048:(lba + 1) * 2048]
    return bytes(raw)


class CoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.img = Image.new('RGB', (24, 32), (80, 160, 248))

    def test_identification_reads_iso_and_vcd_not_title_guess(self):
        for name, vcd, expected in [('Black.iso', False, 'SLUS-21376'), ('Crash.vcd', True, 'SLUS-00747')]:
            path = self.root / name
            path.write_bytes(fixture(vcd, vcd))
            self.assertEqual(disc_serial(path), expected)
        self.assertEqual(serial_id('SCUS_973.99.God of War.iso'), 'SCUS-97399')
        self.assertEqual(serial_id('Black.iso'), '')
        self.assertEqual(serial_id('SLUS-213760'), '')

    def test_scan_handles_case_and_unidentified_games(self):
        dvd, pops = self.root / 'dvd', self.root / 'POPS'
        dvd.mkdir(); pops.mkdir()
        (dvd / 'Game.ISO').write_bytes(fixture())
        (dvd / 'Unknown.iso').write_bytes(b'not an iso')
        (pops / 'Game.VCD').write_bytes(fixture(True, True))
        games = scan(self.root)
        self.assertEqual(len(games), 3)
        self.assertEqual({g.serial for g in games}, {'SLUS-21376', 'SLUS-00747', ''})
        self.assertEqual(scan(self.root, lambda: True), [])

    def test_bad_directory_record_does_not_hang(self):
        raw = bytearray(fixture())
        raw[18 * 2048] = 1
        path = self.root / 'Broken.iso'; path.write_bytes(raw)
        self.assertEqual(disc_serial(path), '')

    def test_pair_binary_layout_and_cache_invalidation(self):
        write_pair(self.root, 'SLUS-21376', self.img)
        self.assertTrue(complete(self.root, 'SLUS-21376'))
        for size, suffix in SIZES:
            data = (self.root / 'covers' / f'SLUS-21376{suffix}.c16').read_bytes()
            self.assertEqual(data[:16], b'C16\0' + struct.pack('<II', *size) + bytes(4))
            self.assertEqual(len(data), 16 + size[0] * size[1] * 2)
            self.assertEqual(struct.unpack_from('<H', data, 16)[0], 0x8000 | 10 | 20 << 5 | 31 << 10)
        cache = self.root / 'covers' / 'SLUS-21376_h.c16'
        cache.write_bytes(b'old cache')
        write_pair(self.root, 'SLUS-21376', self.img)
        self.assertFalse(cache.exists())
        (self.root / 'covers' / 'SLUS-21376_s.c16').write_bytes(b'C16\0')
        self.assertFalse(complete(self.root, 'SLUS-21376'))
        with self.assertRaises(ValueError):
            write_pair(self.root, '../bad', self.img)

    def test_import_opl_and_preserve_existing_without_network(self):
        art = self.root / 'ART'; art.mkdir()
        self.img.save(art / 'SLUS_213.76_COV.png')
        game = Game(self.root / 'Black.iso', 'PS2', 'Black', 'SLUS-21376')
        game.path.write_bytes(b'game never modified')
        with patch('core.download', side_effect=AssertionError('unexpected network')):
            self.assertEqual(process(self.root, game, art), 'Importada da ART')
            self.assertEqual(process(self.root, game, art), 'Capa pronta (mantida)')
        self.assertEqual(game.path.read_bytes(), b'game never modified')
        self.assertTrue((art / 'SLUS_213.76_COV.png').is_file())

    def test_second_file_failure_restores_original_pair(self):
        write_pair(self.root, 'SLUS-21376', self.img)
        paths = list((self.root / 'covers').glob('*.c16'))
        before = {p: p.read_bytes() for p in paths}
        import os
        real_replace, count = os.replace, 0
        def failing(a, b):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('disco cheio')
            return real_replace(a, b)
        with patch('core.os.replace', side_effect=failing):
            with self.assertRaises(OSError):
                write_pair(self.root, 'SLUS-21376', Image.new('RGB', (20, 20), 'red'))
        self.assertEqual(before, {p: p.read_bytes() for p in paths})
        self.assertFalse(list((self.root / 'covers').glob('.nuld-capas-*')))

    def test_ps1_url_404_and_cancel(self):
        def missing(req, timeout):
            self.assertIn('/psx-covers/', req.full_url)
            raise urllib.error.HTTPError(req.full_url, 404, 'not found', {}, None)
        with patch('core.urllib.request.urlopen', side_effect=missing):
            with self.assertRaisesRegex(ValueError, 'não disponível'):
                download('SLUS-00747', 'PS1')
        game = Game(self.root / 'a.vcd', 'PS1', 'a', 'SLUS-00747')
        with patch('core.download', side_effect=AssertionError('unexpected network')):
            self.assertEqual(process(self.root, game, cancelled=lambda: True), 'Cancelado')
            self.assertEqual(process(self.root, game, online=False), 'Não encontrada na pasta ART')
        self.assertFalse((self.root / 'covers').exists())


if __name__ == '__main__':
    unittest.main()

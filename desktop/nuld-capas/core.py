"""NULD cover manager: read-only game identification and compatible C16 conversion.
GPL-3.0; converter by danielnuld/nuld (tools/covers.py), original authors retained.
"""
from dataclasses import dataclass
from pathlib import Path
import io
import os
import re
import struct
import sys
import tempfile
import urllib.error
import urllib.request

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from PIL import Image, ImageOps
from covers import SIZES, resize, quantize, c16_bytes

SERIAL = re.compile(r'(?<![A-Z0-9])([A-Z]{4})[_-](\d{3})\.?([0-9]{2})(?![0-9])', re.I)
LIMIT = 8 * 1024 * 1024


def serial_id(text):
    m = SERIAL.search(text)
    return f'{m[1].upper()}-{m[2]}{m[3]}' if m else ''


@dataclass
class Game:
    path: Path
    kind: str
    title: str
    serial: str
    status: str = ''


class Disc:
    def __init__(self, stream, vcd=False):
        self.stream, self.vcd = stream, vcd

    def read(self, lba, size):
        if not self.vcd:
            self.stream.seek(lba * 2048)
            return self.stream.read(size)
        data = bytearray()
        while len(data) < size:
            self.stream.seek(0x100000 + lba * 2352 + 24)
            part = self.stream.read(min(2048, size - len(data)))
            if not part:
                break
            data.extend(part)
            lba += 1
        return bytes(data)


def disc_serial(path):
    """SYSTEM.CNF BOOT2/BOOT, ISO9660 or cue2pops VCD. Never reads whole game."""
    with path.open('rb') as stream:
        disc = Disc(stream, path.suffix.lower() == '.vcd')
        pvd = disc.read(16, 2048)
        if len(pvd) != 2048 or pvd[:6] != b'\x01CD001':
            return ''
        lba, size = struct.unpack_from('<I', pvd, 158)[0], struct.unpack_from('<I', pvd, 166)[0]
        if size > 4 * 1024 * 1024:
            return ''
        for off in range(0, size, 2048):
            sector = disc.read(lba + off // 2048, 2048)
            p = 0
            while p + 33 <= len(sector):
                n = sector[p]
                if not n:
                    break
                if n < 33 or p + n > len(sector):
                    break
                length = sector[p + 32]
                if 33 + length > n:
                    break
                name = sector[p + 33:p + 33 + length].upper()
                if name.split(b';')[0] == b'SYSTEM.CNF':
                    loc = struct.unpack_from('<I', sector, p + 2)[0]
                    count = struct.unpack_from('<I', sector, p + 10)[0]
                    cnf = disc.read(loc, min(count, 4096)).decode('ascii', errors='ignore')
                    boot = re.search(r'^\s*BOOT' + (r'(?!2)' if disc.vcd else '2') + r'\s*=([^\r\n]+)', cnf, re.M | re.I)
                    return serial_id(boot[1]) if boot else ''
                p += n
    return ''


def valid_cover(path, size):
    try:
        with path.open('rb') as f:
            h = f.read(16)
        return (len(h) == 16 and h[:4] == b'C16\0'
                and struct.unpack_from('<II', h, 4) == size
                and path.stat().st_size == 16 + size[0] * size[1] * 2)
    except OSError:
        return False


def complete(root, serial):
    return bool(serial) and all(valid_cover(root / 'covers' / f'{serial}{suffix}.c16', size)
                                for size, suffix in SIZES)


def scan(root, cancelled=lambda: False):
    games = []
    folders = [p for p in root.iterdir() if p.is_dir() and p.name.upper() in ('DVD', 'CD', 'POPS')]
    for folder in sorted(folders):
        for path in sorted(folder.iterdir()):
            if cancelled():
                return games
            kind = 'PS1' if folder.name.upper() == 'POPS' else 'PS2'
            ext = '.vcd' if kind == 'PS1' else '.iso'
            if not path.is_file() or path.suffix.lower() != ext:
                continue
            error = ''
            try:
                serial = disc_serial(path) or serial_id(path.name)
            except (OSError, ValueError, struct.error) as e:
                serial, error = serial_id(path.name), f'Falha ao ler jogo: {e}'
            title = re.sub(r'^[A-Za-z]{4}_\d{3}\.\d{2}\.', '', path.stem)
            status = error or ('Sem código: duplo clique para informar' if not serial else
                               'Capa pronta' if complete(root, serial) else 'Sem capa')
            games.append(Game(path, kind, title, serial, status))
    return games


def find_art(art, game):
    if not art or not art.is_dir():
        return None
    # Prefer exact serial; fallback accepts OPL artwork named after the game file/title.
    names = {f'{game.serial}_COV', f'{game.serial[:4]}_{game.serial[5:8]}.{game.serial[8:]}_COV',
             f'{game.path.stem}_COV', f'{game.title}_COV'}
    for path in art.iterdir():
        if path.is_file() and path.suffix.lower() in ('.png', '.jpg', '.jpeg') and path.stem.casefold() in {n.casefold() for n in names}:
            return path
    return None


def download(serial, kind):
    project = 'psx-covers' if kind == 'PS1' else 'ps2-covers'
    url = f'https://raw.githubusercontent.com/xlenore/{project}/main/covers/default/{serial}.jpg'
    request = urllib.request.Request(url, headers={'User-Agent': 'NULD-Capas/1.0'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read(LIMIT + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError('Capa não disponível para este código') from e
        raise OSError(f'Servidor respondeu HTTP {e.code}') from e
    if len(data) > LIMIT:
        raise ValueError('Imagem excede o limite de 8 MB')
    return io.BytesIO(data)


def write_pair(root, serial, image):
    """Prepare both files before replacement; roll back a partial pair on write error."""
    if serial_id(serial) != serial:
        raise ValueError('Código de jogo inválido')
    out = root / 'covers'
    out.mkdir(exist_ok=True)
    image = ImageOps.exif_transpose(image).convert('RGB')
    encoded = [(suffix, c16_bytes(quantize(resize(image, size), False))) for size, suffix in SIZES]
    with tempfile.TemporaryDirectory(prefix='.nuld-capas-', dir=out) as tmp:
        staged, old = [], {}
        try:
            for suffix, data in encoded:
                dest = out / f'{serial}{suffix}.c16'
                pending = Path(tmp) / dest.name
                pending.write_bytes(data)
                old[dest] = dest.read_bytes() if dest.exists() else None
                staged.append((pending, dest))
            done = []
            try:
                for pending, dest in staged:
                    os.replace(pending, dest)
                    done.append(dest)
            except OSError:
                for dest in done:
                    if old[dest] is None:
                        dest.unlink(missing_ok=True)
                    else:
                        backup = Path(tmp) / (dest.name + '.restore')
                        backup.write_bytes(old[dest])
                        os.replace(backup, dest)
                raise
        finally:
            pass
    (out / f'{serial}_h.c16').unlink(missing_ok=True)


def process(root, game, art=None, replace=False, online=True, cancelled=lambda: False):
    if not game.serial:
        return 'Sem código: duplo clique para informar'
    if complete(root, game.serial) and not replace:
        return 'Capa pronta (mantida)'
    source = find_art(art, game)
    if source is None and not online:
        return 'Não encontrada na pasta ART'
    if cancelled():
        return 'Cancelado'
    content = source if source else download(game.serial, game.kind)
    with Image.open(content) as img:
        if img.width * img.height > 20_000_000:
            raise ValueError('Imagem grande demais')
        img.load()
        if cancelled():
            return 'Cancelado'
        write_pair(root, game.serial, img)
    return 'Importada da ART' if source else 'Baixada e convertida'

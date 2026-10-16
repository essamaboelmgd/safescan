"""Optional official-PyPI wheel download with verified resumable byte ranges.

Used only when a single slow large transfer blocks setup. No installation,
TLS bypass, package execution or external filesystem writes are performed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


def download(package, version, filename, output_dir):
    metadata_url = f'https://pypi.org/pypi/{package}/{version}/json'
    with urlopen(metadata_url, timeout=20) as response:
        metadata = json.load(response)
    record = next(row for row in metadata['urls'] if row['filename'] == filename)
    if not record['url'].startswith('https://files.pythonhosted.org/'):
        raise ValueError('Unexpected package host')
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / filename
    expected_hash = record['digests']['sha256']
    if output.is_file() and hashlib.sha256(output.read_bytes()).hexdigest() == expected_hash:
        print(f'Already verified: {filename}', flush=True)
        return
    chunk_size = 256 * 1024
    ranges = [(start, min(record['size'] - 1, start + chunk_size - 1)) for start in range(0, record['size'], chunk_size)]
    parts = output_dir / (filename + '.parts')
    parts.mkdir(exist_ok=True)

    def part(bounds):
        start, end = bounds
        path = parts / str(start)
        if path.exists() and path.stat().st_size == end - start + 1:
            return path
        for attempt in range(3):
            try:
                request = Request(record['url'], headers={'Range': f'bytes={start}-{end}'})
                with urlopen(request, timeout=20) as response:
                    if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{record["size"]}':
                        raise ValueError('Server did not honor the requested byte range')
                    data = response.read(end - start + 2)
                if len(data) != end - start + 1:
                    raise ValueError('Incomplete byte range')
                path.write_bytes(data)
                return path
            except Exception:
                if attempt == 2:
                    raise

    with ThreadPoolExecutor(max_workers=24) as pool:
        for count, future in enumerate(as_completed([pool.submit(part, bounds) for bounds in ranges]), 1):
            future.result()
            if count % 20 == 0 or count == len(ranges):
                print(f'{filename}: {count}/{len(ranges)} ranges complete', flush=True)
    with output.open('wb') as stream:
        for start, _ in ranges:
            stream.write((parts / str(start)).read_bytes())
    actual_hash = hashlib.sha256(output.read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        raise ValueError('SHA-256 mismatch; wheel must not be installed')
    print(json.dumps({'filename': filename, 'bytes': output.stat().st_size, 'sha256': actual_hash, 'verified_against': metadata_url}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package')
    parser.add_argument('version')
    parser.add_argument('filename')
    parser.add_argument('--output-dir', type=Path, default=Path('.cache/wheels'))
    args = parser.parse_args()
    download(args.package, args.version, args.filename, args.output_dir)

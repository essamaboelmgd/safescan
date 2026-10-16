"""Opt-in food catalogue lookup. It never infers recall or certification claims."""
from datetime import datetime, timezone
import httpx


def fetch_food_metadata(barcode: str):
    url = f'https://world.openfoodfacts.org/api/v2/product/{barcode}.json'
    try:
        response = httpx.get(url, params={'fields': 'code,product_name,brands,categories'}, timeout=5,
                            headers={'User-Agent': 'SafeScanResearch/0.1 (local educational prototype)'}, follow_redirects=False)
        if response.status_code == 404:
            return None, 'Product was not found in the external food catalogue.'
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError('Invalid response')
        record = body.get('product')
        if body.get('status') != 1 or not isinstance(record, dict) or not record.get('product_name'):
            return None, 'External catalogue has no usable product record.'
        return {
            'id': f'off_{barcode}', 'name': str(record['product_name'])[:300],
            'brand': str(record.get('brands', ''))[:200], 'category': str(record.get('categories', ''))[:200],
            'barcode': barcode, 'batch_number': None, 'description': '',
            'source_url': f'https://world.openfoodfacts.org/product/{barcode}',
            'checked_at': datetime.now(timezone.utc).isoformat(), 'evidence': [], 'alternatives': [],
            'source_note': 'Community-maintained food metadata; no authenticity or safety certification is implied.',
        }, None
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return None, 'External metadata service is unavailable or returned invalid data. Local search is still available.'

from pathlib import Path
import uuid

from .algorithms import exact_neighbors, HyperplaneLSH, hamming_distance
from .database import Database
from .metadata import fetch_food_metadata
from .model import Classifier, is_exploratory
from .vision import preprocess, canonical_png, FEATURE_DIM, FEATURE_VERSION

DISCLAIMER = 'AI predictions are estimates, not official authentication. Visual similarity and barcodes cannot prove authenticity or safety.'
UNKNOWN = 'Unknown / Insufficient Evidence'


def decide(prediction, nearest, quality, enable_estimates, conflict=False):
    # Publisher-label agreement cannot support an authenticity verdict, even if
    # the operator enables estimates or imports a visually identical reference.
    if is_exploratory(prediction):
        return UNKNOWN
    if quality or conflict or not enable_estimates or not prediction.get('available') or nearest is None:
        return UNKNOWN
    if prediction.get('confidence', 0) < 0.9 or nearest['similarity_score'] < 0.9:
        return UNKNOWN
    if prediction['prediction'] != nearest['label']:
        return UNKNOWN
    return 'Likely Authentic' if prediction['prediction'] == 'authentic' else 'Suspicious'


class ScanService:
    def __init__(self, settings):
        self.settings = settings
        self.db = Database(settings.data_dir / 'safescan.sqlite3')
        self.model = Classifier(settings.model_path)
        self.image_dir = settings.data_dir / 'images'
        self.image_dir.mkdir(parents=True, exist_ok=True)

    def store_image(self, data):
        if len(data) > self.settings.max_upload_bytes:
            raise OverflowError('Image exceeds 8 MiB upload limit.')
        image = preprocess(data, self.settings.max_pixels)
        image_id = uuid.uuid4().hex
        path = self.image_dir / f'{image_id}.png'
        path.write_bytes(canonical_png(image))
        self.db.add_upload(image_id, path)
        return {'upload_id': image_id, 'width': 224, 'height': 224, 'warnings': image.warnings}

    def image(self, image_id):
        record = self.db.upload(image_id)
        if not record or not Path(record['path']).is_file():
            raise FileNotFoundError('Upload does not exist. Upload the image again.')
        return preprocess(Path(record['path']).read_bytes(), self.settings.max_pixels)

    def search(self, image_id, k=5, algorithm='exact'):
        image = self.image(image_id)
        references = [r for r in self.db.references() if r['feature_version'] == FEATURE_VERSION]
        vectors = [r['features'] for r in references]
        if algorithm == 'lsh':
            index = HyperplaneLSH(FEATURE_DIM)
            for vector in vectors:
                index.add(vector)
            neighbors = index.search(image.features, k)
        else:
            neighbors = exact_neighbors(image.features, vectors, k)
        matches = []
        for position, score in neighbors:
            record = references[position]
            matches.append({
                'reference_id': record['id'], 'product_id': record['product_id'], 'label': record['label'],
                'source_url': record['source_url'], 'similarity_score': score,
                'phash_distance': hamming_distance(image.phash, record['phash']),
                'image_url': f"/api/uploads/{record['upload_id']}/image",
            })
        return {'algorithm': algorithm, 'approximate': algorithm == 'lsh', 'matches': matches,
                'reference_count': len(references), 'warnings': image.warnings,
                'score_note': 'Cosine similarity is not authenticity confidence.'}

    def lookup(self, barcode):
        product = self.db.by_barcode(barcode)
        if product:
            return {'product': product, 'source': 'local', 'warnings': []}
        if self.settings.network_metadata:
            product, warning = fetch_food_metadata(barcode)
            return {'product': product, 'source': 'openfoodfacts' if product else None, 'warnings': [warning] if warning else []}
        return {'product': None, 'source': None, 'warnings': ['No local record. External metadata lookup is disabled.']}

    def verify(self, request):
        image = self.image(request.upload_id)
        prediction = self.model.predict(image.features)
        search = self.search(request.upload_id, 5, request.algorithm)
        nearest = search['matches'][0] if search['matches'] else None
        visual_product = self.db.product(nearest['product_id']) if nearest else None
        lookup = self.lookup(request.barcode) if request.barcode else {'product': None, 'warnings': []}
        barcode_product = lookup['product']
        conflict = bool(request.barcode and visual_product and visual_product.get('barcode') != request.barcode)
        # A visual candidate is never silently promoted to confirmed identity.
        product = barcode_product
        warnings = list(image.warnings) + lookup['warnings']
        explanations = [DISCLAIMER]
        if not self.model.available:
            explanations.append(self.model.reason)
        if self.model.exploratory:
            explanations.append(
                'This exploratory shoe classifier estimates agreement with publisher-provided labels, '
                'which were not independently verified. It cannot establish real-world authenticity. '
                'The final status remains Unknown / Insufficient Evidence regardless of scores or references.'
            )
            warnings.append('Exploratory model: unknown physical-unit identities and remaining source/background bias limit generalization.')
        elif not self.settings.enable_estimates:
            explanations.append('Estimate labels are disabled pending domain validation of the trained model and thresholds.')
        if nearest:
            explanations.append('Nearest reference is a visual candidate; similar product appearance can be copied. Reference labels are catalog claims, not authentication.')
        else:
            explanations.append('No reference candidate found. Add independently verified reference images.')
        if conflict:
            warnings.append('Barcode and visual candidate do not agree, or the candidate has no matching barcode.')
        evidence = []
        for origin, candidate in [('barcode_metadata', product), ('visual_candidate', visual_product)]:
            if candidate:
                for item in candidate.get('evidence', []):
                    evidence.append({**item, 'product_id': candidate['id'], 'association': origin})
        if not evidence:
            warnings.append('No sourced safety records are available. This does not mean there are no recalls or hazards.')
        if evidence:
            warnings.append('Safety records are conditional on product, batch and jurisdiction; confirm their scope at the linked source.')
        decision = decide(prediction, nearest, image.warnings, self.settings.enable_estimates, conflict)
        if decision == UNKNOWN:
            explanations.append('Available evidence does not satisfy all decision gates: model, confidence, reference agreement, image quality and metadata consistency.')
        return self.db.save_scan({
            'upload_id': request.upload_id, 'barcode': request.barcode, 'status': decision,
            'prediction': prediction, 'nearest_reference': nearest,
            'similarity_score': nearest['similarity_score'] if nearest else None,
            'metadata': product, 'visual_candidate_metadata': visual_product,
            'safety_records': evidence, 'warnings': warnings, 'explanations': explanations,
            'disclaimer': DISCLAIMER, 'algorithm': request.algorithm,
        })

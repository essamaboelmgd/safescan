# API documentation

Start at `http://127.0.0.1:8000/docs` for interactive OpenAPI documentation or `/openapi.json` for machine-readable request schemas. The API is local research software with no authentication; use it on a trusted development network. Native Android HTTP requests do not require browser CORS. The app's base URL must be an HTTP(S) origin with no path, credentials, query or fragment.

## Endpoints

| Method and path | Request | Behavior |
|---|---|---|
| `GET /health` | None | Database probe, model availability/reason, reference count, network and estimate settings |
| `POST /api/uploads` | Multipart field `file` | Decode/validate/canonicalize image; 201 with upload id, dimensions and quality warnings |
| `GET /api/uploads/{upload_id}/image` | 32-character lowercase hex id | Canonical PNG, used for reference preview |
| `POST /api/classify` | JSON `upload_id` | Model prediction, scores and disclaimer; 503 if no usable model |
| `POST /api/search` | JSON `upload_id`; query `k=1..20`, `algorithm=exact\|lsh` | Ranked references, similarity, pHash distance, approximation indicator |
| `POST /api/verify` | JSON `upload_id`, optional `barcode`, optional `algorithm` | Combined visual/model/metadata evidence, conservative status and saved scan |
| `GET /api/barcodes/{barcode}` | Checksum-valid GTIN | Local product or opt-in external food metadata; null product on ordinary miss |
| `GET /api/products` | `q` ≤ 200 chars, `limit=1..100`, `offset≥0` | Literal substring search over name/brand/category; `items` array |
| `GET /api/products/{product_id}` | Catalogue id | Complete source-qualified product record or 404 |
| `GET /api/history` | `limit=1..100`, `offset≥0` | Saved evidence snapshots, newest first, `items` array |
| `GET /api/history/{scan_id}` | Saved id | One saved evidence snapshot or 404 |

Products and reference images are imported using `python -m tools.dataset import`, which validates source records. They cannot be added through a public metadata-writing endpoint.

`/health` also returns `model_file`, `model_scope`, `model_label_provenance`, `estimate_labels_requested`, and `estimate_labels_enabled`. The last field is the effective policy: exploratory publisher-label models cannot enable authenticity decision labels, regardless of the requested setting. The default model is the existing `shoes_exploratory_v1.npz`; models load once at startup. See [restart and optional reference import](SHOE_MODEL.md).

## Upload and verify from PowerShell

Use a real image file you have permission to send. Do not use a simulated product as ground truth.

```powershell
curl.exe -F "file=@C:\path\to\your\product.jpg" http://127.0.0.1:8000/api/uploads
```

Copy the actual `upload_id` returned, then:

```powershell
$body = @{ upload_id = 'PASTE_ACTUAL_UPLOAD_ID' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/verify -ContentType 'application/json' -Body $body
```

The placeholder is deliberately not a valid upload id. Add `barcode` only when you have the real item code and its checksum is valid. MIME type and filename are not trusted as image evidence. Acceptable image containers are single-frame JPEG, PNG and WebP; minimum 32 pixels per side, ≤ 12 million source pixels, ≤ 8 MiB encoded bytes. Images are resized with aspect-preserving padding to 224 × 224, then stored as PNG with metadata removed. The limit bounds bytes read by the route; a production proxy must additionally bound total HTTP/multipart bodies and request rates.

## Combined result contract

`POST /api/verify` returns:

- `scan_id`, UTC `created_at`, `upload_id`, nullable `barcode` and chosen `algorithm`.
- `status`: exactly `Likely Authentic`, `Suspicious`, or `Unknown / Insufficient Evidence`.
- `prediction`: `available`, nullable `prediction` and `confidence`; if loaded, class probabilities, model version, `experiment_scope`, `label_provenance` and an uncalibrated-score note; otherwise `reason`. Exploratory scores estimate publisher-label agreement, not physical authenticity.
- `nearest_reference`: nullable candidate with `reference_id`, `product_id`, source URL, reference label, cosine similarity, 64-bit pHash distance and relative preview URL.
- `similarity_score`: nullable cosine score. This is appearance similarity, independent of classifier confidence.
- `metadata`: nullable barcode-associated product; `visual_candidate_metadata`: nullable unconfirmed nearest-reference product. A copied barcode is possible, and neither field authenticates the physical item.
- `safety_records`: sourced imported records with `product_id`, `association` (`barcode_metadata` or `visual_candidate`), claim kind/title, source, scope, jurisdiction and checked timestamp.
- `warnings`, `explanations`, `disclaimer`: readable reasons and limits. Empty safety records do not establish absence of recalls.

Unknown results can still include useful metadata and high visual similarity. Estimate labels are disabled by default. Classification availability is separate from overall API health; missing models do not disable uploading, search, metadata or history. A scan is saved after successful evidence retrieval, including an unknown decision. Failed input requests create no scan snapshot.

## Errors and external services

| Status | Meaning |
|---|---|
| 200 / 201 | Request succeeded; evidence can still be insufficient |
| 404 | Upload, product or scan id is absent |
| 413 | Encoded upload exceeds configured size cap |
| 422 | Invalid JSON/fields, GTIN/checksum, pagination, image format/content or dimensions |
| 503 | Direct classifier endpoint has no usable model |

Errors use FastAPI's `detail` field; field validation errors may be an array. The Flutter client converts server, network and malformed-response failures into readable messages and permits retry. It uses 20-second request/response timeouts. The optional external adapter uses a five-second timeout, fixed host, no redirects and local-first retrieval. Failure returns null external metadata with a warning, never fabricated information. No external safety registry connection is claimed.

The adapter deliberately uses the still-supported v2 food lookup contract to retrieve only basic name/brand/category fields. A future production adapter should migrate against the current versioned provider schema and add provider-compliant caching/rate limiting. It is disabled by default. See the [Open Food Facts API documentation](https://openfoodfacts.github.io/openfoodfacts-server/api/) for current terms, attribution and limits. File uploads follow the [FastAPI request-files interface](https://fastapi.tiangolo.com/tutorial/request-files/).

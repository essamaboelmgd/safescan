from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .schemas import ImageRequest, VerifyRequest, validate_barcode
from .service import ScanService, DISCLAIMER


def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        app.state.service = ScanService(settings)
        yield

    app = FastAPI(title='SafeScan research API', version='0.1.0', description=DISCLAIMER, lifespan=lifespan)

    def service():
        return app.state.service

    @app.exception_handler(FileNotFoundError)
    async def missing_image(_request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={'detail': str(exc)})

    @app.get('/health')
    def health():
        current = service()
        with current.db.connect() as db:
            db.execute('SELECT 1')
        return {'status': 'ok', 'model_available': current.model.available, 'model_reason': current.model.reason,
                'model_file': settings.model_path.name,
                'model_scope': current.model.metadata.get('experiment_scope'),
                'model_label_provenance': current.model.metadata.get('label_provenance'),
                'reference_count': len(current.db.references()), 'network_metadata': settings.network_metadata,
                'estimate_labels_enabled': settings.enable_estimates and not current.model.exploratory,
                'estimate_labels_requested': settings.enable_estimates}

    @app.post('/api/uploads', status_code=201)
    async def upload(file: Annotated[UploadFile, File()]):
        try:
            # Read at most one byte beyond the cap, independent of caller-supplied MIME/filename.
            data = await file.read(settings.max_upload_bytes + 1)
            return await run_in_threadpool(service().store_image, data)
        except OverflowError as exc:
            raise HTTPException(413, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        finally:
            await file.close()

    @app.get('/api/uploads/{upload_id}/image')
    def image(upload_id: str):
        # Path parameter validation is performed explicitly to avoid filesystem interpolation.
        if len(upload_id) != 32 or any(c not in '0123456789abcdef' for c in upload_id):
            raise HTTPException(422, 'Invalid upload id.')
        record = service().db.upload(upload_id)
        if not record or not Path(record['path']).is_file():
            raise HTTPException(404, 'Image not found.')
        return FileResponse(record['path'], media_type='image/png')

    @app.post('/api/classify')
    def classify(request: ImageRequest):
        current = service()
        prediction = current.model.predict(current.image(request.upload_id).features)
        if not prediction['available']:
            raise HTTPException(503, prediction['reason'])
        return {**prediction, 'disclaimer': DISCLAIMER}

    @app.post('/api/search')
    def search(request: ImageRequest, k: Annotated[int, Query(ge=1, le=20)] = 5,
               algorithm: Literal['exact', 'lsh'] = 'exact'):
        return service().search(request.upload_id, k, algorithm)

    @app.post('/api/verify')
    def verify(request: VerifyRequest):
        return service().verify(request)

    @app.get('/api/barcodes/{barcode}')
    def barcode_lookup(barcode: str):
        try:
            validate_barcode(barcode)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return service().lookup(barcode)

    @app.get('/api/products')
    def products(q: Annotated[str, Query(max_length=200)] = '',
                 limit: Annotated[int, Query(ge=1, le=100)] = 25,
                 offset: Annotated[int, Query(ge=0)] = 0):
        return {'items': service().db.products(q, limit, offset)}

    @app.get('/api/products/{product_id}')
    def product(product_id: str):
        record = service().db.product(product_id)
        if not record:
            raise HTTPException(404, 'Product not found.')
        return record

    @app.get('/api/history')
    def history(limit: Annotated[int, Query(ge=1, le=100)] = 20,
                offset: Annotated[int, Query(ge=0)] = 0):
        return {'items': service().db.history(limit, offset)}

    @app.get('/api/history/{scan_id}')
    def scan(scan_id: str):
        record = service().db.scan(scan_id)
        if not record:
            raise HTTPException(404, 'Scan not found.')
        return record

    return app


app = create_app()

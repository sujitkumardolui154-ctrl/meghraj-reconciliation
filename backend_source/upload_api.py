"""Dashboard v1.3.0: private Excel intake, not financial execution.
Authentication is enforced by the existing Cloud Run IAM layer.
No browser-provided identity or financial status is trusted.
"""
import hashlib
import io
from pathlib import PurePosixPath
import uuid
import zipfile

PROJECT = 'meghraj-reconciliation'
BUCKET = 'meghraj-sbi-uploads-109590290120'
MAX_BYTES = 8 * 1024 * 1024

def validate_excel(name, data):
    name = str(name or '')
    if not name or len(name) > 180 or '/' in name or '\\' in name or any(ord(c) < 32 for c in name):
        raise ValueError('invalid_filename')
    ext = PurePosixPath(name).suffix.lower()
    if ext not in ('.xls', '.xlsx'):
        raise ValueError('excel_files_only')
    if not 8 <= len(data) <= MAX_BYTES:
        raise ValueError('file_size_must_be_8_bytes_to_8_MB')
    if ext == '.xls' and not data.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):
        raise ValueError('invalid_xls_signature')
    if ext == '.xlsx':
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                names = [x.filename for x in entries]
                if len(entries) > 10000 or len(set(names)) != len(names):
                    raise ValueError('invalid_excel_archive')
                if not {'[Content_Types].xml', 'xl/workbook.xml'}.issubset(names):
                    raise ValueError('invalid_xlsx_structure')
                if any(x.flag_bits & 1 for x in entries) or sum(x.file_size for x in entries) > 128 * 1024 * 1024:
                    raise ValueError('unsupported_excel_archive')
                if any(n.lower().endswith('vbaproject.bin') for n in names):
                    raise ValueError('macro_enabled_workbook_not_supported')
        except zipfile.BadZipFile:
            raise ValueError('invalid_xlsx_archive') from None
    # Preflight validation only: XLS compound header and XLSX container structure.
    return ext

def handle_upload(request):
    from flask import jsonify
    if request.method != 'POST':
        return jsonify(error='method_not_allowed'), 405
    if request.content_length is None:
        return jsonify(error='content_length_required'), 411
    if request.content_length > MAX_BYTES + 65536:
        return jsonify(error='file_too_large'), 413
    if request.mimetype != 'multipart/form-data':
        return jsonify(error='multipart_form_required'), 415
    files = request.files.getlist('file')
    if len(files) != 1 or len(request.files) != 1:
        return jsonify(error='one_excel_file_required'), 400
    file = files[0]
    data = file.stream.read(MAX_BYTES + 1)
    try:
        ext = validate_excel(file.filename, data)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    from google.cloud import firestore, storage
    receipt = uuid.uuid4().hex
    object_name = 'excel-intake/' + receipt + ext
    db = firestore.Client(project=PROJECT)
    record = db.collection('dashboard_uploads').document(receipt)
    try:
        record.create({'receipt': receipt, 'filename': file.filename,
            'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'object': object_name, 'bucket': BUCKET, 'status': 'UPLOADING',
            'received_at': firestore.SERVER_TIMESTAMP, 'dashboard_version': '1.3.0',
            'finance_processed': False})
        blob = storage.Client(project=PROJECT).bucket(BUCKET).blob(object_name)
        mime = 'application/vnd.ms-excel' if ext == '.xls' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        blob.upload_from_string(data, content_type=mime, if_generation_match=0, timeout=45)
        record.update({'status': 'RECEIVED_FOR_PREFLIGHT'})
    except Exception:
        # A failed receipt commit can leave an object for administrator recovery.
        # Never claim successful receipt or execute the engine after an error.
        try:
            record.update({'status': 'UPLOAD_REQUIRES_REVIEW'})
        except Exception:
            pass
        return jsonify(error='upload_storage_or_database_unavailable', receipt=receipt), 503
    return jsonify(ok=True, receipt=receipt, status='RECEIVED_FOR_PREFLIGHT',
                   finance_processed=False, version='1.3.0'), 201

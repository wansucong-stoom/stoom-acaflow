"""Extract PDF disclosures in memory; archive JSON only, never PDF bytes."""
from __future__ import annotations
import hashlib
import io
import re
import urllib.parse
import xml.etree.ElementTree as ET
from .direct import DirectClient, SourceError
from .viewer_data import _js_string, _LITERAL

PDF_DOWNLOAD_URL = 'https://academyinfo.go.kr/file/fileDownPram.do'


def attachment_links(xml: bytes):
    """Read source-provided fn_hLink arguments without evaluating JavaScript."""
    links = []
    root = ET.fromstring(xml)
    for item in root.iter('Item'):
        script = item.get('linkfilename', '')
        if not script:
            continue
        match = re.fullmatch(r'fn_hLink\(\s*(' + _LITERAL + r')\s*,\s*(' + _LITERAL + r')\s*,\s*(' + _LITERAL + r')\s*\);?', script)
        if not match:
            raise SourceError('첨부 링크 공개 프로토콜 변경: 임의 실행하지 않습니다.')
        target, descriptor, _ = [_js_string(match[i]) for i in (1, 2, 3)]
        fields = dict(urllib.parse.parse_qsl(target, keep_blank_values=True))
        if set(fields) != {'fp', 'fn', 'sn'}:
            raise SourceError('첨부 링크 선택조건 변경')
        path, name = fields['fp'], fields['fn']
        if not re.fullmatch(r'/infofile/PDF_UPLOAD/PBNF_ITEM_UPLOAD/\d{4}/\d{2}/\d+/', path) or not re.fullmatch(r'[A-Za-z0-9_.-]+\.pdf', name, flags=re.I):
            raise SourceError('공개 PDF 첨부 경로 검증 실패')
        server, separator, display = descriptor.partition('#spl#')
        if not separator or urllib.parse.urlsplit(server).hostname not in {'academyinfo.go.kr', 'www.academyinfo.go.kr'}:
            raise SourceError('첨부 링크 서버 검증 실패')
        links.append({'url': PDF_DOWNLOAD_URL, 'method': 'POST',
                      'parameters': {'fileName': name, 'filePath': path, 'saveName': display},
                      'source_file_year': path.split('/')[4], 'source_geometry': {k:item.get(k) for k in ('x','y','width','height')}})
    return links


def parse_pdf(body: bytes):
    import pdfplumber
    if not body.startswith(b'%PDF-'):
        raise SourceError('공개 첨부 응답이 PDF 형식이 아닙니다.')
    records, warnings = [], []
    with pdfplumber.open(io.BytesIO(body)) as document:
        if not document.pages:
            raise SourceError('PDF 페이지가 없습니다.')
        for index, page in enumerate(document.pages, 1):
            text = page.extract_text() or ''
            tables = []
            for table in page.find_tables():
                tables.append({'경계': list(table.bbox), '행': table.extract()})
            words = page.extract_words()
            if not text.strip():
                warnings.append({'페이지': index, '사유': '텍스트 없음: 이미지·스캔 또는 빈 페이지 검증 필요'})
            if '\ufffd' in text or '(cid:' in text:
                warnings.append({'페이지': index, '사유': '문자 인코딩 검증 필요'})
            if page.images:
                warnings.append({'페이지': index, '사유': '이미지 내 정보의 추가 검증 필요', '이미지수': len(page.images)})
            records.append({'페이지': index, '너비': page.width, '높이': page.height,
                            '본문': text, '표': tables, '단어': words})
    # Extraction is not a guarantee that every number/table was interpreted.
    return records, {'format': 'academyinfo-pdf-json-v1',
                     'source_body_sha256': hashlib.sha256(body).hexdigest(),
                     'source_body_bytes': len(body), 'pdf_original_archived': False,
                     'page_count': len(records), 'extracted_page_count': len(records),
                     'warnings': warnings, 'requires_content_validation': True}


def collect_pdf_json(archive, *, dataset_id, url, selectors, client=None, parameters=None, method='GET'):
    exchange = (client or DirectClient()).request(url, parameters, method=method)
    if not 200 <= exchange.status < 300:
        raise SourceError(f'PDF 첨부 HTTP {exchange.status}')
    records, result = parse_pdf(exchange.body)
    metadata = {**exchange.metadata(), **result, 'source_keys': selectors,
                'kind': 'pdf-disclosure-json', 'source_original_retention': 'hash_only'}
    return archive.import_parsed_only(dataset_id, metadata, records, status='ambiguous')


from flask import Flask, request, jsonify
import requests
import re
import hashlib
import base64
import json
import time
import io
from PIL import Image

app = Flask(__name__)
app.json.sort_keys = False

DEV_NAME = "Tofazzal Hossain"


def ocr_from_bytes(img_bytes, max_retries=3):
    for attempt in range(max_retries):
        try:
            img = Image.open(io.BytesIO(img_bytes))
            w, h = img.size

            s = requests.Session()
            s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})

            r = s.get('https://www.i2ocr.com/', timeout=30)
            site_token = re.search(r'name="site_token"\s+value="([a-f0-9]{32})', r.text).group(1)

            s.post('https://www.i2ocr.com/DevSDK/upload.php',
                files={'upload_file[]': ('image.png', img_bytes, 'image/png')},
                data={'service': 'img-ocr_en', 'site_token': site_token, 'x': '0', 'y': '0', 'w': '0', 'h': '0', 'r': '0'},
                headers={'Referer': 'https://www.i2ocr.com/', 'X-Requested-With': 'XMLHttpRequest'}, timeout=30)

            ch = s.get('https://www.i2ocr.com/DevSDK/challenge.php',
                headers={'Referer': 'https://www.i2ocr.com/'}, timeout=30).json()

            for n in range(ch.get('maxnumber', 50000)):
                if hashlib.sha256(f"{ch['salt']}{n}".encode()).hexdigest() == ch['challenge']:
                    break

            payload = base64.b64encode(json.dumps({
                'algorithm': 'SHA-256', 'challenge': ch['challenge'],
                'number': n, 'salt': ch['salt'], 'signature': ch['signature'], 'tool': 414,
            }).encode()).decode()

            s.post('https://www.i2ocr.com/DevSDK/challenge.php',
                data={'payload': payload},
                headers={'Referer': 'https://www.i2ocr.com/', 'X-Requested-With': 'XMLHttpRequest',
                         'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}, timeout=30)

            ocr = s.post('https://www.i2ocr.com/DevSDK/ajax/ocr_backend.php',
                data={'data': json.dumps({'x': '0', 'y': '0', 'w': str(w), 'h': str(h), 'r': '0',
                      'en_future_engine': '1', 'ocr_lang': 'english', 'page_layout': 's', 'page_filename': 'image'})},
                headers={'Referer': 'https://www.i2ocr.com/', 'X-Requested-With': 'XMLHttpRequest',
                         'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}, timeout=60)

            raw = ocr.text

            m = re.search(r'ocrTextBox["\']\)\.val\(["\'](.+?)["\']\)', raw)
            if not m:
                m = re.search(r'val\(["\'](.+?)["\']\)', raw)

            if m:
                text = m.group(1)
                if text and 'nonce:' not in text:
                    return text

        except Exception:
            pass

    return None


@app.route('/')
def index():
    return jsonify({
        'name': 'OCR API - Image to Text',
        'developer': DEV_NAME,
        'description': 'Extract text from images using i2ocr. Supports file upload, base64, and URL.',
        'endpoints': {
            '/api/ocr': {
                'methods': ['GET', 'POST'],
                'description': 'Extract text from image',
                'params': {
                    'GET': {
                        'url': 'Image URL (query parameter)'
                    },
                    'POST (multipart/form-data)': {
                        'file': 'Image file (field name: file or image)'
                    },
                    'POST (application/json)': {
                        'base64': 'Base64 encoded image (with or without data:image prefix)',
                        'url': 'Image URL'
                    },
                    'POST (application/x-www-form-urlencoded)': {
                        'base64': 'Base64 encoded image',
                        'url': 'Image URL'
                    }
                },
                'examples': {
                    'GET': '/api/ocr?url=https://example.com/captcha.jpg',
                    'POST file': 'curl -X POST -F "file=@image.jpg" /api/ocr',
                    'POST base64': 'curl -X POST -H "Content-Type: application/json" -d \'{"base64":"iVBOR..."}\' /api/ocr',
                    'POST url': 'curl -X POST -H "Content-Type: application/json" -d \'{"url":"https://example.com/captcha.jpg"}\' /api/ocr'
                },
                'response_success': {
                    'success': True,
                    'developer': DEV_NAME,
                    'data': {
                        'text': 'Extracted text from image'
                    }
                },
                'response_error': {
                    'success': False,
                    'developer': DEV_NAME,
                    'message': 'Error description'
                }
            }
        }
    })


@app.route('/api/ocr', methods=['GET', 'POST'])
def ocr():
    img_bytes = None

    if request.method == 'POST':
        content_type = request.content_type or ''

        if 'multipart/form-data' in content_type:
            if 'file' in request.files:
                img_bytes = request.files['file'].read()
            elif 'image' in request.files:
                img_bytes = request.files['image'].read()

        elif 'application/json' in content_type:
            data = request.get_json(silent=True) or {}
            if 'base64' in data:
                b64 = data['base64']
                if ',' in b64:
                    b64 = b64.split(',', 1)[1]
                img_bytes = base64.b64decode(b64)
            elif 'url' in data:
                try:
                    img_resp = requests.get(data['url'], timeout=30, headers={
                        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0'
                    })
                    img_bytes = img_resp.content
                except Exception as e:
                    return jsonify({'success': False, 'developer': DEV_NAME, 'message': f'Failed to fetch image: {str(e)}'})

        elif 'application/x-www-form-urlencoded' in content_type:
            data = request.form
            if 'base64' in data:
                b64 = data['base64']
                if ',' in b64:
                    b64 = b64.split(',', 1)[1]
                img_bytes = base64.b64decode(b64)
            elif 'url' in data:
                try:
                    img_resp = requests.get(data['url'], timeout=30, headers={
                        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0'
                    })
                    img_bytes = img_resp.content
                except Exception as e:
                    return jsonify({'success': False, 'developer': DEV_NAME, 'message': f'Failed to fetch image: {str(e)}'})

    if request.method == 'GET':
        url = request.args.get('url')
        if url:
            try:
                img_resp = requests.get(url, timeout=30, headers={
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0'
                })
                img_bytes = img_resp.content
            except Exception as e:
                return jsonify({'success': False, 'developer': DEV_NAME, 'message': f'Failed to fetch image: {str(e)}'})

    if not img_bytes:
        return jsonify({'success': False, 'developer': DEV_NAME, 'message': 'No image provided. Send file, base64, or url'})

    try:
        text = ocr_from_bytes(img_bytes)
        if text:
            return jsonify({'success': True, 'developer': DEV_NAME, 'data': {'text': text}})
        return jsonify({'success': False, 'developer': DEV_NAME, 'message': 'OCR failed'})
    except Exception as e:
        return jsonify({'success': False, 'developer': DEV_NAME, 'message': str(e)})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

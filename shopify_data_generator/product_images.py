"""Discover product-page images with explicit fallback and bounded validation."""
import hashlib
import io
import ipaddress
import json
import re
import socket
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from PIL import Image, UnidentifiedImageError

MAX_PAGES = 8
MAX_IMAGES = 80
MAX_BYTES = 15 * 1024 * 1024


def public_url(url):
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
        raise ValueError('Only public HTTP(S) URLs are supported.')
    if parts.port not in (None, 80, 443):
        raise ValueError('Nonstandard image/page port is not supported.')
    addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80))
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('Nonpublic page/image address is not allowed.')
    return url


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url):
    public_url(url)
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; ProductImageFinder/1.0)'})
    with urllib.request.build_opener(PublicRedirect()).open(request, timeout=20) as response:
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('Page/image exceeds the 15 MB download limit.')
        return data, response.headers.get_content_type(), response.geturl()


def fetch_page(url):
    data, content_type, final_url = download(url)
    if content_type not in ('text/html', 'application/xhtml+xml'):
        raise ValueError('Source URL is not an HTML product page.')
    return {'html': data.decode('utf-8', errors='replace'), 'url': final_url}


def inspect_image(data):
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if min(width, height) < 150 or max(width, height) < 500:
                raise ValueError('Image is too small (minimum short side 150px, long side 500px).')
            if width * height > 40_000_000:
                raise ValueError('Image exceeds the 40 megapixel decoding limit.')
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            image = image.convert('RGB')
            image.thumbnail((256, 256))
            digest = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
        return {'width': width, 'height': height, 'digest': digest}
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError('URL did not return a valid supported image.') from error


def validate_image(url):
    data, content_type, final_url = download(url)
    if not content_type.startswith('image/'):
        raise ValueError('URL did not return an image content type.')
    return {**inspect_image(data), 'url': final_url}


def product_matches(title, product_name, allow_missing_size=False):
    def words(value):
        value = re.sub(r'(\d)\s*(ml|g)\b', r'\1 \2', value.lower())
        if allow_missing_size:
            value = re.sub(r'\d+(?:\.\d+)?\s*(?:ml|g)\b', '', value)
        return set(re.findall(r'[a-z0-9가-힣]+', value)) - {'the', 'and', 'with', 'for', 'of'}
    expected, actual = words(product_name), words(title)
    if not expected:
        return False
    expected_sizes = re.findall(r'(\d+(?:\.\d+)?)\s*(ml|g)\b', product_name.lower())
    actual_sizes = re.findall(r'(\d+(?:\.\d+)?)\s*(ml|g)\b', title.lower())
    if expected_sizes and (actual_sizes or not allow_missing_size) and not set(expected_sizes) & set(actual_sizes):
        return False
    return expected <= actual


class ProductPageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts, self.metadata, self.images, self.title = [], {}, [], ''
        self.script = None
        self.in_title = False
        self.in_heading = False
        self.heading = ''
        self.context = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script':
            self.script = '' if attrs.get('type', '').split(';')[0] in ('application/ld+json', 'application/json') else None
        elif tag == 'title':
            self.in_title = True
        elif tag == 'h1':
            self.in_heading = True
        elif tag == 'meta':
            self.metadata[attrs.get('property') or attrs.get('name', '')] = attrs.get('content', '')
        elif tag == 'img':
            self.images.append((attrs, ' '.join(value for _, value in self.context)))
        if tag not in ('img', 'meta', 'link', 'br', 'hr', 'input', 'source', 'area', 'base', 'embed', 'wbr'):
            self.context.append((tag, attrs.get('class', '') + ' ' + attrs.get('id', '')))

    def handle_endtag(self, tag):
        if tag == 'script' and self.script is not None:
            self.scripts.append(self.script)
            self.script = None
        if tag == 'title':
            self.in_title = False
        if tag == 'h1':
            self.in_heading = False
        for index in range(len(self.context) - 1, -1, -1):
            if self.context[index][0] == tag:
                del self.context[index:]
                break

    def handle_data(self, data):
        if self.script is not None:
            self.script += data
        if self.in_title:
            self.title += data
        if self.in_heading:
            self.heading += ' ' + data


def extract_images(html, page_url, product_name, vendor=''):
    parser = ProductPageParser()
    parser.feed(html)
    title = parser.heading.strip() or parser.metadata.get('og:title') or parser.title
    expected_title = re.sub(re.escape(vendor), '', product_name, flags=re.I).strip() if vendor else product_name
    if title and not product_matches(title, expected_title, allow_missing_size=True):
        return []
    found = []
    matched_product = False
    def add(value, alt=''):
        if isinstance(value, list):
            for item in value:
                add(item, alt)
        elif isinstance(value, dict):
            add(value.get('url') or value.get('contentUrl') or value.get('src'), alt)
        elif isinstance(value, str) and value.strip():
            url = urljoin(page_url, value.strip())
            if urlsplit(url).scheme in ('http', 'https'):
                found.append({'url': url, 'alt': alt or product_name})
    def visit(value):
        nonlocal matched_product
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            kind = value.get('@type', [])
            kind = [kind] if isinstance(kind, str) else kind
            name = value.get('name') or value.get('title') or ''
            brand = value.get('brand') or ''
            brand = brand.get('name', '') if isinstance(brand, dict) else str(brand)
            combined_name = f'{name} {brand}'
            brand_evidence = f'{title} {parser.title} {combined_name}'
            brand_matches = not vendor or product_matches(brand_evidence, vendor)
            if ('Product' in kind or ('images' in value and 'title' in value)) and brand_matches and product_matches(combined_name, product_name):
                matched_product = True
                add(value.get('image') or value.get('images'), str(name))
                add(value.get('featured_image'), str(name))
                return
            for child in [value.get('@graph'), value.get('mainEntity')]:
                if isinstance(child, (dict, list)):
                    visit(child)
    for script in parser.scripts:
        try:
            visit(json.loads(script))
        except (ValueError, TypeError):
            continue
    if matched_product or (product_matches(title, expected_title) and (not vendor or product_matches(f'{title} {parser.title}', vendor))):
        add(parser.metadata.get('og:image'))
        add(parser.metadata.get('twitter:image'))
        for attrs, context in parser.images:
            marker = (context + ' ' + attrs.get('class', '')).lower()
            if any(word in marker for word in ('recommend', 'related', 'banner', 'logo', 'footer')):
                continue
            alt = attrs.get('alt', '').strip()
            alt_matches = product_matches(alt, product_name)
            generic_alt = not alt or re.fullmatch(r'(?:product\s+)?(?:image|photo|front|back|detail|ingredients|packaging)(?:\s*\d+)?', alt, re.I)
            if alt and not alt_matches and not generic_alt:
                continue
            if not (alt_matches or any(word in marker for word in ('product-gallery', 'product__media', 'product-media', 'product-image'))):
                continue
            srcset = attrs.get('data-srcset') or attrs.get('srcset', '')
            sources = [part.strip().split() for part in srcset.split(',') if part.strip()]
            largest = max(sources, key=lambda parts: float(re.sub(r'[^0-9.]', '', parts[-1]) or 0)) if sources else []
            add(attrs.get('data-zoom-image') or attrs.get('data-large-image') or
                (largest[0] if largest else '') or attrs.get('data-src') or attrs.get('src'), attrs.get('alt', ''))
    unique = {}
    for item in found:
        parts = urlsplit(item['url'])
        key = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ''))
        unique.setdefault(key, {**item, 'url': key})
    return list(unique.values())


def discover(providers, fetch, validate, product_name, vendor=''):
    report = {'provider': '', 'images': [], 'warnings': [], 'pages': [], 'limited': False}
    attempted_urls = set()
    for provider, search in providers:
        try:
            pages = search()
            if not isinstance(pages, list):
                raise ValueError('Search returned an invalid page list.')
        except Exception as error:
            report['warnings'].append(f'{provider}: {error}')
            continue
        if len(pages) > MAX_PAGES:
            report['limited'] = True
        digests = set()
        checked = 0
        for page in pages[:MAX_PAGES]:
            source = page.get('url', '')
            if not source or source in attempted_urls:
                continue
            attempted_urls.add(source)
            report['pages'].append({'url': source, 'provider': provider})
            try:
                response = fetch(source)
                html = response['html'] if isinstance(response, dict) else response
                source = response.get('url', source) if isinstance(response, dict) else source
                candidates = extract_images(html, source, product_name, vendor)
                for candidate in candidates:
                    if checked >= MAX_IMAGES:
                        report['limited'] = True
                        break
                    checked += 1
                    try:
                        details = validate(candidate['url'])
                    except Exception as error:
                        report['warnings'].append(f"Image rejected {candidate['url']}: {error}")
                        continue
                    if details['digest'] in digests:
                        continue
                    digests.add(details['digest'])
                    report['images'].append({**candidate, **details, 'source_url': source,
                        'provider': provider, 'source_kind': page.get('source_kind', 'unverified_retailer'),
                        'authority_evidence': page.get('authority_evidence', '')})
            except Exception as error:
                report['warnings'].append(f'{provider} page {source}: {error}')
        if report['images']:
            report['provider'] = provider
            return report
        report['warnings'].append(f'{provider}: no verified product images found; trying next provider.')
    return report

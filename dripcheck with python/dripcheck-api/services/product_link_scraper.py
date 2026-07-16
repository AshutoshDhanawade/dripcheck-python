import ipaddress
import json
import os
import re
import ssl
import uuid
import urllib.parse
import urllib.request
from html import unescape
from html.parser import HTMLParser

from django.conf import settings


class ProductScrapeError(Exception):
    pass


class NotClothingProductError(ProductScrapeError):
    pass


ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

APPAREL_KEYWORDS = {
    'apparel', 'clothing', 'fashion', 'wear', 'menswear', 'womenswear',
    'shirt', 't-shirt', 'tee', 'top', 'blouse', 'kurta', 'hoodie',
    'sweatshirt', 'jacket', 'coat', 'blazer', 'sweater', 'cardigan',
    'jeans', 'pants', 'trouser', 'shorts', 'skirt', 'dress', 'leggings',
    'jogger', 'cargo', 'sneaker', 'shoe', 'boot', 'loafer', 'sandal',
    'footwear', 'denim', 'polo', 'activewear', 'ethnic wear'
}

NON_APPAREL_KEYWORDS = {
    'phone', 'laptop', 'camera', 'book', 'furniture', 'grocery',
    'toy', 'appliance', 'headphone', 'watch', 'perfume', 'cosmetic'
}

COLOR_WORDS = [
    'black', 'white', 'blue', 'navy', 'grey', 'gray', 'green', 'red',
    'pink', 'purple', 'yellow', 'orange', 'brown', 'beige', 'cream',
    'olive', 'khaki', 'maroon', 'burgundy', 'lavender', 'mint', 'teal',
    'charcoal', 'ivory', 'tan'
]

TYPE_CATEGORY_RULES = [
    ('Footwear', ['sneaker', 'shoe', 'boot', 'loafer', 'sandal', 'footwear']),
    ('Bottom', ['jeans', 'pants', 'trouser', 'shorts', 'skirt', 'leggings', 'jogger', 'cargo']),
    ('Layer', ['jacket', 'coat', 'blazer', 'sweater', 'cardigan', 'hoodie', 'sweatshirt']),
    ('Accessory', ['bag', 'belt', 'cap', 'hat', 'scarf']),
    ('Top', ['shirt', 't-shirt', 'tee', 'top', 'blouse', 'kurta', 'polo']),
]

ITEM_KEYWORDS = {
    keyword
    for _, keywords in TYPE_CATEGORY_RULES
    for keyword in keywords
    if keyword not in {'wear', 'footwear'}
}


class ProductPageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title_parts = []
        self.meta = {}
        self.json_ld = []
        self._in_title = False
        self._in_json_ld = False
        self._script_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title':
            self._in_title = True
        elif tag == 'meta':
            key = attrs.get('property') or attrs.get('name') or attrs.get('itemprop')
            content = attrs.get('content')
            if key and content:
                self.meta[key.lower()] = unescape(content.strip())
        elif tag == 'script' and attrs.get('type', '').lower() == 'application/ld+json':
            self._in_json_ld = True
            self._script_parts = []

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False
        elif tag == 'script' and self._in_json_ld:
            script_text = ''.join(self._script_parts).strip()
            if script_text:
                self.json_ld.append(script_text)
            self._in_json_ld = False
            self._script_parts = []

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data.strip())
        elif self._in_json_ld:
            self._script_parts.append(data)


def scrape_clothing_product(url):
    validated_url = validate_public_url(url)
    html = fetch_text(validated_url)
    parser = ProductPageParser()
    parser.feed(html)

    json_product = find_json_ld_product(parser.json_ld)
    title = first_value(
        value_from_json_product(json_product, 'name'),
        parser.meta.get('og:title'),
        parser.meta.get('twitter:title'),
        ' '.join(part for part in parser.title_parts if part),
    )
    description = first_value(
        value_from_json_product(json_product, 'description'),
        parser.meta.get('og:description'),
        parser.meta.get('description'),
        parser.meta.get('twitter:description'),
    )
    category_text = first_value(
        value_from_json_product(json_product, 'category'),
        parser.meta.get('product:category'),
        parser.meta.get('article:section'),
    )
    brand = normalize_brand(value_from_json_product(json_product, 'brand') or parser.meta.get('product:brand'))
    color = first_value(value_from_json_product(json_product, 'color'), infer_color(title, description), 'Other')

    image_url = first_value(
        extract_image(value_from_json_product(json_product, 'image')),
        parser.meta.get('og:image'),
        parser.meta.get('twitter:image'),
    )
    if image_url:
        image_url = urllib.parse.urljoin(validated_url, image_url)

    combined_text = ' '.join(filter(None, [title, description, category_text, brand, validated_url]))
    if not looks_like_clothing(combined_text):
        raise NotClothingProductError("This is not a clothing item. Try again.")

    if not title:
        raise ProductScrapeError("Could not find a product name from this link.")
    if not image_url:
        raise ProductScrapeError("Could not find a product image from this link.")

    saved_image_url = download_product_image(image_url)
    subcategory = infer_subcategory(title, description, category_text)
    category = infer_category(title, description, category_text)

    return {
        'source_url': validated_url,
        'name': clean_text(title),
        'description': clean_text(description),
        'brand': clean_text(brand),
        'color': color.title() if color else 'Other',
        'type': subcategory,
        'category': category,
        'image_url': saved_image_url,
    }


def validate_public_url(url):
    parsed = urllib.parse.urlparse((url or '').strip())
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ProductScrapeError("Please enter a valid http or https product link.")

    host = parsed.hostname or ''
    if host in {'localhost'} or host.endswith('.local'):
        raise ProductScrapeError("Please enter a public product link.")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ProductScrapeError("Please enter a public product link.")
    except ValueError:
        pass
    return urllib.parse.urlunparse(parsed)


def fetch_text(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; DripCheckProductScraper/1.0)',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    })
    try:
        with urllib.request.urlopen(req, context=ssl_context, timeout=10) as response:
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                raise ProductScrapeError("This link does not look like a product page.")
            data = response.read(2 * 1024 * 1024)
    except ProductScrapeError:
        raise
    except Exception as exc:
        raise ProductScrapeError("Could not open this link. Please check it and try again.") from exc
    return data.decode('utf-8', errors='ignore')


def find_json_ld_product(scripts):
    for script in scripts:
        for candidate in parse_json_ld_candidates(script):
            found = find_product_node(candidate)
            if found:
                return found
    return {}


def parse_json_ld_candidates(script):
    try:
        return [json.loads(script)]
    except json.JSONDecodeError:
        candidates = []
        for match in re.finditer(r'\{.*?\}', script, re.DOTALL):
            try:
                candidates.append(json.loads(match.group(0)))
            except json.JSONDecodeError:
                continue
        return candidates


def find_product_node(node):
    if isinstance(node, list):
        for item in node:
            found = find_product_node(item)
            if found:
                return found
    if not isinstance(node, dict):
        return None
    node_type = node.get('@type')
    types = node_type if isinstance(node_type, list) else [node_type]
    if any(str(t).lower() == 'product' for t in types if t):
        return node
    for key in ('@graph', 'mainEntity', 'itemListElement'):
        found = find_product_node(node.get(key))
        if found:
            return found
    return None


def value_from_json_product(product, key):
    if not isinstance(product, dict):
        return ''
    value = product.get(key)
    if isinstance(value, list):
        return first_value(*value)
    if isinstance(value, dict):
        return first_value(value.get('name'), value.get('@id'), value.get('url'))
    return value or ''


def first_value(*values):
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


def extract_image(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            image = extract_image(item)
            if image:
                return image
    if isinstance(value, dict):
        return first_value(value.get('url'), value.get('contentUrl'))
    return ''


def normalize_brand(value):
    if isinstance(value, dict):
        return value.get('name', '')
    return value or ''


def looks_like_clothing(text):
    normalized = normalize_text(text)
    apparel_hits = sum(1 for keyword in APPAREL_KEYWORDS if keyword in normalized)
    non_apparel_hits = sum(1 for keyword in NON_APPAREL_KEYWORDS if keyword in normalized)
    item_hits = sum(1 for keyword in ITEM_KEYWORDS if keyword in normalized)
    if non_apparel_hits and not item_hits:
        return False
    return item_hits > 0 or (apparel_hits > 0 and non_apparel_hits == 0)


def infer_color(*texts):
    normalized = normalize_text(' '.join(filter(None, texts)))
    for color in COLOR_WORDS:
        if color in normalized:
            return 'Grey' if color == 'gray' else color
    return ''


def infer_category(*texts):
    normalized = normalize_text(' '.join(filter(None, texts)))
    for category, keywords in TYPE_CATEGORY_RULES:
        if any(keyword in normalized for keyword in keywords):
            return category
    return 'Top'


def infer_subcategory(*texts):
    normalized = normalize_text(' '.join(filter(None, texts)))
    for _, keywords in TYPE_CATEGORY_RULES:
        for keyword in keywords:
            if keyword in normalized and keyword not in {'wear', 'footwear'}:
                return keyword.title()
    return 'Clothing'


def download_product_image(image_url):
    validated_url = validate_public_url(image_url)
    req = urllib.request.Request(validated_url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; DripCheckProductScraper/1.0)',
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
    })
    try:
        with urllib.request.urlopen(req, context=ssl_context, timeout=10) as response:
            content_type = response.headers.get('Content-Type', '').split(';')[0].lower()
            if not content_type.startswith('image/'):
                raise ProductScrapeError("Could not fetch a valid product image from this link.")
            image_bytes = response.read(8 * 1024 * 1024 + 1)
            if len(image_bytes) > 8 * 1024 * 1024:
                raise ProductScrapeError("Product image is too large to save.")
    except ProductScrapeError:
        raise
    except Exception as exc:
        raise ProductScrapeError("Could not fetch the product image from this link.") from exc

    ext = extension_for_image(validated_url, content_type)
    wardrobe_dir = os.path.join(settings.MEDIA_ROOT, 'wardrobe')
    os.makedirs(wardrobe_dir, exist_ok=True)
    filename = f"link_{uuid.uuid4()}{ext}"
    path = os.path.join(wardrobe_dir, filename)
    with open(path, 'wb') as image_file:
        image_file.write(image_bytes)
    return f"{settings.MEDIA_URL}wardrobe/{filename}"


def extension_for_image(url, content_type):
    path_ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    if path_ext in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}:
        return path_ext
    return {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/webp': '.webp',
        'image/gif': '.gif',
    }.get(content_type, '.jpg')


def normalize_text(value):
    return re.sub(r'\s+', ' ', clean_text(value).lower())


def clean_text(value):
    return unescape(str(value or '')).strip()

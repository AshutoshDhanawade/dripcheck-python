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

# Specific-first classification rules: (category, subcategory, compiled regex).
# Word boundaries avoid fragile substring hits (e.g. "overshirt" must not
# match "shirt", "shorts" must not match "short sleeve").
def _word_pattern(keyword, allow_plural=False):
    if allow_plural:
        return re.compile(r'\b' + re.escape(keyword) + r's?\b', re.IGNORECASE)
    return re.compile(r'\b' + re.escape(keyword) + r'\b', re.IGNORECASE)

SPECIFIC_CATEGORY_RULES = [
    ('Top', 'Shirt', _word_pattern('dress shirt', allow_plural=True)),
    ('Top', 'Dress', _word_pattern('dress', allow_plural=True)),
    ('Layer', 'Overshirt', _word_pattern('overshirt', allow_plural=True)),
    ('Top', 'Polo', _word_pattern('polo', allow_plural=True)),
    ('Top', 'Henley', _word_pattern('henley', allow_plural=True)),
    ('Top', 'Tunic', _word_pattern('tunic', allow_plural=True)),
    ('Layer', 'Blazer', _word_pattern('blazer', allow_plural=True)),
    ('Layer', 'Suit Jacket', _word_pattern('suit jacket', allow_plural=True)),
    ('Layer', 'Suit', _word_pattern('suit')),
    ('Layer', 'Sweater', _word_pattern('sweater', allow_plural=True)),
    ('Layer', 'Cardigan', _word_pattern('cardigan', allow_plural=True)),
    ('Layer', 'Hoodie', _word_pattern('hoodie', allow_plural=True)),
    ('Layer', 'Sweatshirt', _word_pattern('sweatshirt', allow_plural=True)),
    ('Layer', 'Jacket', _word_pattern('jacket', allow_plural=True)),
    ('Layer', 'Coat', _word_pattern('coat', allow_plural=True)),
    ('Layer', 'Parka', _word_pattern('parka', allow_plural=True)),
    ('Footwear', 'Sneaker', _word_pattern('sneaker', allow_plural=True)),
    ('Footwear', 'Shoes', _word_pattern('shoe', allow_plural=True)),
    ('Footwear', 'Boots', _word_pattern('boot', allow_plural=True)),
    ('Footwear', 'Loafers', _word_pattern('loafer', allow_plural=True)),
    ('Footwear', 'Sandals', _word_pattern('sandal', allow_plural=True)),
    ('Top', 'T-Shirt', re.compile(r'\bt[- ]?shirts?\b', re.IGNORECASE)),
    ('Top', 'T-Shirt', _word_pattern('tee')),
    ('Top', 'Shirt', _word_pattern('shirt', allow_plural=True)),
    ('Top', 'Blouse', _word_pattern('blouse', allow_plural=True)),
    ('Top', 'Kurta', _word_pattern('kurta', allow_plural=True)),
    ('Top', 'Top', _word_pattern('top', allow_plural=True)),
    ('Bottom', 'Jeans', _word_pattern('jeans')),
    ('Bottom', 'Pants', _word_pattern('pants')),
    ('Bottom', 'Trousers', _word_pattern('trouser', allow_plural=True)),
    ('Bottom', 'Shorts', _word_pattern('shorts')),
    ('Bottom', 'Skirt', _word_pattern('skirt', allow_plural=True)),
    ('Bottom', 'Leggings', _word_pattern('leggings')),
    ('Bottom', 'Joggers', _word_pattern('jogger', allow_plural=True)),
    ('Bottom', 'Cargo', _word_pattern('cargo', allow_plural=True)),
    ('Accessory', 'Bag', _word_pattern('bag', allow_plural=True)),
    ('Accessory', 'Belt', _word_pattern('belt', allow_plural=True)),
    ('Accessory', 'Cap', _word_pattern('cap', allow_plural=True)),
    ('Accessory', 'Hat', _word_pattern('hat', allow_plural=True)),
    ('Accessory', 'Scarf', _word_pattern('scarf', allow_plural=True)),
]

ATTRIBUTE_KEYS = {
    'material', 'fabric', 'colour', 'color', 'pattern', 'fit', 'sleeve',
    'sleeve_length', 'occasion', 'season', 'size', 'gender', 'fabric_composition',
}

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
    page_title = ' '.join(part for part in parser.title_parts if part)
    title = first_value(
        value_from_json_product(json_product, 'name'),
        parser.meta.get('og:title'),
        parser.meta.get('twitter:title'),
        page_title,
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
    structured_color = first_value(
        value_from_json_product(json_product, 'color'),
        structured_attribute_value(json_product, ('color', 'colour')),
    )
    structured_material = first_value(
        value_from_json_product(json_product, 'material'),
        structured_attribute_value(json_product, ('material', 'fabric', 'fabric_composition')),
        parser.meta.get('product:material'),
    )
    structured_attributes = extract_structured_attributes(json_product)
    variant_data = extract_variants(json_product)
    specs_text = build_specs_text(description, structured_attributes, variant_data)
    # Fallback color: title/description evidence first, then structured data.
    # (Structured color is NOT automatically the winner — reconciliation in
    # services.product_metadata decides the final value using all sources.)
    color = first_value(infer_color(title, description), structured_color, 'Other')

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

    saved_image_url, image_bytes = download_product_image(image_url)
    subcategory = infer_subcategory(title, description, category_text)
    category = infer_category(title, description, category_text)

    evidence = {
        'name': clean_text(title),
        'description': clean_text(description),
        'brand': clean_text(brand),
        'structured_color': clean_text(structured_color),
        'structured_category': clean_text(category_text),
        'structured_material': clean_text(structured_material),
        'structured_attributes': structured_attributes,
        'variant_data': variant_data,
        'title': clean_text(page_title),
        'meta': dict(parser.meta),
        'specs_text': clean_text(specs_text),
        'image_url': image_url,
        'source_url': validated_url,
    }

    return {
        'source_url': validated_url,
        'name': clean_text(title),
        'description': clean_text(description),
        'brand': clean_text(brand),
        'color': color.title() if color else 'Other',
        'type': subcategory,
        'category': category,
        'image_url': saved_image_url,
        'image_bytes': image_bytes,
        'evidence': evidence,
    }


def structured_attribute_value(product, keys):
    """Look up a named value inside JSON-LD additionalProperty / propertyValue entries."""
    for key in keys:
        value = value_from_json_product(product, key)
        if value:
            return value
    attributes = extract_structured_attributes(product)
    for key in keys:
        if attributes.get(key):
            return attributes[key]
    return ''


def extract_structured_attributes(product):
    """Collect JSON-LD additionalProperty / propertyValue entries into a flat dict."""
    attributes = {}
    if not isinstance(product, dict):
        return attributes
    for node in [product] + (product.get('additionalProperty') or []):
        if not isinstance(node, dict):
            continue
        name = node.get('name') or node.get('propertyID') or node.get('@type')
        value = node.get('value')
        if isinstance(value, dict):
            value = value.get('name') or value.get('value')
        if name and value is not None and not isinstance(value, (dict, list)):
            key = str(name).strip().lower()
            attributes[key] = str(value).strip()
    return attributes


def extract_variants(product):
    """Collect variant information (e.g. color/size variants) from JSON-LD offers."""
    variants = []
    if not isinstance(product, dict):
        return variants
    offers = product.get('offers')
    offer_nodes = offers if isinstance(offers, list) else [offers]
    for offer in offer_nodes:
        if not isinstance(offer, dict):
            continue
        item_offered = offer.get('itemOffered')
        if isinstance(item_offered, dict):
            variant = {}
            for key in ('name', 'color', 'material'):
                value = value_from_json_product(item_offered, key)
                if value:
                    variant[key] = value
            additional = extract_structured_attributes(item_offered)
            if additional:
                variant['attributes'] = additional
            if variant:
                variants.append(variant)
        for key in ('name', 'sku'):
            value = value_from_json_product(offer, key)
            if value:
                variants.append({key: value})
    return variants


def build_specs_text(description, attributes, variants):
    """Concatenate structured product specifications into searchable plain text."""
    parts = []
    if description:
        parts.append(description)
    for key, value in attributes.items():
        if key in ATTRIBUTE_KEYS or any(word in key for word in ('material', 'fabric', 'fit', 'sleeve')):
            parts.append(f"{key}: {value}")
    for variant in variants:
        if isinstance(variant, dict):
            parts.append(' '.join(str(v) for v in variant.values()))
    return ' '.join(filter(None, parts))


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
    for category, _subcategory, pattern in SPECIFIC_CATEGORY_RULES:
        if pattern.search(normalized):
            return category
    for category, keywords in TYPE_CATEGORY_RULES:
        if any(keyword in normalized for keyword in keywords):
            return category
    return 'Top'


def infer_subcategory(*texts):
    normalized = normalize_text(' '.join(filter(None, texts)))
    for _category, subcategory, pattern in SPECIFIC_CATEGORY_RULES:
        if pattern.search(normalized):
            return subcategory
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
    saved_url = f"{settings.MEDIA_URL}wardrobe/{filename}"
    return saved_url, image_bytes


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

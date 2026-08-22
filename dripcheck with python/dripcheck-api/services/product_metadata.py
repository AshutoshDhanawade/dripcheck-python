import re

from services.gemini_service import (
    CATEGORY_CHOICES,
    FIT_CHOICES,
    PATTERN_CHOICES,
    SEASON_CHOICES,
    STYLE_TAG_CHOICES,
    infer_color_family,
)
from services.occasion_taxonomy import OCCASION_ALIASES, normalize_occasion_list

# ── Field vocabularies (mirror api/models.py enum choices) ────────────────────

COLOR_WORDS = [
    'black', 'white', 'blue', 'navy', 'grey', 'gray', 'green', 'red',
    'pink', 'purple', 'yellow', 'orange', 'brown', 'beige', 'cream',
    'olive', 'khaki', 'maroon', 'burgundy', 'lavender', 'mint', 'teal',
    'charcoal', 'ivory', 'tan', 'gold', 'silver', 'peach', 'coral',
]

# Ordered fit rules — more specific phrases first.
FIT_PATTERNS = [
    (re.compile(r'\bslim\s*fit\b', re.IGNORECASE), 'Slim'),
    (re.compile(r'\bslim\b', re.IGNORECASE), 'Slim'),
    (re.compile(r'\bskinny\b', re.IGNORECASE), 'Slim'),
    (re.compile(r'\bfitted\b', re.IGNORECASE), 'Slim'),
    (re.compile(r'\btailored\b', re.IGNORECASE), 'Slim'),
    (re.compile(r'\bregular\s*fit\b', re.IGNORECASE), 'Regular'),
    (re.compile(r'\bclassic\s*fit\b', re.IGNORECASE), 'Regular'),
    (re.compile(r'\bregular\b', re.IGNORECASE), 'Regular'),
    (re.compile(r'\brelaxed\s*fit\b', re.IGNORECASE), 'Relaxed'),
    (re.compile(r'\brelaxed\b', re.IGNORECASE), 'Relaxed'),
    (re.compile(r'\bloose\b', re.IGNORECASE), 'Relaxed'),
    (re.compile(r'\boversized\b', re.IGNORECASE), 'Oversized'),
    (re.compile(r'\bboxy\b', re.IGNORECASE), 'Oversized'),
    (re.compile(r'\bbaggy\b', re.IGNORECASE), 'Baggy'),
    (re.compile(r'\bcropped\b', re.IGNORECASE), 'Cropped'),
    (re.compile(r'\btapered\b', re.IGNORECASE), 'Tapered'),
]

MATERIAL_SYNONYMS = {
    'cotton': 'Cotton', 'linen': 'Linen', 'wool': 'Wool', 'silk': 'Silk',
    'denim': 'Denim', 'polyester': 'Polyester', 'poly': 'Polyester',
    'nylon': 'Nylon', 'elastane': 'Elastane', 'spandex': 'Elastane',
    'lycra': 'Elastane', 'viscose': 'Viscose', 'rayon': 'Viscose',
    'cashmere': 'Cashmere', 'fleece': 'Fleece', 'leather': 'Leather',
    'suede': 'Suede', 'jersey': 'Jersey', 'chambray': 'Chambray',
    'tweed': 'Tweed', 'lace': 'Lace', 'satin': 'Satin', 'velvet': 'Velvet',
    'corduroy': 'Corduroy', 'acrylic': 'Acrylic', 'modal': 'Modal',
    'hemp': 'Hemp', 'bamboo': 'Bamboo', 'georgette': 'Georgette',
    'crepe': 'Crepe', 'polyamide': 'Polyamide', 'oxford': 'Oxford',
    'seersucker': 'Seersucker', 'pique': 'Pique', 'twill': 'Twill',
    'tencel': 'Tencel', 'cupro': 'Cupro',
}
MATERIAL_COMPOSITION_RE = re.compile(
    r'(\d{1,3})\s*%\s*([A-Za-z][A-Za-z\s\-]{1,30})', re.IGNORECASE
)
KNOWN_MATERIAL_NAMES = {value.lower() for value in MATERIAL_SYNONYMS.values()}

# Occasion text extraction is driven by the central taxonomy's alias table
# (services/occasion_taxonomy.py). Keywords map to canonical taxonomy tags;
# the hierarchy (parent + child pairs) is applied by normalize_occasion_list().
OCCASION_KEYWORDS = OCCASION_ALIASES

SEASON_EXPLICIT = {
    'Summer': ['summer', 'spring summer', 'hot weather'],
    'Winter': ['winter', 'cold weather', 'chilly'],
    'Monsoon': ['monsoon', 'rain', 'waterproof', 'windbreaker', 'rainy'],
}
WINTER_MATERIALS = ['wool', 'cashmere', 'fleece', 'thermal', 'woolen']
SUMMER_MATERIALS = ['linen', 'seersucker', 'chambray']
WINTER_GARMENTS = ['sweater', 'cardigan', 'coat', 'parka', 'beanie', 'thermal', 'jacket']
SUMMER_GARMENTS = ['shorts', 'tank', 'swim', 'sandal', 'crop top']
WINTER_TEXT = ['cozy', 'warm', 'knit', 'knitted']
SUMMER_TEXT = ['breathable', 'lightweight', 'airy', 'cooling']

STYLE_TAG_KEYWORDS = {
    'Minimalist': ['minimal', 'simple'],
    'Streetwear': ['street', 'urban'],
    'Sporty': ['sport', 'athletic', 'active'],
    'Vintage': ['vintage', 'retro', 'distressed'],
    'Bohemian': ['bohemian', 'boho', 'hippie'],
    'Classic': ['classic', 'timeless', 'essential'],
    'Business Casual': ['smart casual', 'business casual'],
    'Y2K': ['y2k'],
    'Preppy': ['preppy', 'ivy'],
    'Grunge': ['grunge', 'flannel'],
    'Monochrome': ['monochrome', 'monotone'],
    'Techwear': ['techwear', 'technical'],
    'Cottagecore': ['cottagecore'],
    'Bold': ['bold', 'statement'],
    'Layered': ['layered', 'layer'],
    'Designer': ['designer', 'luxury'],
}

FORMALITY_TEXT = [
    (re.compile(r'\bblack tie\b|\btuxedo\b|\bgala\b', re.IGNORECASE), 9),
    (re.compile(r'\bformal\b', re.IGNORECASE), 8),
    (re.compile(r'\bbusiness\b|\boffice\b|\bcorporate\b', re.IGNORECASE), 7),
    (re.compile(r'\bsmart casual\b|\bbusiness casual\b', re.IGNORECASE), 6),
    (re.compile(r'\bparty\b|\bdate night\b', re.IGNORECASE), 5),
    (re.compile(r'\bweekend\b|\bvacation\b|\bbeach\b|\btravel\b', re.IGNORECASE), 4),
    (re.compile(r'\bcasual\b', re.IGNORECASE), 4),
    (re.compile(r'\bgym\b|\bworkout\b|\brunning\b|\bsport\b', re.IGNORECASE), 2),
]

GARMENT_FORMALITY = {
    'suit': 8, 'blazer': 8, 'tuxedo': 9, 'dress shirt': 7, 'dress': 7,
    'shirt': 5, 'polo': 5, 'henley': 5, 'blouse': 5, 'kurta': 5,
    'sweater': 4, 'cardigan': 4, 'coat': 5, 'trousers': 5, 'skirt': 5,
    'jeans': 4, 'joggers': 3, 'cargo': 3, 'sneakers': 3, 't-shirt': 3,
    'hoodie': 2, 'sweatshirt': 2, 'leggings': 3, 'shorts': 3,
}

# Garment-type occasion rules (conservative: a garment gets only occasions
# its type genuinely supports). Values use taxonomy tags; _resolve_occasion()
# expands them into parent + child pairs via normalize_occasion_list().
GARMENT_OCCASIONS = {
    'suit': ['Formal', 'Business'], 'blazer': ['Formal', 'Business'],
    'tuxedo': ['Formal'], 'dress shirt': ['Formal', 'Business'],
    'dress': ['Formal', 'Party'], 'shirt': ['Casual'], 'polo': ['Casual'],
    'henley': ['Casual'], 't-shirt': ['Casual'], 'hoodie': ['Casual'],
    'sweatshirt': ['Casual'], 'sweater': ['Casual'], 'cardigan': ['Casual'],
    'coat': ['Casual'], 'jacket': ['Casual'], 'overshirt': ['Casual'],
    'jeans': ['Casual'], 'joggers': ['Gym', 'Casual'], 'cargo': ['Casual'],
    'shorts': ['Casual'], 'trousers': ['Business', 'Casual'],
    'leggings': ['Gym', 'Casual'], 'skirt': ['Casual'],
    'sneakers': ['Casual'], 'loafers': ['Business', 'Casual'],
    'boots': ['Casual'], 'sandals': ['Casual'],
}

# Category/subcategory rules, specific-first (shared with the scraper fallback).
def _word_pattern(keyword, allow_plural=False):
    if allow_plural:
        return re.compile(r'\b' + re.escape(keyword) + r's?\b', re.IGNORECASE)
    return re.compile(r'\b' + re.escape(keyword) + r'\b', re.IGNORECASE)


CATEGORY_RULES = [
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


def _normalize(value):
    return re.sub(r'\s+', ' ', str(value or '').strip().lower())


def _title_case(value):
    return re.sub(r'\s+', ' ', str(value or '').strip()).title()


# ── Individual field resolvers ────────────────────────────────────────────────

def extract_color_from_text(text):
    normalized = _normalize(text)
    for color in COLOR_WORDS:
        if re.search(r'\b' + re.escape(color) + r'\b', normalized):
            return 'Grey' if color == 'gray' else color.title()
    return None


def extract_fit_from_text(text):
    for pattern, fit in FIT_PATTERNS:
        if pattern.search(text):
            return fit
    return None


def extract_material_from_text(text):
    normalized = _normalize(text)
    matches = MATERIAL_COMPOSITION_RE.findall(normalized)
    known_matches = []
    for pct, name in matches:
        material = _normalize_material_name(name)
        if material and material.lower() in KNOWN_MATERIAL_NAMES:
            known_matches.append((int(pct), material))
    if known_matches:
        seen = set()
        compositions = []
        for pct, material in known_matches:
            key = material.lower()
            if key not in seen:
                seen.add(key)
                compositions.append((pct, material))
        compositions.sort(key=lambda item: -item[0])
        return '/'.join(material for _, material in compositions)
    for raw, material in MATERIAL_SYNONYMS.items():
        if re.search(r'\b' + re.escape(raw) + r'\b', normalized):
            return material
    return None


def _normalize_material_name(name):
    candidate = _normalize(name)
    candidate = re.sub(r'\b(?:fabric|material|cloth|blend|fibre|fiber)\b', '', candidate)
    candidate = re.sub(r'\b(?:pure|soft|premium|combed|organic|brushed|knitted)\b', '', candidate)
    candidate = re.sub(r'\s+', ' ', candidate).strip()
    if not candidate:
        return None
    first_word = candidate.split()[0]
    return MATERIAL_SYNONYMS.get(first_word) or MATERIAL_SYNONYMS.get(candidate) or first_word.title()


def extract_occasion_from_text(text):
    """Extract canonical occasion tags from free text via the taxonomy aliases.

    Returns canonical taxonomy tags (children or parents). The old blanket
    implications (formal -> Business, party -> Date Night, smart casual ->
    Business + Casual) are gone: the hierarchy handles implication, and only
    explicit text evidence produces a tag.
    """
    # Generic single words that appear in everyday product copy but are not
    # reliable occasion signals (e.g. "shipping date", "Good evening").
    EXCLUDED_EXTRACTION_KEYWORDS = {
        'work', 'date', 'sport', 'sports', 'ceremony', 'evening', 'urban', 'club',
    }

    normalized = _normalize(text)
    matched = []
    for keyword, canonical in OCCASION_ALIASES.items():
        if keyword in EXCLUDED_EXTRACTION_KEYWORDS:
            continue
        if re.search(r'\b' + re.escape(keyword) + r'\b', normalized):
            matched.append((keyword, canonical))

    # A longer matched phrase overrides its sub-phrases: "business casual"
    # must not also trigger "business" and "casual".
    tags = set()
    for keyword, canonical in matched:
        if any(keyword != other and keyword in other for other, _ in matched):
            continue
        tags.add(canonical)
    return tags


def extract_season_from_text(text):
    normalized = _normalize(text)
    for season, keywords in SEASON_EXPLICIT.items():
        if any(re.search(r'\b' + re.escape(kw) + r'\b', normalized) for kw in keywords):
            return season
    return None


def extract_style_tags_from_text(text):
    normalized = _normalize(text)
    tags = set()
    for tag, keywords in STYLE_TAG_KEYWORDS.items():
        if any(re.search(r'\b' + re.escape(kw) + r'\b', normalized) for kw in keywords):
            tags.add(tag)
    return tags


def classify_from_text(text):
    normalized = _normalize(text)
    for category, subcategory, pattern in CATEGORY_RULES:
        if pattern.search(normalized):
            return category, subcategory
    return None


def _vision_confidence(vision, key, default=None):
    if not vision:
        return default
    confidence = (vision.get('confidence') or {}).get(key)
    try:
        return float(confidence)
    except (TypeError, ValueError):
        return default


# ── Top-level reconciliation ──────────────────────────────────────────────────

def resolve_metadata(evidence, vision=None):
    """
    Reconcile scraped product evidence with (optional) Gemini vision output into
    final wardrobe metadata.

    Returns (metadata, provenance) where metadata contains the keys consumed by
    build_wardrobe_item_payload() and provenance contains per-field source
    information plus any detected conflicts between page data and the image.
    """
    evidence = evidence or {}
    name = str(evidence.get('name') or '')
    title = str(evidence.get('title') or '')
    description = str(evidence.get('description') or '')
    specs_text = str(evidence.get('specs_text') or '')
    structured_color = str(evidence.get('structured_color') or '')
    structured_category = str(evidence.get('structured_category') or '')
    structured_material = str(evidence.get('structured_material') or '')
    brand = str(evidence.get('brand') or '')

    text = ' '.join(filter(None, [title, name, description, specs_text]))
    provenance = {'sources': {}, 'conflicts': []}
    metadata = {}

    # ── Category / subcategory / garment type ──
    category, subcategory, garment_type, cat_source = _resolve_category(
        evidence, vision, text
    )
    metadata['category'] = category
    metadata['subcategory'] = subcategory
    metadata['garment_type'] = (garment_type or subcategory).lower()
    provenance['sources']['category'] = {
        'value': category, 'source': cat_source,
        'confidence': _vision_confidence(vision, 'category', 0.9 if cat_source != 'vision' else None),
    }
    provenance['sources']['subcategory'] = {
        'value': subcategory, 'source': cat_source,
        'confidence': _vision_confidence(vision, 'subcategory', 0.9 if cat_source != 'vision' else None),
    }

    # ── Color ──
    primary_color, color_sources, color_conflict = _resolve_color(evidence, vision, title, name)
    metadata['primary_color'] = primary_color
    metadata['color_family'] = infer_color_family(primary_color)
    provenance['sources']['primary_color'] = {
        'value': primary_color,
        'source': '+'.join(color_sources),
        'confidence': _vision_confidence(vision, 'primary_color', 0.8),
    }
    if color_conflict:
        provenance['conflicts'].append({
            'field': 'primary_color',
            'values': color_conflict,
            'resolved': primary_color,
        })

    # ── Fit ──
    fit, fit_source, fit_confidence = _resolve_fit(text, vision)
    metadata['fit'] = fit
    provenance['sources']['fit'] = {'value': fit, 'source': fit_source, 'confidence': fit_confidence}

    # ── Material ──
    material, material_source, material_confidence = _resolve_material(
        specs_text, description, structured_material, title, name, vision
    )
    metadata['material'] = material
    provenance['sources']['material'] = {
        'value': material, 'source': material_source, 'confidence': material_confidence,
    }

    # ── Pattern ──
    pattern, pattern_source = _resolve_pattern(evidence, vision, text)
    metadata['pattern'] = pattern
    provenance['sources']['pattern'] = {
        'value': pattern, 'source': pattern_source,
        'confidence': _vision_confidence(vision, 'pattern', 0.9 if pattern_source != 'vision' else None),
    }

    # ── Formality ──
    formality_level, formality_source = _resolve_formality(text, metadata['garment_type'], vision)
    metadata['formality_level'] = formality_level
    provenance['sources']['formality_level'] = {
        'value': formality_level, 'source': formality_source,
        'confidence': _vision_confidence(vision, 'formality_level', 0.7),
    }

    # ── Occasion ──
    occasion_type, occasion_source = _resolve_occasion(
        text, metadata['garment_type'], metadata['formality_level'], vision
    )
    metadata['occasion_type'] = occasion_type
    provenance['sources']['occasion_type'] = {
        'value': occasion_type, 'source': occasion_source,
        'confidence': _vision_confidence(vision, 'occasion_type', 0.6),
    }

    # ── Season ──
    season, season_source = _resolve_season(
        text, material, metadata['garment_type'], vision
    )
    metadata['season'] = season
    provenance['sources']['season'] = {
        'value': season, 'source': season_source,
        'confidence': _vision_confidence(vision, 'season', 0.5),
    }

    # ── Brand: structured evidence only, never invented ──
    metadata['brand'] = brand or None
    provenance['sources']['brand'] = {
        'value': metadata['brand'],
        'source': 'structured' if brand else 'unknown',
        'confidence': 0.95 if brand else None,
    }

    # ── Tags & tone ──
    style_tags, mood_tags, aesthetic_tone = _resolve_tags(
        text, primary_color, subcategory, pattern, metadata['garment_type'], vision
    )
    metadata['style_tags'] = style_tags
    metadata['mood_tags'] = mood_tags
    metadata['aesthetic_tone'] = aesthetic_tone

    # ── Secondary color ──
    secondary_colors = (vision or {}).get('secondary_colors') or []
    secondary_color = secondary_colors[0] if secondary_colors else None
    if secondary_color and secondary_color.lower() == primary_color.lower():
        secondary_color = None
    metadata['secondary_color'] = secondary_color

    # ── Sleeve (internal; used for season reasoning in future) ──
    metadata['sleeve'] = (vision or {}).get('sleeve')

    return metadata, provenance


def _resolve_category(evidence, vision, text):
    structured_category = str(evidence.get('structured_category') or '')
    if structured_category:
        matched = classify_from_text(structured_category)
        if matched:
            return matched[0], matched[1], matched[1], 'structured'
    matched = classify_from_text(text)
    if matched:
        return matched[0], matched[1], matched[1], 'title/description'
    if vision:
        vision_category = vision.get('category')
        if vision_category in CATEGORY_CHOICES:
            confidence = _vision_confidence(vision, 'category')
            subcategory = str(vision.get('subcategory') or '').strip()
            if confidence is None or confidence >= 0.6:
                if subcategory:
                    matched = classify_from_text(subcategory)
                    if matched:
                        subcategory = matched[1]
                    elif len(subcategory) <= 40 and len(subcategory.split()) <= 3:
                        subcategory = _title_case(subcategory)
                    else:
                        subcategory = subcategory.split()[0].title()
                return vision_category, subcategory, subcategory, 'vision'
    return 'Top', 'Clothing', 'clothing', 'fallback'


def _resolve_color(evidence, vision, title, name):
    title_text = ' '.join(filter(None, [title, name]))
    title_color = extract_color_from_text(title_text)
    structured_color = str(evidence.get('structured_color') or '').strip()
    vision_color = None
    if vision:
        raw = (vision.get('primary_color') or '').strip()
        if raw and raw.lower() != 'other':
            vision_color = raw

    def same(a, b):
        return a and b and a.lower() == b.lower()

    sources = {}
    if vision_color:
        sources['vision'] = vision_color
    if title_color:
        sources['title'] = title_color
    if structured_color:
        sources['structured'] = _title_case(structured_color)

    distinct = {v for v in sources.values()}
    conflict = None
    if len(distinct) > 1:
        conflict = dict(sources)

    if vision_color:
        vision_confidence = _vision_confidence(vision, 'primary_color')
        title_agrees = same(vision_color, title_color)
        structured_agrees = same(vision_color, structured_color)
        if title_agrees or structured_agrees:
            parts = ['vision'] + (['title'] if title_agrees else []) + (['structured'] if structured_agrees else [])
            return vision_color, parts, conflict
        if title_color and structured_color and same(title_color, structured_color):
            # Both independent page sources agree; image may be misleading (lighting/crop).
            return title_color, ['title', 'structured'], conflict
        if vision_confidence is None or vision_confidence >= 0.6:
            return vision_color, ['vision'], conflict
        if title_color:
            return title_color, ['title'], conflict
        return vision_color, ['vision'], conflict

    if title_color:
        return title_color, ['title'], conflict
    if structured_color:
        return structured_color, ['structured'], conflict
    return 'Other', ['unknown'], conflict


def _resolve_fit(text, vision):
    text_fit = extract_fit_from_text(text)
    if text_fit:
        return text_fit, 'product_text', 0.9
    if vision:
        vision_fit = vision.get('fit')
        if vision_fit in FIT_CHOICES:
            confidence = _vision_confidence(vision, 'fit')
            if confidence is None or confidence >= 0.6:
                return vision_fit, 'vision', confidence or 0.6
    # Schema has no "Unknown" fit; Regular is the neutral default.
    return 'Regular', 'unknown-neutral', 0.3


def _resolve_material(specs_text, description, structured_material, title, name, vision):
    sources = [
        (specs_text, 'product_specs'),
        (description, 'product_description'),
        (title, 'title'),
        (name, 'title'),
    ]
    for text, source in sources:
        material = extract_material_from_text(text)
        if material:
            return material, source, 0.9
    if structured_material:
        material = extract_material_from_text(structured_material)
        if material:
            return material, 'structured', 0.85
        material = _normalize_material_name(structured_material)
        if material:
            return material, 'structured', 0.8
    if vision:
        vision_material = (vision.get('material') or '').strip()
        if vision_material:
            confidence = _vision_confidence(vision, 'material')
            if confidence is None or confidence >= 0.6:
                material = extract_material_from_text(vision_material) or _normalize_material_name(vision_material)
                if material:
                    return material, 'vision', confidence or 0.6
    return None, 'unknown', None


def _resolve_pattern(evidence, vision, text):
    structured_attributes = evidence.get('structured_attributes') or {}
    structured_pattern = structured_attributes.get('pattern')
    if structured_pattern and structured_pattern.title() in PATTERN_CHOICES:
        return structured_pattern.title(), 'structured'
    if vision and vision.get('pattern') in PATTERN_CHOICES:
        return vision.get('pattern'), 'vision'
    if extract_color_from_text(text) and 'striped' in _normalize(text):
        return 'Stripes', 'title/description'
    return 'Solid', 'fallback'


def _resolve_formality(text, garment_type, vision):
    normalized = _normalize(text)
    for pattern, level in FORMALITY_TEXT:
        if pattern.search(normalized):
            return level, 'product_text'
    if garment_type in GARMENT_FORMALITY:
        return GARMENT_FORMALITY[garment_type], 'garment_type'
    if vision and vision.get('formality_level'):
        try:
            level = int(vision.get('formality_level'))
        except (TypeError, ValueError):
            level = None
        if level is not None:
            confidence = _vision_confidence(vision, 'formality_level')
            if confidence is None or confidence >= 0.6:
                return max(1, min(10, level)), 'vision'
    return 5, 'fallback'


def _vision_occasion_candidates(vision):
    """Read Gemini occasion candidates (evidence, never truth).

    Prefers the structured occasion_candidates [{tag, confidence}] output;
    falls back to the legacy flat occasion_type list for older responses.
    Candidates below the confidence floor are dropped.
    """
    if not vision:
        return []
    candidates = vision.get('occasion_candidates')
    if isinstance(candidates, list):
        resolved = []
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            tag = str(cand.get('tag') or '').strip()
            if not tag:
                continue
            try:
                confidence = float(cand.get('confidence'))
            except (TypeError, ValueError):
                confidence = None
            if confidence is None or confidence >= 0.5:
                resolved.append(tag)
        if resolved:
            return resolved
    legacy = vision.get('occasion_type')
    if isinstance(legacy, list):
        confidence = _vision_confidence(vision, 'occasion_type')
        if confidence is None or confidence >= 0.6:
            return [str(tag).strip() for tag in legacy if str(tag).strip()]
    return []


def _resolve_occasion(text, garment_type, formality_level, vision):
    text_occasions = extract_occasion_from_text(text)
    if text_occasions:
        occasions = normalize_occasion_list(text_occasions)
        return occasions or ['Casual'], 'product_text'
    if garment_type in GARMENT_OCCASIONS:
        occasions = normalize_occasion_list(GARMENT_OCCASIONS[garment_type])
        return occasions or ['Casual'], 'garment_type'
    vision_occasions = _vision_occasion_candidates(vision)
    if vision_occasions:
        occasions = normalize_occasion_list(vision_occasions)
        if occasions:
            return occasions, 'vision'
    return ['Casual'], 'fallback'


def _resolve_season(text, material, garment_type, vision):
    explicit = extract_season_from_text(text)
    if explicit:
        return explicit, 'product_text'
    normalized = _normalize(text)
    material_lower = _normalize(material)
    winter_score = 0
    summer_score = 0
    if any(m in material_lower for m in WINTER_MATERIALS):
        winter_score += 2
    if any(m in material_lower for m in SUMMER_MATERIALS):
        summer_score += 2
    if any(g in garment_type for g in WINTER_GARMENTS):
        winter_score += 2
    if any(g in garment_type for g in SUMMER_GARMENTS):
        summer_score += 2
    if any(w in normalized for w in WINTER_TEXT):
        winter_score += 1
    if any(w in normalized for w in SUMMER_TEXT):
        summer_score += 1
    if winter_score > summer_score:
        return 'Winter', 'material/garment evidence'
    if summer_score > winter_score:
        return 'Summer', 'material/garment evidence'
    if vision and vision.get('season') in SEASON_CHOICES:
        confidence = _vision_confidence(vision, 'season')
        if confidence is None or confidence >= 0.6:
            if vision.get('season') != 'All-season':
                return vision.get('season'), 'vision'
    # No seasonal evidence: schema has no "Unknown" season, so All-season is
    # the neutral representation — recorded at low confidence.
    return 'All-season', 'unknown-neutral'


def _resolve_tags(text, primary_color, subcategory, pattern, garment_type, vision):
    normalized = _normalize(text)
    style_tags = extract_style_tags_from_text(text)
    if vision and vision.get('style_tags'):
        for tag in vision.get('style_tags'):
            if tag in STYLE_TAG_CHOICES and len(style_tags) < 5:
                style_tags.add(tag)
    if not style_tags:
        style_tags.add('Classic')

    mood_tags = ['Comfy', 'Relaxed']
    if garment_type in ('suit', 'blazer', 'tuxedo', 'dress', 'dress shirt'):
        mood_tags = ['Elegant', 'Confident']
    elif 'gym' in normalized or 'sport' in normalized:
        mood_tags = ['Active', 'Energetic']
    if vision and vision.get('mood_tags'):
        vision_moods = [str(m).strip() for m in vision.get('mood_tags') if str(m).strip()]
        if vision_moods:
            mood_tags = vision_moods[:3]

    tone = ' '.join(filter(None, [pattern, primary_color, subcategory or garment_type])).strip()
    aesthetic_tone = tone or 'Wardrobe item'
    return sorted(style_tags), mood_tags, aesthetic_tone
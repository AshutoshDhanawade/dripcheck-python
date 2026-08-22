"""
services/occasion_taxonomy.py
==============================
Central hierarchical occasion taxonomy — the single source of truth for
occasion tags across the whole application:

  * product ingestion (URL links, image upload, avatar flow)
  * WardrobeItem / MerchantProduct occasion tagging
  * bundle occasion derivation, bundle scoring, bundle filtering & ranking

Design rules
------------
- Exactly two levels: Parent Occasion -> Child Occasion (11 parents).
- A child IMPLIES its parent; a parent does NOT imply any child.
- Stored occasion_type / occasion_tags values are "parent + child" pairs
  (e.g. ['Formal', 'Business']) so every consumer can resolve the hierarchy
  without extra lookups.
- Gemini, scrapers and user input are treated as EVIDENCE: free-form tags
  are resolved to canonical taxonomy tags via aliases. No AI is allowed to
  build or extend the hierarchy.
"""

from collections import Counter
from typing import Dict, List, Optional, Set

# ── The taxonomy ──────────────────────────────────────────────────────────────

OCCASION_TAXONOMY: Dict[str, List[str]] = {
    'Formal': [
        'Business', 'Corporate', 'Work / Office', 'Interview', 'Meeting',
        'Presentation', 'Conference', 'Professional', 'Business Formal',
        'Smart Formal',
    ],
    'Smart Casual': [
        'Business Casual', 'Elevated Casual', 'Smart Dressing', 'Casual Formal',
    ],
    'Casual': ['Weekend', 'Everyday', 'Errands', 'Brunch', 'Hangout'],
    'Streetwear': [
        'Street Style', 'Urban Casual', 'Skate', 'Hypebeast', 'Athleisure',
    ],
    'Party & Nightlife': [
        'Party', 'Club', 'Night Out', 'Cocktail', 'House Party', 'Festival',
    ],
    'Wedding & Celebration': [
        'Wedding', 'Reception', 'Engagement', 'Anniversary', 'Birthday',
        'Graduation', 'Festive',
    ],
    'Ethnic & Traditional': [
        'Ethnic Festive', 'Traditional Ceremony', 'Religious Occasion',
        'Regional Dress',
    ],
    'Sports & Active': [
        'Gym', 'Workout', 'Running', 'Training', 'Yoga', 'Sports Day',
    ],
    'Travel & Vacation': [
        'Vacation', 'Beach', 'Road Trip', 'Getaway', 'Holiday', 'Airport',
    ],
    'Outdoor': [
        'Hiking', 'Camping', 'Picnic', 'Trekking', 'Adventure', 'Garden Party',
    ],
    'Date & Social': [
        'Date Night', 'First Date', 'Dinner Date', 'Social Gathering',
        'Coffee Date', 'Meetup',
    ],
}

# Flat legacy occasion vocabulary used before the hierarchy existed. Every
# legacy value maps onto a taxonomy parent+child pair (see LEGACY_MAPPING).
LEGACY_OCCASIONS = [
    'Casual', 'Formal', 'Business', 'Party', 'Gym', 'Date Night', 'Weekend',
]

# Legacy flat tag -> taxonomy parent+child pair. normalize_occasion_list()
# produces exactly these pairs for legacy values, so this table is used for
# documentation, API exposure, and the data migration.
LEGACY_MAPPING: Dict[str, List[str]] = {
    'Casual': ['Casual'],
    'Formal': ['Formal'],
    'Business': ['Formal', 'Business'],
    'Party': ['Party & Nightlife', 'Party'],
    'Gym': ['Sports & Active', 'Gym'],
    'Date Night': ['Date & Social', 'Date Night'],
    'Weekend': ['Casual', 'Weekend'],
}

# Keyword/alias -> canonical taxonomy tag (lowercase, whitespace-normalized).
# Used both for text extraction (product descriptions) and for resolving
# free-form evidence (Gemini candidates, user input).
OCCASION_ALIASES: Dict[str, str] = {
    # Formal
    'business': 'Business', 'office': 'Work / Office', 'corporate': 'Corporate',
    'work': 'Work / Office', 'workwear': 'Work / Office', 'work wear': 'Work / Office',
    'interview': 'Interview', 'meeting': 'Meeting', 'presentation': 'Presentation',
    'conference': 'Conference', 'professional': 'Professional',
    'business formal': 'Business Formal', 'smart formal': 'Smart Formal',
    'formal': 'Formal', 'black tie': 'Formal', 'tuxedo': 'Formal', 'gala': 'Formal',
    'ceremony': 'Formal', 'evening wear': 'Formal', 'evening': 'Formal',
    # Smart Casual
    'smart casual': 'Smart Casual', 'business casual': 'Business Casual',
    'elevated casual': 'Elevated Casual', 'smart dressing': 'Smart Dressing',
    'casual formal': 'Casual Formal', 'dressy casual': 'Elevated Casual',
    # Casual
    'casual': 'Casual', 'everyday': 'Everyday', 'weekend': 'Weekend',
    'brunch': 'Brunch', 'hangout': 'Hangout', 'errands': 'Errands',
    'relaxed day': 'Casual', 'streetwear': 'Streetwear',
    # Streetwear
    'street style': 'Street Style', 'urban': 'Urban Casual',
    'urban casual': 'Urban Casual', 'skate': 'Skate', 'hypebeast': 'Hypebeast',
    'athleisure': 'Athleisure',
    # Party & Nightlife
    'party': 'Party', 'clubbing': 'Club', 'club': 'Club', 'night out': 'Night Out',
    'cocktail': 'Cocktail', 'house party': 'House Party', 'festival': 'Festival',
    'clubwear': 'Club', 'nightlife': 'Night Out',
    # Wedding & Celebration
    'wedding': 'Wedding', 'reception': 'Reception', 'engagement': 'Engagement',
    'anniversary': 'Anniversary', 'birthday': 'Birthday', 'graduation': 'Graduation',
    'festive': 'Festive',
    # Ethnic & Traditional
    'ethnic': 'Ethnic Festive', 'ethnic festive': 'Ethnic Festive',
    'traditional': 'Traditional Ceremony', 'religious': 'Religious Occasion',
    'religious occasion': 'Religious Occasion', 'regional': 'Regional Dress',
    'puja': 'Religious Occasion', 'diwali': 'Festive',
    # Sports & Active
    'gym': 'Gym', 'workout': 'Workout', 'running': 'Running', 'training': 'Training',
    'sport': 'Sports & Active', 'sports': 'Sports & Active',
    'athletic': 'Sports & Active', 'sportswear': 'Sports & Active',
    'sports day': 'Sports Day', 'yoga': 'Yoga', 'jogging': 'Running',
    # Travel & Vacation
    'vacation': 'Vacation', 'beach': 'Beach', 'road trip': 'Road Trip',
    'getaway': 'Getaway', 'holiday': 'Holiday', 'airport': 'Airport',
    'travel': 'Travel & Vacation', 'tropical': 'Vacation', 'hawaiian': 'Vacation',
    # Outdoor
    'hiking': 'Hiking', 'camping': 'Camping', 'picnic': 'Picnic',
    'trekking': 'Trekking', 'adventure': 'Adventure', 'garden party': 'Garden Party',
    'outdoor': 'Outdoor',
    # Date & Social
    'date night': 'Date Night', 'first date': 'First Date',
    'dinner date': 'Dinner Date', 'social gathering': 'Social Gathering',
    'coffee date': 'Coffee Date', 'meetup': 'Meetup', 'date': 'Date Night',
    'date outfit': 'Date Night',
}

PARENT_OCCASIONS: List[str] = list(OCCASION_TAXONOMY.keys())

_ALL_TAGS: List[str] = list(PARENT_OCCASIONS)
for _parent, _children in OCCASION_TAXONOMY.items():
    for _child in _children:
        if _child not in _ALL_TAGS:
            _ALL_TAGS.append(_child)
ALL_OCCASIONS: List[str] = list(_ALL_TAGS)
del _parent, _children, _child, _ALL_TAGS

_CHILD_TO_PARENT: Dict[str, str] = {}
for _parent, _children in OCCASION_TAXONOMY.items():
    for _child in _children:
        _CHILD_TO_PARENT[_child] = _parent
del _parent, _children, _child


def parent_of(tag: str) -> Optional[str]:
    """Return the canonical parent of a canonical tag (None for parents)."""
    return _CHILD_TO_PARENT.get(tag)


def is_parent(tag: str) -> bool:
    return tag in OCCASION_TAXONOMY


def children_of(parent: str) -> List[str]:
    """Return the children of a canonical parent occasion."""
    return list(OCCASION_TAXONOMY.get(parent, []))


def _fold(key: str) -> str:
    """Case/separator-insensitive folding for tag comparison.

    Hyphens, slashes and ampersands are treated like spaces so URL query
    tokens (e.g. ``smart-casual``, ``work-office``) resolve to the same
    canonical tag as their display form (``Smart Casual``, ``Work / Office``).
    """
    return ' '.join(
        key.lower().replace('/', ' ').replace('-', ' ').replace('&', ' and ').split()
    )


def normalize_tag(tag) -> Optional[str]:
    """Resolve any free-form/legacy occasion string to a canonical taxonomy tag.

    Returns None when the tag is not recognized (never invents occasions).
    """
    if tag is None:
        return None
    key = ' '.join(str(tag).strip().lower().split())
    if not key:
        return None
    if key in OCCASION_ALIASES:
        return OCCASION_ALIASES[key]
    folded_key = _fold(key)
    for name in ALL_OCCASIONS:
        if _fold(name) == folded_key:
            return name
    return None


def normalize_occasion_list(tags) -> List[str]:
    """Canonicalize a list of occasion tags into parent+child pairs.

    A child tag expands to ``[parent, child]`` (parent first); a parent stays
    ``[parent]``. Order is preserved, duplicates are removed. Unknown tags
    are dropped.
    """
    seen: Set[str] = set()
    out: List[str] = []
    for raw in tags or []:
        canonical = normalize_tag(raw)
        if not canonical or canonical in seen:
            continue
        parent = parent_of(canonical)
        if parent and parent not in seen:
            seen.add(parent)
            out.append(parent)
        seen.add(canonical)
        out.append(canonical)
    return out


def canonical_child(tag) -> Optional[str]:
    """The most specific canonical tag for a single free-form value.

    Used where exactly one occasion value is stored (e.g. WearLog).
    Legacy values keep their child (Business -> Business, Party -> Party).
    """
    normalized = normalize_occasion_list([tag])
    return normalized[-1] if normalized else None


def expand_occasion(tag) -> Set[str]:
    """Expand one occasion for filtering.

    Strict hierarchy semantics:
      * a PARENT request expands to the parent + all descendant children
        (``Formal`` matches ``Business``, ``Interview``, ... bundles);
      * a CHILD request expands to exactly that child — bundles already carry
        their parent tag, so a true ``Business`` bundle matches, while a
        generic parent-only ``Formal`` bundle does NOT automatically qualify
        for every child request;
      * unknown tags expand to themselves (validated at the API layer).
    """
    canonical = normalize_tag(tag)
    if canonical is None:
        return {str(tag).strip()} if tag else set()
    if is_parent(canonical):
        return {canonical} | set(OCCASION_TAXONOMY[canonical])
    return {canonical}


def expand_occasion_list(tags) -> Set[str]:
    """Union of expand_occasion() over a list of occasions."""
    expanded: Set[str] = set()
    for tag in tags or []:
        expanded |= expand_occasion(tag)
    return expanded


def derive_bundle_occasions(occasion_lists) -> List[str]:
    """Derive a bundle's occasion tags from its items' occasion_type lists.

    Rule (never a blind union):
      1. Intersection — occasions shared by ALL items (strongest signal).
      2. Majority — occasions supported by >= ceil(n/2) items.
      3. Union — last resort when the items share nothing.

    Inputs are normalized through the taxonomy, so parent tags are already
    implied by their children.
    """
    normalized = [normalize_occasion_list(lst or []) for lst in occasion_lists]
    normalized = [lst for lst in normalized if lst]
    if not normalized:
        return []

    if len(normalized) == 1:
        return list(normalized[0])

    common = set(normalized[0])
    for lst in normalized[1:]:
        common.intersection_update(lst)
    if common:
        return [tag for tag in normalized[0] if tag in common]

    counts: Counter = Counter()
    for lst in normalized:
        counts.update(lst)
    threshold = (len(normalized) + 1) // 2
    majority = [tag for tag, count in counts.items() if count >= threshold]
    if majority:
        return majority

    union: List[str] = []
    for lst in normalized:
        for tag in lst:
            if tag not in union:
                union.append(tag)
    return union


def occasion_match_strength(bundle_tags, requested) -> float:
    """How strongly a bundle matches a requested occasion (0.0 - 1.0).

    Hierarchy-aware: a child implies its parent, so a bundle tagged
    Business matches a Formal request. Eligibility is strict — a parent does
    NOT imply its children, so a plain Formal bundle does not match a
    Business request.

    1.0 - the requested occasion (or its implied family) is present and the
          bundle's occasion profile is focused on that family (e.g. a
          Business Formal bundle for a Formal request — strong).
    0.5 - the requested family is present but the bundle is broad/generic
          (carries occasions from other families too) — weaker.
    0.0 - no hierarchy-level match (not eligible).
    """
    requested = normalize_tag(requested)
    if requested is None:
        return 0.0
    bundle = set(normalize_occasion_list(bundle_tags or []))
    if requested not in bundle:
        return 0.0
    family = requested if is_parent(requested) else parent_of(requested)
    other_family_tags = [
        tag for tag in bundle
        if (is_parent(tag) and tag != family)
        or (not is_parent(tag) and parent_of(tag) != family)
    ]
    if not other_family_tags:
        return 1.0
    return 0.5


def occasion_relevance(bundle_tags) -> Dict[str, float]:
    """Per-tag occasion relevance for a bundle (for the Home Page response).

    Computed from the bundle's already-derived/stored occasion tags only —
    never from item re-analysis — so it is cheap enough to attach to every
    bundle payload. Each value is the hierarchy-aware match strength (1.0 =
    bundle focused on that family, 0.5 = broad/generic) used by the ranking
    layer, keyed by canonical taxonomy tag.
    """
    normalized = normalize_occasion_list(bundle_tags or [])
    return {
        tag: round(occasion_match_strength(normalized, tag), 2)
        for tag in normalized
    }


def taxonomy_payload() -> dict:
    """Backend source-of-truth payload for the frontend (GET /api/occasions/taxonomy)."""
    return {
        'parents': [
            {'name': parent, 'children': list(children)}
            for parent, children in OCCASION_TAXONOMY.items()
        ],
        'aliases': dict(OCCASION_ALIASES),
        'legacy_mapping': dict(LEGACY_MAPPING),
    }
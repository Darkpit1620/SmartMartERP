"""Dependency-free Code 128 subset B renderer.

Subset B encodes printable ASCII only. This intentionally does not claim to
assign GTINs/EAN numbers. Encoded symbols have a Code 128 start-B, weighted
mod-103 checksum, stop symbol, and >=10-module quiet zones on each side.
No untrusted string is interpolated into the SVG; geometry is integer-only.
"""
from html import escape

# ISO/IEC 15417 Code 128 bar/space module patterns, symbols 0..106.
PATTERNS = (
    '212222', '222122', '222221', '121223', '121322', '131222', '122213',
    '122312', '132212', '221213', '221312', '231212', '112232', '122132',
    '122231', '113222', '123122', '123221', '223211', '221132', '221231',
    '213212', '223112', '312131', '311222', '321122', '321221', '312212',
    '322112', '322211', '212123', '212321', '232121', '111323', '131123',
    '131321', '112313', '132113', '132311', '211313', '231113', '231311',
    '112133', '112331', '132131', '113123', '113321', '133121', '313121',
    '211331', '231131', '213113', '213311', '213131', '311123', '311321',
    '331121', '312113', '312311', '332111', '314111', '221411', '431111',
    '111224', '111422', '121124', '121421', '141122', '141221', '112214',
    '112412', '122114', '122411', '142112', '142211', '241211', '221114',
    '413111', '241112', '134111', '111242', '121142', '121241', '114212',
    '124112', '124211', '411212', '421112', '421211', '212141', '214121',
    '412121', '111143', '111341', '131141', '114113', '114311', '411113',
    '411311', '113141', '114131', '311141', '411131', '211412', '211214',
    '211232', '2331112',
)


def encoded_values(text):
    """Return Code128B symbol numbers, including checksum and stop."""
    if not isinstance(text, str) or not (1 <= len(text) <= 48):
        raise ValueError('Barcode must contain 1–48 characters.')
    if any(ord(ch) < 32 or ord(ch) > 126 for ch in text):
        raise ValueError('Code128B supports printable ASCII only.')
    data = [ord(ch) - 32 for ch in text]
    check = (104 + sum(index * value for index, value in enumerate(data, 1))) % 103
    return [104, *data, check, 106]


def svg_for(text):
    """Produce markup without embedding data or escaping user supplied labels."""
    values = encoded_values(text)
    modules = ''.join(PATTERNS[value] for value in values)
    width = sum(int(m) for m in modules) + 20
    x = 10
    blocks = []
    black = True
    for module in modules:
        span = int(module)
        if black:
            blocks.append(f'<rect x="{x}" y="0" width="{span}" height="56"/>')
        x += span
        black = not black
    return ('<svg viewBox="0 0 {0} 56" xmlns="http://www.w3.org/2000/svg" '
            'role="img" aria-label="Code 128 barcode" preserveAspectRatio="none">'
            '<rect width="{0}" height="56" fill="#fff"/>'
            '<g fill="#000">{1}</g></svg>'.format(width, ''.join(blocks)))


def choose_scan_code(product):
    """Prefer existing barcode, fallback to existing SKU, never make up an ID."""
    for code in (product.barcode, product.sku):
        try:
            encoded_values(code)
            return code
        except ValueError:
            continue
    return None

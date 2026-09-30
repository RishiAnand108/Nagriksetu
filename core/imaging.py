# core/imaging.py
"""
Complaint photo pipeline: normalise → resize → watermark → thumbnail.

Properties worth keeping (each was once a bug):

  1. The output format matches the file extension (PNG stays PNG, everything
     else becomes JPEG) instead of JPEG bytes behind a .png name.
  2. EXIF orientation is applied before anything else, so portrait phone
     photos are not stamped sideways.
  3. The watermark panel is measured from the rendered text, not a fixed
     fraction of the image.
  4. The timestamp is the report time in the site's local timezone, labelled.
  5. Re-encoding drops all EXIF, and the raw upload is deleted afterwards, so
     the phone's GPS/device metadata is not retained on disk.

It never raises: a failure is logged and swallowed so a bad photo cannot lose
a citizen's report.
"""
from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

logger = logging.getLogger('nagriksetu.imaging')

# Refuse to decode anything larger; upload validation enforces the same limit.
Image.MAX_IMAGE_PIXELS = settings.IMAGE_MAX_PIXELS

# Fonts are looked up in order; the first that loads wins.
_FONT_CANDIDATES = (
    'DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    'arialbd.ttf',
    'arial.ttf',
    'C:/Windows/Fonts/arialbd.ttf',
)


def _load_font(size: int) -> ImageFont.ImageFont:
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _fit_width(img: Image.Image, max_width: int) -> Image.Image:
    if img.width <= max_width:
        return img
    ratio = max_width / img.width
    return img.resize((max_width, max(1, round(img.height * ratio))), Image.LANCZOS)


def _watermark_lines(complaint) -> list[str]:
    reported = timezone.localtime(complaint.created_at or timezone.now())
    location = (
        f'{complaint.latitude:.5f}, {complaint.longitude:.5f}'
        if complaint.has_location else 'Location not captured'
    )
    lines = [
        f'{settings.SITE_NAME} - #{complaint.pk}',
        location,
        f"Reported {reported.strftime('%d %b %Y  %H:%M')} {reported.tzname()}",
    ]
    if getattr(complaint, 'ward_id', None):
        lines.append(str(complaint.ward))
    return lines


def _draw_watermark(img: Image.Image, complaint) -> Image.Image:
    """Stamp a report-ID/location/time panel sized to the text it contains."""
    lines = _watermark_lines(complaint)
    font_size = max(14, round(img.height * 0.026))
    font = _load_font(font_size)
    spacing = round(font_size * 0.35)
    pad = round(font_size * 0.6)
    margin = round(img.width * 0.015)

    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    text = '\n'.join(lines)
    left, top, right, bottom = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing)
    text_w, text_h = right - left, bottom - top

    box_x0 = margin
    box_y0 = img.height - margin - text_h - 2 * pad
    box_x1 = box_x0 + text_w + 2 * pad
    box_y1 = img.height - margin

    draw.rounded_rectangle(
        [box_x0, box_y0, box_x1, box_y1],
        radius=round(font_size * 0.4),
        fill=(12, 30, 48, 190),
    )
    draw.multiline_text(
        (box_x0 + pad - left, box_y0 + pad - top),
        text,
        font=font,
        fill=(255, 255, 255, 235),
        spacing=spacing,
    )
    return Image.alpha_composite(img.convert('RGBA'), overlay)


def _encode(img: Image.Image, fmt: str) -> ContentFile:
    buffer = BytesIO()
    if fmt == 'PNG':
        img.convert('RGBA').save(buffer, 'PNG', optimize=True)
    else:
        img.convert('RGB').save(
            buffer, 'JPEG', quality=settings.IMAGE_JPEG_QUALITY, optimize=True, progressive=True
        )
    return ContentFile(buffer.getvalue())


def process_complaint_image(complaint) -> bool:
    """
    Normalise, watermark and thumbnail a complaint photo in place.

    Returns True when the complaint was updated. Never raises.
    """
    if not complaint.image:
        return False

    original_name = complaint.image.name
    previous_thumb = complaint.thumbnail.name if complaint.thumbnail else ''
    storage = complaint.image.storage

    try:
        complaint.image.open('rb')
        with Image.open(complaint.image) as raw:
            img = ImageOps.exif_transpose(raw)
            img.load()
        complaint.image.close()
    except (FileNotFoundError, OSError, UnidentifiedImageError, ValueError, Image.DecompressionBombError) as exc:
        logger.warning('Could not read image for complaint %s: %s', complaint.pk, exc)
        return False

    try:
        stem = Path(original_name).stem
        keep_png = Path(original_name).suffix.lower() == '.png'
        fmt, ext = ('PNG', '.png') if keep_png else ('JPEG', '.jpg')

        full = _fit_width(img, settings.IMAGE_MAX_WIDTH)
        stamped = _draw_watermark(full, complaint)
        thumb = _fit_width(stamped.convert('RGB'), settings.IMAGE_THUMBNAIL_WIDTH)

        # save=False everywhere; both fields are written in one UPDATE below.
        complaint.image.save(f'{stem}{ext}', _encode(stamped, fmt), save=False)
        complaint.thumbnail.save(f'{stem}_thumb.jpg', _encode(thumb, 'JPEG'), save=False)
        complaint.image_processed = True
        complaint.save(update_fields=['image', 'thumbnail', 'image_processed'])
    except Exception as exc:  # noqa: BLE001 - deliberate catch-all around I/O
        logger.exception('Image pipeline failed for complaint %s: %s', complaint.pk, exc)
        return False

    # The raw upload still carries the camera's EXIF (GPS, device model).
    # Only the stamped, metadata-free copy is kept.
    for stale in (original_name, previous_thumb):
        if stale and stale not in (complaint.image.name, complaint.thumbnail.name):
            try:
                storage.delete(stale)
            except Exception as exc:  # noqa: BLE001 - storage may be remote
                logger.warning('Could not delete %s: %s', stale, exc)

    logger.info('Processed image for complaint %s', complaint.pk)
    return True

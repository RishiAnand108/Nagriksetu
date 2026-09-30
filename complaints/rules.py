# complaints/rules.py
"""
Validation rules shared by the Django forms and the DRF serializers.

Each rule raises django.core.exceptions.ValidationError; DRF converts those
automatically inside serializer validation, so both front doors report the
same message for the same mistake.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from PIL import Image, UnidentifiedImageError

# Formats Pillow can read and the pipeline can re-encode. MPO is what many
# phone cameras actually write inside a .jpg.
ALLOWED_IMAGE_FORMATS = {'JPEG', 'MPO', 'PNG', 'WEBP'}


def validate_photo(upload) -> None:
    """
    Reject photos that are too large, not images, or in an unsupported format.

    Only the header is decoded here (Image.open is lazy), so an oversized or
    decompression-bomb image is refused before the pipeline ever loads it.
    """
    if not isinstance(upload, UploadedFile):
        return  # nothing new was uploaded (e.g. an edit keeping the old photo)

    limit_mb = settings.MAX_UPLOAD_SIZE_MB
    if upload.size > limit_mb * 1024 * 1024:
        raise ValidationError(
            f'This photo is {upload.size / 1024 / 1024:.1f} MB. Please upload one under {limit_mb} MB.',
            code='file_too_large',
        )

    try:
        upload.seek(0)
        with Image.open(upload) as img:
            fmt, (width, height) = img.format, img.size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValidationError(
            'We could not read that file as a photo. Please upload a JPEG, PNG or WebP image.',
            code='invalid_image',
        )
    finally:
        upload.seek(0)

    if fmt not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError(
            'That image format is not supported. Please upload a JPEG, PNG or WebP photo.',
            code='unsupported_format',
        )
    if width * height > settings.IMAGE_MAX_PIXELS:
        raise ValidationError(
            'That photo has too many pixels to process. Please upload a smaller image.',
            code='too_many_pixels',
        )


def require_description_or_photo(description, image) -> None:
    if not (description or '').strip() and not image:
        raise ValidationError(
            'Add a description or a photo so the ward office knows what to look at.',
            code='empty_report',
        )

from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models

try:
    from PIL import Image
    from PIL import ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def max_dimension():
    return getattr(settings, 'IMAGE_MAX_DIMENSION', 1000)


def webp_quality():
    return getattr(settings, 'IMAGE_WEBP_QUALITY', 80)


def optimize_image(original_name, content):
    """Resize an image to IMAGE_MAX_DIMENSION on the longest side and re-encode
    it as WebP at IMAGE_WEBP_QUALITY.

    Returns a (ContentFile, webp_filename) tuple, or None if ``content`` is not
    a readable image (e.g. a video upload for HeroBanner) so the original file
    is stored untouched.
    """
    if not PIL_AVAILABLE:
        return None
    try:
        image = Image.open(content)
        image.load()
    except Exception:
        content.seek(0)
        return None
    finally:
        content.seek(0)

    image = ImageOps.exif_transpose(image)

    if image.mode == 'P':
        image = image.convert('RGBA' if image.info.get('transparency') is not None else 'RGB')
    elif image.mode in ('RGBA', 'LA'):
        image = image.convert('RGBA')
    elif image.mode != 'RGB':
        image = image.convert('RGB')

    if max(image.size) > max_dimension():
        image.thumbnail((max_dimension(), max_dimension()), Image.LANCZOS)

    output = BytesIO()
    image.save(output, format='WEBP', quality=webp_quality(), optimize=True, method=4)
    output.seek(0)
    base_name = original_name.rsplit('.', 1)[0]
    return ContentFile(output.read()), f'{base_name}.webp'


class OptimizedImageField(models.ImageField):
    """ImageField that resizes uploads to IMAGE_MAX_DIMENSION and re-encodes
    them as WebP at IMAGE_WEBP_QUALITY before the file is written to storage."""

    def pre_save(self, model_instance, add):
        file = super(models.FileField, self).pre_save(model_instance, add)
        if file and not file._committed:
            result = optimize_image(file.name, file.file)
            if result is not None:
                content, webp_name = result
                file.name = webp_name
                file.file = content
        return models.ImageField.pre_save(self, model_instance, add)


class OptimizedMediaField(models.FileField):
    """FileField for mixed image/video uploads: images are optimized to WebP,
    anything else (e.g. MP4) is stored as-is."""

    def pre_save(self, model_instance, add):
        file = super(models.FileField, self).pre_save(model_instance, add)
        if file and not file._committed:
            result = optimize_image(file.name, file.file)
            if result is not None:
                content, webp_name = result
                file.name = webp_name
                file.file = content
        return models.FileField.pre_save(self, model_instance, add)

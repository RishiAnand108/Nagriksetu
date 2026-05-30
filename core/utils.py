# core/utils.py
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

def watermark_image(complaint):
    """
    Stamps GPS coordinates + timestamp on complaint photo.
    Watermark size scales automatically with image size.
    """
    if not complaint.image:
        return

    # open the uploaded image
    image_path = complaint.image.path
    img        = Image.open(image_path).convert('RGBA')

    # ── Step 1: Resize image to max 1200px wide ──────────
    # Phone photos are 3000-4000px — too large for web
    max_width = 1200
    if img.width > max_width:
        ratio  = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)

    img_width, img_height = img.size

    # ── Step 2: Scale watermark to image size ─────────────
    # watermark box = 30% of image width, 15% of image height
    box_width  = int(img_width  * 0.45)
    box_height = int(img_height * 0.16)
    font_size  = max(20, int(img_height * 0.028))  # scales with image

    # ── Step 3: Create overlay ────────────────────────────
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)

    # ── Step 4: Watermark text ────────────────────────────
    lat  = float(complaint.latitude)
    lng  = float(complaint.longitude)
    now  = datetime.now().strftime('%d %b %Y  %H:%M')
    text = (
        f"NagarikSetu\n"
        f"Lat: {lat:.4f}   Lng: {lng:.4f}\n"
        f"{now}\n"
        f"Complaint ID: #{complaint.id}"
    )

    # ── Step 5: Position — bottom left ───────────────────
    padding = int(img_width * 0.015)
    x = padding
    y = img_height - box_height - padding

    # dark semi-transparent background box
    draw.rectangle(
        [x - 8, y - 8, x + box_width, y + box_height],
        fill=(0, 0, 0, 180)
    )

    # try to use a bigger built-in font
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        # fallback — default font with manual size simulation
        font = ImageFont.load_default()

    # white text
    draw.multiline_text(
        (x, y),
        text,
        fill=(255, 255, 255, 255),
        font=font,
        spacing=int(font_size * 0.4)
    )

    # ── Step 6: Merge and save ────────────────────────────
    watermarked = Image.alpha_composite(img, overlay)
    watermarked = watermarked.convert('RGB')
    watermarked.save(image_path, 'JPEG', quality=90)
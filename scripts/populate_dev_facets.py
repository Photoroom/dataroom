# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "Pillow>=10.0",
#     "requests>=2.31",
# ]
# ///
"""
Populate local DataRoom dev instance with diverse data for testing facets.

Creates images with varied sources, resolutions, tags, datasets, and attributes
so that the facets endpoint returns meaningful aggregations.

Usage:
    uv run scripts/populate_dev_facets.py [--api-url URL] [--api-key KEY] [--count N]

    Run from the project root. Uses Django ORM for attribute schema setup and
    the DataRoom client for image/tag/dataset creation.
"""

import argparse
import hashlib
import io
import random
import sys
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

# Add project root so we can import dataroom_client
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "dataroom_client"))
sys.path.insert(0, str(PROJECT_ROOT))
from dataroom_client import DataRoomClientSync, DataRoomFile

# ---------- Configuration ----------

SOURCES = ["photography", "stock-photos", "ai-generated", "user-uploads", "web-scrape"]

RESOLUTIONS = [
    (640, 480),
    (800, 600),
    (1024, 768),
    (1280, 720),
    (1920, 1080),
    (2560, 1440),
    (3840, 2160),
    (512, 512),
    (1024, 1024),
    (768, 1024),
    (1080, 1920),
    (600, 800),
]

TAG_POOL = [
    "landscape", "portrait", "nature", "urban", "indoor",
    "outdoor", "animal", "food", "architecture", "abstract",
    "macro", "aerial", "night", "sunset", "water",
    "mountain", "forest", "beach", "street", "vintage",
]

DATASET_DEFS = [
    ("training-set", "Training Set"),
    ("validation-set", "Validation Set"),
    ("test-set", "Test Set"),
    ("curated-picks", "Curated Picks"),
]

# Attribute values to randomly assign
ATTR_FORMATS = ["jpeg", "png", "webp", "tiff", "bmp"]
ATTR_LICENSES = ["cc-by-4.0", "cc-by-sa-4.0", "cc0", "mit", "proprietary", "editorial"]
ATTR_ORIENTATIONS = ["landscape", "portrait", "square"]
ATTR_QUALITIES = ["low", "medium", "high", "ultra"]


def setup_django():
    """Initialize Django so we can use ORM for attribute schema management."""
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings.local")
    import django
    django.setup()


def get_api_key() -> str:
    """Get API key from the database via Django ORM."""
    from backend.users.models import Token, User
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        print("ERROR: No superuser found. Create one first.")
        sys.exit(1)
    token, _ = Token.objects.get_or_create(user=user)
    return token.key


def ensure_attribute_fields():
    """Ensure the attribute schema has the fields we need, creating any missing ones."""
    from backend.dataroom.models.attributes import AttributesField, AttributesSchema

    desired = [
        {"name": "format", "field_type": "string", "is_indexed": True, "enum_choices": ATTR_FORMATS},
        {"name": "license", "field_type": "string", "is_indexed": True, "enum_choices": ATTR_LICENSES},
        {"name": "orientation", "field_type": "string", "is_indexed": True, "enum_choices": ATTR_ORIENTATIONS},
        {"name": "quality", "field_type": "string", "is_indexed": True, "enum_choices": ATTR_QUALITIES},
    ]

    for spec in desired:
        field, created = AttributesField.objects.get_or_create(
            name=spec["name"],
            defaults={
                "field_type": spec["field_type"],
                "is_indexed": spec["is_indexed"],
                "is_enabled": True,
                "enum_choices": spec.get("enum_choices"),
            },
        )
        if created:
            print(f"  Created attribute field: {field.name}")
        else:
            # Update enum_choices if missing
            changed = False
            if spec.get("enum_choices") and field.enum_choices != spec["enum_choices"]:
                field.enum_choices = spec["enum_choices"]
                changed = True
            if not field.is_indexed:
                field.is_indexed = True
                changed = True
            if changed:
                field.save()
                print(f"  Updated attribute field: {field.name}")
            else:
                print(f"  Attribute field exists: {field.name}")

    # Invalidate schema cache
    AttributesSchema.invalidate_cache()


def generate_image(width: int, height: int, seed: int) -> bytes:
    """Generate a colored test image with text overlay."""
    rng = random.Random(seed)
    # Random base color
    r, g, b = rng.randint(40, 220), rng.randint(40, 220), rng.randint(40, 220)
    img = Image.new("RGB", (width, height), (r, g, b))
    draw = ImageDraw.Draw(img)

    # Draw some shapes for variety
    for _ in range(rng.randint(3, 10)):
        x1, y1 = rng.randint(0, width), rng.randint(0, height)
        x2, y2 = rng.randint(0, width), rng.randint(0, height)
        color = (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
        shape = rng.choice(["rect", "ellipse", "line"])
        if shape == "rect":
            draw.rectangle([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)], fill=color, outline=None)
        elif shape == "ellipse":
            draw.ellipse([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)], fill=color)
        else:
            draw.line([(x1, y1), (x2, y2)], fill=color, width=rng.randint(1, 5))

    # Text overlay
    label = f"{width}x{height} #{seed}"
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", max(16, min(width, height) // 15))
    except (OSError, IOError):
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), label, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx, ty = (width - tw) // 2, (height - th) // 2
    # Background rect for readability
    draw.rectangle([tx - 4, ty - 2, tx + tw + 4, ty + th + 2], fill=(0, 0, 0, 180))
    draw.text((tx, ty), label, fill=(255, 255, 255), font=font)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def create_tags(client: DataRoomClientSync) -> list[str]:
    """Create tags, returning the list of available tag names."""
    print("Creating tags...")
    created = []
    for name in TAG_POOL:
        try:
            client.create_tag(name=name)
            print(f"  Created tag: {name}")
        except Exception as e:
            if "already exist" in str(e).lower() or "unique" in str(e).lower():
                pass
            else:
                print(f"  Tag '{name}' error: {e}")
        created.append(name)
    return created


def create_datasets(client: DataRoomClientSync) -> list[str]:
    """Create datasets, returning list of slug_version strings."""
    print("Creating datasets...")
    slug_versions = []
    for slug, name in DATASET_DEFS:
        try:
            result = client.create_dataset(name=name, slug=slug, description=f"Dev test dataset: {name}")
            sv = result.get("slug_version", f"{slug}/1")
            print(f"  Created dataset: {sv}")
            slug_versions.append(sv)
        except Exception as e:
            if "already exist" in str(e).lower() or "unique" in str(e).lower():
                # Find existing
                sv = f"{slug}/1"
                slug_versions.append(sv)
                print(f"  Dataset exists: {sv}")
            else:
                print(f"  Dataset '{slug}' error: {e}")
    return slug_versions


def populate_images(
    client: DataRoomClientSync,
    count: int,
    tag_names: list[str],
    dataset_svs: list[str],
):
    """Generate and upload images with diverse metadata."""
    print(f"\nCreating {count} images with diverse metadata...")
    rng = random.Random(42)

    for i in range(count):
        # Pick random metadata
        source = rng.choice(SOURCES)
        width, height = rng.choice(RESOLUTIONS)
        seed = 5000 + i

        # Generate image
        image_bytes = generate_image(width, height, seed)
        image_id = hashlib.sha256(image_bytes).hexdigest()[:32]

        # Random tags: 0-4 tags per image
        num_tags = rng.randint(0, 4)
        tags = rng.sample(tag_names, min(num_tags, len(tag_names)))

        # Random datasets: 0-2 per image
        num_datasets = rng.choices([0, 1, 2], weights=[0.3, 0.5, 0.2])[0]
        datasets = rng.sample(dataset_svs, min(num_datasets, len(dataset_svs))) if dataset_svs else []

        # Random attributes
        attributes = {
            "format": rng.choice(ATTR_FORMATS),
            "license": rng.choice(ATTR_LICENSES),
            "quality": rng.choice(ATTR_QUALITIES),
        }
        # Determine orientation from actual dimensions
        if width > height:
            attributes["orientation"] = "landscape"
        elif height > width:
            attributes["orientation"] = "portrait"
        else:
            attributes["orientation"] = "square"

        # Create image
        dr_file = DataRoomFile(bytes_io=io.BytesIO(image_bytes), content_type="image/jpeg")
        try:
            client.create_image(
                image_id=image_id,
                source=source,
                image_file=dr_file,
                tags=tags,
                datasets=datasets,
                attributes=attributes,
            )
            tag_str = ",".join(tags) if tags else "(none)"
            ds_str = ",".join(datasets) if datasets else "(none)"
            print(
                f"  [{i+1}/{count}] {image_id[:12]}... "
                f"{width}x{height} src={source} tags=[{tag_str}] ds=[{ds_str}] "
                f"fmt={attributes['format']} lic={attributes['license']} q={attributes['quality']}"
            )
        except Exception as e:
            if "already exist" in str(e).lower():
                print(f"  [{i+1}/{count}] {image_id[:12]}... already exists, skipping")
            else:
                print(f"  [{i+1}/{count}] ERROR: {e}")


def main():
    parser = argparse.ArgumentParser(description="Populate DataRoom with diverse facet-testable data")
    parser.add_argument("--api-url", default="http://localhost:8000/api/", help="DataRoom API URL")
    parser.add_argument("--api-key", default=None, help="API key (auto-detected from DB if not provided)")
    parser.add_argument("--count", type=int, default=200, help="Number of images to create (default: 200)")
    args = parser.parse_args()

    # Django setup for attribute schema management
    setup_django()

    # Get API key
    api_key = args.api_key or get_api_key()
    client = DataRoomClientSync(api_key=api_key, api_url=args.api_url)

    # 1. Ensure attribute schema fields exist
    print("Setting up attribute schema fields...")
    ensure_attribute_fields()

    # 2. Create tags
    tag_names = create_tags(client)

    # 3. Create datasets
    dataset_svs = create_datasets(client)

    # 4. Create images
    populate_images(client, args.count, tag_names, dataset_svs)

    print(f"\nDone! {args.count} images created.")
    print("Test facets: curl 'localhost:8000/api/images/facets/?fields=source,tags,width'")


if __name__ == "__main__":
    main()

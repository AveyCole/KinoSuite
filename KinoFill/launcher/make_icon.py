"""Generate crisp multi-resolution KinoFill.ico in the KinoSuite badge style."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Deep KinoSuite dark slate rounded square + KinoFill electric blue border
    draw.rounded_rectangle(
        (14, 14, 242, 242),
        radius=52,
        fill=(17, 24, 36, 255),
        outline=(47, 140, 255, 255),
        width=16,
    )
    # Shared KinoSuite cyan top accent bar
    draw.rounded_rectangle((58, 42, 198, 56), radius=7, fill=(0, 194, 255, 255))

    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 112)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "Kf", font=font)
    tw = bbox[2] - bbox[0]
    tx = (size - tw) // 2 - bbox[0]
    draw.text((tx, 74), "Kf", fill=(56, 189, 248, 255), font=font)

    out = Path(__file__).resolve().parent.parent / "KinoFill.ico"
    img.save(out, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("Wrote icon:", out)


if __name__ == "__main__":
    main()

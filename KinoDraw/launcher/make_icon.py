"""Generate crisp multi-resolution KinoDraw.ico in the KinoSuite badge style."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Deep KinoSuite dark slate/espresso rounded square + Illustrator warm amber border
    draw.rounded_rectangle((14, 14, 242, 242), radius=52, fill=(24, 20, 18, 255), outline=(255, 154, 0, 255), width=16)
    # KinoSuite cyan top accent bar
    draw.rounded_rectangle((58, 42, 198, 56), radius=7, fill=(0, 194, 255, 255))

    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 112)
    except Exception:
        font = ImageFont.load_default()
    draw.text((60, 74), "Kd", fill=(255, 154, 0, 255), font=font)

    out = Path(__file__).resolve().parent.parent / "KinoDraw.ico"
    img.save(out, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("Wrote icon:", out)


if __name__ == "__main__":
    main()

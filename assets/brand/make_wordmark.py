# The Sound / Vision wordmark as a large transparent PNG (assets/brand/sound-vision-wordmark-3000.png), for the
# branding layer on covers and videos.
#   uv run --with fonttools --with brotli --with pillow python scripts/make_wordmark.py \
#     web/node_modules/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2 assets/brand/sound-vision-wordmark-3000.png 3000
#
# Drawn the way the app draws it (TopBar.tsx Wordmark):
# Inter at weight 800, letter-spacing -0.025em, a 4px-in-17px gap, and the slash: six stage-colored bars (2.75 of each
# 3.4 units) clipped to the parallelogram M6.4 0H12L5.6 20H0z in a 12 x 20 box.
import sys
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image, ImageDraw, ImageFont

woff, out, width = sys.argv[1], sys.argv[2], int(sys.argv[3])
f = TTFont(woff)
inst = instancer.instantiateVariableFont(f, {"wght": 800})
inst.flavor = None
import os, tempfile
ttf = os.path.join(tempfile.mkdtemp(), "inter-800.ttf")
inst.save(ttf)

S = 400  # font size to draw at; the result is scaled to `width` after
font = ImageFont.truetype(ttf, S)
ink = (0xEC, 0xEC, 0xEF, 255)
colors = ["#4ade80", "#e8e1cf", "#f5c542", "#4d8dff", "#ff4d94", "#2dd4d8"]
track = -0.025 * S
gap = 4 / 17 * S
slash_w, slash_h = 12 / 17 * S, 20 / 17 * S

def text_width(t):
    return sum(font.getlength(ch) for ch in t) + track * (len(t) - 1)

wa, wb = text_width("Sound"), text_width("Vision")
margin_x = 1 / 17 * S  # the svg's 1px side margins
W = int(wa + gap + margin_x + slash_w + margin_x + gap + wb) + 8
asc, desc = font.getmetrics()
H = int(max(asc + desc, slash_h)) + 8
img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
cy = H / 2

def draw_text(t, x):
    # vertically centred on the cap height, like the app's align-items: center
    bbox = font.getbbox("SV")
    y = cy - (bbox[1] + bbox[3]) / 2
    for ch in t:
        d.text((x, y), ch, font=font, fill=ink)
        x += font.getlength(ch) + track
    return x - track

x = draw_text("Sound", 4)
x += gap + margin_x
# the slash, drawn at 4x and scaled down for clean edges
k = 4
sw, sh = int(slash_w * k), int(slash_h * k)
bars = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
bd = ImageDraw.Draw(bars)
u = sh / 20
for i, c in enumerate(colors):
    bd.rectangle([0, i * 3.4 * u, sw, (i * 3.4 + 2.75) * u], fill=c)
mask = Image.new("L", (sw, sh), 0)
ImageDraw.Draw(mask).polygon([(6.4 * u, 0), (12 * u, 0), (5.6 * u, 20 * u), (0, 20 * u)], fill=255)
bars.putalpha(Image.composite(bars.getchannel("A"), Image.new("L", (sw, sh), 0), mask))
bars = bars.resize((int(slash_w), int(slash_h)), Image.LANCZOS)
img.alpha_composite(bars, (int(x), int(cy - slash_h / 2)))
x += slash_w + margin_x + gap
draw_text("Vision", x)
img = img.crop(img.getbbox())
img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
img.save(out)
print(out, img.size)

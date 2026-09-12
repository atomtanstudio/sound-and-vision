# Classic song credits and lossless scene assembly

## Use

Open **Video → Music video → Review & export → Song credits**. Enter any of:
Artist, Song title, Record label. Blank fields are omitted. **Save credits** stores
the fields; **Build updated film** creates an export with them. New-project setup
has the same optional fields. Project name is separate from the on-screen song title.
The checkbox disables the block entirely. Saving credits does not regenerate scenes
or change chosen takes, and cannot change an already-submitted export snapshot.

The block uses white, left-aligned text in the lower left, with a three-pixel dark
shadow at 1080p. Lines share a 56-pixel type size and 64-pixel baseline spacing.
The left inset is 128 pixels (6.67% of width) and the last baseline is 1026
pixels (95% of height), leaving roughly 49 pixels below the shadow. This moves
the block 64 pixels left and 66 pixels down from the previous layout. Long entries reduce the type size
together to fit; no text is silently truncated. There is no banner or network logo.
It appears at 0.7–7.5 seconds and again from 8.5 to 0.8 seconds before the song ends.
Short films merge overlapping credit windows. Disabled/empty blocks draw nothing.

Two inspected 1984 broadcast frame grabs and the placement comparison are saved in
`deliveries/mtv-credit-study/README.md`. The 4:3 frames establish the period scale;
the lower inset is a deliberate widescreen adaptation requested by the user.

## Typeface evidence and exactness

[Type Network's MTV case study](https://typenetwork.com/articles/mtv), written by
the organization behind MTV's later custom typeface, confirms that the network
eventually settled on Rudolf Koch's **Kabel** for its classic identity. The first
day used several typefaces. Kabel Black is the closest weight identified during
this research, but no original broadcast specification confirming exact weight,
size, shadow or positioning was found. The geometry here recreates the familiar
style; it is not represented as an exact archival broadcast template.

No licensed Kabel font was found in this Mac's installed font directories. The
bundled fallback is **League Spartan**, weight 800, from the
[Google Fonts repository](https://github.com/google/fonts/tree/main/ofl/leaguespartan).
It is an approximation, not a renamed copy of Kabel. Its OFL and attribution ship
in `public/fonts/LeagueSpartan-OFL.txt`. The font designer's
[League Spartan repository](https://github.com/theleagueof/league-spartan) documents
its separate origins. Kabala was considered but not bundled: its author's current
download page asks others not to host or distribute the fonts.

For an appropriately licensed Kabel installation, set `SOUND_VISION_CREDIT_FONT`
to the absolute server path of its TTF/OTF file and restart the idle API. The same
configured font is used for preview and export. This setting is operator-controlled;
the API never accepts arbitrary font paths. Font bytes are not served through the
preview endpoint: it returns a rendered transparent PNG and the font family name.
Keep private font files out of the source repository and public web directory.

## Export quality and speed

LosslessCut 3.69.0 is installed on the Mac. Its
[documented merge workflow](https://github.com/mifi/lossless-cut) copies compatible
compressed streams using FFmpeg. Sound/Vision now uses that same underlying FFmpeg
capability through our own code; no GPL-licensed LosslessCut code was copied.

Previously each directed export encoded every scene at CRF 18 and then encoded the
entire film again. Exports always started from scene assets, not previous exports,
but the extra lossy generations were unnecessary.

The new directed-film path:

1. Checks codec/profile, frame reordering, exact frames, dimensions, pixel format, frame rates, time base,
   progressive scan, aspect ratio, start time and number of streams. Matching
   1080p/24 fps scene files are copied byte-for-byte into export work space.
2. Converts incompatible inputs once using H.264 High at CRF 12. In particular,
   earlier lossless range repairs use High 4:4:4 Predictive with no B-frames; direct
   concatenation with ordinary High/B-frame clips produced corrupt decoding in the
   full-film test despite preserved packet data. These clips need a compatibility
   render. Their original lossless files remain intact. This conversion is lossy,
   at a higher quality setting than the old CRF 18 normalization pass.
3. Renders only scenes overlapping a credit window, once at CRF 18.
4. Joins the prepared scene streams using `-c:v copy`, muxing the uninterrupted
   original song once into AAC. Audio is not copied from previous exports.
5. Compares every decoded output frame to its prepared scene, including the credit
   scenes, before marking an export ready. Byte hashes also confirm copied scene
   files still match their sources. A mismatch withholds the export. It checks
   frame count, duration and sampled master-audio offsets as well. Blank artist
   metadata is valid; FFmpeg omits empty tags.

This is not a wholly lossless export: credit-bearing and incompatible scenes are
rendered, and AAC is lossy. Compatible untouched scenes incur no extra video compression. Lyric or
visualizer effects that touch every frame still require full-frame rendering.
FFmpeg progress is shown as actual encoded/muxed frame counts and named phases.

`backend/film_credits.py` produces the shared preview/export PNG. Credit edits use
`PATCH /api/films/{id}/credits`, increment the export revision, and retain every
source take. The compositor stores credit settings, timing windows, font identity,
preparation version and stream-copy mode in its export receipt.

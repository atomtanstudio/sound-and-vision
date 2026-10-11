<!-- Sheet 07 of 08. Original file: 06_AUDIO_CUES.md. "Music, voice, sfx and beat synchronization". Transcribed as received. -->

<session>
Track: assets/audio/score-120bpm.wav
BPM: 120      Meter: 4/4      Sample rate: 48kHz
Duration: 24.0s / 12 bars    First downbeat: 00:00.000
Target: -14 LUFS integrated / -1 dBTP true peak
</session>

<music_arc>
00:00-00:02  thin pad — create dissatisfaction
00:02-00:08  dry percussion enters with the file reveal
00:08-00:16  full groove — strongest forward momentum
00:16-00:19  strip back to waveform and tactile cues
00:19-00:22  rising resolution across three review rounds
00:22-00:24  short cadence and a clean final hold
</music_arc>

<voice>
Target pace: 130-145 words per minute. Total: 24 words.

00:08.4  "Give every beat a purpose."
00:16.4  "Cut to the beat. Mix for the phone."
00:19.2  "Render it. Look at it. Fix what fails."
</voice>

<sfx_cues>
00:00.80  stamp impact      mark the generic frame as MID     -8dBFS
00:02.00  paper rip         open the hidden system            -10dBFS
00:02.25  eight clicks      one cue for each file reveal      -18dBFS
00:05.00  soft whoosh       coral swatch expansion            -20dBFS
00:08.00  card ticks        storyboard cards land             -22dBFS
00:12.00  UI click          start morph sequence              -16dBFS
00:13.50  progress ticks    reinforce measured progression    -24dBFS
00:15.10  confirmation pop  export state                      -14dBFS
00:16.50  mascot pop        one playful reaction              -17dBFS
00:19.00  review marker     enter critique section            -15dBFS
00:19.50  score ticks x3    three review rounds               -18dBFS
00:22.00  keyboard onset    command sequence begins           -20dBFS
00:23.20  final click       lock the final frame              -15dBFS
</sfx_cues>

<sync_rules>
Visual impacts lead low-frequency sound by no more than one frame.
Whooshes peak at maximum velocity, not at the start of motion.
Every UI sound corresponds to a visible action. Do not sonify every label.
Downbeats own scene changes. Offbeats own secondary details.
</sync_rules>

<mix>
Duck music 3-5dB under voice: 40ms attack / 180ms release.
Leave 2dB headroom before limiting. Check laptop and phone speakers.
Export music.wav / sfx.wav / voice.wav / mix.wav.
</mix>

"""Prompt text. Sections A-L follow the PRD (Daily Content Engine — PRD, Step 2)."""

RULES = """\
Rules for the breakdown
- Every finding cites the video and the timestamp it came from, like [DgLPuk1yc_9 0:03.2].
- Report what is actually in the video. Count or time anything that can be counted or timed.
  The MEASUREMENTS block was produced by ffmpeg and a speech model: use those numbers as given,
  don't re-estimate them. Where you count something yourself from the frames, say "counted from frames".
- If something can't be seen or measured (a stat the platform hides, a sound you can't hear,
  something between the frames you were shown), say so instead of guessing.
- You see still frames, not motion, and you can't hear the audio. Infer motion (zooms, pans,
  transitions) only from differences between consecutive frames, and say that's how you know.
  Name sound effects only as "unconfirmed" candidates tied to a loudness jump and what's on screen.
"""

SECTIONS = {
    "A": """\
### A. Video facts
- Link, post date, day of the week, and time posted if shown.
- Length in seconds.
- Views, likes, comments, shares and saves (whatever is visible). Also likes, comments and shares per 1,000 views.
- Which list picked it: top by views, top by shares, or both.
- Aspect ratio, resolution and frame rate.
- Caption text, hashtags, tagged accounts, and the audio used (original sound or a named track).""",
    "B": """\
### B. The hook (first 3 seconds)
- The exact first words spoken, with timestamps.
- Time from 0:00 to the first spoken word, and to the first cut.
- The first frame: what is in it, how the person is framed, where they are in the frame, and whether anything is already moving.
- On-screen text at 0:00: exact words, size, position, color.
- Hook type: a question, a bold claim, the result shown first, starting mid-action, a direct callout to a type of viewer, a curiosity gap, a visual surprise, or something else (describe it).
- What the hook promises the viewer, and the timestamp where that promise is paid off.
- Any sound in the first 3 seconds: music, sound effect, silence.
- Whether the first frame would work as the video's cover image.""",
    "C": """\
### C. Script and structure
- Full transcript with a timestamp on every line (the word-level timestamps are in the measurements).
- Beat map: split the video into timestamped beats (hook, setup, each main point, twist or turn, payoff, call to action, ending) with a one-line description of each.
- Speaking pace in words per minute, and where it speeds up or slows down.
- Average sentence length, the longest and shortest lines, and how many words fit between cuts.
- Pauses: where they happen, how long, and whether they are cut out or kept on purpose.
- Word choice: reading level, slang, industry jargon, swearing, filler words, and any phrases the creator repeats across videos.
- Point of view: "I" (their own story), "you" (talking to the viewer), or "we".
- Style: storytelling, teaching, opinion, reaction, interview, or a mix.
- Storytelling devices: open loops, numbered lists, before-and-after contrast, specific numbers, stakes, acting out a conversation, callbacks, and the type of humor used.
- Re-hooks in the middle: lines or moments that pull attention back, with timestamps.
- Where curiosity is built and where it is resolved.
- How the video ends: the exact closing line, any call to action (exact words), and whether it loops back to the start, ends on a cliffhanger, or cuts off.
- Whether it sounds scripted or off the cuff, and how much of the video is talking versus visuals only.""",
    "D": """\
### D. On-camera delivery
- How the person speaks: to the camera, as a voiceover, or not at all.
- Energy level and tone, and how they change over the video.
- Changes in volume and speed for emphasis, with timestamps.
- Eye contact with the lens versus looking away.
- Facial expressions, hand gestures, and body movement (walking and talking, sitting, standing still).
- Who appears on camera: alone, with others, with the camera person talking.
- What they wear, and whether their look stays the same across videos.""",
    "E": """\
### E. Editing and cuts
Shot-by-shot log for every video, one row per shot, as a table with these columns:
| Start | End | Shot (what's on screen, framing) | Spoken line | On-screen text | Sound / effect | Edit into next shot |
Use the measured shot boundaries as the rows.

From the log, measure:
- Total number of cuts, cuts per second, and average and median shot length.
- The shortest and longest shots, and where they sit in the video.
- How the pace changes from start to middle to end (cuts per second in each third).
- What triggers each cut: a new sentence, a single word, a music beat, a sound effect, or a visual action.
- Cut types and how often each is used: hard cut, jump cut, audio that starts before the picture changes (or carries over after it), match cut, whip or swipe transition, zoom transition, speed ramp, masking transition.
- How tightly pauses and breaths are cut out.
- Zooms and punch-ins: how many, how far in (rough percentage), snap or smooth, and which words or moments trigger them.
- B-roll: share of runtime, what kind (their own footage, stock, screen recordings, photos, clips from elsewhere), and whether it shows exactly what's being said or something more loosely related.
- Overlays: emojis, stickers, arrows, circles, images, memes, green-screen backgrounds. Count them and note when they appear.
- Motion effects: animated text, motion tracking, masks, shake, flashes, glitch, blur.
- Speed changes: slow motion, time-lapse, speed ramps.
- Whether the end flows back into the start so the video loops.""",
    "F": """\
### F. On-screen text and subtitles
- Subtitles: whether they're used. If so: the font (name it if recognizable, otherwise describe it), weight, size as a share of frame width, text color, outline or shadow, the highlight color on the word being spoken, and ALL CAPS or normal case.
- How many words appear per subtitle chunk, and how they animate in (pop, word by word, typewriter, slide).
- Where text sits on screen (center, upper, lower third), and whether it stays clear of the app's buttons and caption area.
- Title or headline text: any text that stays on screen. Exact words, placement, style, and how long it stays.
- Emphasis: which words get a different color, size or emoji, and what those words have in common.
- How long each piece of text stays on screen, and whether it can be read at normal speed.""",
    "G": """\
### G. Camera, lighting, color and locations
- Shot sizes: close-up, medium, wide. Share of runtime for each.
- Framing: centered or off-center, headroom, how the vertical 9:16 frame is filled.
- Camera: phone or dedicated camera (judge by background blur and image quality), front or back camera, handheld, tripod, gimbal or selfie stick.
- Angles: eye level, low, high, point of view, over the shoulder.
- Camera movement: still, walking with the camera, pans, push-ins, follow shots.
- Lighting: natural or artificial, time of day, which direction the main light comes from, ring-light reflections in the eyes, bright or moody.
- Color: warm or cool, saturation, contrast, grain or a film look, and whether the look is the same across videos.
- Locations: list every setting, indoor or outdoor, and how often each one repeats.
- Props and anything deliberately placed in the frame.""",
    "H": """\
### H. Audio, music and sound effects
- Voice quality: phone mic, clip-on mic or studio mic; echo, background noise, wind.
- Music: whether it's used, the track name if shown, genre, energy, and whether it's a trending sound or original.
- Music volume compared to the voice, and the timestamps where music starts, stops, drops out or hits a beat drop.
- Whether cuts land on the beat of the music.
- Sound effects: total count, the types (whoosh, pop, ding, bass hit, record scratch, typing, camera shutter, and so on), and what each one is placed on (a cut, a zoom, text appearing, a punchline).
- Deliberate silence: where it's used, and for how long.
- How audio moves between shots: hard switches, fades, or sound carried across a cut.""",
    "I": """\
### I. Content, topics and post captions
- The topic of each video in one line.
- The bigger category it belongs to. Group the creator's videos into their own categories, built from what's actually there.
- Recurring formats: any repeated format or named series, and the template it follows each time.
- Purpose: teach, entertain, inspire, show behind the scenes, tell a story, give an opinion, react, or show results.
- What the viewer gets out of it, in one line.
- Whether it uses a trend (a sound, a format, a meme) or is fully original.
- Who it's talking to: the audience it seems aimed at, based on what's said and shown.
- Post caption: length, the first line, structure, line breaks, emoji use, number and kind of hashtags, any call to action, and tone.""",
    "J": """\
### J. Personal brand (from the whole page)
- Profile: exact bio text, the name field, link in bio, highlights (names and covers), and profile picture.
- Positioning: what they're known for, in one sentence, and how they describe themselves.
- Content mix: the share of posts in each category from Section I, across every post on the page.
- Posting: how often they post, how consistent it is, and the mix of videos, carousels and photos.
- Signatures: catchphrases, a signature intro or outro, recurring people, and visual trademarks (a color, font, cover style or setting that shows up again and again).
- Grid and covers: what the cover images look like, whether they have text on them, and how consistent the grid looks as a whole.
- What they share about their life: which personal details appear, lifestyle shown, how vulnerable or how flashy they are.
- Proof and credibility: results, numbers, screenshots, testimonials, before-and-afters.
- Relationship with the audience: whether they reply to comments, ask questions, use inside jokes or a name for their followers.
- Calls to action across posts: follow, comment a keyword, link in bio, DM. What they ask for, and how often.
- What they sell or promote, if anything, and how often it shows up.
- Change over time: how the oldest posts on the page differ from the newest.""",
    "K": """\
### K. Performance patterns
- Top by views vs. top by shares: what the most-shared videos have that the most-viewed ones don't, and the reverse.
- Top videos vs. the rest of the page: using the stats from the full page scan, what the top performers have in common that the creator's weaker posts lack. Compare hook type, length, topic, format, pacing, and posting day and time.
- Length vs. performance: which video lengths do best for this creator.
- Hook type vs. performance, and topic vs. performance.
- Why people share: for each top-by-shares video, what makes it worth sending to someone (relatable, useful, funny, says something about the sender, worth saving for later) and the moment in the video that does it.
- Comments: what people say in the comments on the top videos, and what that shows about why the video worked.""",
}

VIDEO_SECTIONS = list("ABCDEFGHI")

BREAKDOWN_SYSTEM = f"""\
You break down short-form vertical videos (Instagram Reels) in extreme detail, so a creator
can learn another creator's style and repeat it exactly.

For each video you get: the post's facts and caption, measurements from ffmpeg and a speech
model (shots, cuts, word timings, pauses, loudness), and still frames, each labelled with its
timestamp. Write the breakdown in Markdown, one `##` heading per section, in the order given.

{RULES}"""


def scope_instructions(scope: str, deep: list[str], extra_focus: bool) -> str:
    if scope == "message":
        return (
            "SCOPE: break down only the message and the story: what is said, how the story is "
            "built, and why it lands. Cover Sections B, C and I for the words and the story only. "
            "Skip editing, delivery and the page (Sections D to H): the user doesn't like those parts. "
            "Do not write a shot log."
        )
    if scope == "format":
        return (
            "SCOPE: break down the format itself, because the user wants to use it: how the YouTube "
            "video (or other source clip) is shown, how the creator is placed over it with the green "
            "screen (size, position, cut-out edges, what's behind them), how they talk about it, and "
            "how the two are edited together (when the clip plays, pauses, zooms, or the creator "
            "takes over the frame). Put this first under `## Format breakdown`, as a step-by-step "
            "recipe someone could follow in CapCut or a similar editor. Then cover Sections A to I as "
            "they apply to this format."
        )
    parts = ["SCOPE: cover every section A to I."]
    if extra_focus:
        parts.append("This creator is marked EXTRA FOCUS: give every section the deepest breakdown.")
    if deep:
        names = ", ".join(deep)
        parts.append(
            f"Go deepest on Sections {names}: that's what the user likes about this creator. "
            "Every bullet in those sections gets specifics, counts and timestamps."
        )
    return " ".join(parts)


PROFILE_SYSTEM = f"""\
You turn many video breakdowns of one creator into a style profile a person can copy.

{RULES}
Write Markdown. Summarize every category with numbers (averages, ranges and percentages),
not adjectives. Give the 3 clearest example videos for each finding, with timestamps."""

PROFILE_TASK = """\
Write the style profile for @{username}.

What the user likes about this creator (from the creator table):
{likes}

{scope}

Structure:
1. `# @{username}: style profile` and one paragraph saying what this creator does best, with numbers.
2. One `##` section per category A to I, summarized across all their videos with numbers,
   each finding with its 3 clearest example videos and timestamps.
3. {jk}
4. `## How to copy it`: for the part the user likes about this creator, specific enough to repeat
   exactly. For example: subtitle font, size, color and position; cuts per second; zoom amounts and
   what triggers them; every sound effect and where it goes; hook formulas; beat-by-beat templates;
   and camera, lighting and audio setup. Write it as rules and templates, each pointing back to the
   videos it came from.
"""

JK_WITH_PAGE = (
    "`## J. Personal brand` and `## K. Performance patterns`, from the page scan, the page statistics "
    "below, the grid covers and the comments.\n\n" + SECTIONS["J"] + "\n\n" + SECTIONS["K"]
)
JK_WITHOUT_PAGE = (
    "Skip Sections J and K: the user asked not to go through this creator's page, so there is no "
    "page data. Say so in one line."
)

COMBINE_SYSTEM = f"""\
You merge several creators' style profiles into one style guide that a script writer follows
every day. Every rule points back to the creator and the videos it came from.

{RULES}"""

COMBINE_TASK = """\
Write the combined style for the daily scripts.

How to combine (from the PRD):
- Each element comes from the creators the user praised for it in the creator table (below),
  with Extra focus creators weighted most.
- Reels 11 and 12 contribute only their message and story.
- The reel 5 green-screen format is included as a format the scripts can use.
- Where creators conflict, the user's notes on what they like decide.
- Every rule points back to the videos it came from.

The creator table:
{table}

Structure:
- `# Combined style guide`, then one paragraph: the style in a nutshell.
- `## Hooks`: hook formulas with fill-in-the-blank templates and examples.
- `## Script structure`: beat-by-beat templates with target timings, words per minute, sentence length.
- `## Formats`: each repeatable format (including the green-screen format) as a recipe.
- `## Delivery`: energy, eye contact, gestures, pace.
- `## Editing`: cuts per second by third, cut types, zoom rules (amount, trigger), b-roll share, overlays.
- `## On-screen text and subtitles`: exact font, size, colors, position, words per chunk, animation.
- `## Camera, lighting and locations`.
- `## Audio`: voice, music level, every sound effect and where it goes.
- `## Captions, hashtags and calls to action`.
- `## Topics and messages that work`, including the messages and stories from reels 11 and 12.
- `## Rules of thumb`: a numbered checklist a script must pass.
Use numbers, not adjectives.
"""

SCRIPTS_SYSTEM = """\
You write short-form vertical video scripts (Instagram Reels) for one creator, in a style guide
built from the creators they admire. Each script is complete: someone with no editing experience
could record and edit it from your instructions alone.

Follow the style guide's numbers exactly (pace, cuts per second, subtitle specs, zoom triggers,
sound effects). Use only the equipment and locations the creator says they have. Write in the
creator's own voice for their niche and audience; never copy another creator's lines, stories or
claims. Don't invent facts, statistics or personal stories about the creator: where a script needs
one, leave a clearly marked blank like [YOUR NUMBER] or [A TIME YOU ...] for them to fill in."""

SCRIPTS_TASK = """\
Today is {date}. Write {n} new video scripts.

About the creator:
{brief}

Recent scripts (don't repeat these topics or hooks):
{history}

For each script, use this structure:

## Script {{k}}: <working title>
**Format:** which format from the style guide, and why it fits this topic.
**Length:** target seconds. **Goal:** what the viewer should do or feel.

### Hook (0:00-0:03)
- Spoken line (exact words), on-screen text at 0:00 (exact words, style), first frame, first sound.

### Script
A table: | Time | Spoken line | Shot (framing, location, action) | On-screen text | Edit (cut type, zoom, b-roll, sound effect) |
Every line timed to the style guide's pace.

### How to record it
- Setup: camera position and height, framing, lighting, mic, location, what to wear, props.
- Shot list in recording order (batch shots by location), with how many takes to get.
- Delivery notes: energy, where to pause, where to look, gestures.

### How to edit it
- Step by step: cuts, zooms (amount and trigger), b-roll, subtitles (font, size, color, position,
  words per chunk), overlays, sound effects and where they land, music and its level, the loop ending.

### Post
- Caption (ready to paste), hashtags, call to action, cover image idea, best day and time to post.

### Why this should work
- 2-4 bullets, each pointing to the style-guide rule it follows.

After the scripts, add `## Filming plan` that batches today's scripts by location and setup.
"""

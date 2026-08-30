# Slick Chick — a playable reconstruction for Android

A portrait 9:16 pinball game for Android, rebuilding **Slick Chick** (D. Gottlieb & Co.,
1963 — designed by Wayne Neyens) from what is documented about the physical machine.

## What is taken from the real machine

* **Nine bumpers in a criss-cross.** SLICK reads across, CHICK reads down, and the two
  words share their middle letter, so five plus five makes nine. The five towards the
  centre are live pop bumpers; the four at the tips are plain scoring bumpers with no coil.
* **The letters must be struck in order.** Each completed title lights one of five
  rollover buttons.
* **A gobble hole in the middle of the playfield.** It swallows the ball. Early, that
  costs you the ball for a hundred points. With all five buttons lit, losing the ball
  down it is the whole plan — it pays a replay.
* **Four numbered rollovers** under the dome; taken in order they light a second special.
* Single player, five balls, tilt.

## What is a reconstruction, and what is original

Exact playfield coordinates are not published anywhere reachable, so the geometry places
the documented furniture in documented relationships — it is not measured off a real
playfield. If you have photographs of a machine, the layout lives in one file
(`engine/.../SlickChick.kt`) and is straightforward to correct.

**All artwork here is original.** Nothing is taken from the real machine's playfield or
backglass art, and nothing is taken from any later video game of it: both are still in
copyright. Only the *layout and rules* follow the original, and those are facts about a
physical object rather than artwork.

## Layout

```
engine/    pure-Kotlin JVM module: geometry, solver, table description, rules.
           No Android dependency, so it runs under plain JUnit.
app/       the Android application: renderer, input, audio.
tools/     preview.html + preview.py render the exported table in a browser,
           so artwork and collision geometry can be checked without an emulator.
```

The table is *data*. `SlickChick.kt` describes it, `World` simulates it, and both the
Android renderer and the HTML preview draw the same exported description — so the paint
cannot drift away from what the ball actually hits.

## Building

```bash
./gradlew :engine:test          # 25 physics and layout tests
./gradlew :engine:exportTable   # writes tools/out/slick_chick.json
python3 tools/preview.py        # renders tools/out/preview.png
./gradlew :app:assembleDebug    # needs an Android SDK (local.properties / ANDROID_HOME)
```

`:app` is only included in the build when an SDK is present, so the engine and its tests
work on any machine with a JDK.

## Notes on the simulation

Units are playfield units and seconds: 1080 units across a 20.25 in playfield puts one
unit at about 0.48 mm, and every constant follows from that — gravity is the along-playfield
component of g on a 6.5° cabinet, and the ball tops out at about 4.3 m/s.

Several details in `World` are load-bearing and are covered by regression tests:

* **Coulomb friction.** The tangential impulse is capped at a fraction of the normal
  impulse. Scaling tangential velocity by a flat factor instead looks identical for a
  single sharp bounce, but a ball *sliding* along a guide is in contact on every substep,
  so it compounds — at 48 substeps it kept only 14% of its speed and no plunge could
  cross the dome.
* **Edge-triggered scoring surfaces.** Targets and bumpers are solid as well as scoring,
  so a ball can come to rest against one. Untriggered, a single ball scored one target
  over forty thousand times.
* **Pop bumper scatter.** A perfectly radial kick is reversible, and the ball settles into
  a closed orbit against one bumper for minutes on end. Real bumpers trip off-axis.
* **Progress-based stuck detection.** A ball rattling in a short section of guide holds a
  respectable 200 units/s while going nowhere, so a speed threshold never fires for it.

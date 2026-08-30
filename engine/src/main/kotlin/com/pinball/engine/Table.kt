package com.pinball.engine

/**
 * Static description of a playfield: what the ball can hit, what lights up, and
 * what gets painted underneath it all.
 *
 * A [Table] is pure data. [World] simulates it, and the Android renderer (plus
 * tools/preview.html, via the JSON export) draws it. Nothing here knows about
 * Android, Canvas or any particular screen size.
 */
class Table(
    val name: String,
    val width: Float,
    val height: Float,
    val ballRadius: Float,
    /** Inclination of the cabinet, in degrees. Drives the along-playfield gravity. */
    val inclineDegrees: Float,
    val walls: List<Wall>,
    val arcs: List<ArcWall>,
    val posts: List<Post>,
    val bumpers: List<Bumper>,
    val slingshots: List<Slingshot>,
    val targets: List<Target>,
    val rollovers: List<Rollover>,
    val saucers: List<Saucer>,
    val gobbleHole: GobbleHole,
    val flippers: List<FlipperSpec>,
    val gates: List<Gate>,
    val plunger: Plunger,
    val drainY: Float,
    val lamps: List<Lamp>,
    val art: List<ArtShape>,
) {
    companion object {
        /**
         * A real playfield is 20.25 in wide, and we model it as 1080 units, so
         * one metre is 1080 / 0.51435 units. Every physical constant in the
         * engine (gravity, ball mass, flipper speed) is derived from this so the
         * table plays at the speed of the real machine it is modelled on.
         */
        const val UNITS_PER_METRE = 2099.7f

        fun metresToUnits(m: Float) = m * UNITS_PER_METRE
    }
}

/** A straight rubber-or-wood wall, modelled as a capsule of radius [radius]. */
class Wall(
    val a: Vec2,
    val b: Vec2,
    val radius: Float = 6f,
    val restitution: Float = 0.42f,
    val friction: Float = 0.04f,
)

/**
 * A curved wall on the circle ([centre], [radius]) between [fromDeg] and [toDeg]
 * (counter-clockwise).
 *
 * [twoSided] rails - the ball guides under the top arch - can be hit from the
 * channel side or from the playfield side. One-sided arcs are containers: the
 * ball is kept on the inside.
 */
class ArcWall(
    val centre: Vec2,
    val radius: Float,
    val fromDeg: Float,
    val toDeg: Float,
    val thickness: Float = 7f,
    val twoSided: Boolean = false,
    val restitution: Float = 0.4f,
    val friction: Float = 0.04f,
)

/** A round post with a rubber ring around it. */
class Post(
    val centre: Vec2,
    val radius: Float,
    val restitution: Float = 0.52f,
)

/**
 * One of the nine bumpers in the criss-cross.
 *
 * Five of them are live pop bumpers that throw the ball back out; the other four
 * are plain scoring bumpers that only register a hit and bounce like a rubber.
 * Each carries one letter of the table's name.
 */
class Bumper(
    val id: String,
    val letter: String,
    val centre: Vec2,
    val radius: Float,
    /** Ejection speed in playfield units per second; zero for a passive bumper. */
    val kick: Float,
    val isPop: Boolean,
    val score: Int,
    val litScore: Int,
)

/**
 * The gobble hole.
 *
 * The defining feature of the machine: a hole in the middle of the playfield
 * that swallows the ball for good. Shoot it early and the ball is simply gone
 * for a handful of points; shoot it with every rollover button lit and losing
 * the ball is the point - it pays a replay.
 */
class GobbleHole(
    val id: String,
    val centre: Vec2,
    val radius: Float,
    val score: Int,
)

/**
 * A slingshot. The ball hits [a]..[b] and is thrown back along the face normal
 * (pointing away from [interior]) with [kick] added on top of the bounce.
 */
class Slingshot(
    val id: String,
    val a: Vec2,
    val b: Vec2,
    val interior: Vec2,
    val kick: Float,
    val score: Int,
    val radius: Float = 8f,
)

/** A stand-up target: a short wall that scores and latches when struck. */
class Target(
    val id: String,
    val letter: String,
    val a: Vec2,
    val b: Vec2,
    val score: Int,
    val litScore: Int,
    val radius: Float = 7f,
)

/** A pass-over switch (rollover button or star rollover). Purely a sensor. */
class Rollover(
    val id: String,
    val label: String,
    val centre: Vec2,
    val radius: Float,
    val kind: RolloverKind,
    val score: Int,
    val litScore: Int,
)

enum class RolloverKind { ARCH_LANE, STAR, INLANE, OUTLANE }

/** A kicker hole: swallows the ball, holds it, then spits it back out. */
class Saucer(
    val id: String,
    val centre: Vec2,
    val radius: Float,
    /** Direction the ball is ejected in, as a unit vector. */
    val ejectDir: Vec2,
    val ejectSpeed: Float,
    val holdSeconds: Float,
    val score: Int,
    val litScore: Int,
)

/**
 * A flipper, modelled as a tapered capsule rotating about [pivot].
 *
 * Angles are in degrees, measured counter-clockwise from +x in a y-down space,
 * so 0 points right and 90 points *up* the playfield.
 */
class FlipperSpec(
    val id: String,
    val pivot: Vec2,
    val length: Float,
    val baseRadius: Float,
    val tipRadius: Float,
    val restDeg: Float,
    val activeDeg: Float,
    /** Angular speed while energised / while returning, in degrees per second. */
    val upSpeedDegPerSec: Float,
    val downSpeedDegPerSec: Float,
    val restitution: Float = 0.30f,
)

/** A one-way gate: solid from one side, transparent from the other. */
class Gate(
    val id: String,
    val a: Vec2,
    val b: Vec2,
    /** Balls may only pass in this direction. */
    val passDir: Vec2,
)

/**
 * The shooter lane and its spring plunger.
 *
 * There is deliberately no one-way gate at the top. On this layout the lane
 * feeds straight into the arch, so a plunge too weak to crest it simply rolls
 * back down and the player shoots again - which is what the real machine does,
 * and which a gate across the lane would turn into a ledge the ball rests on.
 */
class Plunger(
    val laneX: Float,
    val innerX: Float,
    val outerX: Float,
    val restY: Float,
    val topY: Float,
    /** Ball speed at full pull, in playfield units per second. */
    val maxLaunchSpeed: Float,
    val minLaunchSpeed: Float,
)

/** A playfield insert or backbox bulb the rules can switch on and off. */
class Lamp(
    val id: String,
    val centre: Vec2,
    val radius: Float,
    val shape: LampShape,
    val colour: Int,
    val label: String = "",
    val angleDeg: Float = 0f,
    val width: Float = 0f,
    val height: Float = 0f,
)

enum class LampShape { ROUND, OVAL, ARROW, RECT }

// --------------------------------------------------------------------------
// Artwork primitives
// --------------------------------------------------------------------------

/**
 * One painted element of the playfield or cabinet.
 *
 * Everything the player sees that is *not* a moving part is expressed with these
 * few primitives. That keeps the Android renderer and the HTML preview honest:
 * both consume the same list, so what the preview shows is what the game draws.
 *
 * Colours are packed 0xAARRGGBB.
 */
sealed class ArtShape {
    abstract val layer: ArtLayer

    class Rect(
        override val layer: ArtLayer,
        val x: Float, val y: Float, val w: Float, val h: Float,
        val radius: Float = 0f,
        val fill: Int = 0,
        val stroke: Int = 0,
        val strokeWidth: Float = 0f,
        /** Optional vertical gradient: [fill] at the top, [fill2] at the bottom. */
        val fill2: Int = 0,
    ) : ArtShape()

    class Circle(
        override val layer: ArtLayer,
        val cx: Float, val cy: Float, val r: Float,
        val fill: Int = 0,
        val stroke: Int = 0,
        val strokeWidth: Float = 0f,
        val fill2: Int = 0,
    ) : ArtShape()

    class Poly(
        override val layer: ArtLayer,
        val points: List<Vec2>,
        val fill: Int = 0,
        val stroke: Int = 0,
        val strokeWidth: Float = 0f,
        val closed: Boolean = true,
    ) : ArtShape()

    /** A band of a circle - the workhorse for ball guides and concentric decor. */
    class Ring(
        override val layer: ArtLayer,
        val cx: Float, val cy: Float, val r: Float,
        val thickness: Float,
        val fromDeg: Float, val toDeg: Float,
        val fill: Int = 0,
        val cap: Boolean = false,
    ) : ArtShape()

    class Star(
        override val layer: ArtLayer,
        val cx: Float, val cy: Float,
        val outer: Float, val inner: Float,
        val points: Int,
        val angleDeg: Float = 0f,
        val fill: Int = 0,
        val stroke: Int = 0,
        val strokeWidth: Float = 0f,
    ) : ArtShape()

    class Label(
        override val layer: ArtLayer,
        val x: Float, val y: Float,
        val text: String,
        val size: Float,
        val colour: Int,
        val angleDeg: Float = 0f,
        val align: TextAlign = TextAlign.CENTRE,
        val weight: TextWeight = TextWeight.BOLD,
        val letterSpacing: Float = 0f,
        val italic: Boolean = false,
    ) : ArtShape()
}

enum class TextAlign { LEFT, CENTRE, RIGHT }
enum class TextWeight { REGULAR, BOLD, BLACK }

/** Painter's order. Everything in one layer is drawn before the next. */
enum class ArtLayer { BASE, DECOR, INSERT_HOLE, LINEWORK, PLASTIC, TRIM }

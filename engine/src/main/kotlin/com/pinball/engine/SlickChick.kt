package com.pinball.engine

/**
 * Slick Chick - Gottlieb, April 1963. Single player, wedge head.
 *
 * ## What is taken from the real machine
 *
 * The layout follows the documented structure of the original rather than a
 * generic period table:
 *
 *  - **Nine bumpers in a criss-cross.** SLICK reads across, CHICK reads down,
 *    and the two words share their middle letter, so five plus five makes nine.
 *    The five towards the centre are live pop bumpers; the four at the tips are
 *    plain scoring bumpers that only register the hit.
 *  - **The letters must be struck in order**, and each completed title lights
 *    one of five rollover buttons.
 *  - **A gobble hole in the middle of the playfield.** It swallows the ball. Hit
 *    it early and the ball is gone for a hundred points; hit it with all five
 *    buttons lit and losing the ball is the whole point - it pays a replay.
 *  - **Four numbered rollovers**, which taken in order light a second special.
 *
 * ## What is a reconstruction
 *
 * Exact positions are not published anywhere, so the coordinates below place the
 * documented furniture in documented relationships; they are not measured off a
 * real playfield. The artwork is entirely original - none of the machine's art
 * or the later video game's is reproduced here.
 *
 * ## Re-proportioning for a 9:16 phone
 *
 * A real playfield is about 1 : 2.07 (20.25 in x 42 in); after the score header
 * a portrait phone leaves about 1 : 1.55. The criss-cross is 840 units across,
 * so the table is recomposed rather than squashed: the top arch becomes the wide
 * shallow dome the real machine has instead of a deep semicircle, which is the
 * only way the five-wide bumper arm fits under it, and the bonus ladder lives in
 * the score header where a wedge head would have put it on the backglass.
 *
 * Units: 1080 across, 1670 down, so one unit is about 0.48 mm - real scale.
 */
object SlickChick {

    const val W = 1080f
    const val H = 1670f
    const val BALL_R = 27f

    /** Centre of the playable area. The shooter lane sits outside it, on the right. */
    const val PX = 494f

    private const val LEFT_WALL = 24f
    private const val RIGHT_WALL = 1056f
    private const val LANE_INNER = 964f
    private const val LANE_CENTRE = 1010f

    /**
     * The top dome. A wide, shallow arc struck from a centre far below the
     * playfield - the shape a real wedge head has. A true semicircle across this
     * width would need 516 units of height and would leave no room for the
     * bumper arm underneath.
     */
    private val DOME_C = Vec2(540f, 1150f)
    private const val DOME_OUTER = 1010f
    private const val DOME_INNER = 918f
    private const val DOME_MID = (DOME_OUTER + DOME_INNER) / 2f

    /**
     * Each arc runs between the points where it actually meets the cabinet, and
     * the two differ because the radii differ. Starting the inner guide at the
     * outer wall's angle instead puts its end inside the shooter lane, where the
     * ball hits it head-on and never reaches the dome at all.
     */
    private const val DOME_FROM = 72f
    private const val DOME_TO = 120.72f
    private const val GUIDE_FROM = 72f
    /**
     * The guide stops short of the left wall on purpose: run all the way to it
     * and the two meet at a shallow angle, making a wedge the ball rolls into
     * and never comes out of. Ending it at the far side of the last lane lets
     * the ball simply drop out of the channel, as it does on the real machine.
     */
    private const val GUIDE_TO = 120f

    /**
     * The curve that turns the shooter lane into the dome.
     *
     * Its radius is not chosen, it is solved: the arc has to be tangent to the
     * vertical lane where it leaves it and internally tangent to the dome
     * channel where it joins it, which fixes the radius at 249 and the centre at
     * (761, 470). Both its walls then land exactly on the lane walls, and the
     * join with the dome falls at 72 degrees.
     *
     * Without it the lane fires the ball straight into the underside of a nearly
     * horizontal wall: the hit is almost head-on, restitution eats half the
     * speed, and no plunge ever crosses the dome.
     */
    private val TRANSITION_C = Vec2(761f, 470f)
    private const val TRANSITION_R = 249f
    private const val TRANSITION_TO = 72f
    private const val CHANNEL_HALF = 46f

    /** The four numbered rollovers, as gaps in the dome's ball guide. */
    private val NUMBER_LANES = listOf(
        "4" to (113f to 120f),
        "3" to (101f to 108f),
        "2" to (89f to 96f),
        "1" to (77f to 84f),
    )

    // --- The criss-cross ----------------------------------------------------

    /** Centre of the cross, on the shared letter of the two words. */
    private val CROSS = Vec2(PX, 700f)
    /**
     * Spacing and size are set by two clearances that fight each other: the arms
     * must leave a ball's width between the outermost bumper and the side wall,
     * or the ball can never come down the sides at all; and the diagonal gaps
     * between the arms must stay wider than the ball, or it can never get in
     * among the nine. Orthogonally adjacent bumpers are deliberately closer than
     * a ball - the cluster is a nest, not a maze.
     */
    private const val CROSS_STEP = 155f
    private const val BUMPER_R = 58f

    /**
     * SLICK across, CHICK down, crossing on the I they have in common.
     *
     * The four at the tips of the arms are the plain scoring bumpers; the five
     * nearer the middle are the live pop bumpers.
     */
    private val CRISS_CROSS: List<Triple<String, Vec2, Boolean>> = listOf(
        Triple("S", Vec2(CROSS.x - 2 * CROSS_STEP, CROSS.y), false),
        Triple("L", Vec2(CROSS.x - CROSS_STEP, CROSS.y), true),
        Triple("I", CROSS, true),
        Triple("C", Vec2(CROSS.x + CROSS_STEP, CROSS.y), true),
        Triple("K", Vec2(CROSS.x + 2 * CROSS_STEP, CROSS.y), false),
        Triple("C2", Vec2(CROSS.x, CROSS.y - 2 * CROSS_STEP), false),
        Triple("H", Vec2(CROSS.x, CROSS.y - CROSS_STEP), true),
        Triple("C3", Vec2(CROSS.x, CROSS.y + CROSS_STEP), true),
        Triple("K2", Vec2(CROSS.x, CROSS.y + 2 * CROSS_STEP), false),
    )

    /** The order the letters have to be struck in. */
    val LETTER_ORDER = listOf("S", "L", "I", "C", "K", "C2", "H", "I", "C3", "K2")

    private val GOBBLE = Vec2(PX, 1246f)
    private const val GOBBLE_R = 46f

    /** The five buttons a completed title lights, one at a time. */
    /**
     * Four in the corners the criss-cross leaves free, and one under the dome.
     * None of them sits on the centre line below the cross: a button there is
     * crossed by every draining ball and lights itself for nothing.
     */
    private val BUTTONS = listOf(
        "button.1" to Vec2(78f, 520f),
        "button.2" to Vec2(910f, 520f),
        "button.3" to Vec2(78f, 1120f),
        "button.4" to Vec2(910f, 1120f),
        "button.5" to Vec2(593f, 330f),
    )
    private const val BUTTON_R = 30f

    /**
     * The stand-up targets sit in the open upper quadrants, not in the side
     * channels: those are barely two ball widths across, and a target laid over
     * one blocks it. The right-hand target is *derived* by mirroring - written
     * out by hand it drifted into the shooter lane, where it stopped every
     * plunge dead.
     */
    private val TARGET_L = Vec2(150f, 470f) to Vec2(250f, 520f)
    private val TARGET_R get() = mp(TARGET_L.second) to mp(TARGET_L.first)

    private val FLIP_L_PIVOT = Vec2(311f, 1470f)
    private const val FLIP_LEN = 155f
    private const val FLIP_REST = 28f

    private val SLING_L = Triple(Vec2(250f, 1200f), Vec2(370f, 1345f), Vec2(250f, 1345f))
    private val DIVIDER_L = listOf(Vec2(118f, 1190f), Vec2(118f, 1400f), Vec2(292f, 1444f))
    private val OUTLANE_L = Vec2(72f, 1300f)
    private val INLANE_L = Vec2(206f, 1398f)

    private fun mx(x: Float) = 2f * PX - x
    private fun mp(p: Vec2) = Vec2(mx(p.x), p.y)

    // ------------------------------------------------------------------------

    fun build(): Table = Table(
        name = "SLICK CHICK",
        width = W,
        height = H,
        ballRadius = BALL_R,
        inclineDegrees = 6.5f,
        walls = buildWalls(),
        arcs = buildArcs(),
        posts = buildPosts(),
        bumpers = CRISS_CROSS.map { (letter, at, pop) ->
            Bumper(
                id = "bumper.${letter.lowercase()}",
                letter = letter.take(1),
                centre = at,
                radius = BUMPER_R,
                kick = if (pop) 1350f else 0f,
                isPop = pop,
                score = if (pop) 100 else 10,
                litScore = if (pop) 1000 else 100,
            )
        },
        slingshots = listOf(slingshot("sling.left", SLING_L), slingshot("sling.right", mirror(SLING_L))),
        targets = listOf(
            Target("target.left", "L", TARGET_L.first, TARGET_L.second, 500, 5000),
            Target("target.right", "R", TARGET_R.first, TARGET_R.second, 500, 5000),
        ),
        rollovers = buildRollovers(),
        saucers = emptyList(),
        gobbleHole = GobbleHole("gobble", GOBBLE, GOBBLE_R, 100),
        flippers = listOf(
            FlipperSpec(
                id = "flipper.left",
                pivot = FLIP_L_PIVOT,
                length = FLIP_LEN,
                baseRadius = 22f,
                tipRadius = 13f,
                restitution = 0.40f,
                restDeg = -FLIP_REST,
                activeDeg = 30f,
                upSpeedDegPerSec = 2400f,
                downSpeedDegPerSec = 900f,
            ),
            FlipperSpec(
                id = "flipper.right",
                pivot = mp(FLIP_L_PIVOT),
                length = FLIP_LEN,
                baseRadius = 22f,
                tipRadius = 13f,
                restitution = 0.40f,
                restDeg = 180f + FLIP_REST,
                activeDeg = 150f,
                upSpeedDegPerSec = 2400f,
                downSpeedDegPerSec = 900f,
            ),
        ),
        gates = emptyList(),
        plunger = Plunger(
            laneX = LANE_CENTRE,
            innerX = LANE_INNER,
            outerX = RIGHT_WALL,
            restY = 1560f,
            topY = 470f,
            maxLaunchSpeed = 3400f,
            minLaunchSpeed = 2500f,
        ),
        drainY = H + BALL_R,
        lamps = buildLamps(),
        art = SlickChickArt.build(),
    )

    private fun mirror(t: Triple<Vec2, Vec2, Vec2>) = Triple(mp(t.first), mp(t.second), mp(t.third))

    private fun slingshot(id: String, t: Triple<Vec2, Vec2, Vec2>): Slingshot {
        val (a, b, c) = t
        return Slingshot(
            id = id,
            a = a,
            b = b,
            interior = Vec2((a.x + b.x + c.x) / 3f, (a.y + b.y + c.y) / 3f),
            kick = 1250f,
            score = 50,
        )
    }

    private fun buildWalls(): List<Wall> = buildList {
        fun chain(vararg p: Vec2, radius: Float = 6f, restitution: Float = 0.36f) {
            for (i in 0 until p.size - 1) add(Wall(p[i], p[i + 1], radius, restitution))
        }
        // Starts where the dome's outer wall actually meets it (y=282, solved
        // from the arc), not lower: any daylight between the two is a hole the
        // ball leaves the cabinet through.
        chain(Vec2(LEFT_WALL, 281f), Vec2(LEFT_WALL, 1330f), Vec2(88f, 1560f), Vec2(172f, H))
        chain(Vec2(LANE_INNER, 470f), Vec2(LANE_INNER, 1330f), Vec2(mx(88f), 1560f), Vec2(mx(172f), H))
        chain(Vec2(RIGHT_WALL, 470f), Vec2(RIGHT_WALL, H), restitution = 0.2f)
        chain(*DIVIDER_L.toTypedArray(), radius = 7f)
        chain(*DIVIDER_L.map(::mp).toTypedArray(), radius = 7f)
        for (s in listOf(SLING_L, mirror(SLING_L))) {
            add(Wall(s.first, s.third, 8f, 0.3f))
            add(Wall(s.third, s.second, 8f, 0.3f))
        }
        // No guides down the sides: the channels either side of the criss-cross
        // are only about two ball widths wide, and a rail in them would leave a
        // slot the ball jams in rather than a lane it runs down.
    }

    private fun buildArcs(): List<ArcWall> = buildList {
        // Shooter lane -> dome, tangent at both ends.
        add(ArcWall(TRANSITION_C, TRANSITION_R + CHANNEL_HALF, 0f, TRANSITION_TO, thickness = 8f, twoSided = false, restitution = 0.3f))
        add(ArcWall(TRANSITION_C, TRANSITION_R - CHANNEL_HALF, 0f, TRANSITION_TO, thickness = 8f, twoSided = true, restitution = 0.32f))
        add(ArcWall(DOME_C, DOME_OUTER, DOME_FROM, DOME_TO, thickness = 8f, twoSided = false, restitution = 0.3f))
        val gaps = NUMBER_LANES.map { it.second }.sortedBy { it.first }
        var cursor = GUIDE_FROM
        for ((from, to) in gaps) {
            add(ArcWall(DOME_C, DOME_INNER, cursor, from, thickness = 8f, twoSided = true, restitution = 0.32f))
            cursor = to
        }
        if (GUIDE_TO > cursor + 0.5f) {
            add(ArcWall(DOME_C, DOME_INNER, cursor, GUIDE_TO, thickness = 8f, twoSided = true, restitution = 0.32f))
        }
    }

    private fun buildPosts(): List<Post> = listOf(
        Post(Vec2(214f, 1120f), 18f),
        Post(mp(Vec2(214f, 1120f)), 18f),
        // Nothing on the centre line above the gobble hole: a post there shields
        // the one shot the whole game is built around.
    )

    private fun buildRollovers(): List<Rollover> = buildList {
        for ((label, span) in NUMBER_LANES) {
            val mid = (span.first + span.second) / 2f
            add(
                Rollover(
                    id = "lane.$label",
                    label = label,
                    centre = Vec2.polar(DOME_C, DOME_MID, mid),
                    radius = 34f,
                    kind = RolloverKind.ARCH_LANE,
                    score = 500,
                    litScore = 3000,
                )
            )
        }
        for ((id, at) in BUTTONS) {
            add(Rollover(id, "", at, BUTTON_R, RolloverKind.STAR, 100, 1000))
        }
        add(Rollover("outlane.left", "SPECIAL", OUTLANE_L, 26f, RolloverKind.OUTLANE, 1000, 25000))
        add(Rollover("outlane.right", "SPECIAL", mp(OUTLANE_L), 26f, RolloverKind.OUTLANE, 1000, 25000))
        add(Rollover("inlane.left", "", INLANE_L, 26f, RolloverKind.INLANE, 500, 2000))
        add(Rollover("inlane.right", "", mp(INLANE_L), 26f, RolloverKind.INLANE, 500, 2000))
    }

    private fun buildLamps(): List<Lamp> = buildList {
        for ((letter, at, _) in CRISS_CROSS) {
            add(Lamp("letter.${letter.lowercase()}", at, BUMPER_R * 0.5f, LampShape.ROUND, Palette.LAMP_AMBER, letter.take(1)))
        }
        for ((label, span) in NUMBER_LANES) {
            val mid = (span.first + span.second) / 2f
            add(
                Lamp(
                    id = "lane.$label",
                    centre = Vec2.polar(DOME_C, DOME_INNER - 44f, mid),
                    radius = 25f,
                    shape = LampShape.ROUND,
                    colour = Palette.LAMP_GREEN,
                    label = label,
                )
            )
        }
        for ((id, at) in BUTTONS) {
            add(Lamp(id, at, BUTTON_R - 4f, LampShape.ROUND, Palette.LAMP_RED))
        }
        add(Lamp("gobble.lit", Vec2(GOBBLE.x, GOBBLE.y - 82f), 24f, LampShape.OVAL, Palette.LAMP_WHITE, "SPECIAL", width = 150f, height = 42f))
        add(Lamp("outlane.left", OUTLANE_L, 24f, LampShape.OVAL, Palette.LAMP_RED, "SPECIAL", width = 66f, height = 34f))
        add(Lamp("outlane.right", mp(OUTLANE_L), 24f, LampShape.OVAL, Palette.LAMP_RED, "SPECIAL", width = 66f, height = 34f))
    }

    /** Shared with the art and the renderers so paint always lines up with physics. */
    internal object Geo {
        val domeCentre = DOME_C
        const val domeOuter = DOME_OUTER
        const val domeInner = DOME_INNER
        const val domeMid = DOME_MID
        const val domeFrom = DOME_FROM
        const val domeTo = DOME_TO
        const val guideFrom = GUIDE_FROM
        const val guideTo = GUIDE_TO
        val transitionCentre = TRANSITION_C
        const val transitionR = TRANSITION_R
        const val transitionTo = TRANSITION_TO
        const val channelHalf = CHANNEL_HALF
        val numberLanes = NUMBER_LANES
        val crissCross = CRISS_CROSS
        val cross = CROSS
        const val crossStep = CROSS_STEP
        const val bumperR = BUMPER_R
        val gobble = GOBBLE
        const val gobbleR = GOBBLE_R
        val buttons = BUTTONS
        const val buttonR = BUTTON_R
        val targets = listOf(TARGET_L, TARGET_R)
        val flipL = FLIP_L_PIVOT
        val slingL = SLING_L
        val dividerL = DIVIDER_L
        const val leftWall = LEFT_WALL
        const val rightWall = RIGHT_WALL
        const val laneInner = LANE_INNER
        const val laneCentre = LANE_CENTRE
        val outlaneL = OUTLANE_L
        val inlaneL = INLANE_L
        fun mirror(x: Float) = mx(x)
        fun mirror(p: Vec2) = mp(p)
    }
}

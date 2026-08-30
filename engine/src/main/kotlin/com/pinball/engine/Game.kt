package com.pinball.engine

import kotlin.math.max

/** Sounds the rules ask for. The audio layer decides what they actually sound like. */
enum class Sfx {
    CHIME_LOW, CHIME_MID, CHIME_HIGH,
    POP, SLING, FLIP, TARGET, ROLLOVER,
    RAIL, LAUNCH, DRAIN, GOBBLE, KNOCKER, TILT,
}

enum class Phase { ATTRACT, READY, PLAYING, BALL_OVER, GAME_OVER }

/** A short line of text for the header, e.g. "SHOOT AGAIN". */
class Flash(val text: String, var secondsLeft: Float)

/**
 * The rules of the 1963 machine.
 *
 * The whole game is one loop with a nasty hook in it:
 *
 *  1. Strike the nine criss-cross bumpers **in order** to spell the title -
 *     SLICK across, CHICK down, sharing the letter in the middle.
 *  2. Each completed title lights one of the five rollover buttons.
 *  3. With all five lit, the gobble hole in the middle of the playfield pays a
 *     replay - and it *takes the ball*, which is the point of it. Shoot it any
 *     earlier and the ball is simply gone for a hundred points.
 *
 * Separately, the four numbered rollovers under the dome taken in order light a
 * second special. There is no mode stack and nothing to wait through: the state
 * of the game is readable from the lamps, as an electromechanical has to be.
 */
class Game(val world: World) : WorldListener {

    var phase = Phase.ATTRACT
        private set
    var score = 0L
        private set
    var highScore = 0L
    var ball = 1
        private set
    var credits = 0
        private set
    var tilted = false
        private set

    /** How far into SLICK CHICK the player has got, 0 until 10. */
    var letterStep = 0
        private set

    /** How many times the title has been spelled out this game. */
    var titlesSpelled = 0
        private set

    private val lit = HashSet<String>()
    private var tiltWarnings = 0
    private var nextNumberLane = 1
    private var ballOverTimer = 0f
    private var extraBalls = 0

    val litLamps: Set<String> get() = lit
    val flashes = ArrayDeque<Flash>()
    val sounds = ArrayDeque<Sfx>()

    /** True when losing the ball down the gobble hole is worth a replay. */
    val gobbleLit: Boolean get() = BUTTONS.all { it in lit }

    init {
        world.litFeatures = lit
    }

    // --- Lifecycle ----------------------------------------------------------

    fun startGame() {
        score = 0
        ball = 1
        tilted = false
        tiltWarnings = 0
        letterStep = 0
        titlesSpelled = 0
        nextNumberLane = 1
        extraBalls = 0
        lit.clear()
        phase = Phase.READY
        world.serveBall()
        flash("BALL 1", 2f)
        sounds += Sfx.KNOCKER
    }

    fun update(dt: Float) {
        world.step(dt)

        val it = flashes.iterator()
        while (it.hasNext()) {
            val f = it.next()
            f.secondsLeft -= dt
            if (f.secondsLeft <= 0f) it.remove()
        }

        if (world.tiltBob > 1f && !tilted && phase == Phase.PLAYING) warnOrTilt()

        when (phase) {
            Phase.READY -> if (world.ball.state == BallState.FREE) phase = Phase.PLAYING
            Phase.BALL_OVER -> {
                ballOverTimer -= dt
                if (ballOverTimer <= 0f) nextBall()
            }
            else -> Unit
        }
    }

    private fun warnOrTilt() {
        tiltWarnings++
        if (tiltWarnings >= 3) {
            tilted = true
            flash("TILT", 3f)
            sounds += Sfx.TILT
        } else {
            flash("CAREFUL", 1.2f)
        }
    }

    // --- Scoring ------------------------------------------------------------

    private fun award(points: Int) {
        if (tilted) return
        score += points
        sounds += when {
            points >= 1000 -> Sfx.CHIME_LOW
            points >= 500 -> Sfx.CHIME_MID
            else -> Sfx.CHIME_HIGH
        }
        if (score >= REPLAY_SCORE && credits == 0) grantReplay("REPLAY")
    }

    private fun grantReplay(label: String) {
        credits++
        flash(label, 2.5f)
        sounds += Sfx.KNOCKER
    }

    private fun flash(text: String, seconds: Float) {
        flashes += Flash(text, seconds)
    }

    // --- WorldListener ------------------------------------------------------

    override fun onBumper(bumper: Bumper, impactSpeed: Float) {
        sounds += if (bumper.isPop) Sfx.POP else Sfx.CHIME_HIGH

        // Only the bumper carrying the letter the player is waiting for advances
        // the sequence. Everything else just scores.
        val wanted = SlickChick.LETTER_ORDER.getOrNull(letterStep)
        if (wanted != null && bumper.id == "bumper.${wanted.lowercase()}") {
            lit += "letter.${wanted.lowercase()}"
            letterStep++
            award(bumper.litScore)
            if (letterStep >= SlickChick.LETTER_ORDER.size) completeTitle()
        } else {
            award(bumper.score)
        }
    }

    private fun completeTitle() {
        titlesSpelled++
        letterStep = 0
        lit.removeAll { it.startsWith("letter.") }

        val next = BUTTONS.firstOrNull { it !in lit }
        if (next != null) {
            lit += next
            flash("BUTTON ${BUTTONS.indexOf(next) + 1} LIT", 2.5f)
        }
        sounds += Sfx.KNOCKER
        if (gobbleLit) flash("GOBBLE HOLE LIT", 3f)
    }

    override fun onSlingshot(sling: Slingshot) {
        sounds += Sfx.SLING
        award(sling.score)
    }

    override fun onTarget(target: Target) {
        sounds += Sfx.TARGET
        award(target.score)
    }

    override fun onRollover(rollover: Rollover) {
        when (rollover.kind) {
            RolloverKind.ARCH_LANE -> {
                sounds += Sfx.ROLLOVER
                // The numbered rollovers only count taken in order.
                if (rollover.label == nextNumberLane.toString()) {
                    lit += rollover.id
                    award(rollover.litScore)
                    nextNumberLane++
                    if (nextNumberLane > NUMBER_LANES) {
                        nextNumberLane = 1
                        lit.removeAll { it.startsWith("lane.") }
                        grantReplay("SPECIAL")
                    }
                } else {
                    award(rollover.score)
                    nextNumberLane = 1
                    lit.removeAll { it.startsWith("lane.") }
                }
            }

            RolloverKind.STAR -> {
                // The five buttons. Passing over a lit one collects it.
                sounds += Sfx.ROLLOVER
                award(if (rollover.id in lit) rollover.litScore else rollover.score)
            }

            RolloverKind.INLANE -> {
                sounds += Sfx.RAIL
                award(rollover.score)
            }

            RolloverKind.OUTLANE -> {
                sounds += Sfx.RAIL
                if (rollover.id in lit) {
                    award(rollover.litScore)
                    grantReplay("SPECIAL")
                } else {
                    award(rollover.score)
                }
            }
        }
    }

    /**
     * The ball is gone either way. Whether that was a catastrophe or the plan
     * depends entirely on whether the player lit all five buttons first.
     */
    override fun onGobbleHole(hole: GobbleHole) {
        sounds += Sfx.GOBBLE
        if (gobbleLit && !tilted) {
            grantReplay("SPECIAL")
            lit.removeAll { it in BUTTONS }
        } else {
            award(hole.score)
            flash("TOO SOON", 2f)
        }
        endBall()
    }

    override fun onFlipperHit(impactSpeed: Float) {
        if (impactSpeed > 400f) sounds += Sfx.FLIP
    }

    override fun onWallHit(impactSpeed: Float) {
        if (impactSpeed > 900f) sounds += Sfx.RAIL
    }

    override fun onLaunch(power: Float) {
        sounds += Sfx.LAUNCH
    }

    override fun onDrain() {
        sounds += Sfx.DRAIN
        endBall()
    }

    private fun endBall() {
        if (phase != Phase.PLAYING && phase != Phase.READY) return
        phase = Phase.BALL_OVER
        ballOverTimer = 1.6f
    }

    // --- End of ball --------------------------------------------------------

    private fun nextBall() {
        tilted = false
        tiltWarnings = 0
        nextNumberLane = 1
        lit.removeAll { it.startsWith("lane.") }

        if (extraBalls > 0) {
            extraBalls--
            flash("SHOOT AGAIN", 2.5f)
            phase = Phase.READY
            world.serveBall()
            return
        }
        if (ball >= BALLS_PER_GAME) {
            endGame()
            return
        }
        ball++
        // The letters and the buttons carry over; only the ball resets.
        phase = Phase.READY
        world.serveBall()
        flash("BALL $ball", 2f)
    }

    private fun endGame() {
        phase = Phase.GAME_OVER
        highScore = max(highScore, score)
        if ((score % 100).toInt() == (0..9).random() * 10) {
            grantReplay("MATCH")
        } else {
            flash("GAME OVER", 3f)
        }
    }

    companion object {
        const val BALLS_PER_GAME = 5
        const val REPLAY_SCORE = 120_000L
        const val NUMBER_LANES = 4
        val BUTTONS = listOf("button.1", "button.2", "button.3", "button.4", "button.5")
    }
}

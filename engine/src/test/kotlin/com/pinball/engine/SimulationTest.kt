package com.pinball.engine

import kotlin.math.hypot
import kotlin.random.Random
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Exercises the solver: the ball has to stay on the table and behave like a pinball. */
class SimulationTest {

    private fun world() = World(SlickChick.build())

    private fun runFor(w: World, seconds: Float, dt: Float = 1f / 60f, onFrame: (Int) -> Unit = {}) {
        val frames = (seconds / dt).toInt()
        for (i in 0 until frames) {
            onFrame(i)
            w.step(dt)
            if (w.ball.state == BallState.DRAINED) return
        }
    }

    /** Specific energy of the ball: the quantity friction is allowed to eat into. */
    private fun energy(w: World): Float =
        0.5f * w.ball.speed * w.ball.speed + w.gravity * (w.table.height - w.ball.y)

    @Test
    fun `a full plunge carries the ball across the dome and down the far side`() {
        val w = world()
        w.serveBall()
        w.setPlunger(1f)
        w.launch()

        var minY = Float.MAX_VALUE
        var reachedLeftSide = false
        runFor(w, 6f) {
            minY = minOf(minY, w.ball.y)
            if (w.ball.y < 420f && w.ball.x < 320f) reachedLeftSide = true
        }
        assertTrue(minY < 300f, "full plunge only reached y=$minY; it should crest the dome")
        assertTrue(reachedLeftSide, "full plunge never made it across to the left of the dome")
    }

    @Test
    fun `a plunge too weak to crest the dome comes back for another go`() {
        var returned = false
        val w = World(SlickChick.build(), object : WorldListener {
            override fun onReturnToLane() { returned = true }
        })
        w.serveBall()
        w.setPlunger(0f)
        w.launch()
        runFor(w, 8f)

        assertTrue(returned, "a weak plunge should roll back down the shooter lane")
        assertEquals(BallState.IN_LANE, w.ball.state, "the ball should be sitting on the plunger again")
    }

    @Test
    fun `the ball never leaves the cabinet, however hard it is played`() {
        val table = SlickChick.build()
        val w = World(table)
        val rng = Random(7)
        var balls = 0
        w.serveBall()
        w.setPlunger(rng.nextFloat())
        w.launch()

        var frames = 0
        while (frames < 60 * 90) {
            frames++
            if (frames % 7 == 0) {
                w.setFlipper(true, rng.nextInt(3) == 0)
                w.setFlipper(false, rng.nextInt(3) == 0)
            }
            if (w.ball.state == BallState.IN_LANE) {
                w.setPlunger(0.4f + rng.nextFloat() * 0.6f)
                w.launch()
            }
            w.step(1f / 60f)

            val b = w.ball
            assertTrue(b.x > -40f && b.x < table.width + 40f, "ball escaped sideways to x=${b.x} after $frames frames")
            assertTrue(b.y > -40f, "ball escaped through the top at y=${b.y}")
            assertTrue(b.speed <= World.MAX_SPEED + 1f, "ball reached ${b.speed} units/s")

            if (b.state == BallState.DRAINED) {
                balls++
                if (balls > 12) break
                w.serveBall()
                w.setPlunger(rng.nextFloat())
                w.launch()
            }
        }
        assertTrue(balls > 0, "no ball ever drained in 90 seconds of random play")
    }

    @Test
    fun `every ball reaches the drain, from every plunge, in a believable time`() {
        // The most valuable test on the table. Three separate defects showed up
        // here and nowhere else: a ball wedged between the flipper tips, a
        // bumper-and-wall oscillator in a side corridor, and a ball resting on a
        // target while it re-scored on every substep.
        for (seed in 1L..12L) {
            val hits = HashMap<String, Int>()
            val w = World(SlickChick.build(), object : WorldListener {
                override fun onBumper(bumper: Bumper, impactSpeed: Float) { hits.merge(bumper.id, 1, Int::plus) }
                override fun onTarget(target: Target) { hits.merge(target.id, 1, Int::plus) }
            }, seed = seed)
            w.serveBall()
            w.setPlunger(0.35f + (seed % 6) * 0.12f)
            w.launch()

            val rng = Random(seed)
            var frames = 0
            while (frames < 60 * 90 && w.ball.state != BallState.DRAINED) {
                if (w.ball.state == BallState.IN_LANE) {
                    w.setPlunger(0.4f + rng.nextFloat() * 0.6f)
                    w.launch()
                }
                w.step(1f / 60f)
                frames++
            }

            assertEquals(
                BallState.DRAINED, w.ball.state,
                "seed $seed was still in play after 90 seconds without flippers",
            )
            val worst = hits.maxByOrNull { it.value }
            if (worst != null) {
                assertTrue(
                    worst.value < 90,
                    "seed $seed struck ${worst.key} ${worst.value} times: it is stuck on it, not playing",
                )
            }
        }
    }

    @Test
    fun `the gobble hole swallows the ball for good`() {
        val table = SlickChick.build()
        var swallowed = false
        val w = World(table, object : WorldListener {
            override fun onGobbleHole(hole: GobbleHole) { swallowed = true }
        })
        w.ball.state = BallState.FREE
        w.ball.x = table.gobbleHole.centre.x
        w.ball.y = table.gobbleHole.centre.y - 120f
        w.ball.vy = 200f

        runFor(w, 2f)
        assertTrue(swallowed, "the ball rolled over the gobble hole instead of dropping in")
        assertEquals(BallState.DRAINED, w.ball.state, "the gobble hole gave the ball back")
    }

    @Test
    fun `a raised flipper shoots a resting ball back up the playfield`() {
        val w = world()
        val flipper = w.flippers[0]
        val rest = flipper.tip()

        w.ball.state = BallState.FREE
        w.ball.x = (flipper.spec.pivot.x + rest.x) / 2f
        w.ball.y = (flipper.spec.pivot.y + rest.y) / 2f - flipper.spec.baseRadius - w.ball.radius - 1f
        w.ball.vy = 40f

        w.setFlipper(true, true)
        var fastestUp = 0f
        runFor(w, 0.35f) { fastestUp = maxOf(fastestUp, -w.ball.vy) }

        // A real flipper puts 2-5 m/s on the ball; below 2 m/s nothing is reachable.
        val metresPerSecond = fastestUp / Table.UNITS_PER_METRE
        assertTrue(
            metresPerSecond > 2.0f && metresPerSecond < 6.0f,
            "flipper shot the ball at $metresPerSecond m/s",
        )
    }

    @Test
    fun `a live bumper throws the ball away from its centre and a dead one does not`() {
        val table = SlickChick.build()
        for (bumper in listOf(table.bumpers.first { it.isPop }, table.bumpers.first { !it.isPop })) {
            var kickSpeed = 0f
            lateinit var w: World
            w = World(table, object : WorldListener {
                override fun onBumper(b: Bumper, impactSpeed: Float) {
                    if (b.id == bumper.id) kickSpeed = w.ball.speed
                }
            })
            w.ball.state = BallState.FREE
            w.ball.x = bumper.centre.x
            w.ball.y = bumper.centre.y - bumper.radius - table.ballRadius - 3f
            w.ball.vy = 500f

            runFor(w, 0.2f)
            assertTrue(kickSpeed > 0f, "the ball passed through ${bumper.id}")
            if (bumper.isPop) {
                assertTrue(kickSpeed > bumper.kick * 0.85f, "${bumper.id} only managed $kickSpeed units/s")
            } else {
                assertTrue(kickSpeed < 900f, "${bumper.id} has no coil but kicked at $kickSpeed units/s")
            }
        }
    }

    @Test
    fun `sliding along a guide costs the ball almost nothing`() {
        // Regression. Friction used to be applied once per substep instead of per
        // unit of normal impulse, so a ball riding the dome - in contact on every
        // one of those substeps - shed about 70% of its speed. Compare energy,
        // since most of the speed lost climbing is stored as height.
        val w = world()
        w.serveBall()
        w.setPlunger(1f)
        w.launch()
        val launchEnergy = energy(w)

        // Only the first crossing counts. Left running, the ball comes back up
        // later with much less energy and the measurement stops meaning anything.
        var lowestOnDome = Float.MAX_VALUE
        var reachedTop = false
        var frames = 0
        while (frames < 60 * 4 && w.ball.state == BallState.FREE) {
            w.step(1f / 120f)
            frames++
            if (w.ball.y < 210f) {
                reachedTop = true
                lowestOnDome = minOf(lowestOnDome, energy(w))
            } else if (reachedTop) {
                break
            }
        }
        assertTrue(reachedTop, "a full plunge never reached the top of the dome")
        val kept = lowestOnDome / launchEnergy
        assertTrue(kept > 0.70f, "riding the dome cost ${((1 - kept) * 100).toInt()}% of the ball's energy")
    }

    @Test
    fun `rollovers fire once per pass, not once per physics step`() {
        val table = SlickChick.build()
        val fired = mutableListOf<String>()
        val w = World(table, object : WorldListener {
            override fun onRollover(rollover: Rollover) { fired += rollover.id }
        })
        val button = table.rollovers.first { it.kind == RolloverKind.STAR && it.centre.y > 900f }
        w.ball.state = BallState.FREE
        w.ball.x = button.centre.x
        w.ball.y = button.centre.y - 200f
        w.ball.vy = 700f

        runFor(w, 1.2f)
        assertEquals(1, fired.count { it == button.id }, "button fired ${fired.count { it == button.id }} times in one pass")
    }

    @Test
    fun `a target resting against the ball scores once, not once per substep`() {
        // Regression: targets are solid as well as scoring, so a ball can settle
        // against one. Edge-trigger them or a single ball racks up tens of
        // thousands of hits on one target.
        val table = SlickChick.build()
        val target = table.targets.first()
        var hits = 0
        val w = World(table, object : WorldListener {
            override fun onTarget(t: Target) { if (t.id == target.id) hits++ }
        })
        val mid = Vec2((target.a.x + target.b.x) / 2f, (target.a.y + target.b.y) / 2f)
        w.ball.state = BallState.FREE
        w.ball.x = mid.x
        w.ball.y = mid.y - target.radius - table.ballRadius - 1f
        w.ball.vy = 30f

        runFor(w, 3f)
        assertTrue(hits in 1..20, "a ball sitting on one target scored it $hits times in three seconds")
    }
}

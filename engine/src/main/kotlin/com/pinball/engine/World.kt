package com.pinball.engine

import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.sign
import kotlin.math.sin
import kotlin.random.Random

/** Where the ball is in its life cycle. */
enum class BallState { WAITING, IN_LANE, FREE, CAPTURED, DRAINED }

/** The one ball. Kept as bare floats: the solver runs thousands of times a second. */
class Ball(var radius: Float) {
    var x = 0f
    var y = 0f
    var vx = 0f
    var vy = 0f
    var state = BallState.WAITING

    val speed: Float get() = hypot(vx, vy)

    fun place(p: Vec2) {
        x = p.x; y = p.y; vx = 0f; vy = 0f
    }
}

/** Runtime state of one flipper. */
class Flipper(val spec: FlipperSpec) {
    var angleDeg = spec.restDeg
        private set
    var omegaRadPerSec = 0f
        private set
    var pressed = false

    val isMoving: Boolean get() = abs(omegaRadPerSec) > 1e-4f

    fun update(dt: Float) {
        val target = if (pressed) spec.activeDeg else spec.restDeg
        val speed = if (pressed) spec.upSpeedDegPerSec else spec.downSpeedDegPerSec
        val diff = target - angleDeg
        val stepDeg = speed * dt
        if (abs(diff) <= stepDeg) {
            omegaRadPerSec = if (dt > 0f) Math.toRadians((diff / dt).toDouble()).toFloat() else 0f
            angleDeg = target
        } else {
            val d = sign(diff) * stepDeg
            angleDeg += d
            omegaRadPerSec = Math.toRadians((d / dt).toDouble()).toFloat()
        }
    }

    fun direction(): Vec2 {
        val r = Math.toRadians(angleDeg.toDouble())
        return Vec2(cos(r).toFloat(), -sin(r).toFloat())
    }

    fun tip(): Vec2 = spec.pivot + direction() * spec.length

    /** Capsule radius a fraction [t] of the way from pivot to tip. */
    fun radiusAt(t: Float) = spec.baseRadius + (spec.tipRadius - spec.baseRadius) * t
}

/** Everything the rules layer wants to know about. */
interface WorldListener {
    fun onBumper(bumper: Bumper, impactSpeed: Float) {}
    fun onSlingshot(sling: Slingshot) {}
    fun onTarget(target: Target) {}
    fun onRollover(rollover: Rollover) {}
    fun onSaucerCapture(saucer: Saucer) {}
    fun onSaucerEject(saucer: Saucer) {}
    fun onFlipperHit(impactSpeed: Float) {}
    fun onWallHit(impactSpeed: Float) {}
    fun onGobbleHole(hole: GobbleHole) {}
    fun onDrain() {}
    fun onLaunch(power: Float) {}
    fun onReturnToLane() {}
    fun onNudge(strength: Float) {}
}

/**
 * The simulation: one ball, a fixed playfield, and a solver that runs in small
 * enough steps that a 4 m/s ball cannot pass through a 6-unit-thick wall.
 *
 * Units are playfield units and seconds; see [Table.UNITS_PER_METRE]. Gravity is
 * the component of g along an inclined cabinet, which is why a pinball
 * accelerates so much more gently than a falling object.
 */
class World(
    val table: Table,
    private val listener: WorldListener = object : WorldListener {},
    /** Fixed by default so a game replays identically; varied by the tests. */
    seed: Long = 20250830L,
) {

    val ball = Ball(table.ballRadius)
    val flippers: List<Flipper> = table.flippers.map(::Flipper)

    /** Lamp / feature state the rules own; the world only reads it for scoring. */
    var litFeatures: Set<String> = emptySet()

    /** Along-playfield gravity, in units per second squared. */
    val gravity: Float =
        Table.metresToUnits(9.81f) * sin(Math.toRadians(table.inclineDegrees.toDouble())).toFloat()

    private val arcCaps: List<Post> = buildArcCaps()

    private var capturedIn: Saucer? = null
    private var captureTimer = 0f

    /** Rollovers the ball is currently sitting on, so each pass fires once. */
    private val activeSensors = HashSet<String>()

    /** Solid scoring surfaces the ball is resting against; see [freshContact]. */
    private val inContact = HashSet<String>()
    private val touchedThisStep = HashSet<String>()

    private var plungerPower = 0f
    private var stillTime = 0f
    private var anchorX = 0f
    private var anchorY = 0f
    private val rng = Random(seed)

    /** Accumulated cabinet shove; decays back to zero. */
    var tiltBob = 0f
        private set

    // --- Public control -----------------------------------------------------

    fun serveBall() {
        ball.place(Vec2(table.plunger.laneX, table.plunger.restY))
        ball.state = BallState.IN_LANE
        plungerPower = 0f
        activeSensors.clear()
        inContact.clear()
        capturedIn = null
        resetStuckAnchor()
    }

    fun setPlunger(power: Float) {
        plungerPower = power.coerceIn(0f, 1f)
    }

    val plungerPull: Float get() = plungerPower

    fun launch() {
        if (ball.state != BallState.IN_LANE) return
        val p = table.plunger
        val speed = p.minLaunchSpeed + (p.maxLaunchSpeed - p.minLaunchSpeed) * plungerPower
        ball.vy = -speed
        ball.vx = 0f
        ball.state = BallState.FREE
        listener.onLaunch(plungerPower)
        plungerPower = 0f
    }

    /** A shove of the cabinet. [dx]/[dy] are in units per second. */
    fun nudge(dx: Float, dy: Float) {
        if (ball.state == BallState.FREE || ball.state == BallState.IN_LANE) {
            ball.vx += dx
            ball.vy += dy
        }
        tiltBob += hypot(dx, dy) / 260f
        listener.onNudge(hypot(dx, dy))
    }

    fun setFlipper(left: Boolean, down: Boolean) {
        flippers.getOrNull(if (left) 0 else 1)?.pressed = down
    }

    // --- Simulation ---------------------------------------------------------

    /**
     * Advances by [frameDt] seconds, split into as many substeps as the ball's
     * speed requires. The cap keeps a fast ball from stepping further than a
     * fraction of its own radius, which is what stops it tunnelling through a wall.
     */
    fun step(frameDt: Float) {
        val dt = frameDt.coerceAtMost(1f / 30f)
        tiltBob = max(0f, tiltBob - dt * 0.55f)

        val travel = ball.speed * dt
        val needed = (travel / (ball.radius * 0.35f)).toInt() + 1
        val substeps = needed.coerceIn(6, 96)
        val h = dt / substeps

        repeat(substeps) { integrate(h) }
    }

    private fun integrate(dt: Float) {
        for (f in flippers) f.update(dt)

        when (ball.state) {
            BallState.CAPTURED -> {
                captureTimer -= dt
                if (captureTimer <= 0f) releaseFromSaucer()
                return
            }

            BallState.IN_LANE -> {
                // Held against the plunger tip; the pull only moves it a little.
                ball.x = table.plunger.laneX
                ball.y = table.plunger.restY + plungerPower * 46f
                return
            }

            BallState.FREE -> Unit
            else -> return
        }

        ball.vy += gravity * dt
        // Rolling resistance on a wooden playfield, plus a hard speed ceiling so
        // the substep cap above is always enough to prevent tunnelling.
        val damp = 1f - 0.32f * dt
        ball.vx *= damp
        ball.vy *= damp
        val sp = ball.speed
        if (sp > MAX_SPEED) {
            ball.vx *= MAX_SPEED / sp
            ball.vy *= MAX_SPEED / sp
        }

        ball.x += ball.vx * dt
        ball.y += ball.vy * dt

        collideStatic()
        collideFlippers()
        checkSensors()
        checkStuck(dt)

        if (returnedToShooterLane()) return

        if (ball.y > table.drainY) {
            ball.state = BallState.DRAINED
            listener.onDrain()
        }
    }

    /**
     * A plunge too weak to crest the arch rolls back down the shooter lane. The
     * machine does not punish that: the ball settles against the plunger and the
     * player shoots again.
     */
    private fun returnedToShooterLane(): Boolean {
        val p = table.plunger
        if (ball.x <= p.innerX + ball.radius || ball.x >= p.outerX) return false
        if (ball.y < p.restY) return false
        ball.state = BallState.IN_LANE
        ball.place(Vec2(p.laneX, p.restY))
        plungerPower = 0f
        listener.onReturnToLane()
        return true
    }

    // --- Collision ----------------------------------------------------------

    private fun collideStatic() {
        touchedThisStep.clear()
        for (w in table.walls) resolveSegment(w.a, w.b, w.radius, w.restitution, w.friction, null)
        for (a in table.arcs) resolveArc(a)
        for (p in arcCaps) resolveCircle(p.centre, p.radius, p.restitution, null)
        for (p in table.posts) resolveCircle(p.centre, p.radius, p.restitution, null)

        for (b in table.bumpers) {
            if (b.isPop) {
                if (resolveCircle(b.centre, b.radius, 0.25f) { impact -> popBumper(b, impact) }) return
            } else if (resolveCircle(b.centre, b.radius, 0.55f) {} && freshContact(b.id)) {
                // A plain scoring bumper: it registers the hit and bounces like a
                // rubber, but has no coil to throw the ball back out.
                listener.onBumper(b, 0f)
            }
        }

        for (s in table.slingshots) {
            if (resolveSegment(s.a, s.b, s.radius, 0.2f, 0.05f) {} && freshContact(s.id)) {
                val face = (s.b - s.a).normalized()
                var n = face.perp()
                val toInterior = s.interior - s.a
                if (n.dot(toInterior) > 0f) n = -n
                ball.vx = n.x * s.kick + face.x * ball.vx * 0.25f
                ball.vy = n.y * s.kick + face.y * ball.vy * 0.25f
                listener.onSlingshot(s)
            }
        }

        for (t in table.targets) {
            if (resolveSegment(t.a, t.b, t.radius, 0.34f, 0.06f) {} && freshContact(t.id)) {
                listener.onTarget(t)
            }
        }

        for (g in table.gates) {
            // Solid only against balls trying to go the wrong way through it.
            if (ball.vx * g.passDir.x + ball.vy * g.passDir.y < 0f) {
                resolveSegment(g.a, g.b, 5f, 0.1f, 0.1f, null)
            }
        }

        inContact.retainAll(touchedThisStep)
    }

    /**
     * True the first substep the ball touches [id], false while it stays there.
     *
     * Targets and slingshots are solid *and* scoring, so unlike a rollover the
     * ball can come to rest against one. Without this a settled ball re-scored
     * its target on every substep - tens of thousands of times over one ball.
     */
    private fun freshContact(id: String): Boolean {
        touchedThisStep += id
        return inContact.add(id)
    }

    /**
     * Fires a pop bumper.
     *
     * A purely radial kick of a fixed size is the obvious implementation and it
     * is wrong: it makes the bounce perfectly reversible, so a ball can settle
     * into a closed orbit against one bumper and stay there for minutes. A real
     * bumper trips whichever side of its skirt the ball touches first and throws
     * it off-axis, so the kick gets a few degrees of scatter, a little variation
     * in strength, and keeps some of the ball's own sideways motion.
     */
    private fun popBumper(b: Bumper, impact: Float) {
        val n = Vec2(ball.x - b.centre.x, ball.y - b.centre.y).normalized()
        val skew = (rng.nextFloat() - 0.5f) * BUMPER_SCATTER
        val c = cos(skew)
        val s = sin(skew)
        val kx = n.x * c - n.y * s
        val ky = n.x * s + n.y * c
        val power = b.kick * (0.90f + rng.nextFloat() * 0.20f)
        val tangential = -n.y * ball.vx + n.x * ball.vy
        ball.vx = kx * power + -n.y * tangential * 0.22f
        ball.vy = ky * power + n.x * tangential * 0.22f
        listener.onBumper(b, impact)
    }

    private fun collideFlippers() {
        for (f in flippers) {
            val pivot = f.spec.pivot
            val tip = f.tip()
            val abx = tip.x - pivot.x
            val aby = tip.y - pivot.y
            val lenSq = abx * abx + aby * aby
            var t = ((ball.x - pivot.x) * abx + (ball.y - pivot.y) * aby) / lenSq
            t = t.coerceIn(0f, 1f)
            val cx = pivot.x + abx * t
            val cy = pivot.y + aby * t
            var nx = ball.x - cx
            var ny = ball.y - cy
            var d = hypot(nx, ny)
            val minDist = ball.radius + f.radiusAt(t)
            if (d >= minDist) continue
            if (d < 1e-4f) {
                nx = 0f; ny = -1f; d = 1e-4f
            } else {
                nx /= d; ny /= d
            }

            ball.x += nx * (minDist - d)
            ball.y += ny * (minDist - d)

            // Velocity of the flipper surface at the contact point.
            val relx = cx - pivot.x
            val rely = cy - pivot.y
            val svx = f.omegaRadPerSec * rely
            val svy = -f.omegaRadPerSec * relx

            val rvx = ball.vx - svx
            val rvy = ball.vy - svy
            val vn = rvx * nx + rvy * ny
            if (vn < 0f) {
                val j = -(1f + f.spec.restitution) * vn
                ball.vx += nx * j
                ball.vy += ny * j
                // A little tangential grab, so a moving flipper puts English on the ball.
                val tvx = rvx - nx * vn
                val tvy = rvy - ny * vn
                ball.vx -= tvx * FLIPPER_GRAB
                ball.vy -= tvy * FLIPPER_GRAB
                listener.onFlipperHit(abs(vn))
            }
        }
    }

    /** @return true if a hit was resolved. */
    private inline fun resolveSegment(
        a: Vec2,
        b: Vec2,
        radius: Float,
        restitution: Float,
        friction: Float,
        noinline onHit: ((Float) -> Unit)?,
    ): Boolean {
        val abx = b.x - a.x
        val aby = b.y - a.y
        val lenSq = abx * abx + aby * aby
        if (lenSq < 1e-6f) return false
        var t = ((ball.x - a.x) * abx + (ball.y - a.y) * aby) / lenSq
        t = t.coerceIn(0f, 1f)
        val cx = a.x + abx * t
        val cy = a.y + aby * t
        return bounceOffPoint(cx, cy, radius, restitution, friction, onHit)
    }

    private inline fun resolveCircle(
        centre: Vec2,
        radius: Float,
        restitution: Float,
        noinline onHit: ((Float) -> Unit)? = null,
    ): Boolean = bounceOffPoint(centre.x, centre.y, radius, restitution, 0.03f, onHit)

    private inline fun bounceOffPoint(
        cx: Float,
        cy: Float,
        radius: Float,
        restitution: Float,
        friction: Float,
        noinline onHit: ((Float) -> Unit)?,
    ): Boolean {
        var nx = ball.x - cx
        var ny = ball.y - cy
        var d = hypot(nx, ny)
        val minDist = ball.radius + radius
        if (d >= minDist) return false
        if (d < 1e-4f) {
            nx = 0f; ny = -1f; d = 1e-4f
        } else {
            nx /= d; ny /= d
        }
        ball.x += nx * (minDist - d)
        ball.y += ny * (minDist - d)

        val vn = ball.vx * nx + ball.vy * ny
        val impact = abs(vn)
        if (vn < 0f) {
            applyBounce(nx, ny, vn, restitution, friction)
            if (onHit != null) onHit(impact) else if (impact > 220f) listener.onWallHit(impact)
        }
        return true
    }

    /**
     * Applies one contact impulse.
     *
     * Friction is Coulomb - the tangential impulse is capped at [friction] times
     * the normal impulse - and that detail decides whether the table plays at
     * all. Scaling the tangential velocity by a flat `(1 - friction)` instead
     * looks equivalent for a single sharp bounce, but a ball *sliding* along a
     * curved guide is in contact every substep, so the flat version compounds:
     * at 48 substeps a 0.04 coefficient keeps only 14% of the ball's speed and
     * the shooter lane can no longer push a ball round the arch. Here a grazing
     * contact has a small normal impulse and so costs almost nothing.
     */
    private fun applyBounce(nx: Float, ny: Float, vn: Float, restitution: Float, friction: Float) {
        val tvx = ball.vx - nx * vn
        val tvy = ball.vy - ny * vn
        val tangentSpeed = hypot(tvx, tvy)
        val normalImpulse = -(1f + restitution) * vn
        val keep = if (tangentSpeed > 1e-4f) {
            1f - (friction * normalImpulse / tangentSpeed).coerceAtMost(1f)
        } else {
            0f
        }
        ball.vx = tvx * keep - nx * vn * restitution
        ball.vy = tvy * keep - ny * vn * restitution
    }

    private fun resolveArc(arc: ArcWall) {
        val dx = ball.x - arc.centre.x
        val dy = ball.y - arc.centre.y
        val d = hypot(dx, dy)
        if (d < 1e-3f) return

        val half = arc.thickness / 2f
        val insideSurface = arc.radius - half

        val nx: Float
        val ny: Float
        val pen: Float
        if (arc.twoSided) {
            if (d > arc.radius) {
                pen = ball.radius + half - (d - arc.radius)
                if (pen <= 0f) return
                nx = dx / d; ny = dy / d
            } else {
                pen = ball.radius + half - (arc.radius - d)
                if (pen <= 0f) return
                nx = -dx / d; ny = -dy / d
            }
        } else {
            // Container: the ball lives inside and is pushed back towards the centre.
            pen = (d + ball.radius) - insideSurface
            if (pen <= 0f) return
            nx = -dx / d; ny = -dy / d
        }

        val angle = wrap360(Math.toDegrees(kotlin.math.atan2(-dy.toDouble(), dx.toDouble())).toFloat())
        if (!angleInSweep(angle, arc.fromDeg, arc.toDeg)) return

        ball.x += nx * pen
        ball.y += ny * pen
        val vn = ball.vx * nx + ball.vy * ny
        if (vn < 0f) {
            applyBounce(nx, ny, vn, arc.restitution, arc.friction)
            if (abs(vn) > 220f) listener.onWallHit(abs(vn))
        }
    }

    /** Rounded ends for every ball guide, so a gap between two arcs plays fairly. */
    private fun buildArcCaps(): List<Post> = buildList {
        for (a in table.arcs) {
            if (!a.twoSided) continue
            add(Post(Vec2.polar(a.centre, a.radius, a.fromDeg), a.thickness / 2f, a.restitution))
            add(Post(Vec2.polar(a.centre, a.radius, a.toDeg), a.thickness / 2f, a.restitution))
        }
    }

    // --- Sensors ------------------------------------------------------------

    private fun checkSensors() {
        for (r in table.rollovers) {
            val inside = hypot(ball.x - r.centre.x, ball.y - r.centre.y) < r.radius
            if (inside && activeSensors.add(r.id)) listener.onRollover(r)
            if (!inside) activeSensors.remove(r.id)
        }

        val g = table.gobbleHole
        if (hypot(ball.x - g.centre.x, ball.y - g.centre.y) < g.radius * 0.9f) {
            // The gobble hole keeps the ball. Whether that is a disaster or the
            // whole plan is the rules layer's problem, not the simulation's.
            ball.state = BallState.DRAINED
            listener.onGobbleHole(g)
            return
        }

        for (s in table.saucers) {
            val d = hypot(ball.x - s.centre.x, ball.y - s.centre.y)
            if (d < s.radius * 0.85f && ball.speed < 3200f) {
                capturedIn = s
                captureTimer = s.holdSeconds
                ball.state = BallState.CAPTURED
                ball.place(s.centre)
                listener.onSaucerCapture(s)
                return
            }
        }
    }

    private fun releaseFromSaucer() {
        val s = capturedIn ?: return
        ball.x = s.centre.x + s.ejectDir.x * (s.radius + ball.radius + 2f)
        ball.y = s.centre.y + s.ejectDir.y * (s.radius + ball.radius + 2f)
        ball.vx = s.ejectDir.x * s.ejectSpeed
        ball.vy = s.ejectDir.y * s.ejectSpeed
        ball.state = BallState.FREE
        capturedIn = null
        listener.onSaucerEject(s)
    }

    /**
     * Real machines hang balls up on a wire guide or behind a post, and real
     * players shake them loose. Nobody can shake a phone that hard, so the table
     * does it itself.
     *
     * The test is lack of *progress*, not lack of speed: a ball rattling to and
     * fro in a short section of ball guide keeps a respectable 200 units/s while
     * going nowhere at all, and a speed threshold never fires for it.
     */
    private fun checkStuck(dt: Float) {
        stillTime += dt
        if (hypot(ball.x - anchorX, ball.y - anchorY) > STUCK_RADIUS) {
            resetStuckAnchor()
            return
        }
        if (stillTime > STUCK_SECONDS) {
            ball.vx += (rng.nextFloat() - 0.5f) * 900f
            ball.vy += 520f
            resetStuckAnchor()
        }
    }

    private fun resetStuckAnchor() {
        anchorX = ball.x
        anchorY = ball.y
        stillTime = 0f
    }

    companion object {
        /** About 4.3 m/s: harder than any shot a real flipper produces. */
        const val MAX_SPEED = 9000f
        const val FLIPPER_GRAB = 0.22f

        /** Radians of scatter on a pop-bumper kick: about six degrees either way. */
        const val BUMPER_SCATTER = 0.45f

        /** A ball that stays inside this circle for [STUCK_SECONDS] is hung up. */
        const val STUCK_RADIUS = 120f
        const val STUCK_SECONDS = 4f
    }
}

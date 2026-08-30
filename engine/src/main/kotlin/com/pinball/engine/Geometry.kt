package com.pinball.engine

import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin

/**
 * Immutable 2D point / vector, used for describing table geometry.
 *
 * The simulation itself never allocates one of these: the hot loop in [World]
 * works on raw floats. Vec2 is for layout, art and tests, where readability wins.
 *
 * Coordinate system: playfield space, origin top-left, +x right, +y **down**
 * (screen convention). One unit is 1/1080th of the playfield width; see
 * [Table.UNITS_PER_METRE] for the mapping to real-world dimensions.
 */
data class Vec2(val x: Float, val y: Float) {
    operator fun plus(o: Vec2) = Vec2(x + o.x, y + o.y)
    operator fun minus(o: Vec2) = Vec2(x - o.x, y - o.y)
    operator fun times(s: Float) = Vec2(x * s, y * s)
    operator fun unaryMinus() = Vec2(-x, -y)

    fun dot(o: Vec2) = x * o.x + y * o.y
    fun cross(o: Vec2) = x * o.y - y * o.x
    fun length() = hypot(x, y)
    fun lengthSq() = x * x + y * y

    fun normalized(): Vec2 {
        val l = length()
        return if (l < 1e-6f) Vec2(0f, 0f) else Vec2(x / l, y / l)
    }

    /** Rotated 90 degrees counter-clockwise on screen (remember +y is down). */
    fun perp() = Vec2(y, -x)

    fun rotate(radians: Float): Vec2 {
        val c = cos(radians)
        val s = sin(radians)
        return Vec2(x * c - y * s, x * s + y * c)
    }

    fun distanceTo(o: Vec2) = hypot(x - o.x, y - o.y)

    /** Mirrors the point about the vertical line [axisX]. */
    fun mirrorX(axisX: Float) = Vec2(2f * axisX - x, y)

    companion object {
        val ZERO = Vec2(0f, 0f)

        /** Point at [radius] and [degrees] around [centre], measured counter-clockwise from +x. */
        fun polar(centre: Vec2, radius: Float, degrees: Float): Vec2 {
            val r = Math.toRadians(degrees.toDouble())
            return Vec2(
                centre.x + radius * cos(r).toFloat(),
                centre.y - radius * sin(r).toFloat(),
            )
        }
    }
}

/** Squared distance from [p] to the segment [a]..[b], plus the closest point. */
internal fun closestPointOnSegment(p: Vec2, a: Vec2, b: Vec2): Vec2 {
    val abx = b.x - a.x
    val aby = b.y - a.y
    val lenSq = abx * abx + aby * aby
    if (lenSq < 1e-6f) return a
    var t = ((p.x - a.x) * abx + (p.y - a.y) * aby) / lenSq
    if (t < 0f) t = 0f else if (t > 1f) t = 1f
    return Vec2(a.x + abx * t, a.y + aby * t)
}

/** Normalises [degrees] into [0, 360). */
internal fun wrap360(degrees: Float): Float {
    var d = degrees % 360f
    if (d < 0f) d += 360f
    return d
}

/** True when [degrees] lies on the counter-clockwise sweep from [from] to [to]. */
internal fun angleInSweep(degrees: Float, from: Float, to: Float): Boolean {
    val span = wrap360(to - from)
    val rel = wrap360(degrees - from)
    return rel <= span || abs(rel - 360f) < 1e-3f
}

package com.pinball.engine.export

import com.pinball.engine.ArtShape
import com.pinball.engine.SlickChick
import com.pinball.engine.Table
import com.pinball.engine.Vec2
import java.io.File

/**
 * Dumps the table to JSON for `tools/preview.html`.
 *
 * The preview exists so the artwork and the collision geometry can be checked
 * side by side in a browser without an emulator; because it consumes this
 * export rather than its own copy of the numbers, the two can never drift.
 */
private class Json {
    private val sb = StringBuilder()
    private var needComma = false

    fun obj(body: Json.() -> Unit): Json {
        sep(); sb.append('{'); needComma = false; body(); sb.append('}'); needComma = true; return this
    }

    fun arr(body: Json.() -> Unit): Json {
        sep(); sb.append('['); needComma = false; body(); sb.append(']'); needComma = true; return this
    }

    fun key(name: String): Json {
        sep(); sb.append('"').append(name).append("\":"); needComma = false; return this
    }

    fun value(v: String) { sep(); sb.append('"').append(escape(v)).append('"'); needComma = true }
    fun value(v: Float) { sep(); sb.append(fmt(v)); needComma = true }
    fun value(v: Int) { sep(); sb.append(v); needComma = true }
    fun value(v: Boolean) { sep(); sb.append(v); needComma = true }

    fun point(p: Vec2) = arr { value(p.x); value(p.y) }

    fun entry(name: String, v: String) = key(name).also { value(v) }
    fun entry(name: String, v: Float) = key(name).also { value(v) }
    fun entry(name: String, v: Int) = key(name).also { value(v) }
    fun entry(name: String, v: Boolean) = key(name).also { value(v) }
    fun entry(name: String, p: Vec2) = key(name).also { point(p) }

    private fun sep() { if (needComma) sb.append(','); needComma = false }

    private fun fmt(v: Float): String {
        if (v == v.toInt().toFloat()) return v.toInt().toString()
        return String.format(java.util.Locale.ROOT, "%.3f", v)
    }

    private fun escape(s: String) = s.replace("\\", "\\\\").replace("\"", "\\\"")

    override fun toString() = sb.toString()
}

fun main(args: Array<String>) {
    val out = File(args.firstOrNull() ?: "slick_chick.json")
    out.parentFile?.mkdirs()
    out.writeText(encode(SlickChick.build()))
    println("Wrote ${out.absolutePath} (${out.length()} bytes)")
}

private fun encode(t: Table): String = Json().obj {
    entry("name", t.name)
    entry("width", t.width)
    entry("height", t.height)
    entry("ballRadius", t.ballRadius)
    entry("incline", t.inclineDegrees)
    entry("drainY", t.drainY)

    key("walls").arr {
        for (w in t.walls) obj { entry("a", w.a); entry("b", w.b); entry("r", w.radius) }
    }
    key("arcs").arr {
        for (a in t.arcs) obj {
            entry("c", a.centre); entry("r", a.radius)
            entry("from", a.fromDeg); entry("to", a.toDeg)
            entry("t", a.thickness); entry("two", a.twoSided)
        }
    }
    key("posts").arr { for (p in t.posts) obj { entry("c", p.centre); entry("r", p.radius) } }
    key("bumpers").arr {
        for (b in t.bumpers) obj {
            entry("id", b.id); entry("letter", b.letter); entry("c", b.centre)
            entry("r", b.radius); entry("pop", b.isPop)
        }
    }
    key("gobble").obj {
        entry("id", t.gobbleHole.id); entry("c", t.gobbleHole.centre); entry("r", t.gobbleHole.radius)
    }
    key("slings").arr {
        for (s in t.slingshots) obj {
            entry("id", s.id); entry("a", s.a); entry("b", s.b); entry("interior", s.interior)
        }
    }
    key("targets").arr {
        for (x in t.targets) obj { entry("id", x.id); entry("letter", x.letter); entry("a", x.a); entry("b", x.b) }
    }
    key("rollovers").arr {
        for (r in t.rollovers) obj {
            entry("id", r.id); entry("c", r.centre); entry("r", r.radius); entry("kind", r.kind.name)
        }
    }
    key("saucers").arr {
        for (s in t.saucers) obj {
            entry("id", s.id); entry("c", s.centre); entry("r", s.radius); entry("eject", s.ejectDir)
        }
    }
    key("flippers").arr {
        for (f in t.flippers) obj {
            entry("id", f.id); entry("pivot", f.pivot); entry("len", f.length)
            entry("base", f.baseRadius); entry("tip", f.tipRadius)
            entry("rest", f.restDeg); entry("active", f.activeDeg)
        }
    }
    key("gates").arr { for (g in t.gates) obj { entry("a", g.a); entry("b", g.b); entry("dir", g.passDir) } }
    key("plunger").obj {
        entry("laneX", t.plunger.laneX); entry("restY", t.plunger.restY); entry("topY", t.plunger.topY)
    }
    key("lamps").arr {
        for (l in t.lamps) obj {
            entry("id", l.id); entry("c", l.centre); entry("r", l.radius)
            entry("shape", l.shape.name); entry("colour", l.colour)
            entry("label", l.label); entry("w", l.width); entry("h", l.height)
        }
    }
    key("art").arr { for (a in t.art) encodeArt(a) }
}.toString()

private fun Json.encodeArt(a: ArtShape) {
    obj {
        entry("layer", a.layer.name)
        when (a) {
            is ArtShape.Rect -> {
                entry("type", "rect")
                entry("x", a.x); entry("y", a.y); entry("w", a.w); entry("h", a.h)
                entry("radius", a.radius); entry("fill", a.fill); entry("fill2", a.fill2)
                entry("stroke", a.stroke); entry("sw", a.strokeWidth)
            }

            is ArtShape.Circle -> {
                entry("type", "circle")
                entry("cx", a.cx); entry("cy", a.cy); entry("r", a.r)
                entry("fill", a.fill); entry("fill2", a.fill2)
                entry("stroke", a.stroke); entry("sw", a.strokeWidth)
            }

            is ArtShape.Poly -> {
                entry("type", "poly")
                key("points").arr { for (p in a.points) point(p) }
                entry("fill", a.fill); entry("stroke", a.stroke); entry("sw", a.strokeWidth)
                entry("closed", a.closed)
            }

            is ArtShape.Ring -> {
                entry("type", "ring")
                entry("cx", a.cx); entry("cy", a.cy); entry("r", a.r); entry("t", a.thickness)
                entry("from", a.fromDeg); entry("to", a.toDeg); entry("fill", a.fill)
            }

            is ArtShape.Star -> {
                entry("type", "star")
                entry("cx", a.cx); entry("cy", a.cy)
                entry("outer", a.outer); entry("inner", a.inner)
                entry("points", a.points); entry("angle", a.angleDeg)
                entry("fill", a.fill); entry("stroke", a.stroke); entry("sw", a.strokeWidth)
            }

            is ArtShape.Label -> {
                entry("type", "label")
                entry("x", a.x); entry("y", a.y); entry("text", a.text)
                entry("size", a.size); entry("colour", a.colour); entry("angle", a.angleDeg)
                entry("align", a.align.name); entry("weight", a.weight.name)
                entry("tracking", a.letterSpacing); entry("italic", a.italic)
            }
        }
    }
}

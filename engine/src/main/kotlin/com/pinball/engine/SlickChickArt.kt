package com.pinball.engine

import com.pinball.engine.ArtLayer.BASE
import com.pinball.engine.ArtLayer.DECOR
import com.pinball.engine.ArtLayer.INSERT_HOLE
import com.pinball.engine.ArtLayer.LINEWORK
import com.pinball.engine.ArtLayer.TRIM
import com.pinball.engine.SlickChick.Geo

/**
 * The painted playfield.
 *
 * Original vector work in the flat screen-printed idiom of the period: hard
 * colour blocks, starbursts in the quadrants the criss-cross leaves empty, and a
 * gobble hole painted like the hazard it is. Nothing here is traced from the
 * real machine's artwork or from any later game; only the *layout* follows the
 * original, and layout is not artwork.
 *
 * Everything is built from the same constants the physics uses ([Geo]), so the
 * paint cannot drift away from what the ball actually hits.
 */
internal object SlickChickArt {

    fun build(): List<ArtShape> = buildList {
        addAll(ground())
        addAll(dome())
        addAll(crissCross())
        addAll(quadrants())
        addAll(gobbleHole())
        addAll(buttons())
        addAll(lowerField())
        addAll(apron())
    }

    private fun ground() = buildList {
        add(ArtShape.Rect(BASE, 0f, 0f, SlickChick.W, SlickChick.H, fill = Palette.CREAM, fill2 = Palette.CREAM_DEEP))
        add(ArtShape.Rect(BASE, 0f, 0f, Geo.leftWall + 4f, SlickChick.H, fill = Palette.WOOD, fill2 = Palette.WOOD_DARK))
        add(ArtShape.Rect(BASE, Geo.rightWall - 4f, 0f, SlickChick.W - Geo.rightWall + 4f, SlickChick.H, fill = Palette.WOOD, fill2 = Palette.WOOD_DARK))
        add(ArtShape.Rect(BASE, Geo.laneInner, 260f, Geo.rightWall - Geo.laneInner, SlickChick.H - 260f, fill = Palette.SAND))
        add(ArtShape.Rect(BASE, Geo.laneCentre - 4f, 300f, 8f, SlickChick.H - 360f, fill = 0x22000000))
    }

    /** The shallow top dome, with a wedge of colour behind each numbered lane. */
    private fun dome() = buildList {
        val c = Geo.domeCentre
        add(ArtShape.Ring(DECOR, c.x, c.y, Geo.domeInner - 26f, 40f, Geo.guideFrom + 1f, Geo.guideTo - 1f, fill = Palette.TURQUOISE))
        add(ArtShape.Ring(DECOR, c.x, c.y, Geo.domeInner - 62f, 14f, Geo.guideFrom + 2f, Geo.guideTo - 2f, fill = Palette.GOLD))

        for ((label, span) in Geo.numberLanes) {
            val fill = when (label) {
                "1" -> Palette.CORAL
                "2" -> Palette.GOLD
                "3" -> Palette.TURQUOISE_DEEP
                else -> Palette.PINK
            }
            add(ArtShape.Ring(DECOR, c.x, c.y, Geo.domeInner - 26f, 44f, span.first - 2f, span.second + 2f, fill = Palette.CREAM))
            add(ArtShape.Ring(DECOR, c.x, c.y, Geo.domeInner - 28f, 36f, span.first, span.second, fill = fill))
        }

        add(ArtShape.Label(TRIM, 250f, 214f, "SLICK CHICK", 42f, Palette.TEAL_INK, letterSpacing = 5f, italic = true))
        add(ArtShape.Label(TRIM, 250f, 248f, "GOTTLIEB  1963", 18f, Palette.INK_SOFT, letterSpacing = 4f, weight = TextWeight.REGULAR))
    }

    /**
     * The criss-cross: SLICK across, CHICK down, sharing the letter in the
     * middle. A painted cross ties the nine bumpers into one object the way the
     * real machine's playfield does.
     */
    private fun crissCross() = buildList {
        val c = Geo.cross
        val arm = 2f * Geo.crossStep + Geo.bumperR + 34f
        val width = Geo.bumperR * 2f + 68f
        add(ArtShape.Rect(DECOR, c.x - arm, c.y - width / 2f, arm * 2f, width, radius = width / 2f, fill = Palette.TEAL_INK))
        add(ArtShape.Rect(DECOR, c.x - width / 2f, c.y - arm, width, arm * 2f, radius = width / 2f, fill = Palette.TEAL_INK))
        add(ArtShape.Rect(DECOR, c.x - arm + 10f, c.y - width / 2f + 10f, (arm - 10f) * 2f, width - 20f, radius = width / 2f, fill = Palette.TURQUOISE))
        add(ArtShape.Rect(DECOR, c.x - width / 2f + 10f, c.y - arm + 10f, width - 20f, (arm - 10f) * 2f, radius = width / 2f, fill = Palette.TURQUOISE))

        for ((letter, at, pop) in Geo.crissCross) {
            add(ArtShape.Circle(DECOR, at.x, at.y, Geo.bumperR + 22f, fill = Palette.CREAM))
            add(
                ArtShape.Circle(
                    DECOR, at.x, at.y, Geo.bumperR + 14f,
                    fill = if (pop) Palette.CORAL else Palette.GOLD_DEEP,
                )
            )
            add(ArtShape.Circle(DECOR, at.x, at.y, Geo.bumperR + 4f, fill = Palette.CREAM_DEEP))
            // The tip bumpers have no coil, so they are drawn flat rather than
            // as a mushroom cap: the player can see which four are dead.
            if (!pop) add(ArtShape.Circle(LINEWORK, at.x, at.y, Geo.bumperR - 6f, fill = Palette.SAND, stroke = Palette.GOLD_DEEP, strokeWidth = 4f))
            add(ArtShape.Label(TRIM, at.x, at.y + 14f, letter.take(1), 40f, if (pop) Palette.CREAM else Palette.INK))
        }
    }

    /** Starbursts in the four squares the arms of the cross leave empty. */
    private fun quadrants() = buildList {
        val c = Geo.cross
        val d = Geo.crossStep * 1.55f
        for (sx in listOf(-1f, 1f)) for (sy in listOf(-1f, 1f)) {
            val at = Vec2(c.x + sx * d, c.y + sy * d)
            for (i in 0 until 12) {
                add(ArtShape.Poly(DECOR, ray(at, i * 30f + 15f, 7f, 26f, 104f), fill = if (i % 2 == 0) Palette.SAND else Palette.CREAM_DEEP))
            }
            add(ArtShape.Circle(DECOR, at.x, at.y, 30f, fill = Palette.GOLD))
            add(ArtShape.Star(DECOR, at.x, at.y, 26f, 11f, 6, 0f, fill = Palette.CORAL))
        }
    }

    /** The gobble hole, painted as the trap and the prize it is. */
    private fun gobbleHole() = buildList {
        val g = Geo.gobble
        add(ArtShape.Circle(DECOR, g.x, g.y, Geo.gobbleR + 74f, fill = Palette.GOLD))
        for (i in 0 until 16) {
            add(ArtShape.Poly(DECOR, ray(g, i * 22.5f, 8f, Geo.gobbleR + 6f, Geo.gobbleR + 74f), fill = Palette.CORAL))
        }
        add(ArtShape.Circle(DECOR, g.x, g.y, Geo.gobbleR + 44f, fill = Palette.CREAM))
        add(ArtShape.Circle(DECOR, g.x, g.y, Geo.gobbleR + 30f, fill = Palette.CORAL_DEEP))
        add(ArtShape.Circle(DECOR, g.x, g.y, Geo.gobbleR + 12f, fill = Palette.INK))
        add(ArtShape.Circle(DECOR, g.x, g.y, Geo.gobbleR, fill = 0xFF070503.toInt()))
        add(ArtShape.Label(TRIM, g.x, g.y + Geo.gobbleR + 62f, "GOBBLE HOLE", 24f, Palette.INK, letterSpacing = 3f))
        add(ArtShape.Label(TRIM, g.x, g.y + Geo.gobbleR + 88f, "TAKES YOUR BALL", 17f, Palette.INK_SOFT, weight = TextWeight.REGULAR))
    }

    private fun buttons() = buildList {
        for ((_, at) in Geo.buttons) {
            add(ArtShape.Circle(INSERT_HOLE, at.x, at.y, Geo.buttonR + 16f, fill = Palette.CREAM))
            add(ArtShape.Circle(INSERT_HOLE, at.x, at.y, Geo.buttonR + 9f, fill = Palette.TURQUOISE_DEEP))
            add(ArtShape.Circle(INSERT_HOLE, at.x, at.y, Geo.buttonR + 3f, fill = Palette.INK))
        }
    }

    private fun lowerField() = buildList {
        // Outlane and inlane floors, traced from the walls that actually bound them.
        val d = Geo.dividerL
        for (side in listOf(1f, -1f)) {
            fun p(x: Float, y: Float) = if (side > 0) Vec2(x, y) else Vec2(Geo.mirror(x), y)
            add(
                ArtShape.Poly(
                    DECOR,
                    listOf(p(30f, 1244f), p(d[0].x - 8f, 1232f), p(d[1].x - 8f, d[1].y), p(150f, 1520f), p(56f, 1520f), p(30f, 1380f)),
                    fill = Palette.CORAL_DEEP,
                )
            )
            add(
                ArtShape.Poly(
                    DECOR,
                    listOf(p(d[0].x + 10f, 1214f), p(238f, 1214f), p(238f, 1358f), p(300f, 1448f), p(160f, 1440f), p(d[1].x + 10f, d[1].y)),
                    fill = Palette.GOLD,
                )
            )
            add(ArtShape.Label(TRIM, if (side > 0) 200f else Geo.mirror(200f), 1290f, "BONUS", 20f, Palette.INK))
        }

        for (s in listOf(Geo.slingL, Triple(Geo.mirror(Geo.slingL.first), Geo.mirror(Geo.slingL.second), Geo.mirror(Geo.slingL.third)))) {
            add(ArtShape.Poly(DECOR, listOf(s.first, s.second, s.third), fill = Palette.TEAL_INK))
            add(
                ArtShape.Poly(
                    DECOR,
                    listOf(s.first, s.second, s.third).map { Vec2(it.x + (s.third.x - it.x) * 0.18f, it.y + (s.third.y - it.y) * 0.18f) },
                    fill = Palette.TURQUOISE,
                )
            )
        }

        for ((i, ch) in "SHOOT".withIndex()) {
            add(ArtShape.Label(TRIM, Geo.laneCentre, 1150f + i * 38f, ch.toString(), 30f, Palette.INK_SOFT, angleDeg = -90f))
        }
    }

    private fun apron() = buildList {
        add(
            ArtShape.Poly(
                TRIM,
                listOf(
                    Vec2(0f, 1596f), Vec2(300f, 1580f), Vec2(SlickChick.PX, 1592f),
                    Vec2(688f, 1580f), Vec2(SlickChick.W, 1596f),
                    Vec2(SlickChick.W, SlickChick.H), Vec2(0f, SlickChick.H),
                ),
                fill = Palette.STEEL,
            )
        )
        add(ArtShape.Rect(TRIM, 56f, 1614f, 262f, 42f, radius = 6f, fill = Palette.CREAM))
        add(ArtShape.Rect(TRIM, Geo.mirror(318f), 1614f, 262f, 42f, radius = 6f, fill = Palette.CREAM))
        add(ArtShape.Label(TRIM, 187f, 1642f, "5 BALLS  •  TILT", 19f, Palette.INK, weight = TextWeight.REGULAR))
        add(ArtShape.Label(TRIM, Geo.mirror(187f), 1642f, "SPELL IN ORDER", 19f, Palette.INK, weight = TextWeight.REGULAR))
    }

    private fun ray(c: Vec2, angleDeg: Float, halfSpread: Float, rInner: Float, rOuter: Float) = listOf(
        Vec2.polar(c, rInner, angleDeg - halfSpread),
        Vec2.polar(c, rOuter, angleDeg - halfSpread * 0.35f),
        Vec2.polar(c, rOuter, angleDeg + halfSpread * 0.35f),
        Vec2.polar(c, rInner, angleDeg + halfSpread),
    )
}

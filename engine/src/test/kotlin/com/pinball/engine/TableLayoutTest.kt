package com.pinball.engine

import kotlin.math.abs
import kotlin.math.hypot
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Checks the playfield against what is documented about the real machine, and
 * against the clearances that decide whether it can be played at all.
 */
class TableLayoutTest {

    private val table = SlickChick.build()

    @Test
    fun `playfield is a portrait rectangle that fits a phone`() {
        val aspect = table.height / table.width
        assertTrue(aspect in 1.4f..1.7f, "playfield aspect was $aspect")
    }

    @Test
    fun `the criss-cross is nine bumpers spelling SLICK across and CHICK down`() {
        assertEquals(9, table.bumpers.size)

        val cross = SlickChick.Geo.cross
        val across = table.bumpers.filter { it.centre.y == cross.y }.sortedBy { it.centre.x }
        val down = table.bumpers.filter { it.centre.x == cross.x }.sortedBy { it.centre.y }

        assertEquals("SLICK", across.joinToString("") { it.letter })
        assertEquals("CHICK", down.joinToString("") { it.letter })
        // Five plus five is ten, but the two words share their middle letter.
        assertEquals(9, (across + down).distinct().size)
        assertEquals(across[2].id, down[2].id, "the words do not cross on a shared bumper")
    }

    @Test
    fun `five of the nine bumpers are live and four are plain scoring bumpers`() {
        assertEquals(5, table.bumpers.count { it.isPop })
        assertEquals(4, table.bumpers.count { !it.isPop })
        // The live ones are the five towards the middle; the dead ones are the tips.
        val cross = SlickChick.Geo.cross
        for (b in table.bumpers) {
            val armDistance = maxOf(abs(b.centre.x - cross.x), abs(b.centre.y - cross.y))
            assertEquals(
                armDistance <= SlickChick.Geo.crossStep, b.isPop,
                "${b.id} is on the wrong side of the live/dead split",
            )
        }
    }

    @Test
    fun `the ball can weave into the criss-cross but cannot slip straight through it`() {
        val ball = table.ballRadius * 2f
        val step = SlickChick.Geo.crossStep
        val r = SlickChick.Geo.bumperR

        // Orthogonal neighbours are deliberately tighter than a ball: the cluster
        // is a nest the ball rattles around inside, not a grid it passes through.
        assertTrue(step - 2 * r < ball, "adjacent bumpers are far enough apart to be a corridor")
        // The diagonal gaps are the way in, and they have to be a clear ball wide.
        val diagonal = hypot(step, step) - 2 * r
        assertTrue(diagonal > ball, "no diagonal gap wide enough to enter the cluster: $diagonal")
    }

    @Test
    fun `a ball can come down either side of the criss-cross`() {
        val ball = table.ballRadius * 2f
        val r = SlickChick.Geo.bumperR
        val leftmost = table.bumpers.minOf { it.centre.x } - r
        val rightmost = table.bumpers.maxOf { it.centre.x } + r
        assertTrue(
            leftmost - SlickChick.Geo.leftWall > ball,
            "only ${leftmost - SlickChick.Geo.leftWall} units between the cross and the left wall",
        )
        assertTrue(
            SlickChick.Geo.laneInner - rightmost > ball,
            "only ${SlickChick.Geo.laneInner - rightmost} units between the cross and the right wall",
        )
    }

    @Test
    fun `the gobble hole is on the centre line, below the cross and clear of it`() {
        val hole = table.gobbleHole
        assertEquals(SlickChick.PX, hole.centre.x, 0.01f)
        val lowest = table.bumpers.maxOf { it.centre.y } + SlickChick.Geo.bumperR
        assertTrue(hole.centre.y > lowest, "the gobble hole is inside the bumper cluster")
        assertTrue(
            hole.centre.y - hole.radius - lowest > table.ballRadius,
            "no room for the ball to reach the gobble hole",
        )
        // It has to be reachable from the flippers, not tucked behind them.
        assertTrue(hole.centre.y < table.flippers.first().pivot.y, "the gobble hole is below the flippers")
    }

    @Test
    fun `there are five rollover buttons and none sits on the drain line`() {
        val buttons = table.rollovers.filter { it.kind == RolloverKind.STAR }
        assertEquals(5, buttons.size)
        val cross = SlickChick.Geo.cross
        for (b in buttons) {
            val onDrainLine = abs(b.centre.x - SlickChick.PX) < 60f && b.centre.y > cross.y
            assertTrue(!onDrainLine, "${b.id} sits where every draining ball rolls over it")
        }
    }

    @Test
    fun `the four numbered rollovers are in the dome, in order across it`() {
        val lanes = table.rollovers.filter { it.kind == RolloverKind.ARCH_LANE }
        assertEquals(4, lanes.size)
        assertEquals(setOf("1", "2", "3", "4"), lanes.map { it.label }.toSet())
        // Lane 1 is the one the plunger reaches first, so they run right to left.
        val ordered = lanes.sortedBy { it.label }
        for (i in 0 until ordered.size - 1) {
            assertTrue(
                ordered[i].centre.x > ordered[i + 1].centre.x,
                "lane ${ordered[i].label} is not to the right of lane ${ordered[i + 1].label}",
            )
        }
    }

    @Test
    fun `flippers are symmetric and the ball fits through the gap between their tips`() {
        val world = World(table)
        val (l, r) = world.flippers
        assertEquals(SlickChick.PX * 2f - l.spec.pivot.x, r.spec.pivot.x, 0.01f)
        // The clear passage, not the distance between tip centres: subtract both
        // tip radii or the ball ends up wedged on top of the tips instead.
        val passage = (r.tip().x - l.tip().x) - l.spec.tipRadius - r.spec.tipRadius
        val ballWidth = table.ballRadius * 2f
        assertTrue(
            passage > ballWidth * 1.05f && passage < ballWidth * 1.6f,
            "drain passage was $passage units for a $ballWidth unit ball",
        )
    }

    @Test
    fun `every element sits inside the playfield`() {
        fun inside(p: Vec2, margin: Float = 0f) =
            p.x >= margin && p.x <= table.width - margin && p.y >= margin && p.y <= table.height - margin

        for (b in table.bumpers) assertTrue(inside(b.centre, b.radius), "bumper ${b.id} pokes out")
        for (r in table.rollovers) assertTrue(inside(r.centre), "rollover ${r.id} pokes out")
        for (l in table.lamps) assertTrue(inside(l.centre), "lamp ${l.id} pokes out")
        assertTrue(inside(table.gobbleHole.centre, table.gobbleHole.radius))
    }

    @Test
    fun `every lamp the rules switch on exists on the playfield`() {
        val ids = table.lamps.map { it.id }.toSet()
        for (letter in SlickChick.LETTER_ORDER) assertTrue("letter.${letter.lowercase()}" in ids, "missing letter.$letter")
        for (b in Game.BUTTONS) assertTrue(b in ids, "missing $b")
        for (n in 1..Game.NUMBER_LANES) assertTrue("lane.$n" in ids, "missing lane.$n")
    }

    @Test
    fun `the spelling order walks SLICK then CHICK and hits the shared bumper twice`() {
        val order = SlickChick.LETTER_ORDER
        assertEquals(10, order.size, "SLICK CHICK is ten letters over nine bumpers")
        val ids = order.map { "bumper.${it.lowercase()}" }
        for (id in ids) assertTrue(table.bumpers.any { it.id == id }, "spelling order names $id, which is not on the table")
        assertEquals(9, ids.distinct().size, "the shared bumper should be used twice and it is not")
    }

    @Test
    fun `gravity is the along-playfield component of a tilted cabinet`() {
        // 9.81 m/s^2 at 6.5 degrees is 1.11 m/s^2, which is 2331 units/s^2.
        assertEquals(2331f, World(table).gravity, 25f)
    }

    @Test
    fun `slingshot normals point into the playfield`() {
        for (s in table.slingshots) {
            val face = (s.b - s.a).normalized()
            var n = face.perp()
            if (n.dot(s.interior - s.a) > 0f) n = -n
            assertTrue(n.y < 0f, "${s.id} would kick the ball downwards")
            val towardsCentre = if (s.a.x < SlickChick.PX) n.x > 0f else n.x < 0f
            assertTrue(towardsCentre, "${s.id} would kick the ball into the wall")
        }
    }

    @Test
    fun `the whole lower playfield mirrors about the centre`() {
        fun mirrored(p: Vec2) = Vec2(SlickChick.PX * 2f - p.x, p.y)
        for (kind in listOf(RolloverKind.OUTLANE, RolloverKind.INLANE)) {
            val pair = table.rollovers.filter { it.kind == kind }
            assertEquals(2, pair.size)
            assertTrue(abs(mirrored(pair[0].centre).x - pair[1].centre.x) < 0.01f, "$kind is not symmetric")
        }
    }
}

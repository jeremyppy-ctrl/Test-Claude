package com.pinball.engine

/**
 * The table's colour scheme: an original palette in the idiom of early-1960s
 * amusement art - screen-printed flat colour, warm cream ground, coral and
 * turquoise accents, gold linework.
 *
 * Values are packed 0xAARRGGBB.
 */
object Palette {
    const val CREAM = 0xFFF3E7CD.toInt()
    const val CREAM_DEEP = 0xFFE8D6B0.toInt()
    const val SAND = 0xFFDCC49A.toInt()

    const val CORAL = 0xFFE2503C.toInt()
    const val CORAL_DEEP = 0xFFB43724.toInt()
    const val PINK = 0xFFE98BA0.toInt()

    const val TURQUOISE = 0xFF2FA79F.toInt()
    const val TURQUOISE_DEEP = 0xFF16706C.toInt()
    const val TEAL_INK = 0xFF123B3A.toInt()

    const val GOLD = 0xFFE8B33A.toInt()
    const val GOLD_DEEP = 0xFFB9821C.toInt()

    const val INK = 0xFF2A2118.toInt()
    const val INK_SOFT = 0xFF5A4A36.toInt()

    const val WOOD = 0xFF6B4227.toInt()
    const val WOOD_DARK = 0xFF41281A.toInt()

    const val CHROME = 0xFFCBCBD2.toInt()
    const val CHROME_DARK = 0xFF6E6E78.toInt()
    const val STEEL = 0xFF9AA0A8.toInt()

    const val LAMP_OFF = 0xFF6F6552.toInt()
    const val LAMP_WHITE = 0xFFFFF3D0.toInt()
    const val LAMP_RED = 0xFFFF6A50.toInt()
    const val LAMP_GREEN = 0xFF64E0A8.toInt()
    const val LAMP_AMBER = 0xFFFFC24A.toInt()
    const val LAMP_BLUE = 0xFF74C8FF.toInt()

    const val BACKBOX = 0xFF1A1410.toInt()
    const val SHADOW = 0x33000000
}

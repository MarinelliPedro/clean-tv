package com.cleantv.launcher.logic

/** Desfoque em caixa (separável), em Kotlin puro: barato para miniaturas e testável fora do Android. */
object Blur {
    fun box(pixels: IntArray, width: Int, height: Int, radius: Int, passes: Int = 2): IntArray {
        require(pixels.size == width * height) { "pixels não batem com ${width}x$height" }
        if (radius <= 0) return pixels.copyOf()
        var current = pixels.copyOf()
        repeat(passes) {
            current = pass(current, width, height, radius, horizontal = true)
            current = pass(current, width, height, radius, horizontal = false)
        }
        return current
    }

    private fun pass(src: IntArray, width: Int, height: Int, radius: Int, horizontal: Boolean): IntArray {
        val out = IntArray(src.size)
        val lines = if (horizontal) height else width
        val length = if (horizontal) width else height
        for (line in 0 until lines) {
            for (i in 0 until length) {
                var a = 0; var r = 0; var g = 0; var b = 0; var n = 0
                for (k in -radius..radius) {
                    val j = (i + k).coerceIn(0, length - 1)
                    val p = if (horizontal) src[line * width + j] else src[j * width + line]
                    a += (p ushr 24) and 0xFF
                    r += (p shr 16) and 0xFF
                    g += (p shr 8) and 0xFF
                    b += p and 0xFF
                    n++
                }
                val index = if (horizontal) line * width + i else i * width + line
                out[index] = ((a / n) shl 24) or ((r / n) shl 16) or ((g / n) shl 8) or (b / n)
            }
        }
        return out
    }
}

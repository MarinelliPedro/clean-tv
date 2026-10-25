package com.cleantv.launcher.logic

import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Cor do brilho de fundo a partir da arte do app (banner).
 *
 * Dá mais peso aos pixels saturados e claros (o logo), ignora fundo branco/preto
 * e devolve uma cor viva o bastante para aparecer sobre o fundo escuro.
 */
object ArtColor {
    const val FALLBACK = 0xFF4A5A80.toInt()

    fun pick(pixels: IntArray): Int {
        var r = 0.0; var g = 0.0; var b = 0.0; var weight = 0.0
        var ar = 0.0; var ag = 0.0; var ab = 0.0; var count = 0
        for (p in pixels) {
            if ((p ushr 24) and 0xFF < 128) continue
            val pr = (p shr 16) and 0xFF
            val pg = (p shr 8) and 0xFF
            val pb = p and 0xFF
            ar += pr; ag += pg; ab += pb; count++
            val hi = max(pr, max(pg, pb))
            val lo = min(pr, min(pg, pb))
            val value = hi / 255.0
            val saturation = if (hi == 0) 0.0 else (hi - lo).toDouble() / hi
            if (saturation < 0.25 || value < 0.2) continue
            val w = saturation * value * value
            r += pr * w; g += pg * w; b += pb * w; weight += w
        }
        val base = when {
            weight > 0.0 -> rgb(r / weight, g / weight, b / weight)
            count > 0 -> rgb(ar / count, ag / count, ab / count)
            else -> return FALLBACK
        }
        return toGlow(base)
    }

    /** Mantém o matiz; garante saturação e brilho mínimos. Cores neutras continuam neutras. */
    fun toGlow(color: Int): Int {
        val hsv = rgbToHsv(color)
        val saturation = if (hsv[1] < 0.15f) hsv[1] else max(hsv[1], 0.55f)
        val value = max(hsv[2], 0.75f)
        return hsvToRgb(hsv[0], saturation, value)
    }

    fun rgbToHsv(color: Int): FloatArray {
        val r = ((color shr 16) and 0xFF) / 255f
        val g = ((color shr 8) and 0xFF) / 255f
        val b = (color and 0xFF) / 255f
        val hi = max(r, max(g, b))
        val lo = min(r, min(g, b))
        val delta = hi - lo
        val hue = when {
            delta == 0f -> 0f
            hi == r -> 60f * (((g - b) / delta) % 6f)
            hi == g -> 60f * (((b - r) / delta) + 2f)
            else -> 60f * (((r - g) / delta) + 4f)
        }.let { if (it < 0f) it + 360f else it }
        return floatArrayOf(hue, if (hi == 0f) 0f else delta / hi, hi)
    }

    fun hsvToRgb(hue: Float, saturation: Float, value: Float): Int {
        val c = value * saturation
        val x = c * (1 - kotlin.math.abs((hue / 60f) % 2f - 1))
        val m = value - c
        val (r, g, b) = when ((hue / 60f).toInt() % 6) {
            0 -> Triple(c, x, 0f)
            1 -> Triple(x, c, 0f)
            2 -> Triple(0f, c, x)
            3 -> Triple(0f, x, c)
            4 -> Triple(x, 0f, c)
            else -> Triple(c, 0f, x)
        }
        return rgb(((r + m) * 255).toDouble(), ((g + m) * 255).toDouble(), ((b + m) * 255).toDouble())
    }

    private fun rgb(r: Double, g: Double, b: Double): Int {
        fun ch(v: Double) = v.roundToInt().coerceIn(0, 255)
        return (0xFF shl 24) or (ch(r) shl 16) or (ch(g) shl 8) or ch(b)
    }
}

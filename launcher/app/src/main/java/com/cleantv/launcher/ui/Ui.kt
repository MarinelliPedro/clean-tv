package com.cleantv.launcher.ui

import android.animation.TimeInterpolator
import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.util.TypedValue
import android.view.animation.PathInterpolator
import android.widget.TextView
import com.cleantv.launcher.R
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/** Medidas pensadas numa tela de 1920x1080, convertidas para a tela real (720p, 1080p, 4K). */
class Scale(widthPx: Int, heightPx: Int) {
    val factor: Float = min(widthPx / 1920f, heightPx / 1080f)

    fun px(design: Int): Int = (design * factor).roundToInt()
    fun f(design: Int): Float = design * factor

    companion object {
        fun of(context: Context): Scale {
            val m = context.resources.displayMetrics
            return Scale(max(m.widthPixels, m.heightPixels), min(m.widthPixels, m.heightPixels))
        }
    }
}

data class LauncherTheme(val id: String, val labelRes: Int, val top: Int, val bottom: Int, val accent: Int)

object Themes {
    val ALL = listOf(
        LauncherTheme("noite", R.string.theme_noite, 0xFF04050A.toInt(), 0xFF0D1018.toInt(), 0xFF8AB4FF.toInt()),
        LauncherTheme("grafite", R.string.theme_grafite, 0xFF15171C.toInt(), 0xFF2A2D35.toInt(), 0xFFD8DCE4.toInt()),
        LauncherTheme("oceano", R.string.theme_oceano, 0xFF021325.toInt(), 0xFF0B2E52.toInt(), 0xFF6FD3FF.toInt()),
        LauncherTheme("aurora", R.string.theme_aurora, 0xFF0B0615.toInt(), 0xFF2A1240.toInt(), 0xFFC79BFF.toInt()),
    )

    fun byId(id: String?): LauncherTheme = ALL.firstOrNull { it.id == id } ?: ALL[0]
}

/** Pesos da Inter (licença OFL, em assets/licenses) usados no launcher. */
enum class Weight(val res: Int, val fallback: String) {
    REGULAR(R.font.inter_regular, "sans-serif"),
    MEDIUM(R.font.inter_medium, "sans-serif-medium"),
    SEMIBOLD(R.font.inter_semibold, "sans-serif-medium"),
}

object Fonts {
    private val cache = HashMap<Weight, Typeface>()

    fun get(context: Context, weight: Weight): Typeface = cache.getOrPut(weight) {
        runCatching { context.resources.getFont(weight.res) }.getOrNull() ?: Typeface.create(weight.fallback, Typeface.NORMAL)
    }
}

/** Movimento: desacelera suave e para sem passar do ponto, como as molas sem quique da Apple. */
object Motion {
    val EASE: TimeInterpolator = PathInterpolator(0.2f, 0f, 0f, 1f)
    const val FOCUS_MS = 240L

    /** Falso quando o usuário desligou as animações do Android (acessibilidade ou opções do desenvolvedor). */
    fun enabled(): Boolean = ValueAnimator.areAnimatorsEnabled()
}

fun white(alpha: Float): Int = Color.argb((alpha * 255).roundToInt(), 255, 255, 255)

fun withAlpha(color: Int, alpha: Float): Int = (color and 0x00FFFFFF) or ((alpha * 255).roundToInt() shl 24)

/** Espaçamento entre letras por tamanho: mais junto nos títulos grandes, levemente aberto no texto pequeno. */
fun tracking(size: Int): Float = when {
    size >= 64 -> -0.025f
    size >= 40 -> -0.015f
    size >= 30 -> -0.005f
    else -> 0.005f
}

fun TextView.textStyle(s: Scale, size: Int, color: Int, weight: Weight = Weight.REGULAR) {
    setTextSize(TypedValue.COMPLEX_UNIT_PX, s.f(size))
    setTextColor(color)
    typeface = Fonts.get(context, weight)
    letterSpacing = tracking(size)
    includeFontPadding = false
}

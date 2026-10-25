package com.cleantv.launcher.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorMatrix
import android.graphics.ColorMatrixColorFilter
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.PorterDuff
import android.graphics.PorterDuffXfermode
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.drawable.GradientDrawable
import android.os.SystemClock
import android.view.View
import android.widget.FrameLayout
import android.widget.ImageView
import kotlin.math.PI
import kotlin.math.cos

/**
 * Fundo da tela inicial. São só duas camadas de tela cheia, para caber na GPU de TVs fracas:
 *  1. degradê do tema, já com o escurecimento de baixo (legibilidade do dock e dos textos);
 *  2. uma imagem pequena pré-calculada por app, ampliada na tela: a arte do app em foco bem
 *     desfocada, escurecida e dissolvida nas bordas ("fundo cinematográfico"), mais o brilho na cor
 *     da arte. Trocar de app troca a imagem com uma transição suave (que também muda a cor do brilho).
 * Com o fundo em movimento ligado, a imagem se aproxima e se afasta bem devagar (26 s em cada
 * sentido). O movimento muda só escala e posição da camada, 20 vezes por segundo (é lento demais
 * para precisar de mais), e para enquanto outro app ocupa a tela ou com as animações do Android
 * desligadas.
 */
class AmbientView(context: Context) : FrameLayout(context) {
    private val base = View(context)
    private val artA = ImageView(context)
    private val artB = ImageView(context)
    private var front = artA

    private var top = Color.BLACK
    private var bottom = Color.BLACK
    private var thumbnail: Bitmap? = null
    private var glowColor = Color.TRANSPARENT
    private var artEnabled = true
    private var glowEnabled = true
    private var motionEnabled = true
    private var windowVisible = false

    private var drifting = false
    private var driftElapsed = 0L // tempo de movimento acumulado (pausa sem pular)
    private var driftResumedAt = 0L
    private val driftTick = object : Runnable {
        override fun run() {
            if (!drifting) return
            applyDrift(driftPhase(driftElapsed + SystemClock.uptimeMillis() - driftResumedAt))
            postDelayed(this, DRIFT_FRAME_MS)
        }
    }

    private data class Key(val thumbnail: Bitmap?, val color: Int, val art: Boolean, val glow: Boolean)

    // Últimas imagens já preparadas (o foco costuma ir e voltar entre os mesmos apps).
    private val composites = object : LinkedHashMap<Key, Bitmap>(16, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<Key, Bitmap>?) = size > 12
    }

    init {
        addView(base, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
        for (art in arrayOf(artA, artB)) {
            art.scaleType = ImageView.ScaleType.FIT_XY
            art.alpha = 0f
            addView(art, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
        }
    }

    fun setColors(top: Int, bottom: Int) {
        if (top == this.top && bottom == this.bottom && base.background != null) return
        this.top = top
        this.bottom = bottom
        val middle = blend(top, bottom, 0.5f)
        base.background = GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, intArrayOf(top, middle, blend(bottom, Color.BLACK, 0.55f)))
    }

    fun setGlowEnabled(enabled: Boolean) {
        if (enabled == glowEnabled) return
        glowEnabled = enabled
        refresh()
    }

    fun setArtEnabled(enabled: Boolean) {
        if (enabled == artEnabled) return
        artEnabled = enabled
        refresh()
        updateDrift()
    }

    fun setMotionEnabled(enabled: Boolean) {
        motionEnabled = enabled
        updateDrift()
    }

    /** Mostra a arte (null = sem arte, por exemplo nos atalhos) e o brilho na cor indicada. */
    fun show(thumbnail: Bitmap?, color: Int?, animate: Boolean) {
        val newColor = color ?: glowColor
        if (thumbnail === this.thumbnail && newColor == glowColor && front.drawable != null) return
        this.thumbnail = thumbnail
        glowColor = newColor
        swapTo(currentComposite(), animate)
    }

    override fun onWindowVisibilityChanged(visibility: Int) {
        super.onWindowVisibilityChanged(visibility)
        windowVisible = visibility == View.VISIBLE
        updateDrift()
    }

    override fun onDetachedFromWindow() {
        stopDrift(keepPosition = true)
        super.onDetachedFromWindow()
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        // A aproximação parte da região onde a arte aparece (direita, no alto).
        for (art in arrayOf(artA, artB)) {
            art.pivotX = w * 0.72f
            art.pivotY = h * 0.30f
        }
    }

    private fun refresh() {
        if (front.drawable != null) swapTo(currentComposite(), animate = false)
    }

    private fun currentComposite(): Bitmap? {
        val art = artEnabled && thumbnail != null
        val glow = glowEnabled && Color.alpha(glowColor) > 0
        if (!art && !glow) return null
        val key = Key(if (art) thumbnail else null, if (glow) glowColor else 0, art, glow)
        return composites.getOrPut(key) { composite(key) }
    }

    private fun swapTo(bitmap: Bitmap?, animate: Boolean) {
        val old = front
        val next = if (front === artA) artB else artA
        front = next
        next.animate().cancel()
        next.alpha = 0f
        next.setImageBitmap(bitmap)
        if (animate && Motion.enabled()) {
            next.animate().alpha(1f).setDuration(600).setInterpolator(Motion.EASE).start()
            old.animate().alpha(0f).setDuration(600).setInterpolator(Motion.EASE).start()
        } else {
            old.animate().cancel()
            next.alpha = 1f
            old.alpha = 0f
        }
    }

    private fun updateDrift() {
        val wanted = artEnabled && motionEnabled && windowVisible && Motion.enabled()
        when {
            wanted && !drifting -> {
                drifting = true
                driftResumedAt = SystemClock.uptimeMillis()
                removeCallbacks(driftTick)
                post(driftTick)
            }
            !wanted && drifting -> stopDrift(keepPosition = motionEnabled)
            !wanted && !motionEnabled -> {
                driftElapsed = 0L
                applyDrift(0f)
            }
        }
    }

    private fun stopDrift(keepPosition: Boolean) {
        if (drifting) driftElapsed += SystemClock.uptimeMillis() - driftResumedAt
        drifting = false
        removeCallbacks(driftTick)
        if (!keepPosition) {
            driftElapsed = 0L
            applyDrift(0f)
        }
    }

    /** 0 → 1 → 0 a cada 52 s, com início e fim suaves. */
    private fun driftPhase(elapsedMs: Long): Float {
        val cycle = (elapsedMs % (2 * DRIFT_LEG_MS)).toFloat() / DRIFT_LEG_MS
        val t = if (cycle <= 1f) cycle else 2f - cycle
        return ((1 - cos(PI * t)) / 2).toFloat()
    }

    private fun applyDrift(t: Float) {
        val scale = 1.04f + 0.10f * t
        val dx = -width * 0.03f * t
        val dy = height * 0.015f * t
        for (art in arrayOf(artA, artB)) {
            art.scaleX = scale
            art.scaleY = scale
            art.translationX = dx
            art.translationY = dy
        }
    }

    /**
     * Imagem do fundo nas proporções da tela: a miniatura desfocada à direita, escurecida e com as
     * bordas dissolvidas (máscaras DST_IN), o brilho por cima e, por fim, tudo mais fraco embaixo.
     */
    private fun composite(key: Key): Bitmap {
        val out = Bitmap.createBitmap(COMPOSITE_W, COMPOSITE_H, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(out)
        val w = COMPOSITE_W.toFloat()
        val h = COMPOSITE_H.toFloat()
        if (key.art && key.thumbnail != null) {
            val layer = canvas.saveLayer(ART_RECT, null)
            canvas.drawBitmap(key.thumbnail, null, ART_RECT, artPaint)
            canvas.drawRect(ART_RECT, maskHorizontal)
            canvas.drawRect(ART_RECT, maskVertical)
            canvas.restoreToCount(layer)
        }
        if (key.glow) {
            val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.DITHER_FLAG)
            paint.shader = RadialGradient(
                w * 0.80f, h * 0.12f, w * 0.62f,
                intArrayOf(withAlpha(key.color, 0.40f), withAlpha(key.color, 0.12f), Color.TRANSPARENT),
                floatArrayOf(0f, 0.5f, 1f), Shader.TileMode.CLAMP,
            )
            canvas.drawRect(0f, 0f, w, h, paint)
            paint.shader = RadialGradient(
                w * 0.06f, h * 1.02f, w * 0.42f,
                intArrayOf(withAlpha(key.color, 0.20f), Color.TRANSPARENT),
                null, Shader.TileMode.CLAMP,
            )
            canvas.drawRect(0f, 0f, w, h, paint)
        }
        canvas.drawRect(0f, 0f, w, h, fadeBottom)
        return out
    }

    private companion object {
        const val COMPOSITE_W = 320
        const val COMPOSITE_H = 180
        const val DRIFT_FRAME_MS = 50L
        const val DRIFT_LEG_MS = 26_000L
        val ART_RECT = RectF(COMPOSITE_W * 0.20f, 0f, COMPOSITE_W.toFloat(), COMPOSITE_H * 0.86f)

        /** Escurece e satura a arte: fundo, não protagonista (banners brancos não estouram). */
        val artPaint = Paint(Paint.FILTER_BITMAP_FLAG).apply {
            alpha = (0.62f * 255).toInt()
            colorFilter = ColorMatrixColorFilter(ColorMatrix().apply {
                setSaturation(1.35f)
                postConcat(ColorMatrix(floatArrayOf(
                    0.58f, 0f, 0f, 0f, 0f,
                    0f, 0.58f, 0f, 0f, 0f,
                    0f, 0f, 0.58f, 0f, 0f,
                    0f, 0f, 0f, 1f, 0f,
                )))
            })
        }
        val maskHorizontal = Paint().apply {
            xfermode = PorterDuffXfermode(PorterDuff.Mode.DST_IN)
            shader = LinearGradient(
                ART_RECT.left, 0f, ART_RECT.right, 0f,
                intArrayOf(Color.TRANSPARENT, Color.BLACK, Color.BLACK),
                floatArrayOf(0f, 0.45f, 1f), Shader.TileMode.CLAMP,
            )
        }
        val maskVertical = Paint().apply {
            xfermode = PorterDuffXfermode(PorterDuff.Mode.DST_IN)
            shader = LinearGradient(
                0f, ART_RECT.top, 0f, ART_RECT.bottom,
                intArrayOf(withAlpha(Color.BLACK, 0.35f), Color.BLACK, Color.BLACK, Color.TRANSPARENT),
                floatArrayOf(0f, 0.25f, 0.5f, 1f), Shader.TileMode.CLAMP,
            )
        }

        /** Arte e brilho perdem força na metade de baixo (o dock e os textos ficam legíveis). */
        val fadeBottom = Paint().apply {
            xfermode = PorterDuffXfermode(PorterDuff.Mode.DST_IN)
            shader = LinearGradient(
                0f, COMPOSITE_H * 0.5f, 0f, COMPOSITE_H.toFloat(),
                Color.BLACK, withAlpha(Color.BLACK, 0.45f), Shader.TileMode.CLAMP,
            )
        }

        fun blend(from: Int, to: Int, amount: Float): Int {
            fun ch(shift: Int) = (((from shr shift) and 0xFF) * (1 - amount) + ((to shr shift) and 0xFF) * amount).toInt()
            return Color.rgb(ch(16), ch(8), ch(0))
        }
    }
}

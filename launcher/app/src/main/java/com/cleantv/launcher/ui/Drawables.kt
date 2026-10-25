package com.cleantv.launcher.ui

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorFilter
import android.graphics.LinearGradient
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.PorterDuff
import android.graphics.PorterDuffColorFilter
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.drawable.Drawable
import com.cleantv.launcher.logic.Blur
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin

/** Painel de "vidro": preenchimento translúcido em degradê, borda clara e reflexo no topo. */
class GlassDrawable(private val radius: Float, private val stroke: Float, private val strength: Float = 1f) : Drawable() {
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val border = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = stroke }
    private val rect = RectF()

    override fun onBoundsChange(bounds: Rect) {
        rect.set(bounds)
        rect.inset(stroke / 2, stroke / 2)
        val top = bounds.top.toFloat()
        val bottom = bounds.bottom.toFloat()
        fill.shader = LinearGradient(0f, top, 0f, bottom, white(0.15f * strength), white(0.05f * strength), Shader.TileMode.CLAMP)
        border.shader = LinearGradient(0f, top, 0f, bottom, white(0.38f * strength), white(0.06f * strength), Shader.TileMode.CLAMP)
    }

    override fun draw(canvas: Canvas) {
        canvas.drawRoundRect(rect, radius, radius, fill)
        canvas.drawRoundRect(rect, radius, radius, border)
    }

    override fun setAlpha(alpha: Int) {
        fill.alpha = alpha
        border.alpha = alpha
    }

    override fun setColorFilter(colorFilter: ColorFilter?) {
        fill.colorFilter = colorFilter
        border.colorFilter = colorFilter
    }

    @Deprecated("Deprecated in Java")
    override fun getOpacity(): Int = PixelFormat.TRANSLUCENT
}

/**
 * Luz difusa em volta do tile em foco, na cor da arte do app. A máscara (um retângulo arredondado
 * desfocado) é calculada uma vez e só recebe a cor; esticada no tamanho do tile, fica lisa.
 */
class HaloDrawable : Drawable() {
    private val paint = Paint(Paint.FILTER_BITMAP_FLAG)

    fun setColor(color: Int) {
        paint.colorFilter = PorterDuffColorFilter(color, PorterDuff.Mode.SRC_IN)
        invalidateSelf()
    }

    override fun draw(canvas: Canvas) {
        canvas.drawBitmap(mask, null, bounds, paint)
    }

    override fun setAlpha(alpha: Int) {
        paint.alpha = alpha
    }

    override fun setColorFilter(colorFilter: ColorFilter?) {
        paint.colorFilter = colorFilter
    }

    @Deprecated("Deprecated in Java")
    override fun getOpacity(): Int = PixelFormat.TRANSLUCENT

    companion object {
        /** Espaço da luz em volta do tile, em pixels de projeto (tela 1920x1080). */
        const val SPREAD = 56

        /**
         * Tile 16:9 de 320x180 com [SPREAD] de luz para cada lado, em escala 1:4. O núcleo passa um
         * pouco da borda do tile, para a luz sair forte do banner e sumir aos poucos.
         */
        private val mask: Bitmap by lazy {
            val w = 108
            val h = 73
            val bitmap = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
            Canvas(bitmap).drawRoundRect(RectF(10f, 10f, w - 10f, h - 10f), 6f, 6f, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE })
            val pixels = IntArray(w * h)
            bitmap.getPixels(pixels, 0, w, 0, 0, w, h)
            bitmap.setPixels(Blur.box(pixels, w, h, radius = 5), 0, w, 0, 0, w, h)
            bitmap
        }
    }
}

/** Reflexo de luz que atravessa o tile uma vez quando ele ganha foco (progress de 0 a 1). */
class GlareDrawable : Drawable() {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val matrix = Matrix()
    private var band = 0f

    var progress: Float = 1f
        set(value) {
            field = value
            invalidateSelf()
        }

    override fun onBoundsChange(bounds: Rect) {
        band = bounds.width() * 0.5f
        // Faixa diagonal: o degradê corre na direção (1, 0.6), então as listras ficam inclinadas.
        paint.shader = LinearGradient(
            0f, 0f, band, band * 0.6f,
            intArrayOf(Color.TRANSPARENT, white(0.30f), Color.TRANSPARENT),
            floatArrayOf(0f, 0.5f, 1f), Shader.TileMode.CLAMP,
        )
    }

    override fun draw(canvas: Canvas) {
        if (progress <= 0f || progress >= 1f) return
        val travel = bounds.width() + 2 * band
        matrix.setTranslate(bounds.left - band * 1.5f + travel * progress, bounds.top - band * 0.3f)
        paint.shader.setLocalMatrix(matrix)
        canvas.drawRect(bounds, paint)
    }

    override fun setAlpha(alpha: Int) {
        paint.alpha = alpha
    }

    override fun setColorFilter(colorFilter: ColorFilter?) {
        paint.colorFilter = colorFilter
    }

    @Deprecated("Deprecated in Java")
    override fun getOpacity(): Int = PixelFormat.TRANSLUCENT
}

/** Ícones de linha desenhados em código (identidade própria, sem arquivos de terceiros). */
class LineIcon(private val kind: Kind, color: Int) : Drawable() {
    enum class Kind { INPUT, HDMI, LIVE_TV, NETWORK, SETTINGS, CUSTOMIZE, ADD, CHEVRON_DOWN }

    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        strokeWidth = 1.8f
        this.color = color
    }
    private val solid = Paint(Paint.ANTI_ALIAS_FLAG).apply { this.color = color }

    fun setColor(color: Int) {
        line.color = color
        solid.color = color
        invalidateSelf()
    }

    override fun draw(canvas: Canvas) {
        val b = bounds
        val unit = min(b.width(), b.height()) / 24f
        canvas.save()
        canvas.translate(b.exactCenterX() - 12 * unit, b.exactCenterY() - 12 * unit)
        canvas.scale(unit, unit)
        when (kind) {
            Kind.INPUT -> {
                canvas.drawRoundRect(RectF(6f, 5f, 21f, 17f), 2f, 2f, line)
                canvas.drawLine(2f, 11f, 12f, 11f, line)
                canvas.drawLine(9f, 8f, 12f, 11f, line)
                canvas.drawLine(9f, 14f, 12f, 11f, line)
                canvas.drawLine(10f, 20f, 17f, 20f, line)
            }
            Kind.HDMI -> {
                val path = android.graphics.Path().apply {
                    moveTo(4f, 8f); lineTo(20f, 8f); lineTo(20f, 12f); lineTo(17f, 16f)
                    lineTo(7f, 16f); lineTo(4f, 12f); close()
                }
                canvas.drawPath(path, line)
                canvas.drawLine(8f, 12f, 16f, 12f, line)
            }
            Kind.LIVE_TV -> {
                canvas.drawRoundRect(RectF(3f, 8f, 21f, 20f), 2.5f, 2.5f, line)
                canvas.drawLine(8f, 3f, 12f, 8f, line)
                canvas.drawLine(16f, 3f, 12f, 8f, line)
            }
            Kind.NETWORK -> {
                for (r in floatArrayOf(4f, 8.5f, 13f)) {
                    canvas.drawArc(RectF(12f - r, 19f - r, 12f + r, 19f + r), 225f, 90f, false, line)
                }
                canvas.drawCircle(12f, 19f, 1.6f, solid)
            }
            Kind.SETTINGS -> {
                canvas.drawCircle(12f, 12f, 3f, line)
                canvas.drawCircle(12f, 12f, 7f, line)
                for (i in 0 until 8) {
                    val a = Math.toRadians(i * 45.0)
                    canvas.drawLine(
                        12f + 7f * cos(a).toFloat(), 12f + 7f * sin(a).toFloat(),
                        12f + 9.8f * cos(a).toFloat(), 12f + 9.8f * sin(a).toFloat(), line,
                    )
                }
            }
            Kind.CUSTOMIZE -> {
                for ((y, knob) in listOf(7f to 15f, 12f to 8f, 17f to 13f)) {
                    canvas.drawLine(4f, y, 20f, y, line)
                    canvas.drawCircle(knob, y, 2.2f, solid)
                }
            }
            Kind.ADD -> {
                canvas.drawLine(12f, 5f, 12f, 19f, line)
                canvas.drawLine(5f, 12f, 19f, 12f, line)
            }
            Kind.CHEVRON_DOWN -> {
                canvas.drawLine(6f, 9f, 12f, 15f, line)
                canvas.drawLine(12f, 15f, 18f, 9f, line)
            }
        }
        canvas.restore()
    }

    override fun setAlpha(alpha: Int) {
        line.alpha = alpha
        solid.alpha = alpha
    }

    override fun setColorFilter(colorFilter: ColorFilter?) {
        line.colorFilter = colorFilter
        solid.colorFilter = colorFilter
    }

    @Deprecated("Deprecated in Java")
    override fun getOpacity(): Int = PixelFormat.TRANSLUCENT
}

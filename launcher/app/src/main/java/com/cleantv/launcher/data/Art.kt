package com.cleantv.launcher.data

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.Shader
import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.Drawable
import android.text.TextPaint
import android.text.TextUtils
import com.cleantv.launcher.logic.ArtColor
import com.cleantv.launcher.logic.Blur
import com.cleantv.launcher.logic.ArtColor.hsvToRgb
import com.cleantv.launcher.logic.ArtColor.rgbToHsv
import com.cleantv.launcher.ui.Fonts
import com.cleantv.launcher.ui.Weight

object Art {
    private const val W = 320
    private const val H = 180

    /**
     * Versão bem desfocada do banner para o fundo: reduz a 24x14 (some o texto), amplia para 96x54
     * e aplica desfoque em caixa. Ampliada na tela, vira uma mancha de luz lisa, sem blocos.
     */
    fun thumbnail(drawable: Drawable): Bitmap {
        val tiny = Bitmap.createBitmap(24, 14, Bitmap.Config.ARGB_8888)
        val old = Rect(drawable.bounds)
        drawable.setBounds(0, 0, tiny.width, tiny.height)
        drawable.draw(Canvas(tiny))
        drawable.bounds = old
        val big = Bitmap.createBitmap(96, 54, Bitmap.Config.ARGB_8888)
        Canvas(big).drawBitmap(tiny, null, Rect(0, 0, big.width, big.height), Paint(Paint.FILTER_BITMAP_FLAG))
        tiny.recycle()
        val pixels = IntArray(big.width * big.height)
        big.getPixels(pixels, 0, big.width, 0, 0, big.width, big.height)
        big.setPixels(Blur.box(pixels, big.width, big.height, radius = 4), 0, big.width, 0, 0, big.width, big.height)
        return big
    }

    /** Cor do brilho a partir de uma miniatura do desenho. */
    fun colorOf(drawable: Drawable): Int {
        val w = 48
        val h = 27
        val bitmap = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val old = Rect(drawable.bounds)
        drawable.setBounds(0, 0, w, h)
        drawable.draw(Canvas(bitmap))
        drawable.bounds = old
        val pixels = IntArray(w * h)
        bitmap.getPixels(pixels, 0, w, 0, 0, w, h)
        bitmap.recycle()
        return ArtColor.pick(pixels)
    }

    /** Banner para apps que só têm ícone: fundo na cor do ícone, ícone à esquerda e o nome. */
    fun generatedBanner(context: Context, icon: Drawable?, label: String, color: Int? = null): Drawable {
        val base = color ?: icon?.let { colorOf(it) } ?: ArtColor.FALLBACK
        val hsv = rgbToHsv(base)
        val light = hsvToRgb(hsv[0], hsv[1] * 0.8f, 0.42f)
        val dark = hsvToRgb(hsv[0], hsv[1] * 0.9f, 0.16f)
        val bitmap = Bitmap.createBitmap(W, H, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        canvas.drawRect(0f, 0f, W.toFloat(), H.toFloat(), Paint().apply {
            shader = LinearGradient(0f, 0f, W.toFloat(), H.toFloat(), light, dark, Shader.TileMode.CLAMP)
        })
        var textLeft = 28f
        if (icon != null) {
            val size = 88
            val top = (H - size) / 2
            val old = Rect(icon.bounds)
            icon.setBounds(28, top, 28 + size, top + size)
            icon.draw(canvas)
            icon.bounds = old
            textLeft = 28f + size + 22f
        }
        val text = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
            this.color = 0xFFFFFFFF.toInt()
            textSize = if (icon != null) 30f else 38f
            typeface = Fonts.get(context, Weight.SEMIBOLD)
        }
        val shown = TextUtils.ellipsize(label, text, W - textLeft - 20f, TextUtils.TruncateAt.END).toString()
        canvas.drawText(shown, textLeft, H / 2f - (text.ascent() + text.descent()) / 2f, text)
        return BitmapDrawable(context.resources, bitmap)
    }
}

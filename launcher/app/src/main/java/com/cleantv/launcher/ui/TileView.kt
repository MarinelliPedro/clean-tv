package com.cleantv.launcher.ui

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Outline
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.view.View
import android.view.ViewOutlineProvider
import android.widget.FrameLayout
import android.widget.ImageView

/**
 * Tile de app (banner 16:9) com foco no estilo da Apple TV, sem borda: ao receber foco ele cresce,
 * a luz da fileira ([FocusGlow]) vem para trás dele na cor da arte e um reflexo atravessa o banner
 * uma vez; ao apertar OK, afunda um pouco (resposta imediata ao toque, antes de o app abrir).
 */
class TileView(context: Context, private val s: Scale, private val focusScale: Float) : FrameLayout(context) {
    private val card = FrameLayout(context)
    private val image = ImageView(context)
    private val shine = View(context)
    private val glare = GlareDrawable()
    private val radius = s.f(20)
    private var sweep: ValueAnimator? = null
    private var hasFocusLook = false

    /** Avisado quando o foco entra ou sai (o listener padrão do View fica com o próprio tile). */
    var onFocus: ((Boolean) -> Unit)? = null

    /** Luz da fileira e a cor dela quando este tile está em foco. */
    var glow: FocusGlow? = null
    var glowColor: Int = white(0.6f)

    init {
        isFocusable = true
        isFocusableInTouchMode = true
        isClickable = true
        isLongClickable = true
        // Sem contorno: o tile sobe na ordem de desenho (translationZ) sem ganhar sombra preta.
        outlineProvider = null

        card.outlineProvider = object : ViewOutlineProvider() {
            override fun getOutline(view: View, outline: Outline) {
                outline.setRoundRect(0, 0, view.width, view.height, radius)
            }
        }
        card.clipToOutline = true
        image.scaleType = ImageView.ScaleType.CENTER_CROP
        card.addView(image, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
        shine.background = GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, intArrayOf(white(0.22f), white(0f), white(0f)))
        shine.alpha = 0f
        card.addView(shine, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
        card.foreground = glare
        addView(card, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))

        setOnFocusChangeListener { _, hasFocus ->
            setFocusedLook(hasFocus, animate = true)
            if (hasFocus) glow?.show(this, animate = true) else glow?.hide()
            onFocus?.invoke(hasFocus)
        }
    }

    fun setArt(drawable: Drawable?) {
        image.setImageDrawable(drawable)
    }

    fun setFocusedLook(focused: Boolean, animate: Boolean) {
        hasFocusLook = focused
        val target = if (focused) focusScale else 1f
        translationZ = if (focused) 1f else 0f
        if (animate) {
            animate().scaleX(target).scaleY(target).setDuration(Motion.FOCUS_MS).setInterpolator(Motion.EASE).start()
            shine.animate().alpha(if (focused) 1f else 0f).setDuration(Motion.FOCUS_MS).start()
            if (focused && Motion.enabled()) sweepGlare() else stopGlare()
        } else {
            animate().cancel()
            shine.animate().cancel()
            scaleX = target
            scaleY = target
            shine.alpha = if (focused) 1f else 0f
            stopGlare()
            if (focused) glow?.show(this, animate = false)
        }
    }

    override fun setPressed(pressed: Boolean) {
        super.setPressed(pressed)
        if (!hasFocusLook) return
        val target = if (pressed) focusScale - 0.05f else focusScale
        animate().scaleX(target).scaleY(target).setDuration(if (pressed) 90L else Motion.FOCUS_MS).setInterpolator(Motion.EASE).start()
    }

    private fun sweepGlare() {
        sweep?.cancel()
        sweep = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 750
            startDelay = 80
            interpolator = Motion.EASE
            addUpdateListener { glare.progress = it.animatedValue as Float }
            start()
        }
    }

    private fun stopGlare() {
        sweep?.cancel()
        sweep = null
        glare.progress = 1f
    }
}

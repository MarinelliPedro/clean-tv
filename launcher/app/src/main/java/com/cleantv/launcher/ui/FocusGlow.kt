package com.cleantv.launcher.ui

import android.animation.ArgbEvaluator
import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Color
import android.graphics.PointF
import android.graphics.Rect
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import kotlin.math.roundToInt

/**
 * Luz na cor da arte atrás do tile em foco. Há uma só por fileira, desenhada atrás de todos os
 * tiles: ela nunca cobre os vizinhos e desliza de um tile para o outro junto com o foco.
 * Vai como primeiro filho do container da fileira (ver [attachTo]).
 */
class FocusGlow(
    context: Context,
    private val s: Scale,
    tileWidth: Int,
    tileHeight: Int,
    scale: Float,
) : View(context) {
    private val glowWidth = (tileWidth * scale).roundToInt() + 2 * s.px(HaloDrawable.SPREAD)
    private val glowHeight = (tileHeight * scale).roundToInt() + 2 * s.px(HaloDrawable.SPREAD)
    private val drawable = HaloDrawable()
    private var container: ViewGroup? = null
    private var target: TileView? = null
    private var shown = false
    private var sliding = false
    private var color = Color.TRANSPARENT
    private var colorAnimator: ValueAnimator? = null

    // A saída de foco vem antes da entrada no vizinho: só apaga se nenhum tile da fileira pegou o foco.
    private val fadeOut = Runnable {
        shown = false
        target = null
        animate().alpha(0f).setDuration(Motion.FOCUS_MS).setInterpolator(Motion.EASE).start()
    }

    init {
        background = drawable
        alpha = 0f
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
    }

    /**
     * Coloca a luz como primeiro filho (atrás de tudo). As margens compensam o padding e anulam o
     * tamanho da luz, para ela não aumentar a fileira.
     */
    fun attachTo(container: FrameLayout) {
        this.container = container
        container.addView(this, 0, FrameLayout.LayoutParams(glowWidth, glowHeight).apply {
            leftMargin = -container.paddingLeft
            topMargin = -container.paddingTop
            rightMargin = -glowWidth
            bottomMargin = -glowHeight
        })
        // Reposiciona quando a fileira é montada ou muda de lugar (o foco pode chegar antes do layout).
        container.addOnLayoutChangeListener { _, _, _, _, _, _, _, _, _ -> if (!sliding) snap() }
    }

    fun show(tile: TileView, animate: Boolean) {
        removeCallbacks(fadeOut)
        val wasShown = shown
        target = tile
        shown = true
        val position = positionOf(tile)
        val slide = animate && wasShown && position != null && Motion.enabled()
        setColor(tile.glowColor, slide)
        animate().cancel()
        sliding = false
        if (slide && position != null) {
            sliding = true
            animate().translationX(position.x).translationY(position.y).alpha(ALPHA)
                .setDuration(Motion.FOCUS_MS).setInterpolator(Motion.EASE)
                .withEndAction { sliding = false }
                .start()
            return
        }
        if (position != null) {
            translationX = position.x
            translationY = position.y
        }
        if (animate && Motion.enabled()) {
            animate().alpha(ALPHA).setDuration(Motion.FOCUS_MS).setInterpolator(Motion.EASE).start()
        } else {
            alpha = ALPHA
        }
    }

    fun hide() {
        removeCallbacks(fadeOut)
        post(fadeOut)
    }

    private fun snap() {
        val tile = target ?: return
        val position = positionOf(tile) ?: return
        translationX = position.x
        translationY = position.y
    }

    /** Canto da luz para ela ficar centrada no tile (e um pouco abaixo, como se viesse do banner). */
    private fun positionOf(tile: TileView): PointF? {
        val row = container ?: return null
        if (tile.width == 0 || !isInside(tile, row)) return null
        val rect = Rect(0, 0, tile.width, tile.height)
        row.offsetDescendantRectToMyCoords(tile, rect)
        return PointF(rect.exactCenterX() - glowWidth / 2f, rect.exactCenterY() - glowHeight / 2f + s.f(14))
    }

    private fun isInside(view: View, row: ViewGroup): Boolean {
        var current = view.parent
        while (current != null) {
            if (current === row) return true
            current = current.parent
        }
        return false
    }

    private fun setColor(target: Int, animate: Boolean) {
        colorAnimator?.cancel()
        if (!animate || color == target) {
            color = target
            drawable.setColor(target)
            return
        }
        colorAnimator = ValueAnimator.ofObject(ArgbEvaluator(), color, target).apply {
            duration = Motion.FOCUS_MS
            addUpdateListener {
                color = it.animatedValue as Int
                drawable.setColor(color)
            }
            start()
        }
    }

    private companion object {
        const val ALPHA = 0.85f
    }
}

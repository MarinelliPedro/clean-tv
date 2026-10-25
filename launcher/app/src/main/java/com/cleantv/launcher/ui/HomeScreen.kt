package com.cleantv.launcher.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Rect
import android.graphics.drawable.LayerDrawable
import android.text.TextUtils
import android.view.Gravity
import android.view.View
import android.widget.FrameLayout
import android.widget.GridLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextClock
import android.widget.TextView
import com.cleantv.launcher.R
import com.cleantv.launcher.data.AppEntry
import com.cleantv.launcher.data.Art
import com.cleantv.launcher.logic.DockConfig
import kotlin.math.max

data class HomeState(
    val apps: List<AppEntry>,
    val dock: List<AppEntry>,
    val theme: LauncherTheme,
    val blackWallpaper: Boolean,
    val glow: Boolean,
    val columns: Int,
    val clock24: Boolean,
    val greeting: String?,
    val loading: Boolean = false,
    val cinematic: Boolean = true,
    val motion: Boolean = true,
    /** Apps abertos recentemente que não estão no dock (fileira "Recentes" acima da grade). */
    val recent: List<AppEntry> = emptyList(),
)

enum class Shortcut(val icon: LineIcon.Kind, val label: Int, val hint: Int) {
    INPUTS(LineIcon.Kind.INPUT, R.string.shortcut_inputs, R.string.shortcut_inputs_hint),
    HDMI(LineIcon.Kind.HDMI, R.string.shortcut_hdmi, R.string.shortcut_hdmi_hint),
    LIVE_TV(LineIcon.Kind.LIVE_TV, R.string.shortcut_live_tv, R.string.shortcut_live_tv_hint),
    NETWORK(LineIcon.Kind.NETWORK, R.string.shortcut_network, R.string.shortcut_network_hint),
    SETTINGS(LineIcon.Kind.SETTINGS, R.string.shortcut_settings, R.string.shortcut_settings_hint),
    CUSTOMIZE(LineIcon.Kind.CUSTOMIZE, R.string.shortcut_customize, R.string.shortcut_customize_hint),
}

/**
 * Tela inicial. Duas "páginas" numa rolagem vertical:
 *  1. saudação e data à esquerda; atalhos numa cápsula de vidro e relógio à direita; nome do app
 *     em foco; dock de vidro com 4 apps;
 *  2. "Recentes" e a grade com todos os apps (aparecem ao apertar para baixo a partir do dock).
 * A ordem da grade não muda sozinha: os apps usados aparecem só na fileira "Recentes".
 * Toda medida é proporcional a uma tela 1920x1080 (ver [Scale]).
 */
class HomeScreen(context: Context) : FrameLayout(context) {
    interface Listener {
        fun onLaunch(app: AppEntry)
        fun onOptions(app: AppEntry, inDock: Boolean)
        fun onAddToDock()
        fun onShortcut(shortcut: Shortcut)
    }

    private enum class Section { DOCK, RECENT, ALL }

    private data class TileTag(val pkg: String?, val section: Section)

    var listener: Listener? = null

    private val s = Scale.of(context)
    private val ambient = AmbientView(context)
    private val scroll = PagedScroll(context)
    private val column = LinearLayout(context)
    private val homePage = LinearLayout(context)
    private val gridPage = LinearLayout(context)
    private val greetingView = TextView(context)
    private val dateView = TextClock(context)
    private val clockView = TextClock(context)
    private val heroTitle = TextView(context)
    private val heroHint = TextView(context)
    private val dockRow = LinearLayout(context)
    private val dockGlow = FocusGlow(context, s, s.px(DOCK_TILE_W), s.px(DOCK_TILE_H), DOCK_FOCUS_SCALE)
    private var state: HomeState? = null
    private var pendingGridScroll = false

    init {
        clipChildren = false
        addView(ambient, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))

        scroll.isVerticalScrollBarEnabled = false
        scroll.overScrollMode = View.OVER_SCROLL_NEVER
        scroll.isSmoothScrollingEnabled = true
        column.apply {
            orientation = LinearLayout.VERTICAL
            clipChildren = false
            clipToPadding = false
        }
        column.addView(buildHomePage(), LinearLayout.LayoutParams(LayoutParams.MATCH_PARENT, context.resources.displayMetrics.heightPixels))
        column.addView(buildGridPage(), LinearLayout.LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
        scroll.addView(column, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
        addView(scroll, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
    }

    private fun buildHomePage(): View = homePage.apply {
        orientation = LinearLayout.VERTICAL
        clipChildren = false
        clipToPadding = false
        setPadding(s.px(96), s.px(56), s.px(96), s.px(44))

        val top = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            clipChildren = false
        }
        val left = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
        greetingView.textStyle(s, 32, white(0.92f), Weight.MEDIUM)
        dateView.textStyle(s, 23, white(0.52f))
        dateView.format12Hour = "EEEE, d 'de' MMMM"
        dateView.format24Hour = "EEEE, d 'de' MMMM"
        left.addView(greetingView)
        left.addView(dateView, LinearLayout.LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT).apply { topMargin = s.px(8) })
        top.addView(left, LinearLayout.LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))

        val pill = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            clipChildren = false
            clipToPadding = false
            background = GlassDrawable(s.f(36), s.f(2).coerceAtLeast(1f), 0.8f)
            setPadding(s.px(8), s.px(8), s.px(8), s.px(8))
        }
        Shortcut.values().forEachIndexed { index, shortcut ->
            val button = ShortcutButton(context, s, shortcut.icon, context.getString(shortcut.label))
            button.setOnClickListener { listener?.onShortcut(shortcut) }
            button.onFocus = { focused ->
                if (focused) {
                    scroll.smoothScrollTo(0, 0)
                    showHero(context.getString(shortcut.label), context.getString(shortcut.hint), state?.theme?.accent)
                }
            }
            pill.addView(button, LinearLayout.LayoutParams(s.px(56), s.px(56)).apply { if (index > 0) marginStart = s.px(6) })
        }
        top.addView(pill)
        clockView.textStyle(s, 44, white(0.95f), Weight.MEDIUM)
        clockView.fontFeatureSettings = "tnum" // números de mesma largura: o relógio não "pula"
        top.addView(clockView, LinearLayout.LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT).apply { marginStart = s.px(40) })
        addView(top, LinearLayout.LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))

        heroTitle.textStyle(s, 88, white(1f), Weight.SEMIBOLD)
        heroTitle.isSingleLine = true
        heroTitle.ellipsize = TextUtils.TruncateAt.END
        heroHint.textStyle(s, 26, white(0.6f))
        addView(heroTitle, LinearLayout.LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply { topMargin = s.px(120) })
        addView(heroHint, LinearLayout.LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply { topMargin = s.px(14) })

        addView(View(context), LinearLayout.LayoutParams(1, 0, 1f))

        val panel = FrameLayout(context).apply {
            background = GlassDrawable(s.f(48), s.f(2).coerceAtLeast(1f))
            clipChildren = false
            clipToPadding = false
            // Folga para o tile em foco crescer (10%) sem encostar na borda do vidro.
            setPadding(s.px(40), s.px(34), s.px(40), s.px(34))
        }
        dockRow.orientation = LinearLayout.HORIZONTAL
        dockRow.clipChildren = false
        dockRow.clipToPadding = false
        panel.addView(dockRow, LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT))
        dockGlow.attachTo(panel)
        addView(panel, LinearLayout.LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT).apply { gravity = Gravity.CENTER_HORIZONTAL })

        addView(TextView(context).apply {
            textStyle(s, 22, white(0.45f), Weight.MEDIUM)
            text = context.getString(R.string.all_apps)
            val chevron = LineIcon(LineIcon.Kind.CHEVRON_DOWN, white(0.45f)).apply { setBounds(0, 0, s.px(26), s.px(26)) }
            setCompoundDrawables(chevron, null, null, null)
            compoundDrawablePadding = s.px(8)
        }, LinearLayout.LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT).apply {
            topMargin = s.px(30)
            gravity = Gravity.CENTER_HORIZONTAL
        })
    }

    private fun buildGridPage(): View = gridPage.apply {
        orientation = LinearLayout.VERTICAL
        clipChildren = false
        clipToPadding = false
        // Pelo menos uma tela de altura: com poucos apps a rolagem ainda encaixa a grade no topo.
        minimumHeight = context.resources.displayMetrics.heightPixels
        setPadding(s.px(96), s.px(24), s.px(96), s.px(120))
    }

    fun bind(newState: HomeState) {
        val focusedTag = findFocus()?.tag as? TileTag
        state = newState
        val theme = newState.theme
        if (newState.blackWallpaper) ambient.setColors(0xFF000000.toInt(), 0xFF000000.toInt()) else ambient.setColors(theme.top, theme.bottom)
        ambient.setGlowEnabled(newState.glow)
        ambient.setArtEnabled(newState.cinematic)
        ambient.setMotionEnabled(newState.motion)
        val clockFormat = if (newState.clock24) "HH:mm" else "h:mm"
        clockView.format24Hour = clockFormat
        clockView.format12Hour = clockFormat
        setGreeting(newState.greeting)
        buildDock(newState)
        buildSections(newState)

        val restored = focusedTag?.let { tag -> findTile(tag) }
        if (restored != null) restored.requestFocus() else focusDock()
        val first = newState.dock.firstOrNull() ?: newState.apps.firstOrNull()
        if (restored == null) {
            when {
                newState.loading -> showHero(context.getString(R.string.hero_empty), "", theme.accent)
                first != null -> showApp(first)
                else -> showHero(context.getString(R.string.app_name), context.getString(R.string.no_apps), theme.accent)
            }
        }
    }

    fun setGreeting(text: String?) {
        greetingView.visibility = if (text == null) View.GONE else View.VISIBLE
        greetingView.text = text ?: ""
    }

    fun focusDock() {
        val target = dockRow.getChildAt(0) ?: findViewWithTag<View>(state?.apps?.firstOrNull()?.let { TileTag(it.packageName, Section.ALL) })
        target?.requestFocus()
    }

    /** Topo e dock na hora, sem animação (ao voltar para o launcher). */
    fun resetToTop() {
        scroll.scrollTo(0, 0)
        focusDock()
        post { scroll.scrollTo(0, 0) } // o ScrollView pode rolar de novo ao ajustar o foco
    }

    /** Volta ao topo e ao dock. Retorna true se estava rolado para a grade. */
    fun scrollToTop(): Boolean {
        val wasScrolled = scroll.scrollY > 0
        scroll.smoothScrollTo(0, 0)
        focusDock()
        return wasScrolled
    }

    /** Usado nos prints: mostra a grade, sem animação. */
    fun previewGrid() {
        pendingGridScroll = true
        requestLayout()
    }

    /** Usado nos prints: destaca um tile do dock, sem animação. */
    fun previewFocusDock(index: Int) {
        for (i in 0 until dockRow.childCount) {
            val other = dockRow.getChildAt(i) as? TileView ?: continue
            other.setFocusedLook(i == index, animate = false)
        }
        val app = state?.dock?.getOrNull(index) ?: return
        showApp(app, animate = false)
    }

    override fun onLayout(changed: Boolean, left: Int, top: Int, right: Int, bottom: Int) {
        super.onLayout(changed, left, top, right, bottom)
        if (pendingGridScroll) {
            pendingGridScroll = false
            scroll.scrollTo(0, gridPage.top)
        }
    }

    private fun showHero(title: String, hint: String, color: Int?, animate: Boolean = true, art: Bitmap? = null) {
        setHeroText(title, hint, animate)
        ambient.show(art, color, animate)
    }

    private fun showApp(app: AppEntry, animate: Boolean = true) {
        showHero(app.label, "", app.artColor, animate, app.backdrop ?: Art.thumbnail(app.banner))
    }

    /** O título troca na hora e entra com um leve fade e subida (o foco nunca espera a animação). */
    private fun setHeroText(title: String, hint: String, animate: Boolean) {
        val same = heroTitle.text.toString() == title && heroHint.text.toString() == hint
        if (same && animate) return
        heroTitle.text = title
        heroHint.text = hint
        heroHint.visibility = if (hint.isEmpty()) View.INVISIBLE else View.VISIBLE
        for (view in arrayOf(heroTitle, heroHint)) {
            view.animate().cancel()
            if (animate && Motion.enabled()) {
                view.alpha = 0.35f
                view.translationY = s.f(10)
                view.animate().alpha(1f).translationY(0f).setDuration(280).setInterpolator(Motion.EASE).start()
            } else {
                view.alpha = 1f
                view.translationY = 0f
            }
        }
    }

    private fun findTile(tag: TileTag): View? = findViewWithTag(tag)

    /**
     * Rolagem por página: ao entrar na grade ela encaixa no topo; depois, a fileira em foco fica
     * a 30% da altura da tela, sem cortar o título nem a fileira.
     */
    private fun scrollToTile(tile: View) {
        val rect = Rect(0, 0, tile.width, tile.height)
        column.offsetDescendantRectToMyCoords(tile, rect)
        scroll.smoothScrollTo(0, max(gridPage.top, rect.top - (height * 0.30f).toInt()))
    }

    private fun bindTile(tile: TileView, app: AppEntry, section: Section, glow: FocusGlow) {
        tile.setArt(app.banner)
        tile.glow = glow
        tile.glowColor = app.artColor
        tile.contentDescription = app.label
        tile.tag = TileTag(app.packageName, section)
        tile.setOnClickListener { listener?.onLaunch(app) }
        tile.setOnLongClickListener { listener?.onOptions(app, section == Section.DOCK); true }
    }

    private fun buildDock(state: HomeState) {
        dockRow.removeAllViews()
        val w = s.px(DOCK_TILE_W)
        val h = s.px(DOCK_TILE_H)
        val gap = s.px(32)
        state.dock.forEachIndexed { index, app ->
            val tile = TileView(context, s, DOCK_FOCUS_SCALE)
            bindTile(tile, app, Section.DOCK, dockGlow)
            tile.onFocus = { focused ->
                if (focused) {
                    scroll.smoothScrollTo(0, 0)
                    showApp(app)
                }
            }
            dockRow.addView(tile, LinearLayout.LayoutParams(w, h).apply { if (index > 0) marginStart = gap })
        }
        if (state.dock.size < DockConfig.SIZE && !state.loading) {
            val add = TileView(context, s, DOCK_FOCUS_SCALE)
            val icon = LineIcon(LineIcon.Kind.ADD, white(0.75f))
            val inset = s.px(62)
            add.setArt(LayerDrawable(arrayOf(GlassDrawable(s.f(20), s.f(2).coerceAtLeast(1f), 0.8f), icon)).apply {
                setLayerInset(1, inset * 2, inset, inset * 2, inset)
            })
            add.glow = dockGlow
            add.glowColor = state.theme.accent
            add.contentDescription = context.getString(R.string.dock_add_slot)
            add.tag = TileTag(null, Section.DOCK)
            add.setOnClickListener { listener?.onAddToDock() }
            add.onFocus = { focused ->
                if (focused) {
                    scroll.smoothScrollTo(0, 0)
                    showHero(context.getString(R.string.dock_add_slot), "", state.theme.accent)
                }
            }
            dockRow.addView(add, LinearLayout.LayoutParams(w, h).apply { if (state.dock.isNotEmpty()) marginStart = gap })
        }
    }

    private fun buildSections(state: HomeState) {
        gridPage.removeAllViews()
        val columns = state.columns.coerceIn(4, 6)
        if (state.recent.isNotEmpty()) {
            addSection(context.getString(R.string.recent_apps), state.recent.take(columns), Section.RECENT, columns)
        }
        addSection(context.getString(R.string.all_apps), state.apps, Section.ALL, columns)
        if (state.apps.isEmpty()) {
            gridPage.addView(TextView(context).apply {
                textStyle(s, 26, white(0.5f))
                text = context.getString(if (state.loading) R.string.hero_empty else R.string.no_apps)
            })
        }
    }

    private fun addSection(title: String, apps: List<AppEntry>, section: Section, columns: Int) {
        gridPage.addView(TextView(context).apply {
            textStyle(s, 36, white(0.9f), Weight.SEMIBOLD)
            text = title
        }, LinearLayout.LayoutParams(LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT).apply {
            if (gridPage.childCount > 0) topMargin = s.px(16)
        })
        if (apps.isEmpty()) return
        val grid = GridLayout(context).apply {
            columnCount = columns
            clipChildren = false
            clipToPadding = false
        }
        val holder = FrameLayout(context).apply {
            clipChildren = false
            clipToPadding = false
            addView(grid, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT))
        }
        val gap = s.px(32)
        val usable = s.px(1920 - 2 * 96)
        val w = (usable - gap * (columns - 1)) / columns
        val h = w * 9 / 16
        val glow = FocusGlow(context, s, w, h, GRID_FOCUS_SCALE).also { it.attachTo(holder) }
        apps.forEachIndexed { index, app ->
            val cell = LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                clipChildren = false
                clipToPadding = false
            }
            val tile = TileView(context, s, GRID_FOCUS_SCALE)
            bindTile(tile, app, section, glow)
            val label = TextView(context).apply {
                textStyle(s, 22, white(0.6f))
                text = app.label
                isSingleLine = true
                ellipsize = TextUtils.TruncateAt.END
            }
            tile.onFocus = { focused ->
                label.setTextColor(if (focused) white(1f) else white(0.6f))
                label.typeface = Fonts.get(context, if (focused) Weight.MEDIUM else Weight.REGULAR)
                if (focused) {
                    scrollToTile(tile)
                    showApp(app)
                }
            }
            cell.addView(tile, LinearLayout.LayoutParams(w, h))
            cell.addView(label, LinearLayout.LayoutParams(w, LayoutParams.WRAP_CONTENT).apply { topMargin = s.px(16) })
            grid.addView(cell, GridLayout.LayoutParams().apply {
                width = w
                if (index % columns != columns - 1) rightMargin = gap
                bottomMargin = s.px(40)
            })
        }
        gridPage.addView(holder, LinearLayout.LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT).apply { topMargin = s.px(32) })
    }
}

private const val DOCK_TILE_W = 320
private const val DOCK_TILE_H = 180
private const val DOCK_FOCUS_SCALE = 1.10f
private const val GRID_FOCUS_SCALE = 1.08f

/** Rolagem controlada pela tela inicial: o ScrollView não "persegue" o foco sozinho (evita pulos). */
private class PagedScroll(context: Context) : ScrollView(context) {
    override fun computeScrollDeltaToGetChildRectOnScreen(rect: Rect): Int = 0
}

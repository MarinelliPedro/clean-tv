package com.cleantv.launcher

import android.app.Activity
import android.app.AlertDialog
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.SharedPreferences
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.KeyEvent
import android.widget.Toast
import com.cleantv.launcher.data.AppEntry
import com.cleantv.launcher.data.AppRepository
import com.cleantv.launcher.data.LauncherPrefs
import com.cleantv.launcher.logic.AppOrdering
import com.cleantv.launcher.logic.DockConfig
import com.cleantv.launcher.logic.Greeting
import com.cleantv.launcher.logic.Recents
import com.cleantv.launcher.ui.HomeScreen
import com.cleantv.launcher.ui.HomeState
import com.cleantv.launcher.ui.Shortcut
import com.cleantv.launcher.ui.Themes
import java.util.Calendar
import java.util.concurrent.Executors

class HomeActivity : Activity(), HomeScreen.Listener {
    private lateinit var home: HomeScreen
    private lateinit var prefs: LauncherPrefs
    private lateinit var repository: AppRepository
    private val executor = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private var apps: List<AppEntry> = emptyList()
    private var loaded = false

    // Instalar, remover, ativar ou desativar um app atualiza a tela na hora
    // (o launcher original guardava atalhos de apps já desativados).
    private val packageReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) = reload()
    }
    private val timeReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) = home.setGreeting(currentGreeting())
    }
    // Abrir um app grava "Recentes"; a grade só é refeita na volta, sem pesar na abertura do app.
    private var recentsChanged = false
    private val prefsListener = SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
        if (key == LauncherPrefs.RECENT) recentsChanged = true else render()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = LauncherPrefs(this)
        repository = AppRepository(this)
        home = HomeScreen(this).also { it.listener = this }
        setContentView(home)
        window.setBackgroundDrawable(null) // o fundo da tela inicial cobre tudo: menos uma camada por quadro
        registerReceiver(packageReceiver, IntentFilter().apply {
            addAction(Intent.ACTION_PACKAGE_ADDED)
            addAction(Intent.ACTION_PACKAGE_REMOVED)
            addAction(Intent.ACTION_PACKAGE_CHANGED)
            addAction(Intent.ACTION_PACKAGE_REPLACED)
            addDataScheme("package")
        })
        registerReceiver(timeReceiver, IntentFilter(Intent.ACTION_TIME_TICK))
        prefs.prefs.registerOnSharedPreferenceChangeListener(prefsListener)
        render()
        reload()
    }

    override fun onResume() {
        super.onResume()
        if (recentsChanged) {
            recentsChanged = false
            render()
        }
        home.setGreeting(currentGreeting())
        home.resetToTop()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        home.scrollToTop()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        home.scrollToTop() // um launcher nunca fecha com o voltar
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        if (keyCode == KeyEvent.KEYCODE_MENU) {
            val focused = currentFocus
            val app = apps.firstOrNull { it.label == focused?.contentDescription }
            if (app != null) {
                onOptions(app, inDock = app.packageName in currentDock())
                return true
            }
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onDestroy() {
        unregisterReceiver(packageReceiver)
        unregisterReceiver(timeReceiver)
        prefs.prefs.unregisterOnSharedPreferenceChangeListener(prefsListener)
        executor.shutdownNow()
        super.onDestroy()
    }

    private fun reload() {
        executor.execute {
            val list = runCatching { repository.load() }.getOrDefault(emptyList())
            main.post {
                apps = list
                loaded = true
                render()
            }
        }
    }

    private fun currentDock(): List<String> = DockConfig.resolve(prefs.dock, apps.map { it.packageName })

    private fun orderedApps(): List<AppEntry> {
        val hidden = prefs.hidden
        return AppOrdering.order(apps.filter { it.packageName !in hidden }, prefs.order, { it.packageName }, { it.label })
    }

    private fun render() {
        if (isFinishing || isDestroyed) return
        val byPackage = apps.associateBy { it.packageName }
        val visible = orderedApps()
        val dock = currentDock()
        val recent = Recents.visible(prefs.recent, visible.mapTo(HashSet()) { it.packageName }, dock, prefs.columns)
        home.bind(
            HomeState(
                apps = visible,
                dock = dock.mapNotNull { byPackage[it] },
                recent = recent.mapNotNull { byPackage[it] },
                motion = prefs.motion,
                theme = Themes.byId(prefs.themeId),
                blackWallpaper = prefs.blackWallpaper,
                glow = prefs.glow,
                columns = prefs.columns,
                clock24 = prefs.clock24,
                greeting = currentGreeting(),
                loading = !loaded,
                cinematic = prefs.cinematic,
            ),
        )
    }

    private fun currentGreeting(): String? {
        if (!prefs.greeting) return null
        return when (Greeting.forHour(Calendar.getInstance().get(Calendar.HOUR_OF_DAY))) {
            Greeting.Kind.MORNING -> getString(R.string.greeting_morning)
            Greeting.Kind.AFTERNOON -> getString(R.string.greeting_afternoon)
            Greeting.Kind.NIGHT -> getString(R.string.greeting_night)
        }
    }

    // ---- HomeScreen.Listener ----

    override fun onLaunch(app: AppEntry) {
        val intent = Intent(Intent.ACTION_MAIN)
            .addCategory(Intent.CATEGORY_LEANBACK_LAUNCHER)
            .setComponent(app.component)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED)
        try {
            startActivity(intent)
            prefs.recent = Recents.record(prefs.recent, app.packageName)
        } catch (e: Exception) {
            Toast.makeText(this, getString(R.string.cannot_open, app.label), Toast.LENGTH_SHORT).show()
        }
    }

    override fun onOptions(app: AppEntry, inDock: Boolean) {
        val actions = mutableListOf<Pair<String, () -> Unit>>()
        val dock = currentDock()
        if (inDock) {
            actions += getString(R.string.dock_remove) to { prefs.dock = DockConfig.remove(dock, app.packageName) }
            actions += getString(R.string.move_left) to { prefs.dock = AppOrdering.move(dock, app.packageName, -1) }
            actions += getString(R.string.move_right) to { prefs.dock = AppOrdering.move(dock, app.packageName, 1) }
        } else {
            if (app.packageName !in dock) actions += getString(R.string.dock_add) to { addToDock(app.packageName) }
            val order = orderedApps().map { it.packageName }
            actions += getString(R.string.move_left) to { prefs.order = AppOrdering.move(order, app.packageName, -1) }
            actions += getString(R.string.move_right) to { prefs.order = AppOrdering.move(order, app.packageName, 1) }
            actions += getString(R.string.hide_app) to { prefs.hidden = prefs.hidden + app.packageName }
        }
        actions += getString(R.string.app_info) to {
            startSafely(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${app.packageName}")))
        }
        AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
            .setTitle(app.label)
            .setItems(actions.map { it.first }.toTypedArray()) { _, which -> actions[which].second() }
            .show()
    }

    override fun onAddToDock() {
        val dock = currentDock()
        val candidates = orderedApps().filter { it.packageName !in dock }
        if (candidates.isEmpty()) return
        AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
            .setTitle(R.string.pick_app)
            .setItems(candidates.map { it.label }.toTypedArray()) { _, which -> addToDock(candidates[which].packageName) }
            .show()
    }

    override fun onShortcut(shortcut: Shortcut) {
        when (shortcut) {
            Shortcut.INPUTS -> TvShortcuts.openInputs(this)
            Shortcut.HDMI -> TvShortcuts.showInputs(this, passthroughOnly = true)
            Shortcut.LIVE_TV -> TvShortcuts.openLiveTv(this)
            Shortcut.NETWORK -> TvShortcuts.openNetwork(this)
            Shortcut.SETTINGS -> TvShortcuts.openSettings(this)
            Shortcut.CUSTOMIZE -> startSafely(Intent(this, SettingsActivity::class.java))
        }
    }

    private fun addToDock(pkg: String) {
        val updated = DockConfig.add(currentDock(), pkg)
        if (updated == null) Toast.makeText(this, R.string.dock_full, Toast.LENGTH_SHORT).show() else prefs.dock = updated
    }

    private fun startSafely(intent: Intent) {
        try {
            startActivity(intent)
        } catch (e: Exception) {
            Toast.makeText(this, getString(R.string.cannot_open, intent.action ?: ""), Toast.LENGTH_SHORT).show()
        }
    }
}

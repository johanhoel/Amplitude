package app.homedeck

import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import org.json.JSONObject

/**
 * Home Deck: the panels in a WebView with a tab bar. Not paired yet -> the server's /pair page plus a "Scan QR code"
 * button; the page hands the new key to [Bridge.paired]. The key goes to the WebView as the hd_device cookie and to
 * the tiles / widget as a Bearer header. If the server sends the app to /pair while it has a key, the device was
 * removed on /devices: the key is forgotten.
 */
class MainActivity : Activity() {
    private lateinit var web: WebView
    private lateinit var bar: LinearLayout
    private lateinit var scan: TextView
    private val tabs = listOf(
        Tab("🏠", "Home", "/living"), Tab("👪", "Family", "/family"), Tab("🚌", "Info", "/familyinfo"),
        Tab("🎵", "Media", "/media"), Tab("▦", "All", "/start"),
    )
    private val tabViews = mutableListOf<TextView>()

    data class Tab(val icon: String, val label: String, val path: String)

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        window.statusBarColor = BG
        window.navigationBarColor = BAR

        web = WebView(this).apply {
            setBackgroundColor(BG)
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false
            settings.userAgentString = settings.userAgentString + " HomeDeckApp/" + BuildConfig.VERSION_NAME
            addJavascriptInterface(Bridge(), "HomeDeckApp")
            webViewClient = Client()
        }
        bar = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setBackgroundColor(BAR) }
        tabs.forEach { t ->
            val v = TextView(this).apply {
                text = "${t.icon}\n${t.label}"
                gravity = Gravity.CENTER
                textSize = 12f
                setTextColor(MUTE)
                setPadding(0, dp(8), 0, dp(8))
                setOnClickListener { open(t.path) }
            }
            tabViews += v
            bar.addView(v, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        }
        scan = TextView(this).apply {
            text = "📷  Scan QR code"
            textSize = 16f
            setTextColor(Color.parseColor("#062033"))
            gravity = Gravity.CENTER
            setPadding(dp(22), dp(14), dp(22), dp(14))
            background = GradientDrawable().apply { cornerRadius = dp(999).toFloat(); setColor(ACCENT) }
            setOnClickListener { scanQr() }
        }
        val frame = FrameLayout(this).apply {
            addView(web, FrameLayout.LayoutParams(-1, -1))
            addView(scan, FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL).apply { bottomMargin = dp(28) })
        }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(BG)
            addView(frame, LinearLayout.LayoutParams(-1, 0, 1f))
            addView(bar, LinearLayout.LayoutParams(-1, -2))
        }
        // edge-to-edge (Android 15+): keep the page below the status bar and the tab bar above the gesture bar / keyboard
        root.setOnApplyWindowInsetsListener { v, ins ->
            if (Build.VERSION.SDK_INT >= 30) {
                val sys = ins.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
                val ime = ins.getInsets(WindowInsets.Type.ime())
                v.setPadding(sys.left, sys.top, sys.right, maxOf(sys.bottom, ime.bottom))
            } else {
                @Suppress("DEPRECATION")
                v.setPadding(ins.systemWindowInsetLeft, ins.systemWindowInsetTop, ins.systemWindowInsetRight, ins.systemWindowInsetBottom)
            }
            ins
        }
        setContentView(root)

        if (state != null) web.restoreState(state) else start()
    }

    private fun start() {
        val tok = Store.token(this)
        if (tok == null) {
            web.loadUrl(Api.BASE + "/pair")
        } else {
            setCookie(tok)
            open(Store.getString(this, "tab", "/living"))
        }
    }

    private fun setCookie(tok: String) {
        val cm = CookieManager.getInstance()
        cm.setAcceptCookie(true)
        cm.setCookie(Api.BASE, "hd_device=$tok; Path=/; Max-Age=34560000; Secure; HttpOnly; SameSite=Lax")
        cm.flush()
    }

    private fun open(path: String) {
        if (tabs.any { it.path == path }) Store.putString(this, "tab", path)
        web.loadUrl(Api.BASE + path)
    }

    private fun showChrome(url: String?) {
        val path = url?.let { Uri.parse(it).path } ?: ""
        val pairing = path == "/pair" || path == "/pair.html"
        scan.visibility = if (pairing && Store.token(this) == null) View.VISIBLE else View.GONE
        bar.visibility = if (pairing) View.GONE else View.VISIBLE
        tabViews.forEachIndexed { i, v -> v.setTextColor(if (tabs[i].path == path) INK else MUTE) }
    }

    private fun scanQr() {
        val opts = GmsBarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build()
        GmsBarcodeScanning.getClient(this, opts).startScan()
            .addOnSuccessListener { code ->
                val v = code.rawValue ?: ""
                if (v.startsWith(Api.BASE + "/pair?s=")) web.loadUrl(v)
                else Toast.makeText(this, "That is not a Home Deck pairing code", Toast.LENGTH_LONG).show()
            }
            .addOnFailureListener { Toast.makeText(this, "Scanner not available: type the code instead", Toast.LENGTH_LONG).show() }
    }

    override fun onResume() {
        super.onResume()
        if (Store.token(this) != null) {
            HomeWidget.refreshAll(this)
            Updater.checkSoon(this) { name, notes -> offerUpdate(name, notes) }
        }
    }

    private fun offerUpdate(name: String, notes: String) {
        if (isFinishing) return
        AlertDialog.Builder(this)
            .setTitle("Update to $name")
            .setMessage(notes.ifBlank { "A new version of Home Deck is ready." })
            .setPositiveButton("Update") { _, _ ->
                Toast.makeText(this, "Downloading…", Toast.LENGTH_SHORT).show()
                Updater.install(this) { err -> runOnUiThread { Toast.makeText(this, err, Toast.LENGTH_LONG).show() } }
            }
            .setNegativeButton("Later", null)
            .show()
    }

    override fun onSaveInstanceState(out: Bundle) {
        super.onSaveInstanceState(out)
        web.saveState(out)
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else @Suppress("DEPRECATION") super.onBackPressed()
    }

    private inner class Client : WebViewClient() {
        override fun shouldOverrideUrlLoading(view: WebView, req: WebResourceRequest): Boolean {
            if (req.url.host == Api.HOST) return false               // our server (any port): stay in the app
            startActivity(Intent(Intent.ACTION_VIEW, req.url))       // anything else: the phone's browser
            return true
        }

        override fun onPageFinished(view: WebView, url: String?) {
            val path = url?.let { Uri.parse(it).path } ?: ""
            if (path == "/pair" && Store.token(this@MainActivity) != null && url?.contains("s=") != true) {
                // the server sent us here: this device was removed (or its key is no longer valid)
                Store.clear(this@MainActivity)
                CookieManager.getInstance().removeAllCookies(null)
                Toast.makeText(this@MainActivity, "This phone is no longer paired. Pair it again at home.", Toast.LENGTH_LONG).show()
            }
            showChrome(url)
        }
    }

    /** window.HomeDeckApp in the pages (pair.html). Only our own server's pages are ever loaded in this WebView. */
    private inner class Bridge {
        @JavascriptInterface
        fun paired(token: String, id: String, name: String, publicUrl: String?) {
            runOnUiThread {
                if (Uri.parse(web.url ?: "").host != Api.HOST || token.length < 30) return@runOnUiThread
                Store.saveToken(this@MainActivity, token, id, name)
                setCookie(token)
                Toast.makeText(this@MainActivity, "Paired as $name", Toast.LENGTH_SHORT).show()
                web.postDelayed({ open("/living"); web.clearHistory() }, 900)
            }
        }

        @JavascriptInterface
        fun model(): String = "${Build.MANUFACTURER} ${Build.MODEL}".trim()

        @JavascriptInterface
        fun version(): String = BuildConfig.VERSION_NAME
    }

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    companion object {
        val BG = Color.parseColor("#101418")
        val BAR = Color.parseColor("#151a20")
        val INK = Color.parseColor("#f6f4fb")
        val MUTE = Color.parseColor("#7d8794")
        val ACCENT = Color.parseColor("#38bdf8")

        fun json(s: String): JSONObject? = try { JSONObject(s) } catch (e: Exception) { null }
    }
}

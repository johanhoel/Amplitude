package app.homedeck

import android.app.Activity
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.os.Build
import android.widget.Toast
import java.io.File

/**
 * Self-update from the Home Deck server: GET /app/version.json {code, name, notes}; a newer code -> ask, download
 * /app/homedeck.apk (with this phone's key) and hand it to Android's installer, which asks the user to confirm.
 * Checked when the app is opened, at most every 6 hours.
 */
object Updater {
    private const val EVERY_MS = 6 * 3600 * 1000L

    fun checkSoon(act: Activity, offer: (String, String) -> Unit) {
        val now = System.currentTimeMillis()
        if (now - Store.getLong(act, "upd_checked") < EVERY_MS) return
        Store.putLong(act, "upd_checked", now)
        Thread {
            val o = MainActivity.json(Api.get(act, "/app/version.json").body) ?: return@Thread
            if (o.optInt("code") > BuildConfig.VERSION_CODE) {
                act.runOnUiThread { offer(o.optString("name"), o.optString("notes")) }
            }
        }.start()
    }

    fun install(ctx: Context, onError: (String) -> Unit) {
        Thread {
            val apk = File(ctx.cacheDir, "update.apk")
            if (!Api.download(ctx, "/app/homedeck.apk", apk)) return@Thread onError("Download failed")
            try {
                val pi = ctx.packageManager.packageInstaller
                val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
                if (Build.VERSION.SDK_INT >= 31) params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
                val id = pi.createSession(params)
                pi.openSession(id).use { s ->
                    s.openWrite("homedeck.apk", 0, apk.length()).use { out -> apk.inputStream().use { it.copyTo(out) }; s.fsync(out) }
                    val flags = PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0)
                    val cb = PendingIntent.getBroadcast(ctx, 7, Intent(ctx, InstallReceiver::class.java), flags)
                    s.commit(cb.intentSender)
                }
            } catch (e: Exception) {
                onError("Update failed: ${e.message}")
            } finally {
                apk.delete()
            }
        }.start()
    }
}

/** Android's installer reports here; it usually first needs the user's OK (and once: "allow installs from Home Deck"). */
class InstallReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        when (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, -999)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                @Suppress("DEPRECATION")
                val confirm = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT) ?: return
                ctx.startActivity(confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
            PackageInstaller.STATUS_SUCCESS -> {}
            else -> Toast.makeText(ctx, "Update not installed: " + (intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE) ?: ""), Toast.LENGTH_LONG).show()
        }
    }
}

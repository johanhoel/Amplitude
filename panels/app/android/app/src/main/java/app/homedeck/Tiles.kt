package app.homedeck

import android.os.Build
import android.os.Handler
import android.os.Looper
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import android.widget.Toast

/**
 * Quick Settings tiles (swipe down twice -> edit -> drag them in). Each sends one fixed action to POST /api/home/do.
 * Lock and Wake PC ask for the screen to be unlocked first; lights off also works from the lock screen.
 */
abstract class ActionTile(private val body: String, private val doneText: String, private val needsUnlock: Boolean) : TileService() {
    private val main = Handler(Looper.getMainLooper())

    override fun onStartListening() = show(Tile.STATE_INACTIVE, null)

    override fun onClick() {
        if (needsUnlock && isLocked) unlockAndRun { run() } else run()
    }

    private fun run() {
        if (Store.token(this) == null) {
            Toast.makeText(this, "Open Home Deck and pair this phone first", Toast.LENGTH_LONG).show()
            return
        }
        show(Tile.STATE_ACTIVE, "Sending…")
        Thread {
            val r = Api.post(this, "/api/home/do", body)
            val err = MainActivity.json(r.body)?.optString("error").orEmpty()
            main.post {
                show(if (r.ok) Tile.STATE_ACTIVE else Tile.STATE_UNAVAILABLE, if (r.ok) doneText else "Failed")
                if (!r.ok) Toast.makeText(this, "Home Deck: " + err.ifBlank { "no answer (${r.code})" }, Toast.LENGTH_LONG).show()
                main.postDelayed({ show(Tile.STATE_INACTIVE, null) }, 4000)
            }
        }.start()
    }

    private fun show(state: Int, sub: String?) {
        val t = qsTile ?: return
        t.state = state
        if (Build.VERSION.SDK_INT >= 29) t.subtitle = sub
        t.updateTile()
    }
}

class LightsOffTile : ActionTile("""{"do":"all_off"}""", "All off", false)
class LockTile : ActionTile("""{"do":"lock"}""", "Locking", true)
class WakePcTile : ActionTile("""{"do":"wake_pc"}""", "Waking", true)

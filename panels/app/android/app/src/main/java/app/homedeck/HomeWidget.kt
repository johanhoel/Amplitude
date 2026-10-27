package app.homedeck

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.widget.RemoteViews
import java.text.SimpleDateFormat
import java.time.OffsetDateTime
import java.util.Date
import java.util.Locale

/**
 * Home screen widget: who is home (GET /api/family) and the next buses (GET /api/bus).
 * Refreshes every 30 minutes (Android's minimum), when the app is opened, and when ⟳ is tapped.
 * Bus times are clock times, so an older update is still readable.
 */
class HomeWidget : AppWidgetProvider() {
    override fun onUpdate(ctx: Context, mgr: AppWidgetManager, ids: IntArray) = refresh(ctx, ids)

    override fun onReceive(ctx: Context, intent: Intent) {
        super.onReceive(ctx, intent)
        if (intent.action == REFRESH) refreshAll(ctx)
    }

    private fun refresh(ctx: Context, ids: IntArray) {
        val pending = goAsync()
        Thread {
            try {
                val views = build(ctx)
                val mgr = AppWidgetManager.getInstance(ctx)
                ids.forEach { mgr.updateAppWidget(it, views) }
            } finally {
                pending.finish()
            }
        }.start()
    }

    companion object {
        const val REFRESH = "app.homedeck.WIDGET_REFRESH"
        private val GREEN = Color.parseColor("#34d399")
        private val GREY = Color.parseColor("#6b7280")

        fun refreshAll(ctx: Context) {
            val mgr = AppWidgetManager.getInstance(ctx)
            val ids = mgr.getAppWidgetIds(ComponentName(ctx, HomeWidget::class.java))
            if (ids.isEmpty()) return
            Thread { val v = build(ctx); ids.forEach { mgr.updateAppWidget(it, v) } }.start()
        }

        private fun build(ctx: Context): RemoteViews {
            val v = RemoteViews(ctx.packageName, R.layout.widget_home)
            val open = PendingIntent.getActivity(ctx, 0, Intent(ctx, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
            val again = PendingIntent.getBroadcast(ctx, 1, Intent(ctx, HomeWidget::class.java).setAction(REFRESH), PendingIntent.FLAG_IMMUTABLE)
            v.setOnClickPendingIntent(R.id.w_root, open)
            v.setOnClickPendingIntent(R.id.w_refresh, again)
            if (Store.token(ctx) == null) {
                v.setTextViewText(R.id.w_people, "Open Home Deck to pair this phone")
                v.setTextViewText(R.id.w_bus, "")
                v.setTextViewText(R.id.w_time, "")
                return v
            }
            v.setTextViewText(R.id.w_people, people(ctx))
            v.setTextViewText(R.id.w_bus, buses(ctx))
            v.setTextViewText(R.id.w_time, "Updated " + SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date()))
            return v
        }

        private fun people(ctx: Context): CharSequence {
            val r = Api.get(ctx, "/api/family")
            val arr = MainActivity.json(r.body)?.optJSONArray("people") ?: return "Home Deck not reachable"
            val sb = SpannableStringBuilder()
            for (i in 0 until arr.length()) {
                val p = arr.getJSONObject(i)
                if (sb.isNotEmpty()) sb.append("   ")
                val s = sb.length
                sb.append("●")
                sb.setSpan(ForegroundColorSpan(if (p.optBoolean("home")) GREEN else GREY), s, sb.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                sb.append(" ").append(p.optString("name"))
            }
            return sb
        }

        private fun buses(ctx: Context): CharSequence {
            val r = Api.get(ctx, "/api/bus")
            val o = MainActivity.json(r.body) ?: return ""
            val deps = o.optJSONArray("departures") ?: return ""
            val rows = (0 until deps.length()).map { deps.getJSONObject(it) }
                .mapNotNull { d ->
                    val t = d.optJSONObject("next")?.optString("time") ?: return@mapNotNull null
                    val at = try { OffsetDateTime.parse(t) } catch (e: Exception) { return@mapNotNull null }
                    Triple(at, d.optJSONObject("line")?.optString("shortName").orEmpty(), d.optString("to"))
                }
                .sortedBy { it.first }.take(3)
            if (rows.isEmpty()) return ""
            return o.optString("stop") + "\n" + rows.joinToString("\n") { (at, line, to) ->
                "%02d:%02d  %s  %s".format(at.hour, at.minute, line, to)
            }
        }
    }
}

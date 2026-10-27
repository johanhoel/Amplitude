package app.homedeck

import android.content.Context
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/** Calls to the Home Deck server with this phone's key (Authorization: Bearer). Run off the main thread. */
object Api {
    const val BASE = BuildConfig.BASE_URL
    val HOST: String = URL(BASE).host

    class Result(val code: Int, val body: String) {
        val ok get() = code in 200..299
    }

    private fun open(ctx: Context, path: String): HttpURLConnection {
        val c = URL(BASE + path).openConnection() as HttpURLConnection
        c.connectTimeout = 10_000
        c.readTimeout = 15_000
        c.setRequestProperty("User-Agent", "HomeDeckApp/${BuildConfig.VERSION_NAME}")
        Store.token(ctx)?.let { c.setRequestProperty("Authorization", "Bearer $it") }
        return c
    }

    private fun read(c: HttpURLConnection): Result {
        val code = c.responseCode
        val body = (if (code < 400) c.inputStream else c.errorStream)?.bufferedReader()?.use { it.readText() } ?: ""
        c.disconnect()
        return Result(code, body)
    }

    fun get(ctx: Context, path: String): Result = try { read(open(ctx, path)) } catch (e: Exception) { Result(0, e.message ?: "no connection") }

    fun post(ctx: Context, path: String, json: String): Result = try {
        val c = open(ctx, path)
        c.requestMethod = "POST"
        c.doOutput = true
        c.setRequestProperty("Content-Type", "application/json")
        c.outputStream.use { it.write(json.toByteArray()) }
        read(c)
    } catch (e: Exception) {
        Result(0, e.message ?: "no connection")
    }

    /** Download to a file (the app update). */
    fun download(ctx: Context, path: String, to: File): Boolean = try {
        val c = open(ctx, path)
        c.readTimeout = 60_000
        if (c.responseCode != 200) false else {
            c.inputStream.use { inp -> to.outputStream().use { inp.copyTo(it) } }
            c.disconnect()
            true
        }
    } catch (e: Exception) {
        false
    }
}

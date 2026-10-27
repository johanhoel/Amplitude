package app.homedeck

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** This phone's device key for Home Deck. Kept encrypted with a key in the Android Keystore (it never leaves the phone). */
object Store {
    private const val ALIAS = "homedeck_device_key"
    private fun prefs(ctx: Context) = ctx.getSharedPreferences("homedeck", Context.MODE_PRIVATE)

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as SecretKey?)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .build())
        return gen.generateKey()
    }

    fun saveToken(ctx: Context, token: String, id: String, name: String) {
        val c = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        val enc = c.doFinal(token.toByteArray())
        prefs(ctx).edit()
            .putString("tok", Base64.encodeToString(enc, Base64.NO_WRAP))
            .putString("iv", Base64.encodeToString(c.iv, Base64.NO_WRAP))
            .putString("id", id).putString("name", name).apply()
    }

    fun token(ctx: Context): String? {
        val p = prefs(ctx)
        val tok = p.getString("tok", null) ?: return null
        val iv = p.getString("iv", null) ?: return null
        return try {
            val c = Cipher.getInstance("AES/GCM/NoPadding")
            c.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)))
            String(c.doFinal(Base64.decode(tok, Base64.NO_WRAP)))
        } catch (e: Exception) {
            null
        }
    }

    fun deviceName(ctx: Context): String = prefs(ctx).getString("name", "") ?: ""

    fun clear(ctx: Context) = prefs(ctx).edit().remove("tok").remove("iv").remove("id").remove("name").apply()

    fun getString(ctx: Context, k: String, def: String): String = prefs(ctx).getString(k, def) ?: def
    fun putString(ctx: Context, k: String, v: String) = prefs(ctx).edit().putString(k, v).apply()
    fun getLong(ctx: Context, k: String): Long = prefs(ctx).getLong(k, 0)
    fun putLong(ctx: Context, k: String, v: Long) = prefs(ctx).edit().putLong(k, v).apply()
}

package dev.wire.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * Keeps the session token (and the pending recovery codes) encrypted with an
 * AES-GCM key that lives in the Android Keystore. This is the same scheme the
 * old native app used; the web layer never sees the key.
 */
@CapacitorPlugin(name = "WireVault")
public class WireVaultPlugin extends Plugin {
  private static final String ALIAS = "wire_session_key_v1";
  private static final String PREFS = "session";

  private SharedPreferences prefs() {
    return getContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
  }

  private SecretKey key() throws Exception {
    KeyStore store = KeyStore.getInstance("AndroidKeyStore");
    store.load(null);
    if (store.containsAlias(ALIAS)) return (SecretKey) store.getKey(ALIAS, null);
    KeyGenerator generator =
        KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
    generator.init(
        new KeyGenParameterSpec.Builder(
                ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .build());
    return generator.generateKey();
  }

  private String encrypt(String value) throws Exception {
    Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
    cipher.init(Cipher.ENCRYPT_MODE, key());
    return Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP)
        + ":"
        + Base64.encodeToString(
            cipher.doFinal(value.getBytes(StandardCharsets.UTF_8)), Base64.NO_WRAP);
  }

  private String decrypt(String value) throws Exception {
    String[] parts = value.split(":");
    if (parts.length != 2) throw new Exception("Invalid secure state");
    Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
    cipher.init(
        Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)));
    return new String(
        cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)), StandardCharsets.UTF_8);
  }

  private String slot(PluginCall call) {
    String name = call.getString("key", "");
    if (name == null || !name.matches("[a-z_]{1,32}")) {
      call.reject("Invalid key");
      return null;
    }
    return "v_" + name;
  }

  @PluginMethod
  public synchronized void setItem(PluginCall call) {
    String slot = slot(call);
    if (slot == null) return;
    String value = call.getString("value");
    if (value == null) {
      call.reject("Missing value");
      return;
    }
    try {
      if (!prefs().edit().putString(slot, encrypt(value)).commit()) {
        call.reject("Could not save secure state");
        return;
      }
      call.resolve();
    } catch (Exception error) {
      call.reject("Could not save secure state");
    }
  }

  @PluginMethod
  public synchronized void getItem(PluginCall call) {
    String slot = slot(call);
    if (slot == null) return;
    JSObject result = new JSObject();
    try {
      String stored = prefs().getString(slot, null);
      if (stored == null) result.put("value", JSObject.NULL);
      else result.put("value", decrypt(stored));
    } catch (Exception error) {
      // An unreadable value (for example a lost key) is treated as signed out.
      prefs().edit().remove(slot).commit();
      result.put("value", JSObject.NULL);
    }
    call.resolve(result);
  }

  @PluginMethod
  public synchronized void removeItem(PluginCall call) {
    String slot = slot(call);
    if (slot == null) return;
    prefs().edit().remove(slot).commit();
    call.resolve();
  }
}

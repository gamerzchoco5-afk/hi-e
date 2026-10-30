package dev.wire.app;

import android.view.WindowManager;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/** Blocks screenshots and the recent-apps thumbnail on sign-in, recovery and password screens. */
@CapacitorPlugin(name = "ScreenGuard")
public class ScreenGuardPlugin extends Plugin {
  @PluginMethod
  public void setSecure(PluginCall call) {
    final boolean secure = Boolean.TRUE.equals(call.getBoolean("secure", false));
    getActivity()
        .runOnUiThread(
            () -> {
              if (secure) getActivity().getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
              else getActivity().getWindow().clearFlags(WindowManager.LayoutParams.FLAG_SECURE);
              call.resolve();
            });
  }
}

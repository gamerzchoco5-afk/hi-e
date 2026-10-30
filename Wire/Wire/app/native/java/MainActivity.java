package dev.wire.app;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
  @Override
  public void onCreate(Bundle savedInstanceState) {
    registerPlugin(WireVaultPlugin.class);
    registerPlugin(ScreenGuardPlugin.class);
    super.onCreate(savedInstanceState);
    getWindow().setStatusBarColor(0xff0b0c0e);
    getWindow().setNavigationBarColor(0xff0b0c0e);
  }
}

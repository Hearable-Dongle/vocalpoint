import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:universal_ble/universal_ble.dart';

void main() => runApp(const MyApp());

class AppColors {
  static const Color background = Color(0xFF181818);
  static const Color surfaceDark = Color(0xFF232323);
  static const Color surfaceDarkSoft = Color(0xFF2C2C2C);
  static const Color outline = Color(0xFF3A3A3A);

  static const Color peach = Color(0xFFF4A261);
  static const Color yellow = Color(0xFFE9C46A);
  static const Color coral = Color(0xFFE76F51);

  static const Color white = Colors.white;
  static const Color black = Colors.black87;
  static const Color textMuted = Color(0xFFB8B8B8);

  static const Color charcoal = surfaceDarkSoft;
  static const Color charcoalSoft = outline;
}

/// Simple app-wide state (no extra packages).
class AppState {
  static void clearConnection() {
    connectedDeviceId.value = null;
    connectedDeviceName.value = null;
  }

  /// Remembered devices (in-app "paired" list).
  static final ValueNotifier<List<RememberedDevice>> rememberedDevices =
      ValueNotifier<List<RememberedDevice>>(<RememberedDevice>[]);

  /// Currently connected deviceId (if any).
  static final ValueNotifier<String?> connectedDeviceId =
      ValueNotifier<String?>(null);

  /// Currently connected device name (best-effort).
  static final ValueNotifier<String?> connectedDeviceName =
      ValueNotifier<String?>(null);

  /// Volume 0..100
  static final ValueNotifier<double> volume = ValueNotifier<double>(50);
  static final ValueNotifier<double> battery = ValueNotifier<double>(75);

  static final ValueNotifier<String> bleAddress = ValueNotifier<String>("");
  static final ValueNotifier<String?> audioOutputDeviceName =
      ValueNotifier<String?>(null);
  static final ValueNotifier<String> param1 = ValueNotifier<String>(
    "Morning Tide",
  );
  static final ValueNotifier<String> param2 = ValueNotifier<String>(
    "Amber Lantern",
  );

  /// UUIDs for ESP32 control (default matches 0xFFFF service / 0xFF01 + 0xFF02 chars).
  static final ValueNotifier<String> volumeServiceUuid =
      ValueNotifier<String>("0000FFFF-0000-1000-8000-00805F9B34FB");
  static final ValueNotifier<String> volumeCharUuid =
      ValueNotifier<String>("0000FF01-0000-1000-8000-00805F9B34FB");
  static final ValueNotifier<String> metadataCharUuid =
      ValueNotifier<String>("0000FF02-0000-1000-8000-00805F9B34FB");
}

class RememberedDevice {
  final String deviceId;
  final String name;
  final DateTime lastSeen;

  const RememberedDevice({
    required this.deviceId,
    required this.name,
    required this.lastSeen,
  });

  RememberedDevice copyWith({String? name, DateTime? lastSeen}) {
    return RememberedDevice(
      deviceId: deviceId,
      name: name ?? this.name,
      lastSeen: lastSeen ?? this.lastSeen,
    );
  }
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    final base = ThemeData(
      useMaterial3: true,
      colorScheme: const ColorScheme(
        brightness: Brightness.dark,
        primary: AppColors.surfaceDarkSoft,
        onPrimary: AppColors.white,
        secondary: AppColors.yellow,
        onSecondary: AppColors.black,
        tertiary: AppColors.peach,
        onTertiary: AppColors.black,
        error: AppColors.coral,
        onError: AppColors.white,
        surface: AppColors.surfaceDark,
        onSurface: AppColors.white,
      ),
    );

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: "VocalPoint Demo",
      theme: base.copyWith(
        scaffoldBackgroundColor: AppColors.background,
        appBarTheme: const AppBarTheme(
          backgroundColor: AppColors.background,
          foregroundColor: AppColors.white,
          elevation: 0,
          centerTitle: false,
        ),
        cardTheme: CardThemeData(
          color: AppColors.surfaceDark,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(22),
            side: const BorderSide(color: AppColors.outline),
          ),
          margin: EdgeInsets.zero,
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: AppColors.yellow,
            foregroundColor: AppColors.black,
            elevation: 0,
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
            ),
            textStyle: const TextStyle(fontWeight: FontWeight.w700),
          ),
        ),
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            backgroundColor: AppColors.coral,
            foregroundColor: AppColors.white,
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
            ),
            textStyle: const TextStyle(fontWeight: FontWeight.w700),
          ),
        ),
        outlinedButtonTheme: OutlinedButtonThemeData(
          style: OutlinedButton.styleFrom(
            foregroundColor: AppColors.white,
            side: const BorderSide(color: AppColors.outline, width: 1.2),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
            ),
            textStyle: const TextStyle(fontWeight: FontWeight.w600),
          ),
        ),
        textButtonTheme: TextButtonThemeData(
          style: TextButton.styleFrom(
            foregroundColor: AppColors.peach,
            textStyle: const TextStyle(fontWeight: FontWeight.w700),
          ),
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: AppColors.surfaceDark,
          labelStyle: const TextStyle(color: AppColors.textMuted),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(16),
            borderSide: const BorderSide(color: AppColors.outline),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(16),
            borderSide: const BorderSide(color: AppColors.outline),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(16),
            borderSide: const BorderSide(color: AppColors.peach, width: 2),
          ),
        ),
        dividerTheme: const DividerThemeData(
          color: AppColors.outline,
          thickness: 1,
        ),
        snackBarTheme: SnackBarThemeData(
          backgroundColor: AppColors.surfaceDarkSoft,
          contentTextStyle: const TextStyle(color: AppColors.white),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
          behavior: SnackBarBehavior.floating,
        ),
      ),
      initialRoute: '/',
      routes: {
        '/': (_) => const HomePage(),
        '/connect-vocalpoint': (_) => const ConnectVocalPointPage(),
        '/connect-listening-device': (_) => const ConnectListeningDevicePage(),
        '/volume': (_) => const VolumeControlPage(),
      },
    );
  }
}

/// Shared "Home" button for AppBars.
class HomeButton extends StatelessWidget {
  const HomeButton({super.key});

  @override
  Widget build(BuildContext context) {
    return IconButton(
      tooltip: "Home",
      onPressed: () => Navigator.of(context).popUntil((r) => r.isFirst),
      icon: SvgPicture.asset(
        'assets/Squiggly.svg',
        width: 28,
        height: 28,
        colorFilter: const ColorFilter.mode(
          AppColors.white,
          BlendMode.srcIn,
        ),
      ),
    );
  }
}

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  Widget _statusLine(String label, Widget value) {
    return Row(
      children: [
        SizedBox(
          width: 130,
          child: Text(
            label,
            style: const TextStyle(
              fontWeight: FontWeight.w600,
              color: AppColors.textMuted,
            ),
          ),
        ),
        Expanded(child: value),
      ],
    );
  }

  Widget _circleNavButton(
    BuildContext context, {
    required IconData icon,
    required String label,
    required String route,
    required Color background,
    required Color foreground,
  }) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Material(
          color: background,
          shape: const CircleBorder(),
          child: InkWell(
            customBorder: const CircleBorder(),
            onTap: () => Navigator.pushNamed(context, route),
            child: SizedBox(
              width: 96,
              height: 96,
              child: Icon(icon, color: foreground, size: 38),
            ),
          ),
        ),
        const SizedBox(height: 10),
        SizedBox(
          width: 110,
          child: Text(
            label,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: AppColors.white,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const SizedBox.shrink(),
        actions: const [HomeButton()],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const SizedBox(height: 12),
            Center(
              child: Wrap(
                spacing: 24,
                runSpacing: 24,
                alignment: WrapAlignment.center,
                children: [
                  _circleNavButton(
                    context,
                    icon: Icons.bluetooth,
                    label: "VocalPoint",
                    route: '/connect-vocalpoint',
                    background: AppColors.yellow,
                    foreground: AppColors.black,
                  ),
                  _circleNavButton(
                    context,
                    icon: Icons.hearing,
                    label: "Listening Device",
                    route: '/connect-listening-device',
                    background: AppColors.peach,
                    foreground: AppColors.black,
                  ),
                  _circleNavButton(
                    context,
                    icon: Icons.volume_up,
                    label: "Volume",
                    route: '/volume',
                    background: AppColors.coral,
                    foreground: AppColors.white,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 32),
            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: AppColors.surfaceDark,
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: AppColors.outline),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    "Quick status",
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                      color: AppColors.white,
                    ),
                  ),
                  const SizedBox(height: 14),
                  _statusLine(
                    "Connected:",
                    ValueListenableBuilder<String?>(
                      valueListenable: AppState.connectedDeviceId,
                      builder: (_, id, __) {
                        return ValueListenableBuilder<String?>(
                          valueListenable: AppState.connectedDeviceName,
                          builder: (_, name, __) {
                            if (id == null) {
                              return const Text(
                                "No",
                                style: TextStyle(
                                  color: AppColors.coral,
                                  fontWeight: FontWeight.w700,
                                ),
                              );
                            }
                            return Text(
                              "Yes — ${name ?? 'Unnamed'}",
                              style: const TextStyle(
                                color: AppColors.white,
                                fontWeight: FontWeight.w700,
                              ),
                            );
                          },
                        );
                      },
                    ),
                  ),
                  const SizedBox(height: 10),
                  _statusLine(
                    "Volume:",
                    ValueListenableBuilder<double>(
                      valueListenable: AppState.volume,
                      builder: (_, v, __) => Text(
                        v.round().toString(),
                        style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          color: AppColors.white,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  _statusLine(
                    "Battery:",
                    ValueListenableBuilder<double>(
                      valueListenable: AppState.battery,
                      builder: (_, v, __) => Text(
                        v.round().toString(),
                        style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          color: AppColors.white,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  _statusLine(
                    "Audio Output:",
                    ValueListenableBuilder<String>(
                      valueListenable: AppState.bleAddress,
                      builder: (_, address, __) {
                        return ValueListenableBuilder<String?>(
                          valueListenable: AppState.audioOutputDeviceName,
                          builder: (_, name, __) {
                            final label = address.isEmpty
                                ? "Not selected"
                                : (name == null || name.isEmpty)
                                    ? address
                                    : "$name — $address";
                            return Text(
                              label,
                              style: const TextStyle(
                                fontWeight: FontWeight.w700,
                                color: AppColors.white,
                              ),
                            );
                          },
                        );
                      },
                    ),
                  ),
                  const SizedBox(height: 10),
                  _statusLine(
                    "Remembered:",
                    ValueListenableBuilder<List<RememberedDevice>>(
                      valueListenable: AppState.rememberedDevices,
                      builder: (_, devices, __) => Text(
                        "${devices.length} device(s)",
                        style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          color: AppColors.white,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class DeviceFilterConfig {
  final String title;
  final bool Function(BleDevice device) shouldShow;

  const DeviceFilterConfig({
    required this.title,
    required this.shouldShow,
  });
}

class FilteredBluetoothPage extends StatefulWidget {
  final DeviceFilterConfig config;

  const FilteredBluetoothPage({
    super.key,
    required this.config,
  });

  @override
  State<FilteredBluetoothPage> createState() => _FilteredBluetoothPageState();
}

class _FilteredBluetoothPageState extends State<FilteredBluetoothPage> {
  bool _scanning = false;
  final List<BleDevice> _found = <BleDevice>[];
  StreamSubscription? _scanTimeoutSub;

  bool _hasDisplayName(BleDevice device) {
    final name = device.name;
    return name != null && name.trim().isNotEmpty && name.trim() != "Unnamed";
  }

  @override
  void initState() {
    super.initState();

    UniversalBle.onScanResult = (BleDevice device) {
      if (!mounted) return;

      if (!_hasDisplayName(device)) {
        _touchRemembered(device.deviceId, device.name ?? "Unnamed");
        return;
      }

      if (!widget.config.shouldShow(device)) return;

      final idx = _found.indexWhere((d) => d.deviceId == device.deviceId);
      if (idx == -1) {
        setState(() => _found.add(device));
      } else {
        final existing = _found[idx];
        final existingName = existing.name;
        final newName = device.name;
        if ((existingName == null || existingName.isEmpty) &&
            (newName != null && newName.isNotEmpty)) {
          setState(() => _found[idx] = device);
        }
      }

      _touchRemembered(device.deviceId, device.name ?? "Unnamed");
    };

    UniversalBle.onConnectionChange =
        (String deviceId, bool isConnected, String? error) {
      if (!mounted) return;

      final currentId = AppState.connectedDeviceId.value;
      if (currentId != deviceId) return;

      if (!isConnected) {
        final disconnectedName =
            AppState.connectedDeviceName.value ?? "device";

        AppState.clearConnection();

        _snack(
          error == null || error.isEmpty
              ? "$disconnectedName disconnected"
              : "$disconnectedName disconnected: $error",
        );
      }
    };
  }

  @override
  void dispose() {
    _scanTimeoutSub?.cancel();
    if (_scanning) {
      UniversalBle.stopScan();
    }
    UniversalBle.onScanResult = null;
    UniversalBle.onConnectionChange = null;
    super.dispose();
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  void _touchRemembered(String deviceId, String name) {
    final current =
        List<RememberedDevice>.from(AppState.rememberedDevices.value);
    final idx = current.indexWhere((d) => d.deviceId == deviceId);
    if (idx == -1) return;
    current[idx] = current[idx].copyWith(name: name, lastSeen: DateTime.now());
    AppState.rememberedDevices.value = current;
  }

  Future<void> _startScan() async {
    setState(() {
      _found.clear();
      _scanning = true;
    });

    try {
      await UniversalBle.startScan();
      // Auto-stop after 10 seconds so scans do not run indefinitely.
      _scanTimeoutSub?.cancel();
      _scanTimeoutSub = Stream<void>.periodic(const Duration(seconds: 10))
          .take(1)
          .listen((_) => _stopScan());
    } on PlatformException catch (e) {
      _snack("Scan failed: ${e.code} — ${e.message ?? ''}");
      setState(() => _scanning = false);
    } catch (e) {
      _snack("Scan failed: $e");
      setState(() => _scanning = false);
    }
  }

  Future<void> _stopScan() async {
    try {
      await UniversalBle.stopScan();
    } catch (_) {
      // ignore
    }
    if (mounted) setState(() => _scanning = false);
  }

  void _rememberDevice(BleDevice d) {
    final name = (d.name == null || d.name!.isEmpty) ? "Unnamed" : d.name!;
    final current =
        List<RememberedDevice>.from(AppState.rememberedDevices.value);
    final idx = current.indexWhere((x) => x.deviceId == d.deviceId);

    if (idx == -1) {
      current.insert(
        0,
        RememberedDevice(
          deviceId: d.deviceId,
          name: name,
          lastSeen: DateTime.now(),
        ),
      );
      AppState.rememberedDevices.value = current;
      _snack("Remembered $name");
    } else {
      _snack("$name is already remembered");
    }
  }

  void _forgetRemembered(String deviceId) {
    final current =
        List<RememberedDevice>.from(AppState.rememberedDevices.value);
    current.removeWhere((d) => d.deviceId == deviceId);
    AppState.rememberedDevices.value = current;
    _snack("Forgot device");
  }

  Future<void> _connect(BleDevice d) async {
    final name = (d.name == null || d.name!.isEmpty) ? "Unnamed" : d.name!;

    try {
      if (_scanning) await _stopScan();

      await UniversalBle.connect(
        d.deviceId,
        connectionTimeout: const Duration(seconds: 10),
      );

      await UniversalBle.discoverServices(d.deviceId);

      AppState.connectedDeviceId.value = d.deviceId;
      AppState.connectedDeviceName.value = name;

      _rememberDevice(d);

      _snack("Connected to $name");
    } on PlatformException catch (e) {
      _snack("Connect failed: ${e.code} — ${e.message ?? ''}");
    } catch (e) {
      _snack("Connect failed: $e");
    }
  }

  Future<void> _disconnect() async {
    final id = AppState.connectedDeviceId.value;
    if (id == null) return;

    try {
      await UniversalBle.disconnect(id);
    } catch (_) {}

    AppState.connectedDeviceId.value = null;
    AppState.connectedDeviceName.value = null;
    _snack("Disconnected");
  }

  Future<void> _showServicesForConnected() async {
    final id = AppState.connectedDeviceId.value;
    if (id == null) {
      _snack("No device connected");
      return;
    }

    try {
      final services = await UniversalBle.discoverServices(id);
      if (!mounted) return;

      showDialog(
        context: context,
        builder: (_) => AlertDialog(
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(24),
          ),
          title: const Text("Discovered services"),
          content: SizedBox(
            width: 520,
            child: SingleChildScrollView(
              child: Text(services.toString()),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text("Close"),
            ),
          ],
        ),
      );
    } catch (e) {
      _snack("Discover services failed: $e");
    }
  }

  @override
  Widget build(BuildContext context) {
    final connectedId = AppState.connectedDeviceId.value;

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.config.title),
        actions: const [HomeButton()],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: AppColors.charcoal,
                borderRadius: BorderRadius.circular(24),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.yellow,
                        foregroundColor: AppColors.black,
                      ),
                      icon: _scanning
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: AppColors.black,
                              ),
                            )
                          : const Icon(Icons.search),
                      label: Text(_scanning ? "Scanning..." : "Scan for devices"),
                      onPressed: _scanning ? null : _startScan,
                    ),
                  ),
                  const SizedBox(width: 12),
                  OutlinedButton(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.white,
                      side: const BorderSide(color: AppColors.white),
                    ),
                    onPressed: _scanning ? _stopScan : null,
                    child: const Text("Stop"),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            ValueListenableBuilder<String?>(
              valueListenable: AppState.connectedDeviceId,
              builder: (_, id, __) {
                return ValueListenableBuilder<String?>(
                  valueListenable: AppState.connectedDeviceName,
                  builder: (_, name, __) {
                    final connected = id != null;
                    return Container(
                      decoration: BoxDecoration(
                        color: connected ? AppColors.peach : Colors.white,
                        borderRadius: BorderRadius.circular(22),
                        border: Border.all(
                          color: connected ? AppColors.peach : Colors.black12,
                        ),
                      ),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Row(
                          children: [
                            Icon(
                              connected ? Icons.link : Icons.link_off,
                              color: connected
                                  ? AppColors.charcoal
                                  : AppColors.coral,
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                connected
                                    ? "Connected: ${name ?? 'Unnamed'}"
                                    : "Not connected",
                                style: TextStyle(
                                  fontWeight: FontWeight.w700,
                                  color: connected
                                      ? AppColors.charcoal
                                      : AppColors.black,
                                ),
                              ),
                            ),
                            if (connected)
                              TextButton(
                                onPressed: _showServicesForConnected,
                                child: const Text("Services"),
                              ),
                            const SizedBox(width: 8),
                            FilledButton(
                              style: FilledButton.styleFrom(
                                backgroundColor:
                                    connected ? AppColors.coral : null,
                              ),
                              onPressed: connected ? _disconnect : null,
                              child: const Text("Disconnect"),
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                );
              },
            ),
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerLeft,
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: AppColors.yellow,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  "Remembered devices",
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w800,
                        color: AppColors.black,
                      ),
                ),
              ),
            ),
            const SizedBox(height: 8),
            ValueListenableBuilder<List<RememberedDevice>>(
              valueListenable: AppState.rememberedDevices,
              builder: (_, remembered, __) {
                if (remembered.isEmpty) {
                  return const _EmptyCard(
                    text:
                        "No remembered devices yet. Connect to one to remember it.",
                    icon: Icons.bluetooth_disabled,
                  );
                }
                return _RememberedListCard(
                  items: remembered,
                  connectedDeviceId: connectedId,
                  onForget: _forgetRemembered,
                );
              },
            ),
            const SizedBox(height: 16),
            Align(
              alignment: Alignment.centerLeft,
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: AppColors.peach,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  "Found devices",
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w800,
                        color: AppColors.black,
                      ),
                ),
              ),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: _found.isEmpty
                  ? const _EmptyCard(
                      text: "Tap Scan to find nearby BLE devices.",
                      icon: Icons.radar,
                    )
                  : Card(
                      child: ListView.separated(
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        itemCount: _found.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (_, i) {
                          final d = _found[i];
                          final name = (d.name == null || d.name!.isEmpty)
                              ? "Unnamed"
                              : d.name!;
                          final isConnected =
                              AppState.connectedDeviceId.value == d.deviceId;

                          return ListTile(
                            leading: CircleAvatar(
                              backgroundColor: isConnected
                                  ? AppColors.coral
                                  : AppColors.yellow,
                              foregroundColor: isConnected
                                  ? AppColors.white
                                  : AppColors.black,
                              child: const Icon(Icons.bluetooth),
                            ),
                            title: Text(
                              name,
                              style: const TextStyle(
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            subtitle: Text(d.deviceId),
                            trailing: Wrap(
                              spacing: 8,
                              children: [
                                TextButton(
                                  onPressed: () => _rememberDevice(d),
                                  child: const Text("Remember"),
                                ),
                                FilledButton(
                                  style: FilledButton.styleFrom(
                                    backgroundColor: isConnected
                                        ? AppColors.charcoalSoft
                                        : AppColors.coral,
                                  ),
                                  onPressed:
                                      isConnected ? null : () => _connect(d),
                                  child: Text(
                                    isConnected ? "Connected" : "Connect",
                                  ),
                                ),
                              ],
                            ),
                          );
                        },
                      ),
                    ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                OutlinedButton.icon(
                  icon: const Icon(Icons.arrow_back),
                  label: const Text("Back"),
                  onPressed: () => Navigator.pop(context),
                ),
                const SizedBox(width: 12),
                OutlinedButton.icon(
                  icon: const Icon(Icons.home),
                  label: const Text("Home"),
                  onPressed: () =>
                      Navigator.of(context).popUntil((r) => r.isFirst),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class ConnectVocalPointPage extends StatelessWidget {
  const ConnectVocalPointPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const FilteredBluetoothPage(
      config: DeviceFilterConfig(
        title: "Connect to VocalPoint Device",
        shouldShow: _isVocalPointDevice,
      ),
    );
  }
}

class AudioOutputSelectionPage extends StatefulWidget {
  const AudioOutputSelectionPage({super.key});

  @override
  State<AudioOutputSelectionPage> createState() =>
      _AudioOutputSelectionPageState();
}

class _AudioOutputSelectionPageState extends State<AudioOutputSelectionPage> {
  bool _scanning = false;
  final List<BleDevice> _found = <BleDevice>[];
  StreamSubscription? _scanTimeoutSub;

  bool _isSelectableAudioOutput(BleDevice device) {
    return _isNamedDevice(device) && !_isVocalPointDevice(device);
  }

  @override
  void initState() {
    super.initState();

    UniversalBle.onScanResult = (BleDevice device) {
      if (!mounted || !_isSelectableAudioOutput(device)) return;

      final idx = _found.indexWhere((d) => d.deviceId == device.deviceId);
      if (idx == -1) {
        setState(() => _found.add(device));
      } else {
        setState(() => _found[idx] = device);
      }
    };
  }

  @override
  void dispose() {
    _scanTimeoutSub?.cancel();
    if (_scanning) {
      UniversalBle.stopScan();
    }
    UniversalBle.onScanResult = null;
    super.dispose();
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  Future<void> _startScan() async {
    setState(() {
      _found.clear();
      _scanning = true;
    });

    try {
      await UniversalBle.startScan();
      _scanTimeoutSub?.cancel();
      _scanTimeoutSub = Stream<void>.periodic(const Duration(seconds: 10))
          .take(1)
          .listen((_) => _stopScan());
    } on PlatformException catch (e) {
      _snack("Scan failed: ${e.code} — ${e.message ?? ''}");
      setState(() => _scanning = false);
    } catch (e) {
      _snack("Scan failed: $e");
      setState(() => _scanning = false);
    }
  }

  Future<void> _stopScan() async {
    try {
      await UniversalBle.stopScan();
    } catch (_) {
      // ignore
    }
    if (mounted) setState(() => _scanning = false);
  }

  void _selectOutput(BleDevice device) {
    final name = (device.name == null || device.name!.trim().isEmpty)
        ? device.deviceId
        : device.name!.trim();
    AppState.bleAddress.value = device.deviceId;
    AppState.audioOutputDeviceName.value = name;
    AppState.param1.value = name;
    _snack("Selected audio output: $name");
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Connect to Listening Device"),
        actions: const [HomeButton()],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: AppColors.charcoal,
                borderRadius: BorderRadius.circular(24),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.peach,
                        foregroundColor: AppColors.black,
                      ),
                      icon: _scanning
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: AppColors.black,
                              ),
                            )
                          : const Icon(Icons.search),
                      label: Text(_scanning ? "Scanning..." : "Scan for devices"),
                      onPressed: _scanning ? null : _startScan,
                    ),
                  ),
                  const SizedBox(width: 12),
                  OutlinedButton(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.white,
                      side: const BorderSide(color: AppColors.white),
                    ),
                    onPressed: _scanning ? _stopScan : null,
                    child: const Text("Stop"),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            ValueListenableBuilder<String>(
              valueListenable: AppState.bleAddress,
              builder: (_, address, __) {
                return ValueListenableBuilder<String?>(
                  valueListenable: AppState.audioOutputDeviceName,
                  builder: (_, name, __) {
                    final selected = address.isNotEmpty;
                    return Container(
                      decoration: BoxDecoration(
                        color: selected ? AppColors.peach : Colors.white,
                        borderRadius: BorderRadius.circular(22),
                        border: Border.all(
                          color: selected ? AppColors.peach : Colors.black12,
                        ),
                      ),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Row(
                          children: [
                            Icon(
                              selected
                                  ? Icons.speaker_group
                                  : Icons.speaker_outlined,
                              color: selected
                                  ? AppColors.charcoal
                                  : AppColors.coral,
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                selected
                                    ? "Selected output: ${name ?? address}"
                                    : "No listening device selected",
                                style: TextStyle(
                                  fontWeight: FontWeight.w700,
                                  color: selected
                                      ? AppColors.charcoal
                                      : AppColors.black,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                );
              },
            ),
            const SizedBox(height: 16),
            Align(
              alignment: Alignment.centerLeft,
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: AppColors.peach,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  "Available devices",
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w800,
                        color: AppColors.black,
                      ),
                ),
              ),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: _found.isEmpty
                  ? const _EmptyCard(
                      text: "Tap Scan to find nearby listening devices.",
                      icon: Icons.speaker,
                    )
                  : ValueListenableBuilder<String>(
                      valueListenable: AppState.bleAddress,
                      builder: (_, selectedAddress, __) {
                        return Card(
                          child: ListView.separated(
                            padding: const EdgeInsets.symmetric(vertical: 6),
                            itemCount: _found.length,
                            separatorBuilder: (_, __) =>
                                const Divider(height: 1),
                            itemBuilder: (_, i) {
                              final device = _found[i];
                              final name = device.name?.trim() ?? device.deviceId;
                              final isSelected =
                                  selectedAddress == device.deviceId;

                              return ListTile(
                                leading: CircleAvatar(
                                  backgroundColor: isSelected
                                      ? AppColors.coral
                                      : AppColors.peach,
                                  foregroundColor: isSelected
                                      ? AppColors.white
                                      : AppColors.black,
                                  child: Icon(
                                    isSelected
                                        ? Icons.check_circle
                                        : Icons.speaker,
                                  ),
                                ),
                                title: Text(
                                  name,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                                subtitle: Text(device.deviceId),
                                trailing: FilledButton(
                                  style: FilledButton.styleFrom(
                                    backgroundColor: isSelected
                                        ? AppColors.charcoalSoft
                                        : AppColors.coral,
                                  ),
                                  onPressed: isSelected
                                      ? null
                                      : () => _selectOutput(device),
                                  child: Text(
                                    isSelected ? "Selected" : "Use Output",
                                  ),
                                ),
                              );
                            },
                          ),
                        );
                      },
                    ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                OutlinedButton.icon(
                  icon: const Icon(Icons.arrow_back),
                  label: const Text("Back"),
                  onPressed: () => Navigator.pop(context),
                ),
                const SizedBox(width: 12),
                OutlinedButton.icon(
                  icon: const Icon(Icons.home),
                  label: const Text("Home"),
                  onPressed: () =>
                      Navigator.of(context).popUntil((r) => r.isFirst),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class ConnectListeningDevicePage extends StatelessWidget {
  const ConnectListeningDevicePage({super.key});

  @override
  Widget build(BuildContext context) {
    return const AudioOutputSelectionPage();
  }
}

class VolumeControlPage extends StatefulWidget {
  const VolumeControlPage({super.key});

  @override
  State<VolumeControlPage> createState() => _VolumeControlPageState();
}

class _VolumeControlPageState extends State<VolumeControlPage> {
  static const List<String> _param2Options = <String>[
    "Amber Lantern",
    "Static Bloom",
    "Copper Atlas",
  ];

  Timer? _volumeWriteDebounce;
  Timer? _batteryWriteDebounce;
  late final TextEditingController _serviceUuidController;
  late final TextEditingController _volumeCharUuidController;
  late final TextEditingController _metadataCharUuidController;

  late final VoidCallback _serviceUuidListener;
  late final VoidCallback _volumeCharUuidListener;
  late final VoidCallback _metadataCharUuidListener;

  @override
  void initState() {
    super.initState();
    _serviceUuidController = TextEditingController(
      text: AppState.volumeServiceUuid.value,
    );
    _volumeCharUuidController = TextEditingController(
      text: AppState.volumeCharUuid.value,
    );
    _metadataCharUuidController = TextEditingController(
      text: AppState.metadataCharUuid.value,
    );

    _serviceUuidListener = () {
      final value = AppState.volumeServiceUuid.value;
      if (_serviceUuidController.text != value) {
        _serviceUuidController.value = _serviceUuidController.value.copyWith(
          text: value,
          selection: TextSelection.collapsed(offset: value.length),
          composing: TextRange.empty,
        );
      }
    };
    _volumeCharUuidListener = () {
      final value = AppState.volumeCharUuid.value;
      if (_volumeCharUuidController.text != value) {
        _volumeCharUuidController.value =
            _volumeCharUuidController.value.copyWith(
          text: value,
          selection: TextSelection.collapsed(offset: value.length),
          composing: TextRange.empty,
        );
      }
    };
    _metadataCharUuidListener = () {
      final value = AppState.metadataCharUuid.value;
      if (_metadataCharUuidController.text != value) {
        _metadataCharUuidController.value =
            _metadataCharUuidController.value.copyWith(
          text: value,
          selection: TextSelection.collapsed(offset: value.length),
          composing: TextRange.empty,
        );
      }
    };

    AppState.volumeServiceUuid.addListener(_serviceUuidListener);
    AppState.volumeCharUuid.addListener(_volumeCharUuidListener);
    AppState.metadataCharUuid.addListener(_metadataCharUuidListener);
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  void _onVolumeChanged(double value) {
    AppState.volume.value = value;

    _volumeWriteDebounce?.cancel();
    _volumeWriteDebounce = Timer(const Duration(milliseconds: 120), () {
      _writeVolumeToDevice();
    });
  }

  void _onBatteryChanged(double value) {
    AppState.battery.value = value;

    _batteryWriteDebounce?.cancel();
    _batteryWriteDebounce = Timer(const Duration(milliseconds: 120), () {
      _writeBatteryToDevice();
    });
  }

  Future<void> _writeCharacteristic({
    required String charUuid,
    required Uint8List payload,
    bool showSuccess = false,
    bool showErrors = true,
    String? successMessage,
  }) async {
    final id = AppState.connectedDeviceId.value;
    if (id == null) {
      if (showErrors) {
        _snack("No device connected");
      }
      return;
    }

    final serviceUuid = AppState.volumeServiceUuid.value.trim();
    if (serviceUuid.isEmpty || charUuid.trim().isEmpty) {
      if (showErrors) {
        _snack("Service/characteristic UUID is missing");
      }
      return;
    }

    try {
      await UniversalBle.writeValue(
        id,
        serviceUuid,
        charUuid,
        payload,
        BleOutputProperty.withResponse,
      );
      if (showSuccess && successMessage != null) {
        _snack(successMessage);
      }
    } catch (e) {
      if (showErrors) {
        _snack("Write failed: $e");
      }
    }
  }

  Future<void> _writeVolumeToDevice({bool showSuccess = false}) async {
    final volume = AppState.volume.value.round().clamp(0, 100);
    await _writeCharacteristic(
      charUuid: AppState.volumeCharUuid.value.trim(),
      payload: Uint8List.fromList(<int>[volume]),
      showSuccess: showSuccess,
      showErrors: showSuccess,
      successMessage: "Sent volume=$volume",
    );
  }

  Future<void> _writeBatteryToDevice({bool showSuccess = false}) async {
    final battery = AppState.battery.value.round().clamp(0, 100);
    await _writeMetadataToken(
      "BATTERY=$battery",
      showSuccess: showSuccess,
      successMessage: "Sent BATTERY=$battery",
    );
  }

  Future<void> _writeMetadataToken(
    String token, {
    bool showSuccess = true,
    String? successMessage,
  }) async {
    await _writeCharacteristic(
      charUuid: AppState.metadataCharUuid.value.trim(),
      payload: Uint8List.fromList(utf8.encode(token)),
      showSuccess: showSuccess,
      showErrors: true,
      successMessage: successMessage ?? "Sent $token",
    );
  }

  Future<void> _sendBleAddress() async {
    final address = AppState.bleAddress.value;
    final outputName = AppState.audioOutputDeviceName.value?.trim() ?? "";
    if (address.isEmpty) {
      _snack("Select a listening device first");
      return;
    }
    if (outputName.isEmpty) {
      _snack("Selected output is missing a device name");
      return;
    }
    await _writeMetadataToken("BLE_ADDR=$address", showSuccess: false);
    await _writeMetadataToken("PARAM1=$outputName", showSuccess: false);
    _snack("Sent BLE_ADDR and PARAM1 from selected output");
  }

  Future<void> _sendParam2(String value) async {
    AppState.param2.value = value;
    await _writeMetadataToken(
      "PARAM2=$value",
      successMessage: "Sent PARAM2=$value",
    );
  }

  Widget _buildSliderPanel({
    required String title,
    required ValueNotifier<double> notifier,
    required ValueChanged<double> onChanged,
    required VoidCallback onSendPressed,
    required Color accent,
    required IconData icon,
  }) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: AppColors.charcoal,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Icon(icon, color: AppColors.white),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.w800,
                    color: AppColors.white,
                  ),
                ),
              ),
              TextButton(
                onPressed: onSendPressed,
                child: const Text("Send now"),
              ),
            ],
          ),
          const SizedBox(height: 14),
          ValueListenableBuilder<double>(
            valueListenable: notifier,
            builder: (_, value, __) {
              return Card(
                color: Colors.white,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text("0"),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 14,
                              vertical: 6,
                            ),
                            decoration: BoxDecoration(
                              color: accent,
                              borderRadius: BorderRadius.circular(999),
                            ),
                            child: Text(
                              value.round().toString(),
                              style: const TextStyle(
                                fontSize: 24,
                                fontWeight: FontWeight.w800,
                                color: AppColors.white,
                              ),
                            ),
                          ),
                          const Text("100"),
                        ],
                      ),
                      const SizedBox(height: 8),
                      SliderTheme(
                        data: SliderTheme.of(context).copyWith(
                          activeTrackColor: accent,
                          inactiveTrackColor: accent.withValues(alpha: 0.25),
                          thumbColor: accent,
                          overlayColor: accent.withValues(alpha: 0.15),
                          trackHeight: 6,
                        ),
                        child: Slider(
                          value: value,
                          min: 0,
                          max: 100,
                          divisions: 100,
                          label: value.round().toString(),
                          onChanged: onChanged,
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _buildOptionPanel({
    required String title,
    required String subtitle,
    required ValueNotifier<String> notifier,
    required Color accent,
    required List<Widget> actions,
  }) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: AppColors.charcoal,
        borderRadius: BorderRadius.circular(24),
      ),
      child: ValueListenableBuilder<String>(
        valueListenable: notifier,
        builder: (_, value, __) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: accent,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  title,
                  style: const TextStyle(
                    fontWeight: FontWeight.w800,
                    color: AppColors.black,
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Text(
                subtitle,
                style: const TextStyle(color: AppColors.textMuted),
              ),
              const SizedBox(height: 10),
              Text(
                "Current: ${value.isEmpty ? 'Not selected' : value}",
                style: const TextStyle(
                  color: AppColors.white,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 14),
              Wrap(spacing: 10, runSpacing: 10, children: actions),
            ],
          );
        },
      ),
    );
  }

  @override
  void dispose() {
    _volumeWriteDebounce?.cancel();
    _batteryWriteDebounce?.cancel();
    AppState.volumeServiceUuid.removeListener(_serviceUuidListener);
    AppState.volumeCharUuid.removeListener(_volumeCharUuidListener);
    AppState.metadataCharUuid.removeListener(_metadataCharUuidListener);
    _serviceUuidController.dispose();
    _volumeCharUuidController.dispose();
    _metadataCharUuidController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final uuidStyle = Theme.of(context).textTheme.bodySmall;

    return Scaffold(
      appBar: AppBar(
        title: const Text("Device Control"),
        actions: const [HomeButton()],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: ListView(
          children: [
            ValueListenableBuilder<String?>(
              valueListenable: AppState.connectedDeviceId,
              builder: (_, id, __) {
                return ValueListenableBuilder<String?>(
                  valueListenable: AppState.connectedDeviceName,
                  builder: (_, name, __) {
                    return Container(
                      decoration: BoxDecoration(
                        color: id != null ? AppColors.peach : Colors.white,
                        borderRadius: BorderRadius.circular(22),
                        border: Border.all(
                          color: id != null ? AppColors.peach : Colors.black12,
                        ),
                      ),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Row(
                          children: [
                            Icon(
                              id == null ? Icons.link_off : Icons.link,
                              color: id == null
                                  ? AppColors.coral
                                  : AppColors.charcoal,
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                id == null
                                    ? "Not connected — controls only change local UI"
                                    : "Connected: ${name ?? 'Unnamed'}",
                                style: const TextStyle(
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ),
                            if (id != null)
                              Wrap(
                                spacing: 8,
                                runSpacing: 8,
                                children: [
                                  TextButton(
                                    onPressed: () =>
                                        _writeVolumeToDevice(showSuccess: true),
                                    child: const Text("Send Volume"),
                                  ),
                                  TextButton(
                                    onPressed: () =>
                                        _writeBatteryToDevice(showSuccess: true),
                                    child: const Text("Send Battery"),
                                  ),
                                ],
                              ),
                          ],
                        ),
                      ),
                    );
                  },
                );
              },
            ),
            const SizedBox(height: 16),
            _buildSliderPanel(
              title: "Volume",
              notifier: AppState.volume,
              onChanged: _onVolumeChanged,
              onSendPressed: () => _writeVolumeToDevice(showSuccess: true),
              accent: AppColors.coral,
              icon: Icons.volume_up,
            ),
            const SizedBox(height: 16),
            _buildSliderPanel(
              title: "Battery",
              notifier: AppState.battery,
              onChanged: _onBatteryChanged,
              onSendPressed: () => _writeBatteryToDevice(showSuccess: true),
              accent: AppColors.peach,
              icon: Icons.battery_full,
            ),
            const SizedBox(height: 16),
            _buildOptionPanel(
              title: "BLE Address",
              subtitle:
                  "Uses the selected listening device and sends its address as BLE_ADDR plus its name as PARAM1.",
              notifier: AppState.bleAddress,
              accent: AppColors.yellow,
              actions: [
                OutlinedButton.icon(
                  icon: const Icon(Icons.hearing),
                  label: const Text("Select Listening Device"),
                  onPressed: () =>
                      Navigator.pushNamed(context, '/connect-listening-device'),
                ),
                FilledButton.icon(
                  icon: const Icon(Icons.bluetooth_audio),
                  label: const Text("Send BLE_ADDR"),
                  onPressed: _sendBleAddress,
                ),
              ],
            ),
            const SizedBox(height: 16),
            _buildOptionPanel(
              title: "Param 1",
              subtitle:
                  "Automatically mirrors the selected listening device name and is sent together with BLE_ADDR.",
              notifier: AppState.param1,
              accent: AppColors.peach,
              actions: [
                OutlinedButton.icon(
                  icon: const Icon(Icons.hearing),
                  label: const Text("Select Listening Device"),
                  onPressed: () =>
                      Navigator.pushNamed(context, '/connect-listening-device'),
                ),
              ],
            ),
            const SizedBox(height: 16),
            _buildOptionPanel(
              title: "Param 2",
              subtitle: "Select one metadata option to send as PARAM2.",
              notifier: AppState.param2,
              accent: AppColors.coral,
              actions: _param2Options
                  .map(
                    (value) => FilledButton(
                      onPressed: () => _sendParam2(value),
                      child: Text(value),
                    ),
                  )
                  .toList(),
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(
                color: AppColors.yellow,
                borderRadius: BorderRadius.circular(999),
              ),
              child: const Text(
                "ESP32 UUIDs",
                style: TextStyle(
                  fontWeight: FontWeight.w800,
                  color: AppColors.black,
                ),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              "Control service plus separate volume and metadata characteristics.",
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: AppColors.charcoalSoft,
                  ),
            ),
            const SizedBox(height: 10),
            TextField(
              decoration: const InputDecoration(
                labelText: "Service UUID",
              ),
              style: uuidStyle,
              controller: _serviceUuidController,
              onChanged: (value) => AppState.volumeServiceUuid.value = value,
            ),
            const SizedBox(height: 10),
            TextField(
              decoration: const InputDecoration(
                labelText: "Volume Characteristic UUID (FF01)",
              ),
              style: uuidStyle,
              controller: _volumeCharUuidController,
              onChanged: (value) => AppState.volumeCharUuid.value = value,
            ),
            const SizedBox(height: 10),
            TextField(
              decoration: const InputDecoration(
                labelText: "Metadata Characteristic UUID (FF02)",
              ),
              style: uuidStyle,
              controller: _metadataCharUuidController,
              onChanged: (value) => AppState.metadataCharUuid.value = value,
            ),
            const SizedBox(height: 24),
            Row(
              children: [
                OutlinedButton.icon(
                  icon: const Icon(Icons.arrow_back),
                  label: const Text("Back"),
                  onPressed: () => Navigator.pop(context),
                ),
                const SizedBox(width: 12),
                OutlinedButton.icon(
                  icon: const Icon(Icons.home),
                  label: const Text("Home"),
                  onPressed: () =>
                      Navigator.of(context).popUntil((r) => r.isFirst),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _RememberedListCard extends StatelessWidget {
  final List<RememberedDevice> items;
  final String? connectedDeviceId;
  final void Function(String deviceId) onForget;

  const _RememberedListCard({
    required this.items,
    required this.connectedDeviceId,
    required this.onForget,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListView.separated(
        shrinkWrap: true,
        itemCount: items.length,
        separatorBuilder: (_, __) => const Divider(height: 1),
        itemBuilder: (_, i) {
          final d = items[i];
          final connected = connectedDeviceId == d.deviceId;
          final last = "${d.lastSeen.hour.toString().padLeft(2, '0')}:"
              "${d.lastSeen.minute.toString().padLeft(2, '0')}";
          return ListTile(
            leading: CircleAvatar(
              backgroundColor:
                  connected ? AppColors.coral : AppColors.yellow,
              foregroundColor:
                  connected ? AppColors.white : AppColors.black,
              child: Icon(connected ? Icons.check_circle : Icons.history),
            ),
            title: Text(
              d.name,
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
            subtitle: Text("${d.deviceId}\nLast seen: $last"),
            isThreeLine: true,
            trailing: TextButton.icon(
              icon: const Icon(Icons.delete_outline),
              label: const Text("Forget"),
              onPressed: () => onForget(d.deviceId),
            ),
          );
        },
      ),
    );
  }
}

class _EmptyCard extends StatelessWidget {
  final String text;
  final IconData icon;

  const _EmptyCard({required this.text, required this.icon});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.white,
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          children: [
            CircleAvatar(
              backgroundColor: AppColors.peach,
              foregroundColor: AppColors.black,
              child: Icon(icon),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                text,
                style: const TextStyle(fontWeight: FontWeight.w500),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

bool _isVocalPointDevice(BleDevice device) {
  final name = device.name?.trim().toLowerCase() ?? "";
  return name.contains("vocalpoint");
}

bool _isNamedDevice(BleDevice device) {
  final name = device.name?.trim() ?? "";
  return name.isNotEmpty && name != "Unnamed";
}

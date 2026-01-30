import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:universal_ble/universal_ble.dart';

void main() => runApp(const MyApp());

/// Simple app-wide state (no extra packages).
class AppState {
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

  /// UUIDs for ESP32 control (default matches 0xFFFF service / 0xFF01 char).
  static final ValueNotifier<String> volumeServiceUuid =
      ValueNotifier<String>("0000FFFF-0000-1000-8000-00805F9B34FB");
  static final ValueNotifier<String> volumeCharUuid =
      ValueNotifier<String>("0000FF01-0000-1000-8000-00805F9B34FB");
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
    return MaterialApp(
      title: "VocalPoint Demo",
      theme: ThemeData(useMaterial3: true),
      initialRoute: '/',
      routes: {
        '/': (_) => const HomePage(),
        '/bluetooth': (_) => const BluetoothSetupPage(),
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
      icon: const Icon(Icons.home),
      onPressed: () => Navigator.of(context).popUntil((r) => r.isFirst),
    );
  }
}

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  Widget _statusLine(String label, Widget value) {
    return Row(
      children: [
        SizedBox(width: 130, child: Text(label)),
        Expanded(child: value),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Home"),
        actions: const [HomeButton()],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              "Navigate",
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 12),
            ElevatedButton.icon(
              icon: const Icon(Icons.bluetooth),
              label: const Text("Bluetooth Setup"),
              onPressed: () => Navigator.pushNamed(context, '/bluetooth'),
            ),
            const SizedBox(height: 12),
            ElevatedButton.icon(
              icon: const Icon(Icons.volume_up),
              label: const Text("Volume Control"),
              onPressed: () => Navigator.pushNamed(context, '/volume'),
            ),
            const SizedBox(height: 24),
            const Divider(),
            const SizedBox(height: 12),
            const Text(
              "Quick status",
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),
            _statusLine(
              "Connected:",
              ValueListenableBuilder<String?>(
                valueListenable: AppState.connectedDeviceId,
                builder: (_, id, __) {
                  return ValueListenableBuilder<String?>(
                    valueListenable: AppState.connectedDeviceName,
                    builder: (_, name, __) {
                      if (id == null) return const Text("No");
                      return Text("Yes — ${name ?? 'Unnamed'}");
                    },
                  );
                },
              ),
            ),
            const SizedBox(height: 8),
            _statusLine(
              "Volume:",
              ValueListenableBuilder<double>(
                valueListenable: AppState.volume,
                builder: (_, v, __) => Text(v.round().toString()),
              ),
            ),
            const SizedBox(height: 8),
            _statusLine(
              "Remembered:",
              ValueListenableBuilder<List<RememberedDevice>>(
                valueListenable: AppState.rememberedDevices,
                builder: (_, devices, __) => Text("${devices.length} device(s)"),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class BluetoothSetupPage extends StatefulWidget {
  const BluetoothSetupPage({super.key});

  @override
  State<BluetoothSetupPage> createState() => _BluetoothSetupPageState();
}

class _BluetoothSetupPageState extends State<BluetoothSetupPage> {
  bool _scanning = false;
  final List<BleDevice> _found = <BleDevice>[];
  StreamSubscription? _scanTimeoutSub;

  @override
  void initState() {
    super.initState();

    // Scan callback.
    UniversalBle.onScanResult = (BleDevice device) {
      final idx = _found.indexWhere((d) => d.deviceId == device.deviceId);
      if (idx == -1) {
        setState(() => _found.add(device));
      } else {
        // Update name if it was null before.
        final existing = _found[idx];
        final existingName = existing.name;
        final newName = device.name;
        if ((existingName == null || existingName!.isEmpty) &&
            (newName != null && newName.isNotEmpty)) {
          setState(() => _found[idx] = device);
        }
      }

      // Update remembered "last seen" if this device is already remembered.
      _touchRemembered(device.deviceId, device.name ?? "Unnamed");
    };
  }

  @override
  void dispose() {
    _scanTimeoutSub?.cancel();
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
      // Auto-stop after 10 seconds so it doesn't run forever.
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
      // Many BLE stacks don’t like scanning while connecting.
      if (_scanning) await _stopScan();

      await UniversalBle.connect(
        d.deviceId,
        connectionTimeout: const Duration(seconds: 10),
      );

      await UniversalBle.discoverServices(d.deviceId);

      AppState.connectedDeviceId.value = d.deviceId;
      AppState.connectedDeviceName.value = name;

      // Auto-remember on successful connect.
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
    } catch (_) {
      // ignore
    }

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
        title: const Text("Bluetooth Setup"),
        actions: const [HomeButton()],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Row(
              children: [
                Expanded(
                  child: ElevatedButton.icon(
                    icon: _scanning
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.search),
                    label: Text(_scanning ? "Scanning..." : "Scan for devices"),
                    onPressed: _scanning ? null : _startScan,
                  ),
                ),
                const SizedBox(width: 12),
                OutlinedButton(
                  onPressed: _scanning ? _stopScan : null,
                  child: const Text("Stop"),
                ),
              ],
            ),
            const SizedBox(height: 12),

            // Connected status + actions
            ValueListenableBuilder<String?>(
              valueListenable: AppState.connectedDeviceId,
              builder: (_, id, __) {
                return ValueListenableBuilder<String?>(
                  valueListenable: AppState.connectedDeviceName,
                  builder: (_, name, __) {
                    final connected = id != null;
                    return Card(
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Row(
                          children: [
                            Icon(connected ? Icons.link : Icons.link_off),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                connected
                                    ? "Connected: ${name ?? 'Unnamed'}"
                                    : "Not connected",
                                style: const TextStyle(
                                  fontWeight: FontWeight.w600,
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
              child: Text(
                "Remembered devices",
                style: Theme.of(context).textTheme.titleMedium,
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
              child: Text(
                "Found devices",
                style: Theme.of(context).textTheme.titleMedium,
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
                            leading: const Icon(Icons.bluetooth),
                            title: Text(name),
                            subtitle: Text(d.deviceId),
                            trailing: Wrap(
                              spacing: 8,
                              children: [
                                TextButton(
                                  onPressed: () => _rememberDevice(d),
                                  child: const Text("Remember"),
                                ),
                                FilledButton(
                                  onPressed:
                                      isConnected ? null : () => _connect(d),
                                  child: Text(
                                      isConnected ? "Connected" : "Connect"),
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

class VolumeControlPage extends StatefulWidget {
  const VolumeControlPage({super.key});

  @override
  State<VolumeControlPage> createState() => _VolumeControlPageState();
}

class _VolumeControlPageState extends State<VolumeControlPage> {
  Timer? _writeDebounce;

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  void _onVolumeChanged(double v) {
    AppState.volume.value = v;

    _writeDebounce?.cancel();
    _writeDebounce = Timer(const Duration(milliseconds: 120), () {
      _writeVolumeToDevice();
    });
  }

  Future<void> _writeVolumeToDevice() async {
    final id = AppState.connectedDeviceId.value;
    if (id == null) return;

    final serviceUuid = AppState.volumeServiceUuid.value.trim();
    final charUuid = AppState.volumeCharUuid.value.trim();
    if (serviceUuid.isEmpty || charUuid.isEmpty) return;

    final vol = AppState.volume.value.round().clamp(0, 100);
    final payload = Uint8List.fromList([vol]);

    try {
      await UniversalBle.writeValue(
        id,
        serviceUuid,
        charUuid,
        payload,
        BleOutputProperty.withResponse,
      );
      // Uncomment if you want confirmations:
      // _snack("Sent volume $vol");
    } catch (e) {
      _snack("Write failed: $e");
    }
  }

  @override
  void dispose() {
    _writeDebounce?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final uuidStyle = Theme.of(context).textTheme.bodySmall;

    return Scaffold(
      appBar: AppBar(
        title: const Text("Volume Control"),
        actions: const [HomeButton()],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ValueListenableBuilder<String?>(
              valueListenable: AppState.connectedDeviceId,
              builder: (_, id, __) {
                return ValueListenableBuilder<String?>(
                  valueListenable: AppState.connectedDeviceName,
                  builder: (_, name, __) {
                    return Card(
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Row(
                          children: [
                            Icon(id == null ? Icons.link_off : Icons.link),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                id == null
                                    ? "Not connected — slider only changes local UI"
                                    : "Connected: ${name ?? 'Unnamed'}",
                                style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                            if (id != null)
                              TextButton(
                                onPressed: _writeVolumeToDevice,
                                child: const Text("Send now"),
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

            const Text(
              "Adjust volume",
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 12),

            ValueListenableBuilder<double>(
              valueListenable: AppState.volume,
              builder: (_, v, __) {
                return Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            const Text("0"),
                            Text(
                              v.round().toString(),
                              style: const TextStyle(
                                fontSize: 28,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            const Text("100"),
                          ],
                        ),
                        Slider(
                          value: v,
                          min: 0,
                          max: 100,
                          divisions: 100,
                          label: v.round().toString(),
                          onChanged: _onVolumeChanged,
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),

            const SizedBox(height: 16),
            const Text(
              "ESP32 UUIDs (paste your custom service/characteristic later)",
              style: TextStyle(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),

            ValueListenableBuilder<String>(
              valueListenable: AppState.volumeServiceUuid,
              builder: (_, s, __) {
                final controller = TextEditingController(text: s)
                  ..selection = TextSelection.fromPosition(
                    TextPosition(offset: s.length),
                  );
                return TextField(
                  decoration: const InputDecoration(
                    labelText: "Service UUID",
                    border: OutlineInputBorder(),
                  ),
                  style: uuidStyle,
                  controller: controller,
                  onChanged: (v) => AppState.volumeServiceUuid.value = v,
                );
              },
            ),
            const SizedBox(height: 10),
            ValueListenableBuilder<String>(
              valueListenable: AppState.volumeCharUuid,
              builder: (_, s, __) {
                final controller = TextEditingController(text: s)
                  ..selection = TextSelection.fromPosition(
                    TextPosition(offset: s.length),
                  );
                return TextField(
                  decoration: const InputDecoration(
                    labelText: "Characteristic UUID",
                    border: OutlineInputBorder(),
                  ),
                  style: uuidStyle,
                  controller: controller,
                  onChanged: (v) => AppState.volumeCharUuid.value = v,
                );
              },
            ),

            const Spacer(),

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
            leading: Icon(connected ? Icons.check_circle : Icons.history),
            title: Text(d.name),
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

/// A small “empty state” card.
class _EmptyCard extends StatelessWidget {
  final String text;
  final IconData icon;

  const _EmptyCard({required this.text, required this.icon});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(icon),
            const SizedBox(width: 12),
            Expanded(child: Text(text)),
          ],
        ),
      ),
    );
  }
}